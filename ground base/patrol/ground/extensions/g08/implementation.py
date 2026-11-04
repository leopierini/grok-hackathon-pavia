"""Adapter gateway factory and the simulation driver for GROUND-08."""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Mapping
from pathlib import Path

from patrol.contract import (
    AdapterError,
    DogStatus,
    DroneStatus,
    Frame,
    Incident,
    InspectionRequest,
    Resolution,
    RunContext,
)
from patrol.ground.extensions.g08.gateway import (
    AdapterGateway,
    clear_claims_for_tests,
)
from patrol.ground.extensions.g08.resolve import MISSING_PUBLIC
from patrol.ground.extensions.g08.support import Bundle
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundSettings,
    KernelContext,
    ServicePorts,
    Ticket,
)
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import service_ports

_PUBLIC = {
    "dog": ("patrol.dog", "create_dog"),
    "drone": ("patrol.drone", "create_drone"),
    "reasoner": ("patrol.grok", "create_reasoner"),
}


class GatewayHarness:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        clear_claims_for_tests()
        handler = {
            "keyword_factories": self._keywords,
            "fake_signatures": self._signatures,
            "missing_public_factory": self._missing_public,
            "stale_epoch_blocks_second": self._stale,
            "optional_drone_ground_only": self._optional_drone,
            "profile_switch_one_owner": self._profile_switch,
            "cleanup_aggregation": self._cleanup,
            "pending_worker_blocks_recreate": self._pending,
            "late_generation_discarded": self._late,
            "active_link_loss": self._link_loss,
            "unknown_status": self._unknown,
            "wrong_boundary_type": self._wrong_type,
            "real_to_fake_substitution": self._real_to_fake,
            "duplicate_owner": self._duplicate,
        }.get(request.name)
        if handler is None:
            return _failed("invalid_input", "unknown adapter case")
        try:
            return await handler()
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail)
        finally:
            clear_claims_for_tests()

    async def _keywords(self) -> FeatureResult:
        bundle = Bundle(self.services.kernel)
        installed = _install_public(bundle)
        try:
            gateway = self._gateway()
            await gateway.build(self._settings(), self._output(), resolver={"source": "public"})
            await gateway.connect("dog")
            await gateway.connect("drone")
            await gateway.connect("reasoner")
            if not _keywords_ok(bundle):
                return _failed(
                    "contract_mismatch",
                    "factory keywords were not mode, config, output_dir",
                )
            if _sdk_loaded():
                return _failed("unavailable", "fake gateway imported a vendor SDK")
            return _ok(tuple(bundle.log), "keywords=mode,config,output_dir", authorized=True)
        finally:
            _remove_modules(installed)

    async def _signatures(self) -> FeatureResult:
        bundle = Bundle(self.services.kernel)
        gateway = self._gateway()
        await gateway.build(self._settings(), self._output(), resolver=bundle.resolver())
        await gateway.connect("dog")
        await gateway.connect("drone")
        await gateway.connect("reasoner")
        ticket, context = self._permit("signatures")
        await gateway.invoke("dog", "prepare", (context,), ticket=ticket, context=context)
        await gateway.status("dog")
        await gateway.invoke(
            "dog",
            "run_route",
            ("room_2", context),
            ticket=ticket,
            context=context,
        )
        await gateway.invoke(
            "dog",
            "capture_frame",
            ("room_2", context),
            ticket=ticket,
            context=context,
        )
        await gateway.invoke("dog", "halt", (), ticket=ticket, context=context)
        await gateway.status("drone")
        request = InspectionRequest("room_2", "room_2_view_v1", "floor")
        await gateway.invoke("drone", "inspect", (request, context), ticket=ticket, context=context)
        await gateway.invoke("drone", "land", (), ticket=ticket, context=context)
        incident = _incident()
        frame = _frame("dog")
        await gateway.invoke(
            "reasoner",
            "assess_incident",
            (incident, context),
            ticket=ticket,
            context=context,
        )
        await gateway.invoke(
            "reasoner",
            "assess_ground_view",
            (incident, frame, context),
            ticket=ticket,
            context=context,
        )
        await gateway.invoke(
            "reasoner",
            "resolve_incident",
            (incident, frame, None, context),
            ticket=ticket,
            context=context,
        )
        resolution = Resolution("confirmed", "target is present", "scripted")
        await gateway.invoke(
            "reasoner",
            "compose_alert",
            (incident, resolution, context),
            ticket=ticket,
            context=context,
        )
        await gateway.close()
        return _ok(tuple(bundle.log), "contract-signatures", authorized=True)

    async def _missing_public(self) -> FeatureResult:
        called = False

        def stub(*, mode: str, config: Mapping[str, object], output_dir: str) -> object:
            del mode, config, output_dir
            nonlocal called
            called = True
            return object()

        gateway = self._gateway()
        try:
            await gateway.build(
                self._settings(),
                self._output(),
                resolver={"source": "public", "dog": stub, "drone": stub, "reasoner": stub},
            )
        except GroundFault as exc:
            if called:
                return _failed("rejected", "public resolution called a private stub")
            if exc.error.detail != MISSING_PUBLIC:
                return _failed(exc.error.code, exc.error.detail)
            return _failed("unavailable", MISSING_PUBLIC)
        return _failed("validation_failed", "missing public factories were accepted")

    async def _stale(self) -> FeatureResult:
        bundle, gateway = await self._built()
        bundle.dog.hold = "dog.run_route"
        self.services.kernel.barriers.arm("dog.run_route")
        ticket, context = self._permit("stale")
        first = asyncio.create_task(
            gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        )
        await _park(bundle.log, "dog.run_route")
        self.services.kernel.authority.latch_cancel("operator halt")
        try:
            await gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        except GroundFault:
            pass
        else:
            return _failed("validation_failed", "stale operation was accepted")
        if bundle.log.count("dog.run_route") != 1:
            return _failed("validation_failed", "a second route call started")
        self.services.kernel.barriers.release("dog.run_route")
        await first
        trace = tuple([*bundle.log, *gateway.events])
        await gateway.close()
        return _ok(trace, "second-operation-blocked", authorized=False)

    async def _optional_drone(self) -> FeatureResult:
        bundle, gateway = await self._built()
        bundle.drone.connect_result = DroneStatus(False, "unknown", None)
        dog = await gateway.connect("dog")
        drone = await gateway.connect("drone")
        await gateway.connect("reasoner")
        if drone.availability != "optional_unavailable" or drone.recovery_required:
            return _failed("validation_failed", drone.detail)
        status = drone.status
        flight = getattr(status, "flight_state", None)
        battery = getattr(status, "battery_percent", "missing")
        if flight != "unknown" or battery is not None:
            return _failed("validation_failed", "optional drone status was rewritten")
        if dog.availability != "available":
            return _failed("validation_failed", "dog was blocked by an optional drone")
        ticket, context = self._permit("ground-only")
        await gateway.invoke(
            "dog",
            "capture_frame",
            ("room_2", context),
            ticket=ticket,
            context=context,
        )
        if "drone.inspect" in bundle.log:
            return _failed("rejected", "optional absence started a flight")
        return _ok(tuple(bundle.log), "optional_unavailable", authorized=True)

    async def _profile_switch(self) -> FeatureResult:
        bundle, gateway = await self._built()
        await gateway.close()
        await gateway.build(
            self._settings("wifi"),
            self._output(),
            resolver=bundle.resolver(),
        )
        if gateway.live_components().count("dog") != 1:
            return _failed("rejected", "profile switch created a second dog owner")
        dog_creates = [item for item in bundle.kwargs if item["component"] == "dog"]
        transports: list[object] = []
        for item in dog_creates:
            config = item["config"]
            if isinstance(config, (str, bytes)) or not isinstance(config, Mapping):
                return _failed("contract_mismatch", "dog config was not a mapping")
            transports.append(config.get("transport"))
        if transports != ["ethernet", "wifi"]:
            return _failed("contract_mismatch", "dog profile config was not switched")
        return _ok(tuple(bundle.log), "one-owner:wifi", authorized=True)

    async def _cleanup(self) -> FeatureResult:
        bundle, gateway = await self._built()
        bundle.dog.route_result = AdapterError("device_error", "boom")
        bundle.dog.close_error = RuntimeError("dog close failed")
        bundle.drone.close_error = RuntimeError("drone close failed")
        ticket, context = self._permit("cleanup")
        try:
            await gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        except GroundFault:
            pass
        try:
            await gateway.close()
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, trace=tuple(bundle.log))
        return _failed("validation_failed", "close hid adapter failures")

    async def _pending(self) -> FeatureResult:
        bundle, gateway = await self._built()
        bundle.dog.hold = "pending-route"
        self.services.kernel.barriers.arm("pending-route")
        ticket, context = self._permit("pending")
        first = asyncio.create_task(
            gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        )
        await _park(bundle.log, "dog.run_route")
        first.cancel()
        try:
            await first
        except asyncio.CancelledError:
            pass
        if not gateway._pending_workers():
            return _failed("validation_failed", "cancelled outer call stopped the worker")
        try:
            await gateway.build(self._settings(), self._output(), resolver=bundle.resolver())
        except GroundFault as exc:
            if exc.error.detail != "pending worker blocks recreation":
                return _failed(exc.error.code, exc.error.detail)
        else:
            return _failed("rejected", "recreation started while a worker was pending")
        gateway.events.append("recreation-blocked")
        trace = tuple([*bundle.log, *gateway.events])
        self.services.kernel.barriers.release("pending-route")
        await _drain(gateway)
        await gateway.close()
        return _ok(
            trace,
            "pending worker blocks recreation",
            authorized=False,
            retained=True,
        )

    async def _late(self) -> FeatureResult:
        bundle, gateway = await self._built()
        bundle.dog.hold = "late-route"
        self.services.kernel.barriers.arm("late-route")
        ticket, context = self._permit("late")
        first = asyncio.create_task(
            gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        )
        await _park(bundle.log, "dog.run_route")
        try:
            await gateway.close()
        except GroundFault:
            pass
        self.services.kernel.barriers.release("late-route")
        try:
            await first
        except GroundFault as exc:
            if exc.error.detail != "stale generation result discarded":
                return _failed(exc.error.code, exc.error.detail)
        else:
            return _failed("validation_failed", "late result was published")
        if gateway.last_invoke is not None:
            return _failed("validation_failed", "late result changed the new session")
        observed = _late_trace(bundle.log, gateway.events)
        before = bundle.log.count("dog.create:ethernet")
        await gateway.build(self._settings(), self._output(), resolver=bundle.resolver())
        if bundle.log.count("dog.create:ethernet") != before + 1:
            return _failed("validation_failed", "quiescent recreate did not build one new dog")
        return _ok(observed, "stale generation result discarded", authorized=False)

    async def _link_loss(self) -> FeatureResult:
        bundle, gateway = await self._built()
        bundle.drone.connect_result = DroneStatus(True, "grounded", 80)
        bundle.drone.status_result = DroneStatus(False, "unknown", None)
        await gateway.connect("drone")
        snapshot = await gateway.status("drone")
        if snapshot.availability != "active_link_loss" or not snapshot.recovery_required:
            return _failed("validation_failed", snapshot.detail)
        status = snapshot.status
        if getattr(status, "flight_state", None) != "unknown":
            return _failed("validation_failed", "link loss rewrote flight state")
        if getattr(status, "battery_percent", "missing") is not None:
            return _failed("validation_failed", "link loss invented a battery reading")
        return _ok(tuple(bundle.log), "active_link_loss", authorized=True)

    async def _unknown(self) -> FeatureResult:
        bundle, gateway = await self._built()
        bundle.dog.connect_result = DogStatus(True, None, None, None)
        snapshot = await gateway.connect("dog")
        status = snapshot.status
        if snapshot.availability != "unknown":
            return _failed("validation_failed", snapshot.detail)
        if not isinstance(status, DogStatus):
            return _failed("contract_mismatch", "unknown dog status changed type")
        if status.standing is not None or status.stationary is not None:
            return _failed("validation_failed", "unknown posture was defaulted")
        if status.avoidance_enabled is not None or status.connected is not True:
            return _failed("validation_failed", "unknown avoidance or connection was defaulted")
        if snapshot.device_sample_time is not None:
            return _failed("validation_failed", "gateway invented a device sample time")
        return _ok(tuple(bundle.log), "unknown", authorized=True)

    async def _wrong_type(self) -> FeatureResult:
        bundle = Bundle(self.services.kernel)
        resolver = bundle.resolver()
        resolver["dog"] = _bad_dog_factory
        gateway = self._gateway()
        await gateway.build(self._settings(), self._output(), resolver=resolver)
        try:
            await gateway.connect("dog")
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail)
        return _failed("validation_failed", "wrong dog status was accepted")

    async def _real_to_fake(self) -> FeatureResult:
        bundle = Bundle(self.services.kernel)
        gateway = self._gateway()
        await gateway.build(
            self._settings(modes={"dog": "real", "drone": "fake", "grok": "fake"}),
            self._output(),
            resolver=bundle.resolver(),
        )
        return _failed("validation_failed", "real mode accepted a private stub")

    async def _duplicate(self) -> FeatureResult:
        _bundle, gateway = await self._built()
        await gateway.build(self._settings(), self._output(), resolver=_bundle.resolver())
        return _failed("validation_failed", "a second dog connection was accepted")

    def _gateway(self) -> AdapterGateway:
        created = create(self.services.kernel, service_ports(self.services))
        if not isinstance(created, AdapterGateway):
            raise fault("internal", "adapter factory did not return the gateway")
        return created

    async def _built(self) -> tuple[Bundle, AdapterGateway]:
        bundle = Bundle(self.services.kernel)
        gateway = self._gateway()
        await gateway.build(self._settings(), self._output(), resolver=bundle.resolver())
        return bundle, gateway

    def _settings(
        self,
        transport: str = "ethernet",
        modes: Mapping[str, str] | None = None,
    ) -> GroundSettings:
        return make_settings(
            dog_transport=transport,
            profile_identity=f"dog.{transport}",
            modes=modes,
            adapter_configs={
                "dog": {"transport": transport, "profile": f"dog.{transport}"},
                "drone": {},
                "grok": {},
            },
        )

    def _output(self) -> Path:
        devices = getattr(self.services.adapters, "devices", None)
        output = getattr(devices, "output_dir", None)
        if not isinstance(output, Path):
            raise fault("internal", "simulation output directory is missing")
        return output

    def _permit(self, stage: str) -> tuple[Ticket, RunContext]:
        ticket = self.services.kernel.authority.issue(stage, stage)
        context = context_for_stage(
            stage,
            self.services.kernel.clock.monotonic() + 100,
            30,
            self.services.kernel.authority.cancel_event,
            self.services.kernel.clock,
            real_adapter=False,
        )
        return ticket, context


