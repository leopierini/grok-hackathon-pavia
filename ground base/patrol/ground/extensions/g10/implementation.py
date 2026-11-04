"""Independent halt, cleanup, shutdown, and reset.

``create(kernel, peers)`` is the production factory. The Task 01 simulator calls
``create(services)`` and expects ``execute``; that path builds this same service
and does not replace it with the kernel safety double.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Protocol, cast

from patrol.contract import DogStatus, DroneStatus
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import (
    AdapterPort,
    BaseServices,
    ConsolePort,
    FeatureRequest,
    FeatureResult,
    GroundError,
    KernelContext,
    SafetyHandle,
    SafetySnapshot,
    ServicePorts,
    Ticket,
    WaitSpec,
)
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.validation import freeze_map

_RECOVERY_LIMIT_S = 30.0


class _StopDevice(Protocol):
    async def halt(self) -> None: ...

    async def get_status(self) -> object: ...

    async def close(self) -> None: ...


class _LandDevice(Protocol):
    async def land(self) -> None: ...

    async def get_status(self) -> object: ...

    async def close(self) -> None: ...


class _Closeable(Protocol):
    async def close(self) -> None: ...


class _RouteDevice(Protocol):
    def run_route(self, zone: str, context: object) -> Awaitable[object]: ...


class _Bundle(Protocol):
    dog: _StopDevice
    drone: _LandDevice
    reasoner: _Closeable
    calls: list[str]
    output_dir: Path


def create(
    kernel: KernelContext | BaseServices,
    peers: ServicePorts | None = None,
) -> SafetyService | SafetyProbe:
    """Build the safety port, or the simulator probe when given base services."""
    if isinstance(kernel, BaseServices):
        if peers is not None:
            raise fault("invalid_input", "harness create takes services only")
        return SafetyProbe(kernel)
    if peers is None:
        raise fault("invalid_input", "safety create expects kernel and peers")
    return SafetyService(kernel, peers)


class SafetyService:
    """One supervisor per latch. A later halt joins it; it does not land twice."""

    def __init__(self, kernel: KernelContext, peers: ServicePorts) -> None:
        bundle = _bundle(peers.adapters)
        self.kernel = kernel
        self._adapters: AdapterPort = peers.adapters
        self._console: ConsolePort = peers.console
        self._dog: _StopDevice = bundle.dog
        self._drone: _LandDevice = bundle.drone
        self._reasoner: _Closeable = bundle.reasoner
        self._output_dir = bundle.output_dir
        self.trace: list[str] = []
        self.mission_failure: str | None = None
        self.cleanup_errors: list[str] = []
        self.recovery_required = False
        self.motion_locked = False
        self.armed = False
        self.reconnected = False
        self.confirmation_generation = 0
        self.supervisor_id = ""
        self.reason = ""
        self.dog_posture = "unread"
        self.drone_posture = "unread"
        self.dog_error = ""
        self.drone_error = ""
        self.settled = False
        self._shutdown_started = False
        self._handle: SafetyHandle | None = None
        self._dog_task: asyncio.Task[None] | None = None
        self._drone_task: asyncio.Task[None] | None = None
        self._supervisor_task: asyncio.Task[None] | None = None

    @property
    def handle(self) -> SafetyHandle | None:
        return self._handle

    @property
    def dog_task(self) -> asyncio.Task[None] | None:
        return self._dog_task

    @property
    def drone_task(self) -> asyncio.Task[None] | None:
        return self._drone_task

    @property
    def supervisor_task(self) -> asyncio.Task[None] | None:
        return self._supervisor_task

    @property
    def detail(self) -> str:
        return self._detail()

    def note_mission_failure(self, detail: str) -> None:
        """Record the mission failure that cleanup must not replace."""
        if not isinstance(detail, str) or not detail.strip():
            raise fault("invalid_input", "mission failure detail is required")
        if self.mission_failure is None:
            self.mission_failure = detail.strip()

    def request(self, reason: str, ticket: Ticket) -> SafetyHandle:
        """Latch and schedule both stops before any device or disk wait."""
        cleaned = _text(reason, "safety reason is required")
        if not isinstance(ticket, Ticket):
            raise fault("invalid_input", "expected a Ticket")
        if self._handle is not None:
            self.kernel.authority.latch_cancel(cleaned)
            return self._handle
        self.kernel.authority.latch_cancel(cleaned)
        self.reason = cleaned
        self.recovery_required = True
        self.motion_locked = True
        self.confirmation_generation += 1
        self.supervisor_id = f"safety-{self.confirmation_generation}"
        self.trace.append("latched")
        self.trace.append("scheduled:dog.halt")
        self.trace.append("scheduled:drone.land")
        self._dog_task = asyncio.create_task(self._run_dog(), name="safety.dog.halt")
        self._drone_task = asyncio.create_task(self._run_drone(), name="safety.drone.land")
        self._supervisor_task = asyncio.create_task(
            self._supervise(),
            name="safety.supervisor",
        )
        self.kernel.tasks.retain("safety.dog.halt", self._dog_task)
        self.kernel.tasks.retain("safety.drone.land", self._drone_task)
        self.kernel.tasks.retain("safety.supervisor", self._supervisor_task)
        self._handle = SafetyHandle(ticket, cleaned, self.kernel.authority.epoch)
        self._console.write(f"halt requested: {cleaned}")
        return self._handle

    async def observe(self, handle: SafetyHandle, *, deadline: float) -> SafetySnapshot:
        """Wait on the safety clock, not a cancelled mission RunContext."""
        _positive_deadline(deadline)
        self._check_handle(handle)
        await _wait_for(self._supervisor_task, deadline, self.kernel.clock.sleep)
        if not self._stops_pending():
            await self._read_status()
        return self._snapshot()

    async def reset(self, recovery: Mapping[str, object]) -> None:
        """Recreate adapters only after quiescence, safe status, and close."""
        if isinstance(recovery, (str, bytes)) or not isinstance(recovery, Mapping):
            raise fault("invalid_input", "recovery must be a mapping")
        if recovery.get("verified") is not True:
            raise fault("invalid_input", "recovery verified must be true")
        if recovery.get("replay_route") is True or recovery.get("replay_takeoff") is True:
            raise fault("invalid_input", "recovery must not replay a route or takeoff")
        if self.kernel.tasks.pending():
            self.trace.append("reset:refused")
            raise fault(
                "unsafe_state",
                "old work is still active",
                recovery_required=True,
            )
        await self._read_status()
        if not _physically_safe(self.dog_posture, self.drone_posture):
            self.trace.append("reset:refused")
            raise fault(
                "unsafe_state",
                "physical state is not verified stopped and grounded",
                recovery_required=True,
            )
        errors = await self._close_all()
        if errors:
            self.cleanup_errors.extend(errors)
            self.recovery_required = True
            self.trace.append("reset:cleanup_failed")
            raise fault(
                "unsafe_state",
                "cleanup failed; adapters were not recreated",
                recovery_required=True,
            )
        await self._reconnect()

    async def shutdown(self, reason: str) -> None:
        """Latch and stop, then close only after those attempts settle."""
        cleaned = _text(reason, "safety reason is required")
        if self._shutdown_started:
            self.trace.append("shutdown:duplicate")
            return
        self._shutdown_started = True
        if self._handle is None:
            if self.kernel.authority.cancelled:
                ticket = Ticket("safety", self.kernel.authority.epoch, "shutdown")
            else:
                ticket = self.kernel.authority.issue("safety", "shutdown")
            self.request(cleaned, ticket)
        handle = self._handle
        if handle is None:
            raise fault("internal", "shutdown did not retain a supervisor", recovery_required=True)
        self.trace.append("shutdown:requested")
        await self.observe(handle, deadline=_RECOVERY_LIMIT_S)
        if self._stops_pending():
            self.trace.append("shutdown:stops_pending")
            return
        errors = await self._close_all()
        self.cleanup_errors.extend(errors)
        if errors:
            self.trace.append("shutdown:cleanup_errors")
            return
        self.trace.append("shutdown:closed")

    async def _run_dog(self) -> None:
        self.trace.append("started:dog.halt")
        try:
            await self._dog.halt()
        except asyncio.CancelledError:
            self.dog_error = "CancelledError"
            self.trace.append("error:dog.halt")
            raise
        except Exception as exc:
            self.dog_error = f"{type(exc).__name__}: {exc}"
            self.trace.append("error:dog.halt")
            return
        self.trace.append("finished:dog.halt")

    async def _run_drone(self) -> None:
        self.trace.append("started:drone.land")
        try:
            await self._drone.land()
        except asyncio.CancelledError:
            self.drone_error = "CancelledError"
            self.trace.append("error:drone.land")
            raise
        except Exception as exc:
            self.drone_error = f"{type(exc).__name__}: {exc}"
            self.trace.append("error:drone.land")
            return
        self.trace.append("finished:drone.land")

    async def _supervise(self) -> None:
        dog_task = self._dog_task
        drone_task = self._drone_task
        if dog_task is None or drone_task is None:
            return
        try:
            await asyncio.gather(dog_task, drone_task, return_exceptions=True)
        except asyncio.CancelledError:
            self.trace.append("supervisor:children_kept")
            raise
        await self._read_status()
        self.settled = True

    async def _read_status(self) -> None:
        try:
            dog_status = await self._dog.get_status()
        except Exception as exc:
            self.dog_posture = "unknown"
            self.trace.append(f"status-error:dog:{type(exc).__name__}")
        else:
            self.dog_posture = _dog_posture(dog_status)
        try:
            drone_status = await self._drone.get_status()
        except Exception as exc:
            self.drone_posture = "unknown"
            self.trace.append(f"status-error:drone:{type(exc).__name__}")
        else:
            self.drone_posture = _drone_posture(drone_status)

    async def _close_all(self) -> list[str]:
        errors: list[str] = []
        for label, device in (
            ("dog.close", self._dog),
            ("drone.close", self._drone),
            ("reasoner.close", self._reasoner),
        ):
            try:
                await device.close()
            except Exception as exc:
                errors.append(f"{label}:{exc}")
                self.trace.append(f"cleanup:{label}")
            else:
                self.trace.append(f"closed:{label}")
        return errors

    async def _reconnect(self) -> None:
        try:
            await self._adapters.build(
                make_settings(),
                self._output_dir,
                resolver={},
            )
            await self._adapters.connect("dog")
            await self._adapters.connect("drone")
        except Exception as exc:
            self.cleanup_errors.append(f"reconnect:{exc}")
            self.recovery_required = True
            self.reconnected = False
            self.trace.append("reset:reconnect_failed")
            raise fault(
                "unsafe_state",
                "reconnect failed; motion stays latched",
                recovery_required=True,
            ) from exc
        self.kernel.authority.reset_generation("operator recovery")
        self.confirmation_generation += 1
        self._handle = None
        self._dog_task = None
        self._drone_task = None
        self._supervisor_task = None
        self.supervisor_id = ""
        self.motion_locked = False
        self.recovery_required = False
        self.reconnected = True
        self.armed = False
        self.trace.append("reset:disarmed")
        self._console.write("reconnected disarmed")

    def _check_handle(self, handle: SafetyHandle) -> None:
        if not isinstance(handle, SafetyHandle):
            raise fault("invalid_input", "expected a SafetyHandle")
        active = self._handle
        if (
            active is None
            or handle.ticket != active.ticket
            or handle.reason != active.reason
            or handle.generation != active.generation
        ):
            raise fault(
                "stale_ticket",
                "safety handle is not current",
                recovery_required=True,
            )

    def _stops_pending(self) -> bool:
        for task in (self._dog_task, self._drone_task):
            if task is not None and not task.done():
                return True
        return False

    def _snapshot(self) -> SafetySnapshot:
        pending = self._stops_pending() or bool(self.kernel.tasks.pending())
        return SafetySnapshot(
            halted=self.kernel.authority.cancelled,
            recovery_required=self.recovery_required,
            pending=pending,
            detail=self._detail(),
        )

    def _detail(self) -> str:
        parts = [self.reason or "idle"]
        if "link" in self.reason.lower():
            parts.append("delivery_not_assumed")
        if self.dog_error:
            parts.append("dog_error")
        if self.drone_error:
            parts.append("drone_error")
        parts.append(f"dog:{self.dog_posture}")
        parts.append(f"drone:{self.drone_posture}")
        if self.mission_failure:
            parts.append(f"original:{self.mission_failure}")
        if self.cleanup_errors:
            parts.append("cleanup:" + ",".join(self.cleanup_errors))
        if self._stops_pending():
            parts.append("pending")
        if self.reconnected:
            parts.append("disarmed")
        return "; ".join(parts)


class SafetyProbe:
    """Runs scripted cases through SafetyService for the frozen simulator."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        handlers: dict[str, Callable[[], Awaitable[FeatureResult]]] = {
            "immediate_latch": self._immediate_latch,
            "independent_stops": self._independent_stops,
            "coalesce": self._coalesce,
            "stop_errors": self._stop_errors,
            "unknown_landing": self._unknown_landing,
            "resistant_worker": self._resistant_worker,
            "fresh_reset": self._fresh_reset,
            "responsiveness": self._responsiveness,
            "cleanup_fault": self._cleanup_fault,
            "expired_context": self._expired_context,
            "link_loss": self._link_loss,
            "shutdown_once": self._shutdown_once,
            "invalid_recovery": self._invalid_recovery,
            "observe_timeout": self._observe_timeout,
        }
        handler = handlers.get(request.name)
        if handler is None:
            return self._failed("invalid_input", f"unknown safety case {request.name}")
        try:
            return await handler()
        except GroundFault as exc:
            return self._failed(exc.error.code, exc.error.detail)

    async def _immediate_latch(self) -> FeatureResult:
        await self._park_route()
        service = self._open()
        calls = self._calls()
        ticket = self.services.kernel.authority.issue("mission-10", "halt")
        service.request("operator halt", ticket)
        records = getattr(self.services.journal, "records", None)
        ok = (
            tuple(service.trace[:3])
            == ("latched", "scheduled:dog.halt", "scheduled:drone.land")
            and "dog.halt" not in calls
            and "drone.land" not in calls
            and self.services.kernel.authority.cancelled
            and records == []
        )
        return self._gate(
            ok,
            "latch was not visible before device entry",
            authorized=False,
            retained=True,
            detail="latched_before_device_await",
            trace=(
                "latched",
                "scheduled:dog.halt",
                "scheduled:drone.land",
                "devices_not_entered",
                "journal_untouched",
            ),
            device_calls=len(calls),
        )

    async def _independent_stops(self) -> FeatureResult:
        service = self._open()
        devices = self._devices()
        barriers = self.services.kernel.barriers
        barriers.arm("safety.dog.halt")

        async def dog_halt() -> None:
            devices.calls.append("dog.halt")
            await barriers.wait("safety.dog.halt")

        async def drone_land() -> None:
            devices.calls.append("drone.land")

        _install(devices.dog, "halt", dog_halt)
        _install(devices.drone, "land", drone_land)
        ticket = self.services.kernel.authority.issue("mission-10", "halt")
        service.request("operator halt", ticket)
        entered = "dog.halt" in devices.calls or "drone.land" in devices.calls
        latched = self.services.kernel.authority.cancelled
        await _spin(lambda: "dog.halt" in devices.calls and "drone.land" in devices.calls)
        dog_task = service.dog_task
        drone_task = service.drone_task
        ok = (
            latched
            and not entered
            and dog_task is not None
            and not dog_task.done()
            and drone_task is not None
            and drone_task.done()
            and "started:dog.halt" in service.trace
            and "started:drone.land" in service.trace
        )
        barriers.release("safety.dog.halt")
        await _settle(service)
        return self._gate(
            ok,
            "dog and drone stops were not independent",
            authorized=False,
            retained=True,
            detail="independent_stop_requests",
            trace=(
                "latched_before_await",
                "started:dog.halt",
                "started:drone.land",
                "drone_done",
                "dog_pending",
            ),
            device_calls=len(devices.calls),
        )

    async def _coalesce(self) -> FeatureResult:
        service = self._open()
        calls = self._calls()
        ticket = self.services.kernel.authority.issue("mission-10", "halt")
        first = service.request("operator halt", ticket)
        dog_task = service.dog_task
        drone_task = service.drone_task
        second = service.request("operator halt", ticket)
        await _settle(service)
        ok = (
            first is second
            and service.dog_task is dog_task
            and service.drone_task is drone_task
            and calls.count("dog.halt") == 1
            and calls.count("drone.land") == 1
        )
        return self._gate(
            ok,
            "repeated halt started another landing",
            authorized=False,
            retained=True,
            detail="one_supervisor",
            trace=("same_handle", "dog.halt:1", "drone.land:1"),
            device_calls=len(calls),
        )

    async def _stop_errors(self) -> FeatureResult:
        service = self._open()
        devices = self._devices()

        async def dog_halt() -> None:
            devices.calls.append("dog.halt")
            raise RuntimeError("dog halt failed")

        async def drone_land() -> None:
            devices.calls.append("drone.land")
            raise RuntimeError("drone land failed")

        _install(devices.dog, "halt", dog_halt)
        _install(devices.drone, "land", drone_land)
        ticket = self.services.kernel.authority.issue("mission-10", "halt")
        service.request("operator halt", ticket)
        await _settle(service)
        ok = (
            bool(service.dog_error)
            and bool(service.drone_error)
            and devices.calls.count("dog.halt") == 1
            and devices.calls.count("drone.land") == 1
            and service.recovery_required
            and service.motion_locked
        )
        return self._gate(
            ok,
            "one stop error suppressed the other attempt",
            authorized=False,
            retained=True,
            detail="both_stop_errors",
            trace=("error:dog.halt", "error:drone.land", "both_attempted"),
            device_calls=len(devices.calls),
        )

    async def _unknown_landing(self) -> FeatureResult:
        service = self._open()
        devices = self._devices()
        state: dict[str, object] = {"stationary": None, "flight": "unknown"}

        async def dog_status() -> DogStatus:
            devices.calls.append("dog.get_status")
            if state["stationary"] is True:
                return DogStatus(True, True, True, True)
            return DogStatus(True, True, None, True)

        async def drone_status() -> DroneStatus:
            devices.calls.append("drone.get_status")
            if state["flight"] == "grounded":
                return DroneStatus(True, "grounded", 80)
            if state["flight"] == "airborne":
                return DroneStatus(True, "airborne", 80)
            return DroneStatus(True, "unknown", 80)

        _install(devices.dog, "get_status", dog_status)
        _install(devices.drone, "get_status", drone_status)
        ticket = self.services.kernel.authority.issue("mission-10", "halt")
        handle = service.request("operator halt", ticket)
        await _settle(service)
        first = await service.observe(handle, deadline=1)
        state["stationary"] = True
        state["flight"] = "grounded"
        second = await service.observe(handle, deadline=1)
        ok = (
            first.recovery_required
            and second.recovery_required
            and service.motion_locked
            and self.services.kernel.authority.cancelled
            and "adapters.build" not in devices.calls
            and "delivered" not in second.detail
        )
        return self._gate(
            ok,
            "late grounded status cleared the fault",
            authorized=False,
            retained=True,
            detail="recovery_latched",
            trace=("status:unknown", "late_grounded_ignored", "motion_locked"),
            device_calls=len(devices.calls),
        )

    async def _resistant_worker(self) -> FeatureResult:
        service = self._open()
        calls = self._calls()
        barriers = self.services.kernel.barriers
        barriers.arm("resistant")
        barriers.arm("resistant-done")
        ignored = {"value": False}

        async def worker() -> None:
            try:
                await barriers.wait("resistant")
            except asyncio.CancelledError:
                ignored["value"] = True
            await barriers.wait("resistant-done")

        task = asyncio.create_task(worker(), name="old-route")
        self.services.kernel.tasks.retain("old-route", task)
        try:
            await _spin(lambda: "old-route" in self.services.kernel.tasks.pending())
            ticket = self.services.kernel.authority.issue("mission-10", "halt")
            service.request("operator halt", ticket)
            await _settle(service)
            task.cancel()
            await _spin(lambda: ignored["value"])
            refused = False
            try:
                await service.reset({"verified": True})
            except GroundFault as exc:
                refused = exc.error.code == "unsafe_state"
            ok = (
                refused
                and ignored["value"]
                and calls.count("adapters.build") == 0
                and service.recovery_required
                and service.motion_locked
            )
        finally:
            barriers.release("resistant-done")
            with contextlib.suppress(asyncio.CancelledError):
                await task
        return self._gate(
            ok,
            "reset recreated adapters while old work was alive",
            authorized=False,
            retained=True,
            detail="reset_refused",
            trace=("cancel_ignored", "reset_refused", "build:0"),
            device_calls=len(calls),
        )

    async def _fresh_reset(self) -> FeatureResult:
        service = self._open()
        calls = self._calls()
        authority = self.services.kernel.authority
        ticket = authority.issue("mission-10", "halt")
        service.request("operator halt", ticket)
        await _settle(service)
        old_event = authority.cancel_event
        old_epoch = authority.epoch
        spec = WaitSpec("arrival", "room_2", "arrival", self.services.kernel.clock.monotonic() + 5)
        before = await self.services.console.confirm(spec)
        await service.reset(_fixture_recovery())
        after = await self.services.console.confirm(spec)
        stale = False
        try:
            authority.require_current(ticket)
        except GroundFault as exc:
            stale = exc.error.code == "stale_ticket"
        fresh = authority.issue("mission-10", "after-reset")
        authority.require_current(fresh)
        ok = (
            authority.epoch == old_epoch + 1
            and authority.cancel_event is not old_event
            and not authority.cancelled
            and stale
            and before.accepted is False
            and after.accepted is True
            and service.reconnected
            and service.armed is False
            and service.motion_locked is False
            and service.recovery_required is False
            and "dog.run_route" not in calls
            and "drone.inspect" not in calls
            and "takeoff_attempt" not in calls
            and "adapters.build" in calls
            and "adapters.connect:dog" in calls
            and "adapters.connect:drone" in calls
        )
        return self._gate(
            ok,
            "reset did not leave a fresh disarmed generation",
            authorized=not authority.cancelled,
            retained=service.recovery_required,
            detail="disarmed",
            trace=(
                "epoch_replaced",
                "event_replaced",
                "stale_ticket",
                "confirmation_replaced",
                "reconnected",
                "disarmed",
                "route_not_replayed",
            ),
            device_calls=len(calls),
            measurement_clock="manual",
        )

    async def _responsiveness(self) -> FeatureResult:
        service = self._open()
        calls = self._calls()
        ticket = self.services.kernel.authority.issue("mission-10", "halt")
        started = time.monotonic()
        service.request("operator halt", ticket)
        elapsed = time.monotonic() - started
        recognized = elapsed < 0.5 and self.services.kernel.authority.cancelled
        await _settle(service)
        return self._gate(
            recognized,
            "halt recognition exceeded the fake 0.5s target",
            authorized=False,
            retained=True,
            detail="recognition_only",
            trace=("recognized",),
            device_calls=len(calls),
            within_limit=recognized,
            measurement_clock="real",
        )

    async def _cleanup_fault(self) -> FeatureResult:
        service = self._open()
        devices = self._devices()
        authority = self.services.kernel.authority
        service.note_mission_failure("route failed")
        ticket = authority.issue("mission-10", "halt")
        service.request("operator halt", ticket)
        await _settle(service)

        async def dog_close() -> None:
            devices.calls.append("dog.close")
            raise RuntimeError("dog close failed")

        async def drone_close() -> None:
            devices.calls.append("drone.close")
            raise RuntimeError("drone close failed")

        _install(devices.dog, "close", dog_close)
        _install(devices.drone, "close", drone_close)
        epoch = authority.epoch
        failed = False
        try:
            await service.reset({"verified": True})
        except GroundFault as exc:
            failed = exc.error.code == "unsafe_state"
        ok = (
            failed
            and service.mission_failure == "route failed"
            and any(item.startswith("dog.close:") for item in service.cleanup_errors)
            and any(item.startswith("drone.close:") for item in service.cleanup_errors)
            and "reasoner.close" in devices.calls
            and "adapters.build" not in devices.calls
            and authority.epoch == epoch
            and authority.cancelled
        )
        return self._gate(
            ok,
            "cleanup replaced the original mission failure",
            authorized=False,
            retained=True,
            detail="original_preserved",
            trace=(
                "original:route failed",
                "cleanup:dog.close",
                "cleanup:drone.close",
                "cleanup:reasoner.close",
                "generation_unchanged",
            ),
            device_calls=len(devices.calls),
        )

    async def _expired_context(self) -> FeatureResult:
        service = self._open()
        calls = self._calls()
        authority = self.services.kernel.authority
        clock = self.services.kernel.clock
        ticket = authority.issue("mission-10", "route")
        expired = False
        try:
            authority.require_action(
                ticket,
                deadline_monotonic=clock.monotonic(),
                clock=clock,
            )
        except GroundFault as exc:
            expired = exc.error.code == "expired_deadline"
        service.request("operator halt", ticket)
        await _settle(service)
        ok = expired and "dog.halt" in calls and "drone.land" in calls
        return self._gate(
            ok,
            "expired mission deadline blocked recovery stops",
            authorized=False,
            retained=True,
            detail="recovery_after_expired_deadline",
            trace=(
                "ordinary_deadline_expired",
                "recovery_halt_started",
                "recovery_land_started",
            ),
            device_calls=len(calls),
        )

    async def _link_loss(self) -> FeatureResult:
        service = self._open()
        devices = self._devices()

        async def dog_status() -> DogStatus:
            devices.calls.append("dog.get_status")
            return DogStatus(False, None, None, None)

        async def drone_status() -> DroneStatus:
            devices.calls.append("drone.get_status")
            return DroneStatus(False, "unknown", None)

        _install(devices.dog, "get_status", dog_status)
        _install(devices.drone, "get_status", drone_status)
        ticket = self.services.kernel.authority.issue("mission-10", "halt")
        service.request("ethernet link lost", ticket)
        await _settle(service)
        ok = (
            "delivery_not_assumed" in service.detail
            and "delivered" not in service.detail
            and "started:dog.halt" in service.trace
            and "started:drone.land" in service.trace
            and "dog.halt" in devices.calls
            and "drone.land" in devices.calls
            and service.recovery_required
        )
        return self._gate(
            ok,
            "link loss skipped a stop or claimed delivery",
            authorized=False,
            retained=True,
            detail="delivery_not_assumed",
            trace=("delivery_not_assumed", "started:dog.halt", "started:drone.land"),
            device_calls=len(devices.calls),
        )

    async def _shutdown_once(self) -> FeatureResult:
        service = self._open()
        calls = self._calls()
        await service.shutdown("operator quit")
        await service.shutdown("operator quit")
        ok = (
            calls.count("drone.land") == 1
            and calls.count("dog.halt") == 1
            and "shutdown:duplicate" in service.trace
            and "dog.close" in calls
            and "drone.close" in calls
            and "reasoner.close" in calls
            and service.recovery_required
            and service.reconnected is False
            and "dog.run_route" not in calls
            and "emergency" not in calls
        )
        return self._gate(
            ok,
            "shutdown started a second landing or cleared recovery",
            authorized=False,
            retained=True,
            detail="shutdown",
            trace=(
                "one_supervisor",
                "closed:dog.close",
                "closed:drone.close",
                "closed:reasoner.close",
                "no_second_land",
            ),
            device_calls=len(calls),
        )

    async def _invalid_recovery(self) -> FeatureResult:
        service = self._open()
        calls = self._calls()
        authority = self.services.kernel.authority
        epoch = authority.epoch
        try:
            await service.reset({"verified": "true"})
        except GroundFault as exc:
            ok = (
                exc.error.code == "invalid_input"
                and exc.error.detail == "recovery verified must be true"
                and authority.epoch == epoch
                and not authority.cancelled
                and calls == []
            )
            if not ok:
                return self._failed("validation_failed", "string recovery was accepted")
            return self._finish(
                authorized=True,
                retained=False,
                detail=exc.error.detail,
                trace=("rejected_string_bool",),
                device_calls=0,
                status="failed",
                error=exc.error,
            )
        return self._failed("validation_failed", "string recovery was accepted")

    async def _observe_timeout(self) -> FeatureResult:
        service = self._open()
        devices = self._devices()
        barriers = self.services.kernel.barriers
        barriers.arm("safety.dog.halt")
        barriers.arm("safety.drone.land")
        observed: asyncio.Task[SafetySnapshot] | None = None

        async def dog_halt() -> None:
            devices.calls.append("dog.halt")
            await barriers.wait("safety.dog.halt")

        async def drone_land() -> None:
            devices.calls.append("drone.land")
            await barriers.wait("safety.drone.land")

        _install(devices.dog, "halt", dog_halt)
        _install(devices.drone, "land", drone_land)
        try:
            ticket = self.services.kernel.authority.issue("mission-10", "halt")
            handle = service.request("operator halt", ticket)
            await _spin(lambda: "dog.halt" in devices.calls and "drone.land" in devices.calls)
            observed = asyncio.create_task(service.observe(handle, deadline=1))
            await _spin(lambda: bool(getattr(self.services.kernel.clock, "_waiters", None)))
            advance = getattr(self.services.kernel.clock, "advance", None)
            if not callable(advance):
                raise fault("internal", "manual clock cannot advance")
            advance(1)
            snapshot = await observed
            dog_task = service.dog_task
            drone_task = service.drone_task
            ok = (
                snapshot.pending
                and snapshot.recovery_required
                and dog_task is not None
                and not dog_task.done()
                and drone_task is not None
                and not drone_task.done()
                and self.services.kernel.authority.cancelled
            )
        finally:
            barriers.release("safety.dog.halt")
            barriers.release("safety.drone.land")
            if observed is not None and not observed.done():
                observed.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await observed
            await _settle(service)
        return self._gate(
            ok,
            "observation deadline cancelled a stop attempt",
            authorized=False,
            retained=True,
            detail="pending_after_deadline",
            trace=(
                "pending_after_deadline",
                "dog_attempt_alive",
                "drone_attempt_alive",
            ),
            device_calls=len(devices.calls),
        )

    async def _park_route(self) -> None:
        devices = self._devices()
        barriers = self.services.kernel.barriers
        barriers.arm("dog.run_route")
        authority = self.services.kernel.authority
        authority.issue("mission-10", "route")
        context = context_for_stage(
            "mission-10",
            self.services.kernel.clock.monotonic() + 30,
            30,
            authority.cancel_event,
            self.services.kernel.clock,
            real_adapter=False,
        )
        routed = cast(_RouteDevice, devices.dog)

        async def hold() -> None:
            await routed.run_route("room_2", context)

        task = asyncio.create_task(hold(), name="mission.route")
        self.services.kernel.tasks.retain("mission.route", task)
        await _spin(lambda: _barrier_holding(barriers, "dog.run_route"))

    def _open(self) -> SafetyService:
        return SafetyService(self.services.kernel, _ports(self.services))

    def _devices(self) -> _Bundle:
        return _bundle(self.services.adapters)

    def _calls(self) -> list[str]:
        return self._devices().calls

    def _gate(
        self,
        ok: bool,
        reason: str,
        *,
        authorized: bool,
        retained: bool,
        detail: str,
        trace: tuple[str, ...],
        device_calls: int,
        within_limit: bool = True,
        measurement_clock: str = "manual",
    ) -> FeatureResult:
        if not ok:
            return self._finish(
                authorized=False,
                retained=True,
                detail=reason,
                trace=("check_failed", reason),
                device_calls=device_calls,
            )
        return self._finish(
            authorized=authorized,
            retained=retained,
            detail=detail,
            trace=trace,
            device_calls=device_calls,
            within_limit=within_limit,
            measurement_clock=measurement_clock,
        )

    def _finish(
        self,
        *,
        authorized: bool,
        retained: bool,
        detail: str,
        trace: tuple[str, ...],
        device_calls: int,
        within_limit: bool = True,
        measurement_clock: str = "manual",
        status: str = "ok",
        error: GroundError | None = None,
    ) -> FeatureResult:
        if self._live() != 0:
            status = "failed"
            error = GroundError("unsafe_state", "simulation made a live device call", True)
        data = freeze_map(
            {
                "authorized": authorized,
                "retained": retained,
                "detail": detail,
                "trace": trace,
                "device_calls": device_calls,
                "measurement_clock": measurement_clock,
                "within_limit": within_limit,
                "simulated": True,
                "live_call_count": 0,
                "slot": "base.safety",
                "schema_version": SCHEMA_VERSION,
            }
        )
        return FeatureResult(status, data, (), error)

    def _failed(self, code: str, detail: str) -> FeatureResult:
        recovery = code in {"cancelled", "timeout", "unsafe_state", "io_fault"}
        error = GroundError(code, detail, recovery)
        return self._finish(
            authorized=False,
            retained=recovery,
            detail=detail,
            trace=("failed", code),
            device_calls=len(self._calls()) if _has_devices(self.services.adapters) else 0,
            status="failed",
            error=error,
        )

    def _live(self) -> int:
        devices = getattr(self.services.adapters, "devices", None)
        value = getattr(devices, "live_call_count", 0)
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return value


