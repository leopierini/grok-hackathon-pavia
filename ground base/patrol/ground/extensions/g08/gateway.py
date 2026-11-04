"""One owner per adapter, fenced calls, and truthful availability."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from datetime import UTC
from pathlib import Path

from patrol.contract import (
    AdapterError,
    DispatchDecision,
    DogStatus,
    DroneStatus,
    Frame,
    GroundDecision,
    Incident,
    InspectionRequest,
    InspectionResult,
    Resolution,
    RouteResult,
    RunContext,
)
from patrol.ground.extensions.g08.resolve import COMPONENTS, MODE_KEYS, resolve_factories
from patrol.ground.extensions.g08.snapshots import EVIDENCE_GAPS, ComponentSnapshot
from patrol.ground.kernel.catalog import LAUNCH_ORIGINS, ZONES
from patrol.ground.kernel.contracts import GroundSettings, KernelContext, ServicePorts, Ticket
from patrol.ground.kernel.faults import GroundFault, fault

_ASYNC_METHODS: dict[str, tuple[str, ...]] = {
    "dog": ("connect", "prepare", "get_status", "run_route", "capture_frame", "halt", "close"),
    "drone": ("connect", "get_status", "inspect", "land", "close"),
    "reasoner": (
        "assess_incident",
        "assess_ground_view",
        "resolve_incident",
        "compose_alert",
        "close",
    ),
}
_INVOKE: dict[str, frozenset[str]] = {
    "dog": frozenset({"prepare", "run_route", "capture_frame", "halt"}),
    "drone": frozenset({"inspect", "land"}),
    "reasoner": frozenset(
        {
            "metadata",
            "assess_incident",
            "assess_ground_view",
            "resolve_incident",
            "compose_alert",
        }
    ),
}
_STOP = frozenset({"halt", "land"})
_OUTPUT = {"dog": "dog", "drone": "drone", "reasoner": "grok"}


class _Claim:
    def __init__(self, gateway: AdapterGateway, mode: str) -> None:
        self.gateway = gateway
        self.mode = mode


_CLAIMS: dict[str, _Claim] = {}


def clear_claims_for_tests() -> None:
    """Drop process owner records between isolated tests. Does not close devices."""
    _CLAIMS.clear()


class AdapterGateway:
    def __init__(self, kernel: KernelContext, peers: ServicePorts) -> None:
        self.kernel = kernel
        self._peers = peers
        self.events: list[str] = []
        self._settings: GroundSettings | None = None
        self._adapters: dict[str, object] = {}
        self._modes: dict[str, str] = {}
        self._workers: list[asyncio.Task[object]] = []
        self._generation = 1
        self._open_generation = 1
        self._built_epoch = kernel.authority.epoch
        self._accepting = False
        self._closed = False
        self._close_requested = False
        self._primary = ""
        self._published: dict[str, ComponentSnapshot] = {}
        self._seen_connected: set[str] = set()
        self._closed_components: set[str] = set()
        self._close_error_notes: list[str] = []
        self._close_failed = False
        self._saved_close: str | None = None
        self._bumped = False
        self._last_invoke: object = None
        self._seq = 0

    @property
    def peers(self) -> ServicePorts:
        return self._peers

    @property
    def evidence_gaps(self) -> tuple[str, ...]:
        return EVIDENCE_GAPS

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def last_invoke(self) -> object:
        return self._last_invoke

    @property
    def published(self) -> Mapping[str, ComponentSnapshot]:
        return dict(self._published)

    def live_components(self) -> tuple[str, ...]:
        return tuple(name for name, claim in _CLAIMS.items() if claim.gateway is self)

    async def build(
        self,
        settings: GroundSettings,
        output_root: str | Path,
        *,
        resolver: Mapping[str, object],
    ) -> None:
        if not isinstance(settings, GroundSettings):
            raise fault("invalid_input", "settings must be GroundSettings")
        if self._workers_block():
            raise fault(
                "recovery_required",
                "pending worker blocks recreation",
                recovery_required=True,
            )
        if self._close_failed:
            raise fault(
                "recovery_required",
                "failed close blocks recreation",
                recovery_required=True,
            )
        if self._close_requested:
            self._release_own_claims()
            self._closed = True
        source = _source(resolver)
        real_modes = [_mode_of(settings, name) == "real" for name in COMPONENTS]
        if source == "private-stub" and any(real_modes):
            raise fault("rejected", "real-to-fake substitution", recovery_required=True)
        self._reject_live_conflict(settings)
        _check_dog_profile(settings)
        factories = resolve_factories(resolver)
        self._reset_for_build(settings)
        claimed: list[str] = []
        try:
            for name in COMPONENTS:
                mode = _mode_of(settings, name)
                self._claim(name, mode)
                claimed.append(name)
                config = _component_config(settings, name)
                output = _output_dir(output_root, name)
                self._adapters[name] = _construct(
                    factories[name],
                    name,
                    mode=mode,
                    config=config,
                    output_dir=str(output),
                )
                self._modes[name] = mode
        except Exception:
            await self._rollback(claimed)
            raise
        self._accepting = True

    async def connect(self, component: str) -> ComponentSnapshot:
        self._require_open(component)
        try:
            raw = await self._bounded(component, self._connection_call(component))
        except GroundFault as exc:
            if exc.error.code in {"contract_mismatch", "timeout"}:
                raise
            return self._failure_snapshot(component, exc)
        except Exception as exc:
            return self._failure_snapshot(component, exc)
        return self._accept_status(component, raw)

    async def status(self, component: str) -> ComponentSnapshot:
        self._require_open(component)
        try:
            raw = await self._bounded(component, self._status_call(component))
        except GroundFault as exc:
            if exc.error.code in {"contract_mismatch", "timeout"}:
                raise
            return self._failure_snapshot(component, exc)
        except Exception as exc:
            return self._failure_snapshot(component, exc)
        return self._accept_status(component, raw)

    async def invoke(
        self,
        component: str,
        method: str,
        args: tuple[object, ...],
        *,
        ticket: Ticket,
        context: RunContext,
    ) -> object:
        self._require_open(component)
        if method not in _INVOKE[component]:
            raise fault("forbidden_command", f"{component}.{method} is not a contract call")
        _check_args(component, method, args, context)
        generation = self._generation
        task = asyncio.create_task(
            self._invoke_inner(component, method, args, ticket, context),
            name=f"g08-{component}-{method}",
        )
        self._workers.append(task)
        self._seq += 1
        self.kernel.tasks.retain(f"g08:{generation}:{component}.{method}:{self._seq}", task)
        try:
            value = await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        if generation != self._generation or not self._accepting:
            self.events.append(f"discarded:{component}.{method}")
            raise fault(
                "epoch_mismatch",
                "stale generation result discarded",
                recovery_required=True,
            )
        self._last_invoke = value
        return value

    async def close(self) -> None:
        if self._saved_close is not None and not self._pending_workers():
            if self._saved_close:
                raise fault("recovery_required", self._saved_close, recovery_required=True)
            return
        self._close_requested = True
        self._accepting = False
        if not self._bumped:
            self._generation += 1
            self._bumped = True
        close_errors: list[str] = []
        for name in COMPONENTS:
            adapter = self._adapters.get(name)
            if adapter is None or name in self._closed_components:
                continue
            self._closed_components.add(name)
            try:
                result = await _maybe_await(_invoke_named(adapter, "close"))
            except Exception as exc:
                close_errors.append(f"{name}: {type(exc).__name__}: {exc}")
                continue
            if result is not None:
                close_errors.append(f"{name}: close returned {type(result).__name__}")
        self._close_error_notes.extend(close_errors)
        if self._close_error_notes:
            self._close_failed = True
        notes: list[str] = []
        if self._primary:
            notes.append(f"primary: {self._primary}")
        notes.extend(self._close_error_notes)
        if self._pending_workers():
            notes.append("pending worker blocks recreation")
            raise fault("recovery_required", "; ".join(notes), recovery_required=True)
        if not self._close_failed:
            self._release_own_claims()
            self._closed = True
        detail = "; ".join(notes)
        self._saved_close = detail
        if detail:
            raise fault("recovery_required", detail, recovery_required=True)

    async def _invoke_inner(
        self,
        component: str,
        method: str,
        args: tuple[object, ...],
        ticket: Ticket,
        context: RunContext,
    ) -> object:
        try:
            self._fence(component, method, ticket, context)
        except GroundFault:
            self.events.append(f"refused:{component}.{method}")
            raise
        adapter = self._adapters[component]
        action = getattr(adapter, method)
        try:
            if method == "metadata":
                value: object = action(*args)
            else:
                value = await action(*args)
        except Exception as exc:
            self._primary = f"{component}.{method}: {type(exc).__name__}: {exc}"
            raise _translate(exc) from exc
        return _check_return(component, method, value)

    def _fence(
        self,
        component: str,
        method: str,
        ticket: Ticket,
        context: RunContext,
    ) -> None:
        if not isinstance(ticket, Ticket):
            raise fault("invalid_input", "expected a Ticket")
        if not isinstance(context, RunContext):
            raise fault("invalid_input", "expected a RunContext")
        if ticket.epoch != self._built_epoch or self._generation != self._open_generation:
            raise fault(
                "stale_ticket",
                "ticket is not the current adapter generation",
                recovery_required=True,
            )
        if method in _STOP:
            return
        self.kernel.authority.require_current(ticket)
        if context.cancel.is_set():
            raise fault("cancelled", "operation context is cancelled", recovery_required=True)
        if self._modes.get(component) == "real":
            now = time.monotonic()
        else:
            now = self.kernel.clock.monotonic()
        if now >= context.deadline_monotonic:
            raise fault("expired_deadline", "stage deadline has passed", recovery_required=True)

    def _connection_call(self, component: str) -> Awaitable[object]:
        adapter = self._adapters[component]
        if component == "reasoner":
            return _ready(_invoke_named(adapter, "metadata"))
        return _ensure_awaitable(_invoke_named(adapter, "connect"))

    def _status_call(self, component: str) -> Awaitable[object]:
        adapter = self._adapters[component]
        if component == "reasoner":
            return _ready(_invoke_named(adapter, "metadata"))
        return _ensure_awaitable(_invoke_named(adapter, "get_status"))

    async def _bounded(self, component: str, call: Awaitable[object]) -> object:
        async def runner() -> object:
            return await call

        task: asyncio.Task[object] = asyncio.create_task(runner())
        self._workers.append(task)
        self._seq += 1
        self.kernel.tasks.retain(f"g08:{self._generation}:{component}:status:{self._seq}", task)
        return await self._wait_task(task, self._settings_limit(), component)

    async def _wait_task(
        self,
        task: asyncio.Task[object],
        limit_s: float,
        component: str,
    ) -> object:
        real = self._modes.get(component) == "real"
        start = time.monotonic() if real else self.kernel.clock.monotonic()
        deadline = start + limit_s
        await asyncio.sleep(0)
        if task.done():
            return _unwrap(task)
        while not task.done():
            now = time.monotonic() if real else self.kernel.clock.monotonic()
            if now >= deadline:
                self._primary = f"{component}: timeout"
                raise fault("timeout", f"{component} exceeded its limit", recovery_required=True)
            if not real and self.kernel.clock.is_manual():
                ticker = asyncio.create_task(self.kernel.clock.sleep(deadline - now))
                await asyncio.wait({task, ticker}, return_when=asyncio.FIRST_COMPLETED)
                if not ticker.done():
                    ticker.cancel()
                    with suppress(asyncio.CancelledError):
                        await ticker
            else:
                remaining = max(0.0, deadline - now)
                await asyncio.wait({task}, timeout=remaining)
                if not task.done():
                    self._primary = f"{component}: timeout"
                    raise fault(
                        "timeout",
                        f"{component} exceeded its limit",
                        recovery_required=True,
                    )
        return _unwrap(task)

    def _accept_status(self, component: str, raw: object) -> ComponentSnapshot:
        if component == "reasoner":
            if isinstance(raw, (str, bytes)) or not isinstance(raw, Mapping):
                raise fault("contract_mismatch", "reasoner metadata must be a mapping")
            pairs = ((key, value) for key, value in raw.items())
            if any(not isinstance(key, str) or not isinstance(value, str) for key, value in pairs):
                raise fault("contract_mismatch", "reasoner metadata must be strings")
            self._seen_connected.add(component)
            return self._publish(component, "available", raw, False, "available")
        if component == "dog":
            status = _copy_dog(raw)
            availability, recovery = _classify_dog(
                status,
                previously=component in self._seen_connected,
            )
            if status.connected is True:
                self._seen_connected.add(component)
            return self._publish(component, availability, status, recovery, availability)
        status_drone = _copy_drone(raw)
        availability, recovery = _classify_drone(
            status_drone,
            previously=component in self._seen_connected,
        )
        if status_drone.connected is True:
            self._seen_connected.add(component)
        return self._publish(component, availability, status_drone, recovery, availability)

    def _failure_snapshot(self, component: str, exc: Exception) -> ComponentSnapshot:
        previously = component in self._seen_connected
        if component == "drone" and not previously:
            availability = "optional_unavailable"
            recovery = False
        elif previously:
            availability = "active_link_loss"
            recovery = True
        else:
            availability = "unavailable"
            recovery = component == "dog"
        detail = f"{availability}: {type(exc).__name__}: {exc}"
        self._primary = f"{component}: {type(exc).__name__}: {exc}"
        return self._publish(component, availability, None, recovery, detail)

    def _publish(
        self,
        component: str,
        availability: str,
        status: object,
        recovery: bool,
        detail: str,
    ) -> ComponentSnapshot:
        if not self._accepting or self._generation != self._open_generation:
            raise fault(
                "epoch_mismatch",
                "stale generation result discarded",
                recovery_required=True,
            )
        settings = self._settings
        snapshot = ComponentSnapshot(
            component=component,
            availability=availability,
            status=status,
            observed_at=_observed(self),
            device_sample_time=None,
            recovery_required=recovery,
            detail=detail,
            generation=self._generation,
            dog_transport=None if settings is None else settings.dog_transport,
            profile_identity=None if settings is None else settings.profile_identity,
            evidence_gaps=EVIDENCE_GAPS,
        )
        self._published[component] = snapshot
        return snapshot

    def _settings_limit(self) -> float:
        if self._settings is None:
            raise fault("invalid_input", "adapter lifecycle is not built")
        return self._settings.connect_limit_s

    def _require_open(self, component: str) -> None:
        if component not in COMPONENTS:
            raise fault("invalid_input", "unknown adapter component")
        if not self._accepting or component not in self._adapters:
            raise fault("invalid_input", "adapter lifecycle is not built")

    def _pending_workers(self) -> bool:
        return any(not task.done() for task in self._workers)

    def _workers_block(self) -> bool:
        if self._pending_workers():
            return True
        return any(
            claim.gateway is not self and claim.gateway._pending_workers()
            for claim in _CLAIMS.values()
        )

    def _claim(self, component: str, mode: str) -> None:
        current = _CLAIMS.get(component)
        if current is not None and current.gateway is not self:
            _raise_conflict(component, current.mode, mode)
        _CLAIMS[component] = _Claim(self, mode)

    def _release_own_claims(self) -> None:
        for name in list(_CLAIMS):
            if _CLAIMS[name].gateway is self:
                del _CLAIMS[name]

    def _reject_live_conflict(self, settings: GroundSettings) -> None:
        for name in COMPONENTS:
            mode = _mode_of(settings, name)
            claim = _CLAIMS.get(name)
            if claim is not None and (claim.gateway is not self or not self._closed):
                _raise_conflict(name, claim.mode, mode)

    def _reset_for_build(self, settings: GroundSettings) -> None:
        self._settings = settings
        self._adapters = {}
        self._modes = {}
        self._accepting = False
        self._closed = False
        self._close_requested = False
        self._primary = ""
        self._published = {}
        self._seen_connected = set()
        self._closed_components = set()
        self._close_error_notes = []
        self._close_failed = False
        self._saved_close = None
        self._bumped = False
        self._last_invoke = None
        self._open_generation = self._generation
        self._built_epoch = self.kernel.authority.epoch

    async def _rollback(self, claimed: list[str]) -> None:
        for name in claimed:
            adapter = self._adapters.get(name)
            if adapter is not None:
                with suppress(Exception):
                    await _maybe_await(_invoke_named(adapter, "close"))
            current = _CLAIMS.get(name)
            if current is not None and current.gateway is self:
                del _CLAIMS[name]
        self._adapters = {}
        self._accepting = False


def _source(resolver: Mapping[str, object]) -> str:
    if isinstance(resolver, (str, bytes)) or not isinstance(resolver, Mapping):
        raise fault("invalid_input", "resolver must be a mapping")
    source = resolver.get("source", "public")
    if not isinstance(source, str):
        raise fault("invalid_input", "resolver source must be a string")
    return source


def _mode_of(settings: GroundSettings, component: str) -> str:
    mode = settings.modes[MODE_KEYS[component]]
    if mode not in {"fake", "real"}:
        raise fault("invalid_input", f"{component} mode must be fake or real")
    return mode


def _component_config(settings: GroundSettings, component: str) -> Mapping[str, object]:
    key = MODE_KEYS[component]
    raw = settings.adapter_configs.get(key, {})
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Mapping):
        raise fault("invalid_input", f"{component} config must be a mapping")
    return raw


def _check_dog_profile(settings: GroundSettings) -> None:
    config = _component_config(settings, "dog")
    transport = config.get("transport")
    if transport is not None and transport != settings.dog_transport:
        raise fault("invalid_input", "dog config transport does not match the selected profile")


def _output_dir(output_root: str | Path, component: str) -> Path:
    path = Path(output_root).expanduser().resolve() / _OUTPUT[component]
    path.mkdir(parents=True, exist_ok=True)
    return path


def _construct(
    factory: Callable[..., object],
    component: str,
    *,
    mode: str,
    config: Mapping[str, object],
    output_dir: str,
) -> object:
    try:
        value = factory(mode=mode, config=config, output_dir=output_dir)
    except TypeError as exc:
        raise fault(
            "contract_mismatch",
            f"{component} factory rejected the frozen keywords",
        ) from exc
    _require_shape(component, value)
    return value


def _require_shape(component: str, value: object) -> None:
    if value is None or isinstance(value, (str, bytes, int, float, Mapping)):
        raise fault("contract_mismatch", f"{component} factory returned {type(value).__name__}")
    for name in _ASYNC_METHODS[component]:
        action = getattr(value, name, None)
        if not callable(action) or not inspect.iscoroutinefunction(action):
            raise fault("contract_mismatch", f"{component}.{name} must be an async method")
    if component == "reasoner":
        metadata = getattr(value, "metadata", None)
        if not callable(metadata) or inspect.iscoroutinefunction(metadata):
            raise fault("contract_mismatch", "reasoner.metadata must be a synchronous method")


def _check_args(
    component: str,
    method: str,
    args: tuple[object, ...],
    context: RunContext,
) -> None:
    if not isinstance(args, tuple):
        raise fault("invalid_input", "invoke args must be a tuple")
    if method in _STOP or method == "metadata":
        if args:
            raise fault("invalid_input", f"{component}.{method} takes no arguments")
        return
    contexts = [arg for arg in args if isinstance(arg, RunContext)]
    if len(contexts) != 1 or contexts[0] is not context:
        raise fault("invalid_input", "device call context must be the fenced RunContext")
    if method in {"run_route", "capture_frame"}:
        if len(args) != 2 or not isinstance(args[0], str) or args[0] not in ZONES:
            raise fault("invalid_input", f"{component}.{method} needs a frozen zone")
    elif method == "prepare":
        if len(args) != 1:
            raise fault("invalid_input", "dog.prepare takes a RunContext")
    elif method == "inspect":
        if len(args) != 2 or not isinstance(args[0], InspectionRequest):
            raise fault("invalid_input", "drone.inspect takes an InspectionRequest")
        request = args[0]
        if request.zone not in ZONES or request.launch_origin not in LAUNCH_ORIGINS:
            raise fault("invalid_input", "inspection request is not allowlisted")
        if not isinstance(request.profile_id, str) or not request.profile_id:
            raise fault("invalid_input", "inspection profile is required")
    elif method == "assess_incident":
        if len(args) != 2 or not isinstance(args[0], Incident):
            raise fault("invalid_input", "assess_incident takes an Incident")
    elif method == "assess_ground_view":
        if len(args) != 3 or not isinstance(args[0], Incident) or not isinstance(args[1], Frame):
            raise fault("invalid_input", "assess_ground_view takes an incident and a frame")
    elif method == "resolve_incident":
        if len(args) != 4 or not isinstance(args[0], Incident) or not isinstance(args[1], Frame):
            raise fault("invalid_input", "resolve_incident takes incident, ground, and aerial")
        if args[2] is not None and not isinstance(args[2], Frame):
            raise fault("invalid_input", "aerial frame must be a Frame or None")
    elif method == "compose_alert":
        incident_ok = isinstance(args[0], Incident)
        resolution_ok = isinstance(args[1], Resolution)
        if len(args) != 3 or not incident_ok or not resolution_ok:
            raise fault("invalid_input", "compose_alert takes an incident and a resolution")


def _check_return(component: str, method: str, value: object) -> object:
    if method in _STOP:
        if value is not None:
            raise fault("contract_mismatch", f"{component}.{method} must return None")
        return None
    if method in {"prepare"}:
        return _copy_dog(value)
    if method == "run_route":
        if not isinstance(value, RouteResult):
            raise fault("contract_mismatch", "run_route must return RouteResult")
        return value
    if method == "capture_frame":
        if not isinstance(value, Frame) or value.source != "dog":
            raise fault("contract_mismatch", "capture_frame must return a dog Frame")
        return value
    if method == "inspect":
        if not isinstance(value, InspectionResult):
            raise fault("contract_mismatch", "inspect must return InspectionResult")
        return value
    if method == "assess_incident":
        if not isinstance(value, DispatchDecision):
            raise fault("contract_mismatch", "assess_incident must return DispatchDecision")
        return value
    if method == "assess_ground_view":
        if not isinstance(value, GroundDecision):
            raise fault("contract_mismatch", "assess_ground_view must return GroundDecision")
        return value
    if method == "resolve_incident":
        if not isinstance(value, Resolution):
            raise fault("contract_mismatch", "resolve_incident must return Resolution")
        return value
    if method == "compose_alert":
        if not isinstance(value, str) or not value.strip():
            raise fault("contract_mismatch", "alert text must be a nonempty string")
        return value
    if method == "metadata":
        if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
            raise fault("contract_mismatch", "reasoner metadata must be a mapping")
        return value
    raise fault("forbidden_command", f"{component}.{method} is not a contract call")


def _copy_dog(value: object) -> DogStatus:
    if not isinstance(value, DogStatus):
        raise fault("contract_mismatch", "dog status must be DogStatus")
    if not isinstance(value.connected, bool):
        raise fault("contract_mismatch", "dog connected must be a boolean")
    for label, item in (
        ("standing", value.standing),
        ("stationary", value.stationary),
        ("avoidance_enabled", value.avoidance_enabled),
    ):
        if item is not None and not isinstance(item, bool):
            raise fault("contract_mismatch", f"dog {label} must be boolean or unknown")
    return DogStatus(value.connected, value.standing, value.stationary, value.avoidance_enabled)


def _copy_drone(value: object) -> DroneStatus:
    if not isinstance(value, DroneStatus):
        raise fault("contract_mismatch", "drone status must be DroneStatus")
    if not isinstance(value.connected, bool):
        raise fault("contract_mismatch", "drone connected must be a boolean")
    if value.flight_state not in {"grounded", "airborne", "unknown"}:
        raise fault("contract_mismatch", "drone flight state is not in the contract")
    battery = value.battery_percent
    if battery is not None and (isinstance(battery, bool) or not isinstance(battery, int)):
        raise fault("contract_mismatch", "drone battery must be an integer or unknown")
    return DroneStatus(value.connected, value.flight_state, battery)


def _classify_dog(status: DogStatus, *, previously: bool) -> tuple[str, bool]:
    if status.connected is not True:
        if previously:
            return "active_link_loss", True
        return "unavailable", True
    if status.standing is None or status.stationary is None or status.avoidance_enabled is None:
        return "unknown", False
    return "available", False


def _classify_drone(status: DroneStatus, *, previously: bool) -> tuple[str, bool]:
    if status.connected is not True:
        if previously:
            return "active_link_loss", True
        return "optional_unavailable", False
    if status.flight_state == "unknown" or status.battery_percent is None:
        return "unknown", previously and status.flight_state == "unknown"
    return "available", False


def _raise_conflict(component: str, old: str, new: str) -> None:
    if old == "real" and new == "fake":
        raise fault("rejected", "real-to-fake substitution", recovery_required=True)
    if component == "dog":
        raise fault("rejected", "duplicate dog connection", recovery_required=True)
    raise fault("rejected", f"duplicate {component} connection", recovery_required=True)


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, GroundFault):
        return exc
    if isinstance(exc, AdapterError):
        if exc.code == "timeout":
            return fault("timeout", exc.detail, recovery_required=True)
        if exc.code == "cancelled":
            return fault("cancelled", exc.detail, recovery_required=True)
        if exc.code == "invalid_input":
            return fault("invalid_input", exc.detail)
        return fault("unavailable", f"{exc.code}: {exc.detail}")
    return exc


def _observed(gateway: AdapterGateway) -> str:
    return gateway.kernel.clock.utc_now().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unwrap(task: asyncio.Task[object]) -> object:
    exc = task.exception()
    if exc is not None:
        raise exc
    return task.result()


async def _ready(value: object) -> object:
    return value


def _invoke_named(adapter: object, name: str) -> object:
    action = getattr(adapter, name, None)
    if not callable(action):
        raise fault("contract_mismatch", f"adapter has no {name} method")
    return action()


def _ensure_awaitable(value: object) -> Awaitable[object]:
    if inspect.isawaitable(value):
        return value
    raise fault("contract_mismatch", "adapter method must return an awaitable")


async def _maybe_await(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value