def create(
    kernel: KernelContext | BaseServices,
    peers: ServicePorts | None = None,
) -> AdapterGateway | GatewayHarness:
    if isinstance(kernel, BaseServices):
        if peers is not None:
            raise fault("invalid_input", "simulation create accepts services only")
        return GatewayHarness(kernel)
    if not isinstance(kernel, KernelContext):
        raise fault("invalid_input", "kernel must be a KernelContext")
    if peers is None:
        raise fault("invalid_input", "peers are required")
    return AdapterGateway(kernel, peers)


class _BadDog:
    async def connect(self) -> object:
        return {"connected": True}

    async def prepare(self, ctx: object) -> object:
        del ctx
        return {}

    async def get_status(self) -> object:
        return {}

    async def run_route(self, zone: object, ctx: object) -> object:
        del zone, ctx
        return {}

    async def capture_frame(self, zone: object, ctx: object) -> object:
        del zone, ctx
        return {}

    async def halt(self) -> None:
        return None

    async def close(self) -> None:
        return None


def _bad_dog_factory(*, mode: str, config: Mapping[str, object], output_dir: str) -> _BadDog:
    del mode, config, output_dir
    return _BadDog()


def _install_public(bundle: Bundle) -> dict[str, types.ModuleType]:
    resolver = bundle.resolver()
    installed: dict[str, types.ModuleType] = {}
    for component, (module_name, attr) in _PUBLIC.items():
        module = types.ModuleType(module_name)
        setattr(module, attr, resolver[component])
        sys.modules[module_name] = module
        installed[module_name] = module
    return installed


