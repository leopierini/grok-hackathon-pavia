"""Compose the ten base services so one mission can run through all of them.

Device doubles stand in for the robot packages. They do not replace config,
state, the journal, the executor, evidence, the console, adapters, workflow,
or safety.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from patrol.contract import Frame, Incident
from patrol.ground.extensions.g02.implementation import ConfigService
from patrol.ground.extensions.g03.store import SessionStore
from patrol.ground.extensions.g04.implementation import Journal, JournalLimits
from patrol.ground.extensions.g05.implementation import OperationExecutor
from patrol.ground.extensions.g06.implementation import EvidenceValidator
from patrol.ground.extensions.g06.io import RealIO
from patrol.ground.extensions.g06.model import CaptureInterval as EvidenceInterval
from patrol.ground.extensions.g06.model import EvidenceLimits
from patrol.ground.extensions.g06.model import EvidenceResult as EvidenceReport
from patrol.ground.extensions.g06.model import KernelContext as EvidenceContext
from patrol.ground.extensions.g06.model import ServicePorts as EvidencePeers
from patrol.ground.extensions.g07.implementation import ConsoleService
from patrol.ground.extensions.g08.gateway import AdapterGateway, clear_claims_for_tests
from patrol.ground.extensions.g09.implementation import Workflow
from patrol.ground.extensions.g10.implementation import SafetyService
from patrol.ground.kernel.build import build_kernel
from patrol.ground.kernel.contracts import (
    AdapterPort,
    BaseServices,
    CaptureInterval,
    ConfigPort,
    ConsolePort,
    EventRecord,
    EvidencePort,
    EvidenceResult,
    ExecutorPort,
    GroundEvent,
    GroundSettings,
    JournalPort,
    SafetyPort,
    ServicePorts,
    SessionSnapshot,
    StatePort,
    Ticket,
    WorkflowPort,
)
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.devices import DeviceBundle

_TERMINAL = frozenset({"DONE", "FAULT", "ABORTED", "REPORT"})
_SCAN_SKIP = frozenset({"", "live", "dog", "drone", "grok"})
_FRAME_TIME = "2026-01-01T00:00:00+00:00"


class SessionLink:
    """Turn workflow phase commits into the session store's legal events."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._seq = 0

    def open(self, incident: Incident, settings: GroundSettings) -> SessionSnapshot:
        self._seq = 0
        return self._store.open(incident, settings)

    def snapshot(self) -> SessionSnapshot:
        return self._store.snapshot()

    def apply(self, event: GroundEvent, *, expected_ticket: Ticket) -> SessionSnapshot:
        if event.kind == "state_changed":
            return self._walk(event, expected_ticket)
        if event.kind == "recovery_required":
            return self._send("recovery_required", event.ticket, {}, expected_ticket)
        body = dict(event.payload)
        ticket = event.ticket if event.ticket is not None else expected_ticket
        return self._send(event.kind, ticket, body, expected_ticket)

    def _walk(self, event: GroundEvent, expected: Ticket) -> SessionSnapshot:
        target = event.payload.get("phase")
        if not isinstance(target, str) or not target:
            raise fault("invalid_input", "phase commit is missing its phase")
        outcome = event.payload.get("outcome")
        if not isinstance(outcome, str):
            outcome = ""
        current = self._store.snapshot()
        if current.phase == target:
            return current
        for _ in range(24):
            current = self._store.snapshot()
            if current.phase == target:
                return current
            step = _step(current, target, outcome)
            if step is None:
                raise fault("rejected", f"no session step from {current.phase} to {target}")
            kind, body = step
            before = _mark(current)
            current = self._send(kind, event.ticket, body, expected)
            after = _mark(current)
            if after == before:
                raise fault("rejected", f"session step {kind} did not advance {current.phase}")
        raise fault("rejected", f"session walk to {target} did not finish")

    def _send(
        self,
        kind: str,
        ticket: Ticket | None,
        body: Mapping[str, object],
        expected: Ticket,
    ) -> SessionSnapshot:
        self._seq += 1
        payload = dict(body)
        payload["event_id"] = f"{kind}-{self._seq}"
        payload["sequence"] = self._seq
        sent = GroundEvent(kind, ticket, freeze_map(payload))
        return self._store.apply(sent, expected_ticket=expected)


