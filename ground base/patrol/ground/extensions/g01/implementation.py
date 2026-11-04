"""Foundation provider. It checks composition and seeded doubles; it does not fly."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path

from PIL import Image

from patrol.contract import Frame
from patrol.ground.kernel.catalog import SCHEMA_VERSION, SLOT_BY_NAME
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
)
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.loader import discover, load_callable
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.devices import DeviceBundle


class FoundationFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        handlers = {
            "synthetic_slot": self._synthetic,
            "happy_devices": self._happy,
            "duplicate_slot": self._duplicate,
            "missing_provider": self._missing,
            "schema_mismatch": self._schema,
            "path_escape": self._escape,
            "forbidden_command": self._command,
            "cancel_barrier": self._cancel,
            "manual_deadline": self._deadline,
            "responsiveness": self._responsive,
            "fixture_io_fault": self._io,
            "teardown_release": self._teardown,
        }
        handler = handlers.get(request.name)
        if handler is None:
            return _failed("invalid_input", "unknown foundation case")
        try:
            return await handler()
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, device_calls=self._device_calls())


    async def _synthetic(self) -> FeatureResult:
        root = Path(tempfile.mkdtemp(prefix="ground-g01-"))
        self.cleanup_paths = (str(root),)
        try:
            _write_extension(root, "23", "feature.status", SCHEMA_VERSION)
            found = discover(root, only_task="23")
            manifest = found[0]
            if manifest.slot != SLOT_BY_NAME["feature.status"].slot:
                return _failed("contract_mismatch", "synthetic slot drifted")
            if manifest.schema_version != SCHEMA_VERSION:
                return _failed("schema_mismatch", "synthetic schema drifted")
            load_callable(manifest, "factory")
            return _ok(
                slot=manifest.slot,
                schema_version=manifest.schema_version,
                device_calls=self._device_calls(),
                live_call_count=self._live(),
                cleanup=(str(root),),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    async def _happy(self) -> FeatureResult:
        devices = self._bundle()
        settings = make_settings()
        await self.services.adapters.build(settings, devices.output_dir, resolver={})
        await self.services.adapters.connect("dog")
        ticket = self.services.kernel.authority.issue("happy", "capture")
        clock = self.services.kernel.clock
        context = context_for_stage(
            "happy",
            clock.monotonic() + 10,
            5,
            self.services.kernel.authority.cancel_event,
            clock,
            real_adapter=False,
        )
        frame = await self.services.adapters.invoke(
            "dog",
            "capture_frame",
            ("room_2", context),
            ticket=ticket,
            context=context,
        )
        if not isinstance(frame, Frame) or frame.simulated is not True:
            return _failed("validation_failed", "capture was not a simulated frame")
        with Image.open(frame.path) as image:
            image.load()
        calls = self._bundle().calls
        return _ok(
            live_call_count=self._live(),
            simulated=True,
            trace=tuple(calls),
            device_calls=len(calls),
            slot="kernel.foundation",
            schema_version=SCHEMA_VERSION,
        )

    async def _duplicate(self) -> FeatureResult:
        def action(root: Path) -> None:
            _write_extension(root, "23", "feature.status", SCHEMA_VERSION)
            _write_extension(root, "24", "feature.status", SCHEMA_VERSION)
            discover(root)

        return self._expect_reject(action)

    async def _schema(self) -> FeatureResult:
        def action(root: Path) -> None:
            _write_extension(root, "23", "feature.status", "ground-task-v0")
            discover(root, only_task="23")

        return self._expect_reject(action)

    async def _escape(self) -> FeatureResult:
        def action(root: Path) -> None:
            _write_extension(
                root,
                "23",
                "feature.status",
                SCHEMA_VERSION,
                factory="patrol.ground.extensions.g99.implementation:create",
            )
            discover(root, only_task="23")

        return self._expect_reject(action)

    async def _command(self) -> FeatureResult:
        def action(root: Path) -> None:
            _write_extension(
                root,
                "23",
                "feature.status",
                SCHEMA_VERSION,
                extra={"command": "cmd.exe /c echo no"},
            )
            discover(root, only_task="23")

        return self._expect_reject(action)

    async def _missing(self) -> FeatureResult:
        try:
            self.services.kernel.features.get("feature.dispatch")
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, device_calls=self._device_calls())
        return _failed("validation_failed", "missing provider was treated as present")

    async def _cancel(self) -> FeatureResult:
        authority = self.services.kernel.authority
        barriers = self.services.kernel.barriers
        barriers.arm("hold")
        ticket = authority.issue("mission", "held")
        authorized = {"value": True}

        async def operation() -> None:
            await barriers.wait("hold")
            try:
                authority.require_current(ticket)
            except GroundFault:
                authorized["value"] = False
                return
            authorized["value"] = True

        task = asyncio.create_task(operation(), name="held-operation")
        self.services.kernel.tasks.retain("held-operation", task)
        await _park(self.services, "held-operation")
        authority.latch_cancel("operator halt")
        barriers.release("hold")
        await self.services.kernel.tasks.collect(deadline=2)
        issued = True
        try:
            authority.issue("mission", "next")
        except GroundFault:
            issued = False
        return _ok(
            authorized=bool(authorized["value"] or issued),
            device_calls=self._device_calls(),
            detail="cancelled ticket cannot authorize another action",
        )

    async def _deadline(self) -> FeatureResult:
        clock = self.services.kernel.clock
        if not isinstance(clock, ManualClock):
            return _failed("invalid_input", "deadline case requires the manual clock")
        authority = self.services.kernel.authority
        ticket = authority.issue("mission", "deadline")
        deadline = clock.monotonic() + 5
        trace = ["issued"]
        authority.require_action(ticket, deadline_monotonic=deadline, clock=clock)
        trace.append("before_deadline")
        clock.advance(5)
        try:
            authority.require_action(ticket, deadline_monotonic=deadline, clock=clock)
            trace.append("accepted_late")
        except GroundFault as exc:
            trace.append(exc.error.code)
        return _ok(trace=tuple(trace), device_calls=self._device_calls(), detail="deadline order")

    async def _responsive(self) -> FeatureResult:
        seen = asyncio.Event()

        async def watch() -> None:
            while not self.services.kernel.authority.cancelled:
                await asyncio.sleep(0.01)
            seen.set()

        task = asyncio.create_task(watch(), name="halt-watch")
        self.services.kernel.tasks.retain("halt-watch", task)
        await asyncio.sleep(0.02)
        started = time.monotonic()
        self.services.kernel.authority.latch_cancel("operator halt")
        await asyncio.wait_for(seen.wait(), timeout=0.5)
        elapsed = time.monotonic() - started
        return _ok(
            within_limit=elapsed < 0.5,
            measurement_clock="real",
            device_calls=self._device_calls(),
            detail="halt latch observed on the real clock",
        )

    async def _io(self) -> FeatureResult:
        fixture = repo_root() / "fixtures" / "ground" / "g01" / "sample.json"
        self.services.kernel.io.fail_next("read", "injected fixture read failure")
        try:
            self.services.kernel.io.read_text(fixture)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, device_calls=self._device_calls())
        return _failed("validation_failed", "io fault was skipped")

    async def _teardown(self) -> FeatureResult:
        flag = {"released": False, "cancelled": False}
        self.observations["released"] = flag
        barriers = self.services.kernel.barriers
        barriers.arm("stuck")

        async def worker() -> None:
            try:
                await barriers.wait("stuck")
                flag["released"] = True
            except asyncio.CancelledError:
                flag["cancelled"] = True
                raise

        task = asyncio.create_task(worker(), name="stuck-worker")
        self.services.kernel.tasks.retain("stuck-worker", task)
        await _park(self.services, "stuck-worker")
        return _ok(retained=True, device_calls=self._device_calls(), detail="worker held")

    def _expect_reject(self, action: object) -> FeatureResult:
        root = Path(tempfile.mkdtemp(prefix="ground-g01-"))
        self.cleanup_paths = (str(root),)
        try:
            if not callable(action):
                return _failed("internal", "composition action is not callable")
            try:
                action(root)
            except GroundFault as exc:
                return _failed(exc.error.code, exc.error.detail, device_calls=self._device_calls())
            return _failed("validation_failed", "invalid composition was accepted")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _bundle(self) -> DeviceBundle:
        devices = getattr(self.services.adapters, "devices", None)
        if not isinstance(devices, DeviceBundle):
            raise GroundFault(GroundError("internal", "device doubles are not installed", True))
        return devices

    def _device_calls(self) -> int:
        try:
            return len(self._bundle().calls)
        except GroundFault:
            return 0

    def _live(self) -> int:
        try:
            return self._bundle().live_call_count
        except GroundFault:
            return 0


def create(services: BaseServices) -> FoundationFeature:
    return FoundationFeature(services)


def _ok(**data: object) -> FeatureResult:
    return FeatureResult("ok", freeze_map(data), (), None)


def _failed(code: str, detail: str, **extra: object) -> FeatureResult:
    payload = {"device_calls": extra.pop("device_calls", 0), "detail": detail, **extra}
    recovery = code in {
        "cancelled",
        "expired_deadline",
        "io_fault",
        "missing_provider",
        "timeout",
    }
    return FeatureResult(
        "failed",
        freeze_map(payload),
        (),
        GroundError(code, detail, recovery),
    )


def _write_extension(
    root: Path,
    number: str,
    slot: str,
    schema: str,
    *,
    factory: str | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    directory = root / f"g{number}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "implementation.py").write_text(
        "def create(services):\n    return services\n",
        encoding="utf-8",
    )
    (directory / "scenarios.py").write_text(
        "def cases(seed=0):\n    return ()\n",
        encoding="utf-8",
    )
    body: dict[str, object] = {
        "schema_version": schema,
        "task_id": f"GROUND-{number}",
        "slot": slot,
        "factory": factory or f"patrol.ground.extensions.g{number}.implementation:create",
        "scenario_factory": f"patrol.ground.extensions.g{number}.scenarios:cases",
    }
    if extra:
        body.update(extra)
    (directory / "manifest.json").write_text(json.dumps(body), encoding="utf-8")


async def _park(services: BaseServices, name: str) -> None:
    for _ in range(5):
        await asyncio.sleep(0)
        if name in services.kernel.tasks.pending():
            return
    raise GroundFault(GroundError("internal", "worker did not park", True))