def _ports(services: BaseServices) -> ServicePorts:
    return ServicePorts(
        config=services.config,
        state=services.state,
        journal=services.journal,
        executor=services.executor,
        evidence=services.evidence,
        console=services.console,
        adapters=services.adapters,
        workflow=services.workflow,
        safety=services.safety,
    )


def _bundle(adapters: object) -> _Bundle:
    devices = getattr(adapters, "devices", None)
    calls = getattr(devices, "calls", None)
    output = getattr(devices, "output_dir", None)
    dog = getattr(devices, "dog", None)
    drone = getattr(devices, "drone", None)
    reasoner = getattr(devices, "reasoner", None)
    if (
        dog is None
        or drone is None
        or reasoner is None
        or not isinstance(calls, list)
        or not isinstance(output, Path)
    ):
        raise fault("missing_provider", "dog and drone ports are not injected")
    return cast(_Bundle, devices)


def _has_devices(adapters: object) -> bool:
    try:
        _bundle(adapters)
    except GroundFault:
        return False
    return True


def _install(device: object, name: str, method: Callable[..., Awaitable[object]]) -> None:
    setattr(device, name, method)


def _text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", message)
    return value.strip()


def _positive_deadline(deadline: object) -> float:
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        raise fault("invalid_input", "observe deadline must be a real number")
    number = float(deadline)
    if not math.isfinite(number) or number <= 0:
        raise fault("invalid_input", "observe deadline must be positive")
    return number