class ProtocolJournal:
    """JournalPort over the GROUND-04 journal."""

    def __init__(self, journal: Journal, modes: Mapping[str, str] | None = None) -> None:
        self._journal = journal
        self._modes = dict(modes or {})

    async def open(self, run_id: str, output_root: str | Path) -> None:
        result = await self._journal.open(run_id, Path(output_root))
        if not result.ok:
            raise fault("unavailable", result.detail or "journal did not open")

    def emit(self, record: EventRecord) -> None:
        if not isinstance(record, EventRecord):
            return
        mission = record.mission_id if isinstance(record.mission_id, str) else ""
        state = record.state if isinstance(record.state, str) else ""
        if not mission or not state:
            return
        data = _plain(record.data)
        if not isinstance(data, dict):
            return
        body: dict[str, object] = {
            "mission_id": mission,
            "state": state,
            "event": record.event,
            "modes": {**self._modes, **record.modes},
            "data": data,
            "timestamp_utc": record.timestamp_utc,
            "elapsed_s": record.elapsed_s,
        }
        if record.ticket is not None:
            body["ticket"] = {
                "mission_id": record.ticket.mission_id,
                "epoch": record.ticket.epoch,
                "stage_id": record.ticket.stage_id,
            }
        if isinstance(record.zone, str):
            body["zone"] = record.zone
        if isinstance(record.target, str) and record.target:
            body["target"] = record.target[:80]
        result = self._journal.emit(body)
        if not result.ok:
            raise fault("io_fault", result.detail, recovery_required=True)

    async def flush(self) -> None:
        result = await self._journal.flush()
        if not result.ok:
            raise fault("io_fault", result.detail, recovery_required=True)

    async def publish(self, summary: Mapping[str, object]) -> None:
        result = await self._journal.publish(summary)
        if not result.ok:
            raise fault("io_fault", result.detail, recovery_required=True)

    async def scan(self, output_root: str | Path) -> tuple[Mapping[str, object], ...]:
        result = await self._journal.scan(Path(output_root))
        if not result.ok:
            return ()
        kept: list[Mapping[str, object]] = []
        for row in result.scan:
            run_id = row.get("run_id")
            if not isinstance(run_id, str) or run_id in _SCAN_SKIP:
                continue
            kept.append(row)
        return tuple(kept)

    async def close(self) -> None:
        result = await self._journal.close()
        if not result.ok:
            raise fault("io_fault", result.detail, recovery_required=True)


class ProtocolEvidence:
    """EvidencePort over the GROUND-06 validator."""

    def __init__(self, validator: EvidenceValidator) -> None:
        self._validator = validator

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
        started = interval.started_utc
        ended = interval.ended_utc if isinstance(interval.ended_utc, str) else started
        local = EvidenceInterval(started, ended)
        report = await self._validator.validate(
            frame,
            expected_source=expected_source,
            zone=zone,
            mode=mode,
            output_root=Path(output_root),
            interval=local,
        )
        return _kernel_evidence(report)


async def build_base_services(
    *,
    scenario: str,
    output_dir: Path,
    clock_mode: str = "manual",
    journal_run_id: str | None = "live",
) -> BaseServices:
    """Build the real base providers and connect the scripted device bundle."""

    output_dir.mkdir(parents=True, exist_ok=True)
    kernel = build_kernel(clock_mode=clock_mode, seed=0, mode="simulation")
    bundle = DeviceBundle(kernel, scenario=scenario, output_dir=output_dir)
    ports = ServicePorts(
        config=cast(ConfigPort, None),
        state=cast(StatePort, None),
        journal=cast(JournalPort, None),
        executor=cast(ExecutorPort, None),
        evidence=cast(EvidencePort, None),
        console=cast(ConsolePort, None),
        adapters=cast(AdapterPort, None),
        workflow=cast(WorkflowPort, None),
        safety=cast(SafetyPort, None),
    )
    config = ConfigService(kernel, ports)
    ports.config = config
    state = SessionLink(SessionStore(kernel, ports))
    ports.state = state
    journal = ProtocolJournal(
        Journal(
            kernel,
            ports,
            limits=JournalLimits(max_event_bytes=65536, max_queue=256),
        ),
        modes={"dog": "fake", "drone": "fake", "grok": "fake"},
    )
    ports.journal = journal
    executor = OperationExecutor(kernel, ports)
    ports.executor = executor
    evidence_io = RealIO()
    validator = EvidenceValidator(
        EvidenceContext(clock=kernel.clock, io=evidence_io, limits=EvidenceLimits()),
        EvidencePeers(),
        EvidenceLimits(),
        evidence_io,
    )
    evidence = ProtocolEvidence(validator)
    ports.evidence = evidence
    console = ConsoleService(kernel, ports)
    ports.console = console
    gateway = AdapterGateway(kernel, ports)
    gateway.devices = bundle  # type: ignore[attr-defined]
    ports.adapters = gateway
    safety = SafetyService(kernel, ports)
    ports.safety = safety
    workflow = Workflow(kernel, ports, None)
    ports.workflow = workflow
    services = BaseServices(
        kernel=kernel,
        config=config,
        state=state,
        journal=journal,
        executor=executor,
        evidence=evidence,
        console=console,
        adapters=gateway,
        workflow=workflow,
        safety=safety,
    )
    workflow.services = services
    settings = make_settings(scenario=scenario, output_root=str(output_dir))
    workflow.bind_settings(settings)
    clear_claims_for_tests()
    await gateway.build(
        settings,
        output_dir,
        resolver={
            "source": "private-stub",
            "dog": _factory(bundle.dog),
            "drone": _factory(bundle.drone),
            "reasoner": _factory(bundle.reasoner),
        },
    )
    if journal_run_id is not None:
        await journal.open(journal_run_id, output_dir)
    return services