def _remove_modules(installed: Mapping[str, types.ModuleType]) -> None:
    for name in installed:
        sys.modules.pop(name, None)


def _keywords_ok(bundle: Bundle) -> bool:
    if len(bundle.kwargs) != 3:
        return False
    for item in bundle.kwargs:
        if set(item) != {"component", "mode", "config", "output_dir"}:
            return False
        if item["mode"] != "fake":
            return False
        output = item["output_dir"]
        if not isinstance(output, str) or not Path(output).is_absolute():
            return False
    return True


def _sdk_loaded() -> bool:
    banned = ("djitellopy", "unitree_webrtc_connect", "go2_webrtc_connect", "xai_sdk")
    for name in sys.modules:
        if name in banned or name.startswith(tuple(item + "." for item in banned)):
            return True
    return False


def _incident() -> Incident:
    target = "a person or an object left in a marked closed area"
    return Incident("sim-ground", "room_2", target, _frame("phone"))


def _frame(source: str) -> Frame:
    if source == "phone":
        return Frame("C:/sim/phone.jpg", "phone", "room_2", None, True)
    return Frame("C:/sim/dog.jpg", "dog", "room_2", None, True)


def _late_trace(log: list[str], events: list[str]) -> tuple[str, ...]:
    return tuple([*log, *events])


