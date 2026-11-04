"""Test-only service doubles. Constructors do not call peers or devices."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

from prompt_toolkit.input import DummyInput

from patrol.contract import AdapterError, Frame, Incident, RunContext, Zone
from patrol.ground.kernel.catalog import EVENT_KINDS, PHASES, ZONES
from patrol.ground.kernel.commands import parse_command
from patrol.ground.kernel.contracts import (
    AdmissionResult,
    CaptureInterval,
    Command,
    ConfirmationResult,
    EventRecord,
    EvidenceResult,
    GroundError,
    GroundEvent,
    GroundSettings,
    IncidentInput,
    KernelContext,
    MissionHandle,
    OperationResult,
    SafetyHandle,
    SafetySnapshot,
    SessionSnapshot,
    Ticket,
    WaitSpec,
)
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.settings import make_settings, redact
from patrol.ground.kernel.snapshots import idle_snapshot
from patrol.ground.kernel.validation import freeze_map, require_bool
from patrol.ground.testing.devices import DeviceBundle

_PROMPT_PROBE = DummyInput()


class ConfigDouble:
    def __init__(self, kernel: KernelContext) -> None:
        self.kernel = kernel
        self.trace: list[str] = []

    def load(
        self,
        path: str | Path | None,
        *,
        modes: Mapping[str, str],
        scenario: str | None,
    ) -> GroundSettings:
        self.trace.append("config.load")
        if path is not None:
            self.kernel.io.read_text(Path(path))
        return make_settings(modes=dict(modes), scenario=scenario or "blocked_resolved")

    def redacted(self, settings: GroundSettings) -> Mapping[str, object]:
        self.trace.append("config.redacted")
        view = redact(settings)
        if "adapter_configs" in settings.adapter_configs:
            secret = settings.adapter_configs["adapter_configs"]
            if isinstance(secret, Mapping) and "token" in secret:
                text = str(view)
                if str(secret["token"]) in text:
                    raise fault("validation_failed", "redacted view leaked a secret")
        return view


class StateDouble:
    def __init__(self, kernel: KernelContext) -> None:
        self.kernel = kernel
        self.trace: list[str] = []
        self._snapshot: SessionSnapshot | None = None

    def open(self, incident: Incident, settings: GroundSettings) -> SessionSnapshot:
        self.trace.append("state.open")
        if self._snapshot is not None and self._snapshot.phase not in {"IDLE", "DONE", "ABORTED"}:
            raise fault("rejected", "a mission is already open")
        self._snapshot = idle_snapshot(
            epoch=self.kernel.authority.epoch,
            modes=settings.modes,
            dog_transport=settings.dog_transport,
            incident=incident,
            phase="ASSESS",
        )
        return self._snapshot

    def apply(self, event: GroundEvent, *, expected_ticket: Ticket) -> SessionSnapshot:
        self.trace.append("state.apply")
        self.kernel.authority.require_current(expected_ticket)
        if event.kind not in EVENT_KINDS:
            raise fault("validation_failed", "event kind is not allowed")
        if event.ticket is not None and event.ticket != expected_ticket:
            raise fault("stale_ticket", "event ticket does not match the stage")
        if self._snapshot is None:
            raise fault("not_admitted", "no session is open")
        phase = self._snapshot.phase
        if event.kind == "state_changed":
            requested = event.payload.get("phase")
            if requested not in PHASES or not isinstance(requested, str):
                raise fault("invalid_input", "unknown phase")
            if self._snapshot.recovery_required and requested == "DONE":
                raise fault("unsafe_state", "recovery lock blocks DONE", recovery_required=True)
            phase = requested
        self._snapshot = replace(
            self._snapshot,
            phase=phase,
            epoch=self.kernel.authority.epoch,
            recovery_required=self._snapshot.recovery_required or event.kind == "recovery_required",
            halt_latched=self._snapshot.halt_latched
            or event.kind == "halt_requested"
            or self.kernel.authority.cancelled,
        )
        return self._snapshot

    def snapshot(self) -> SessionSnapshot:
        self.trace.append("state.snapshot")
        if self._snapshot is None:
            raise fault("not_admitted", "no session is open")
        return self._snapshot


class JournalDouble:
    def __init__(self, kernel: KernelContext) -> None:
        self.kernel = kernel
        self.records: list[EventRecord] = []
        self.published: Mapping[str, object] | None = None
        self.closed = False

    async def open(self, run_id: str, output_root: str | Path) -> None:
        del run_id, output_root

    def emit(self, record: EventRecord) -> None:
        if record.event not in EVENT_KINDS:
            raise fault("validation_failed", "event name is not allowed")
        self.records.append(record)

    async def flush(self) -> None:
        return None

    async def publish(self, summary: Mapping[str, object]) -> None:
        self.published = dict(summary)

    async def scan(self, output_root: str | Path) -> tuple[Mapping[str, object], ...]:
        root = Path(output_root)
        if not root.exists():
            return ()
        return tuple({"path": str(path)} for path in sorted(root.glob("*/summary.json")))

    async def close(self) -> None:
        self.closed = True


class ExecutorDouble:
    def __init__(self, kernel: KernelContext) -> None:
        self.kernel = kernel
        self.trace: list[str] = []
        self._names: list[tuple[str, asyncio.Task[object]]] = []

    async def run(
        self,
        name: str,
        ticket: Ticket,
        factory: object,
        *,
        limit_s: float,
    ) -> OperationResult:
        self.trace.append(f"executor.run:{name}")
        started = self.kernel.clock.monotonic()
        started_utc = self.kernel.clock.utc_now().isoformat()
        try:
            self.kernel.authority.require_action(
                ticket,
                deadline_monotonic=started + float(limit_s),
                clock=self.kernel.clock,
            )
        except GroundFault as exc:
            return self._finish(name, ticket, exc.error.code, None, exc.error, started, started_utc)
        if not callable(factory):
            raise fault("invalid_input", "operation factory must be callable")
        context = context_for_stage(
            ticket.mission_id,
            started + float(limit_s),
            float(limit_s),
            self.kernel.authority.cancel_event,
            self.kernel.clock,
            real_adapter=False,
        )

        async def work() -> object:
            return await factory(context)

        task = asyncio.create_task(work(), name=name)
        self.kernel.tasks.retain(name, task)
        self._names.append((name, task))
        try:
            value = await task
        except AdapterError as exc:
            error = GroundError("unavailable", exc.detail, True)
            return self._finish(name, ticket, "failed", None, error, started, started_utc)
        except GroundFault as exc:
            return self._finish(name, ticket, exc.error.code, None, exc.error, started, started_utc)
        try:
            self.kernel.authority.require_action(
                ticket,
                deadline_monotonic=context.deadline_monotonic,
                clock=self.kernel.clock,
            )
        except GroundFault as exc:
            return self._finish(
                name,
                ticket,
                exc.error.code,
                value,
                exc.error,
                started,
                started_utc,
            )
        return self._finish(name, ticket, "completed", value, None, started, started_utc)

    def pending(self) -> tuple[str, ...]:
        return tuple(name for name, task in self._names if not task.done())

    async def collect(self, *, deadline: float) -> None:
        await self.kernel.tasks.collect(deadline=deadline)

    def _finish(
        self,
        name: str,
        ticket: Ticket,
        code: str,
        value: object,
        error: GroundError | None,
        started: float,
        started_utc: str,
    ) -> OperationResult:
        status = {
            "cancelled": "cancelled",
            "expired_deadline": "timeout",
            "timeout": "timeout",
            "completed": "completed",
        }.get(code, "failed")
        if code == "completed":
            error = None
        elif error is None:
            error_code = code if code in {"cancelled", "timeout"} else "unavailable"
            error = GroundError(error_code, code, True)
        ended = self.kernel.clock.utc_now().isoformat()
        return OperationResult(
            operation=name,
            ticket=ticket,
            status=status,
            value=value,
            error=error,
            pending=False,
            started_utc=started_utc,
            ended_utc=ended,
            started_monotonic=started,
            ended_monotonic=self.kernel.clock.monotonic(),
        )


class EvidenceDouble:
    def __init__(self, kernel: KernelContext) -> None:
        self.kernel = kernel
        self.trace: list[str] = []

    async def validate(
        self,
        frame: Frame,
        *,
        expected_source: str,
        zone: str,
        mode: str,
        output_root: str | Path,
        interval: CaptureInterval,
    ) -> EvidenceResult:
        del interval
        self.trace.append("evidence.validate")
        if not isinstance(frame, Frame):
            return EvidenceResult(False, "type", None, freeze_map({}))
        if frame.source != expected_source or frame.zone != zone:
            return EvidenceResult(False, "metadata", None, freeze_map({}))
        if mode == "real" and frame.simulated:
            return EvidenceResult(False, "simulated", None, freeze_map({}))
        if mode == "fake" and frame.simulated is not True:
            return EvidenceResult(False, "simulation-flag", None, freeze_map({}))
        path = Path(frame.path).resolve()
        try:
            path.relative_to(Path(output_root).resolve())
        except ValueError:
            return EvidenceResult(False, "path", None, freeze_map({}))
        try:
            data = self.kernel.io.read_bytes(path, limit=2_000_000)
        except GroundFault as exc:
            return EvidenceResult(False, exc.error.code, None, freeze_map({}))
        if not data.startswith(b"\xff\xd8"):
            return EvidenceResult(False, "jpeg", None, freeze_map({}))
        return EvidenceResult(True, "ok", frame, freeze_map({"bytes": len(data)}))


class ConsoleDouble:
    def __init__(self, kernel: KernelContext) -> None:
        self.kernel = kernel
        self.messages: list[str] = []
        self._script: list[Command] = []
        self._input = _PROMPT_PROBE

    def push(self, text: str) -> None:
        self._script.append(parse_command(text))

    def parse(self, text: str) -> Command:
        return parse_command(text)

    async def commands(self) -> AsyncIterator[Command]:
        for command in self._script:
            yield command

    async def confirm(self, wait_spec: WaitSpec) -> ConfirmationResult:
        if self.kernel.authority.cancelled:
            return ConfirmationResult(False, None, wait_spec.zone, "cancelled")
        return ConfirmationResult(True, "simulated", wait_spec.zone, "simulated")

    def write(self, message: str) -> None:
        self.messages.append(message)

    async def close(self) -> None:
        self.messages.append("closed")


class AdapterDouble:
    def __init__(self, kernel: KernelContext, devices: DeviceBundle) -> None:
        self.kernel = kernel
        self.devices = devices

    async def build(
        self,
        settings: GroundSettings,
        output_root: str | Path,
        *,
        resolver: Mapping[str, object],
    ) -> None:
        del settings, output_root
        if isinstance(resolver, (str, bytes)) or not isinstance(resolver, Mapping):
            raise fault("invalid_input", "resolver must be a mapping")
        self.devices.note("adapters.build")

    async def connect(self, component: str) -> object:
        self.devices.note(f"adapters.connect:{component}")
        if component == "dog":
            return await self.devices.dog.connect()
        if component == "drone":
            return await self.devices.drone.connect()
        raise fault("invalid_input", "component has no connect method")

    async def status(self, component: str) -> object:
        self.devices.note(f"adapters.status:{component}")
        if component == "dog":
            return await self.devices.dog.get_status()
        if component == "drone":
            return await self.devices.drone.get_status()
        raise fault("invalid_input", "component has no status method")

    async def invoke(
        self,
        component: str,
        method: str,
        args: tuple[object, ...],
        *,
        ticket: Ticket,
        context: RunContext,
    ) -> object:
        self.kernel.authority.require_current(ticket)
        if context.cancel.is_set():
            raise fault("cancelled", "operation context is cancelled", recovery_required=True)
        self.devices.note(f"adapters.invoke:{component}.{method}")
        target = self.devices.component(component)
        action = getattr(target, method)
        return await action(*args)

    async def close(self) -> None:
        await self.devices.dog.close()
        await self.devices.drone.close()
        await self.devices.reasoner.close()


class WorkflowDouble:
    def __init__(self, kernel: KernelContext) -> None:
        self.kernel = kernel
        self.trace: list[str] = []
        self._handle: MissionHandle | None = None

    async def load(self, raw: IncidentInput) -> AdmissionResult:
        self.trace.append("workflow.load")
        if raw.zone not in ZONES or not raw.target or not raw.image_path:
            return AdmissionResult(
                False,
                None,
                GroundError("invalid_input", "input was rejected", False),
            )
        try:
            require_bool(raw.simulated, label="simulated")
        except GroundFault as exc:
            return AdmissionResult(False, None, exc.error)
        zone = raw.zone
        if zone not in {"entrance", "room_2", "display"}:
            return AdmissionResult(False, None, GroundError("invalid_input", "zone", False))
        trusted_zone = cast(Zone, zone)
        frame = Frame(raw.image_path, "phone", trusted_zone, raw.captured_at, raw.simulated)
        incident = Incident(f"sim-{self.kernel.seed}", trusted_zone, raw.target, frame)
        return AdmissionResult(True, incident, None)

    def start(self, incident: Incident) -> MissionHandle:
        if self._handle is not None:
            raise fault("rejected", "a mission is already active")
        ticket = self.kernel.authority.issue(incident.mission_id, "start")
        self._handle = MissionHandle(incident.mission_id, ticket)
        self.trace.append("workflow.start")
        return self._handle

    def snapshot(self) -> SessionSnapshot:
        return idle_snapshot(
            epoch=self.kernel.authority.epoch,
            modes={"dog": "fake", "drone": "fake", "grok": "fake"},
            dog_transport="ethernet",
        )

    async def join(self, handle: MissionHandle) -> None:
        self.kernel.authority.require_current(handle.ticket)
        self.trace.append("workflow.join")


class SafetyDouble:
    def __init__(self, kernel: KernelContext) -> None:
        self.kernel = kernel
        self.trace: list[str] = []

    def request(self, reason: str, ticket: Ticket) -> SafetyHandle:
        self.kernel.authority.latch_cancel(reason)
        self.trace.append("safety.request")
        return SafetyHandle(ticket, reason, self.kernel.authority.epoch)

    async def observe(self, handle: SafetyHandle, *, deadline: float) -> SafetySnapshot:
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or deadline <= 0:
            raise fault("invalid_input", "observe deadline must be positive")
        return SafetySnapshot(
            halted=self.kernel.authority.cancelled,
            recovery_required=True,
            pending=bool(self.kernel.tasks.pending()),
            detail=handle.reason,
        )

    async def reset(self, recovery: Mapping[str, object]) -> None:
        verified = recovery.get("verified")
        if verified is not True:
            raise fault("invalid_input", "recovery must set verified to true")
        if self.kernel.tasks.pending():
            raise fault("unsafe_state", "a worker is still pending", recovery_required=True)
        self.kernel.authority.reset_generation("operator recovery")
        self.trace.append("safety.reset")

    async def shutdown(self, reason: str) -> None:
        self.kernel.authority.latch_cancel(reason)
        self.trace.append("safety.shutdown")