def _factory(device: object) -> Callable[..., object]:
    def build(*, mode: str, config: Mapping[str, object], output_dir: str) -> object:
        del mode, config, output_dir
        return device

    return build


def _kernel_evidence(report: EvidenceReport) -> EvidenceResult:
    diagnostics = {
        "status": report.status,
        "detail": report.detail,
    }
    return EvidenceResult(
        report.status == "accepted",
        report.reason,
        report.frame,
        freeze_map(diagnostics),
    )


def _mark(snapshot: SessionSnapshot) -> tuple[object, ...]:
    return (
        snapshot.phase,
        snapshot.outcome,
        snapshot.readiness_confirmed,
        tuple(snapshot.evidence),
        snapshot.decisions.get("operation_open"),
        snapshot.decisions.get("operation"),
    )


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _step(
    snapshot: SessionSnapshot,
    target: str,
    outcome: str,
) -> tuple[str, dict[str, object]] | None:
    phase = snapshot.phase
    if target == "FAULT" and phase != "FAULT":
        return "recovery_required", {}
    if target == "ABORTED" and phase not in {"ABORTED", "FAULT"}:
        return "halt_requested", {"physical_state": "known", "reason": "halt"}
    zone = snapshot.incident.zone if snapshot.incident is not None else "room_2"
    terminal = target in _TERMINAL
    if phase == "IDLE":
        return "permission_consumed", {}
    if phase == "ASSESS":
        if terminal and outcome == "ignored":
            return _decision("dispatch", "dismiss")
        if terminal and outcome == "unresolved":
            return "operation_failed", {"operation": "reasoner.assess_incident"}
        return _decision("dispatch", "dispatch")
    if phase == "PREPARE_DOG":
        if snapshot.decisions.get("operation_open") is not True:
            return "operation_started", {"operation": "dog.prepare"}
        if terminal and outcome == "failed":
            return "operation_failed", {"operation": "dog.prepare"}
        return "operation_completed", {
            "operation": "dog.prepare",
            "connected": True,
            "standing": True,
            "stationary": True,
            "avoidance_enabled": True,
        }
    if phase == "MOVE_DOG":
        if snapshot.decisions.get("operation_open") is not True:
            return "operation_started", {"operation": "dog.run_route"}
        if terminal and outcome == "failed":
            return "operation_failed", {"operation": "dog.run_route", "stopped": True}
        return "operation_completed", {
            "operation": "dog.run_route",
            "completed": True,
            "stopped": True,
        }
    if phase == "WAIT_ARRIVAL":
        if terminal and outcome in {"unresolved", "failed"}:
            return "arrival_rejected", {}
        return "arrival_confirmed", {"zone": zone, "method": "simulated", "monotonic": 1.0}
    if phase == "GROUND_VIEW":
        if "ground" not in snapshot.evidence:
            return "frame_validated", _ground_frame(zone)
        if target in {"PREFLIGHT", "INSPECT"}:
            return _decision("ground", "inspect")
        if target == "RESOLVE" or outcome in {"cleared", "alerted"}:
            return _decision("ground", "sufficient")
        if terminal:
            return "frame_rejected", {}
        return _decision("ground", "sufficient")
    if phase == "PREFLIGHT":
        if snapshot.readiness_confirmed is not True:
            if terminal and outcome == "unresolved":
                return "flight_ready_rejected", {}
            return "flight_ready_confirmed", {"method": "simulated"}
        return "operation_started", {"operation": "drone.inspect", "launch_origin": "floor"}
    if phase == "INSPECT":
        if target == "RESOLVE" or outcome in {"alerted", "cleared"}:
            return "operation_completed", _aerial(zone, "captured")
        if outcome == "unresolved":
            return "operation_completed", _aerial(zone, "unavailable")
        return "operation_completed", _aerial(zone, "failed")
    if phase == "RESOLVE":
        action = {"alerted": "confirmed", "cleared": "cleared"}.get(outcome, "inconclusive")
        return _decision("resolution", action)
    if phase == "REPORT":
        return "report_saved", {}
    return None


def _decision(scope: str, action: str) -> tuple[str, dict[str, object]]:
    return "decision_received", {"scope": scope, "action": action, "reason": "scripted"}


def _ground_frame(zone: str) -> dict[str, object]:
    return {
        "source": "dog",
        "zone": zone,
        "path": "simulated-ground.jpg",
        "captured_at": _FRAME_TIME,
        "simulated": True,
    }


def _aerial(zone: str, inspection: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "operation": "drone.inspect",
        "outcome": inspection,
        "flight_state": "grounded",
    }
    if inspection == "captured":
        payload.update(
            {
                "frame_source": "drone",
                "frame_zone": zone,
                "frame_path": "simulated-aerial.jpg",
                "frame_captured_at": _FRAME_TIME,
                "frame_simulated": True,
            }
        )
    return payload