def _ok(
    trace: tuple[str, ...],
    detail: str,
    *,
    authorized: bool,
    retained: bool = False,
) -> FeatureResult:
    payload: dict[str, object] = {
        "live_call_count": 0,
        "device_calls": 0,
        "simulated": True,
        "slot": "base.adapters",
        "schema_version": SCHEMA_VERSION,
        "authorized": authorized,
        "detail": detail,
        "trace": trace,
    }
    if retained:
        payload["retained"] = True
    return FeatureResult("ok", freeze_map(payload), (), None)


def _failed(code: str, detail: str, **extra: object) -> FeatureResult:
    recovery = code in {
        "cancelled",
        "expired_deadline",
        "timeout",
        "recovery_required",
        "stale_ticket",
        "epoch_mismatch",
        "rejected",
    }
    payload: dict[str, object] = {"device_calls": 0, "detail": detail, **extra}
    return FeatureResult(
        "failed",
        freeze_map(payload),
        (),
        GroundError(code, detail, recovery),
    )


async def _park(log: list[str], marker: str) -> None:
    for _ in range(30):
        await asyncio.sleep(0)
        if marker in log:
            return
    raise fault("internal", f"{marker} did not start")


async def _drain(gateway: AdapterGateway) -> None:
    pending = [task for task in gateway._workers if not task.done()]
    if pending:
        await asyncio.wait(pending)