def _dog_posture(status: object) -> str:
    if not isinstance(status, DogStatus):
        return "unknown"
    if status.connected is not True:
        return "disconnected"
    if status.standing is not True or status.stationary is not True:
        return "not_stopped"
    return "safe"


def _drone_posture(status: object) -> str:
    if not isinstance(status, DroneStatus):
        return "unknown"
    if status.connected is not True:
        return "disconnected"
    if status.flight_state == "grounded":
        return "grounded"
    if status.flight_state == "airborne":
        return "airborne"
    return "unknown"


def _physically_safe(dog_posture: str, drone_posture: str) -> bool:
    return dog_posture == "safe" and drone_posture == "grounded"


async def _wait_for(
    supervisor: asyncio.Task[None] | None,
    deadline: float,
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    if supervisor is None or supervisor.done():
        return
    sleep_task: asyncio.Task[None] = asyncio.create_task(_pause(deadline, sleep))
    wait_task = asyncio.create_task(_shielded(supervisor))
    try:
        await asyncio.wait({sleep_task, wait_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sleep_task, wait_task):
            if not task.done():
                task.cancel()
        for task in (sleep_task, wait_task):
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _pause(seconds: float, sleep: Callable[[float], Awaitable[None]]) -> None:
    await sleep(seconds)


async def _shielded(task: asyncio.Task[None]) -> None:
    await asyncio.shield(task)


def _barrier_holding(barriers: object, name: str) -> bool:
    waiters = getattr(barriers, "_waiters", None)
    if not isinstance(waiters, dict):
        return False
    waiting = waiters.get(name)
    return isinstance(waiting, list) and bool(waiting)


async def _spin(ready: Callable[[], bool]) -> None:
    for _ in range(50):
        if ready():
            return
        await asyncio.sleep(0)
    raise fault("timeout", "safety condition was not observed")


async def _settle(service: SafetyService) -> None:
    task = service.supervisor_task
    if task is None:
        return
    for _ in range(50):
        if task.done():
            break
        await asyncio.sleep(0)
    else:
        raise fault("timeout", "safety supervisor did not settle")
    if not task.cancelled():
        await task


def _fixture_recovery() -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g10" / "recovery.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise fault(
            "io_fault",
            "recovery fixture could not be read",
            recovery_required=True,
        ) from exc
    if not isinstance(loaded, dict):
        raise fault("invalid_input", "recovery fixture must be an object")
    if loaded.get("replay_route") is not False or loaded.get("replay_takeoff") is not False:
        raise fault("invalid_input", "recovery fixture must not replay motion")
    if loaded.get("verified") is not True:
        raise fault("invalid_input", "recovery fixture is not verified")
    return cast(dict[str, object], loaded)
