"""Pure session transitions. This module does not call devices, journals, or peers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from patrol.contract import Incident
from patrol.ground.kernel.catalog import OUTCOMES, PHASES
from patrol.ground.kernel.contracts import GroundEvent, SessionSnapshot, Ticket
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.snapshots import idle_snapshot
from patrol.ground.kernel.validation import freeze_map

_KEEP = object()

_FAULT_SOURCES = frozenset(phase for phase in PHASES if phase != "FAULT")

ROTATE_KINDS = frozenset(
    {
        "permission_granted",
        "permission_consumed",
        "operation_started",
        "halt_requested",
        "stop_attempted",
        "stop_result",
        "recovery_required",
        "recovery_cleared",
        "reset_requested",
        "link_lost",
        "persistence_fault",
        "shutdown_requested",
        "arrival_confirmed",
        "arrival_rejected",
        "flight_ready_confirmed",
        "flight_ready_rejected",
        "report_saved",
        "mission_finished",
    }
)

SAFETY_KINDS = frozenset(
    {
        "halt_requested",
        "stop_attempted",
        "stop_result",
        "recovery_required",
        "recovery_cleared",
        "reset_requested",
        "link_lost",
        "persistence_fault",
        "shutdown_requested",
    }
)

LEGAL_EDGES = frozenset(
    {
        ("IDLE", "ASSESS"),
        ("IDLE", "ABORTED"),
        ("ASSESS", "PREPARE_DOG"),
        ("ASSESS", "REPORT"),
        ("ASSESS", "ABORTED"),
        ("PREPARE_DOG", "MOVE_DOG"),
        ("PREPARE_DOG", "REPORT"),
        ("PREPARE_DOG", "FAULT"),
        ("PREPARE_DOG", "ABORTED"),
        ("MOVE_DOG", "WAIT_ARRIVAL"),
        ("MOVE_DOG", "REPORT"),
        ("MOVE_DOG", "FAULT"),
        ("MOVE_DOG", "ABORTED"),
        ("WAIT_ARRIVAL", "GROUND_VIEW"),
        ("WAIT_ARRIVAL", "REPORT"),
        ("WAIT_ARRIVAL", "ABORTED"),
        ("GROUND_VIEW", "RESOLVE"),
        ("GROUND_VIEW", "PREFLIGHT"),
        ("GROUND_VIEW", "REPORT"),
        ("GROUND_VIEW", "ABORTED"),
        ("PREFLIGHT", "INSPECT"),
        ("PREFLIGHT", "REPORT"),
        ("PREFLIGHT", "FAULT"),
        ("PREFLIGHT", "ABORTED"),
        ("INSPECT", "RESOLVE"),
        ("INSPECT", "REPORT"),
        ("INSPECT", "FAULT"),
        ("INSPECT", "ABORTED"),
        ("RESOLVE", "REPORT"),
        ("RESOLVE", "ABORTED"),
        ("REPORT", "DONE"),
        ("REPORT", "ABORTED"),
    }
) | {(phase, "FAULT") for phase in _FAULT_SOURCES}


def fresh_idle(snapshot: SessionSnapshot, epoch: int) -> SessionSnapshot:
    return idle_snapshot(
        epoch=epoch,
        modes=snapshot.modes,
        dog_transport=snapshot.dog_transport,
    )


def reduce_event(
    snapshot: SessionSnapshot,
    event: GroundEvent,
    ticket: Ticket,
) -> SessionSnapshot:
    """Return the next snapshot, or raise while leaving the caller unchanged."""
    if event.kind in {"recovery_cleared", "reset_requested"}:
        return _recover(snapshot, event.payload)
    return _reduce_active(snapshot, event, ticket)


def _reduce_active(
    snapshot: SessionSnapshot,
    event: GroundEvent,
    ticket: Ticket,
) -> SessionSnapshot:
    if snapshot.incident is None or snapshot.mission_id is None:
        raise fault("not_admitted", "no mission is admitted")
    _reject_transport_change(snapshot, event.payload)
    if snapshot.halt_latched and event.kind not in SAFETY_KINDS:
        raise fault("cancelled", "halt is latched", recovery_required=True)
    if _actions_blocked(snapshot) and event.kind not in SAFETY_KINDS:
        raise fault("rejected", "new ordinary actions are blocked", recovery_required=True)
    updated = _dispatch(snapshot, event)
    if updated.phase not in PHASES:
        raise fault("invalid_input", "unknown phase")
    if (snapshot.phase, updated.phase) not in LEGAL_EDGES and updated.phase != snapshot.phase:
        raise fault("rejected", "phase transition is not legal")
    _reject_cleared_locks(snapshot, updated)
    return replace(updated, stage_id=ticket.stage_id)


def _dispatch(snapshot: SessionSnapshot, event: GroundEvent) -> SessionSnapshot:
    kind = event.kind
    payload = event.payload
    if kind == "state_changed":
        raise fault("rejected", "phase jumps are not accepted")
    if kind == "permission_granted":
        return _arm(snapshot)
    if kind == "permission_consumed":
        return _start(snapshot)
    if kind == "decision_received":
        return _decision(snapshot, payload)
    if kind == "operation_started":
        return _operation_started(snapshot, payload)
    if kind == "operation_completed":
        return _operation_completed(snapshot, payload)
    if kind == "operation_failed":
        return _operation_failed(snapshot, payload)
    if kind == "arrival_confirmed":
        return _arrival(snapshot, payload)
    if kind == "arrival_rejected":
        return _arrival_timeout(snapshot)
    if kind == "flight_ready_confirmed":
        return _flight_ready(snapshot, payload)
    if kind == "flight_ready_rejected":
        return _flight_ready_timeout(snapshot)
    if kind == "frame_validated":
        return _frame_validated(snapshot, payload)
    if kind == "frame_rejected":
        return _frame_rejected(snapshot)
    if kind == "halt_requested":
        return _halt(snapshot, payload)
    if kind == "stop_attempted":
        return _stop_attempted(snapshot)
    if kind == "stop_result":
        return _stop_result(snapshot, payload)
    if kind == "recovery_required":
        return _require_recovery(snapshot)
    if kind == "link_lost":
        return _link_lost(snapshot)
    if kind == "persistence_fault":
        return _persistence(snapshot)
    if kind == "shutdown_requested":
        return _halt(snapshot, {"physical_state": "known", "reason": "shutdown"})
    if kind == "report_saved":
        return _publish(snapshot)
    if kind == "mission_finished":
        return _finish(snapshot)
    raise fault("rejected", "event is not a session transition")


def _recover(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    if payload.get("verified") is not True:
        raise fault(
            "recovery_required",
            "physical recovery is not verified",
            recovery_required=True,
        )
    return snapshot


def _arm(snapshot: SessionSnapshot) -> SessionSnapshot:
    _require_phase(snapshot, "IDLE")
    permission = _permission(snapshot)
    if permission == "consumed":
        raise fault("rejected", "permission was already consumed")
    if permission == "invalidated":
        raise fault("rejected", "permission was invalidated")
    if permission == "granted":
        raise fault("rejected", "permission is already granted")
    return _touch(snapshot, armed=True, decisions={"permission": "granted"})


def _start(snapshot: SessionSnapshot) -> SessionSnapshot:
    _require_phase(snapshot, "IDLE")
    if _motion_real(snapshot) and _permission(snapshot) != "granted":
        raise fault("rejected", "real motion requires arming for this incident")
    return _touch(
        snapshot,
        phase="ASSESS",
        armed=False,
        decisions={"permission": "consumed"},
    )


def _decision(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    scope = _text(payload, "scope")
    action = _text(payload, "action")
    reason = _text(payload, "reason")
    if scope == "dispatch":
        _require_phase(snapshot, "ASSESS")
        if action == "dispatch":
            return _touch(
                snapshot,
                phase="PREPARE_DOG",
                decisions={"dispatch": action, "dispatch_reason": reason},
            )
        if action == "dismiss":
            return _terminal_report(snapshot, "ignored", "dispatch", action, reason)
        if action == "review":
            return _terminal_report(snapshot, "unresolved", "dispatch", action, reason)
        raise fault("invalid_input", "dispatch action is not allowed")
    if scope == "ground":
        _require_phase(snapshot, "GROUND_VIEW")
        if "ground" not in snapshot.evidence:
            raise fault("rejected", "ground view has no accepted frame")
        if action == "sufficient":
            return _touch(
                snapshot,
                phase="RESOLVE",
                decisions={"ground": action, "ground_reason": reason},
            )
        if action == "inspect":
            return _touch(
                snapshot,
                phase="PREFLIGHT",
                flight_lock=True,
                decisions={"ground": action, "ground_reason": reason},
            )
        if action == "review":
            return _terminal_report(snapshot, "unresolved", "ground", action, reason)
        raise fault("invalid_input", "ground action is not allowed")
    if scope == "resolution":
        _require_phase(snapshot, "RESOLVE")
        if "ground" not in snapshot.evidence:
            raise fault("rejected", "resolution requires ground evidence")
        if snapshot.decisions.get("ground") == "inspect" and "aerial" not in snapshot.evidence:
            raise fault("rejected", "inspection resolution requires aerial evidence")
        mapped = {"confirmed": "alerted", "cleared": "cleared", "inconclusive": "unresolved"}
        if action not in mapped:
            raise fault("invalid_input", "resolution action is not allowed")
        return _touch(
            snapshot,
            phase="REPORT",
            outcome=mapped[action],
            decisions={"resolution": action, "resolution_reason": reason},
        )
    raise fault("invalid_input", "decision scope is not allowed")


def _operation_started(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    operation = _text(payload, "operation")
    if snapshot.decisions.get("operation_open") is True:
        raise fault("rejected", "an operation is already open")
    if operation == "dog.prepare":
        _require_phase(snapshot, "PREPARE_DOG")
    elif operation == "dog.run_route":
        _require_phase(snapshot, "MOVE_DOG")
        if snapshot.flight_lock:
            raise fault("rejected", "dog motion is locked", recovery_required=True)
    elif operation == "dog.capture_frame":
        _require_phase(snapshot, "GROUND_VIEW")
    elif operation == "drone.inspect":
        _require_phase(snapshot, "PREFLIGHT")
        if snapshot.readiness_confirmed is not True:
            raise fault("rejected", "flight readiness is not confirmed")
        if snapshot.flight_lock is not True:
            raise fault("unsafe_state", "flight lock is not held", recovery_required=True)
        _reject_fake_pad(snapshot, payload)
        return _touch(
            snapshot,
            phase="INSPECT",
            flight_lock=True,
            decisions={"operation_open": True, "operation": operation},
        )
    else:
        raise fault("rejected", "operation cannot start in this phase")
    return _touch(snapshot, decisions={"operation_open": True, "operation": operation})


def _operation_completed(
    snapshot: SessionSnapshot,
    payload: Mapping[str, object],
) -> SessionSnapshot:
    operation = _text(payload, "operation")
    if operation == "dog.prepare":
        return _prepare_completed(snapshot, payload)
    if operation == "dog.run_route":
        return _route_completed(snapshot, payload)
    if operation == "dog.capture_frame":
        _require_phase(snapshot, "GROUND_VIEW")
        return _touch(snapshot, decisions={"operation_open": False})
    if operation == "dog.get_status":
        return _status_completed(snapshot, payload)
    if operation == "drone.inspect":
        return _inspect_completed(snapshot, payload)
    raise fault("rejected", "operation result is not accepted in this phase")


def _operation_failed(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    operation = _text(payload, "operation")
    if snapshot.phase == "ASSESS" and operation.startswith("reasoner."):
        return _terminal_report(
            snapshot,
            "unresolved",
            "dispatch",
            "review",
            "model request failed",
        )
    if snapshot.phase == "PREPARE_DOG":
        return _terminal_report(snapshot, "failed", "prepare", "failed", "preparation failed")
    if snapshot.phase == "MOVE_DOG":
        stopped = payload.get("stopped")
        if stopped is not True:
            return _fault_report(snapshot, "failed")
        return _terminal_report(snapshot, "failed", "route", "failed", "route failed")
    if snapshot.phase == "WAIT_ARRIVAL":
        return _arrival_timeout(snapshot)
    if snapshot.phase == "PREFLIGHT":
        return _terminal_report(snapshot, "unresolved", "preflight", "failed", "preflight failed")
    if snapshot.phase == "INSPECT":
        merged = dict(payload)
        merged.setdefault("outcome", "failed")
        return _inspect_completed(snapshot, merged)
    if snapshot.phase == "GROUND_VIEW":
        return _terminal_report(
            snapshot,
            "unresolved",
            "ground",
            "review",
            "ground evidence failed",
        )
    raise fault("rejected", "failure is not accepted in this phase")


def _prepare_completed(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    _require_phase(snapshot, "PREPARE_DOG")
    connected = _exact_bool(payload.get("connected"), "connected")
    standing = _tri_state(payload.get("standing"), "standing")
    stationary = _tri_state(payload.get("stationary"), "stationary")
    avoidance = _tri_state(payload.get("avoidance_enabled"), "avoidance_enabled")
    status = {
        "connected": connected,
        "standing": standing,
        "stationary": stationary,
        "avoidance_enabled": avoidance,
    }
    decisions = {"dog_status": status, "operation_open": False}
    unknown = standing is None or stationary is None or avoidance is None
    if unknown or connected is not True:
        if unknown:
            return _fault_report(snapshot, "failed", extra=decisions)
        return _touch(
            snapshot,
            phase="REPORT",
            outcome="failed",
            decisions=decisions | {"prepare": "failed"},
        )
    if standing is not True or stationary is not True or avoidance is not True:
        return _touch(
            snapshot,
            phase="REPORT",
            outcome="failed",
            decisions=decisions | {"prepare": "failed"},
        )
    return _touch(snapshot, phase="MOVE_DOG", decisions=decisions | {"prepare": "ready"})


def _route_completed(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    _require_phase(snapshot, "MOVE_DOG")
    completed = _exact_bool(payload.get("completed"), "completed")
    stopped = _exact_bool(payload.get("stopped"), "stopped")
    decisions = {
        "route_completed": completed,
        "route_stopped": stopped,
        "operation_open": False,
    }
    if stopped is not True:
        return _fault_report(snapshot, "failed", extra=decisions)
    if completed is not True:
        return _touch(
            snapshot,
            phase="REPORT",
            outcome="failed",
            decisions=decisions,
        )
    return _touch(snapshot, phase="WAIT_ARRIVAL", decisions=decisions)


def _status_completed(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    standing = _tri_state(payload.get("standing"), "standing")
    stationary = _tri_state(payload.get("stationary"), "stationary")
    connected = _exact_bool(payload.get("connected"), "connected")
    decisions = {
        "dog_status": {
            "connected": connected,
            "standing": standing,
            "stationary": stationary,
            "avoidance_enabled": _tri_state(
                payload.get("avoidance_enabled"),
                "avoidance_enabled",
            ),
        },
        "operation_open": False,
    }
    if snapshot.phase == "PREFLIGHT" and (
        standing is None or stationary is None or connected is not True
    ):
        return _fault_report(snapshot, "failed", extra=decisions)
    return _touch(snapshot, decisions=decisions)


def _inspect_completed(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    _require_phase(snapshot, "INSPECT")
    outcome = payload.get("outcome")
    flight_state = payload.get("flight_state", "unknown")
    if outcome not in {"captured", "unavailable", "failed", "cancelled"}:
        raise fault("invalid_input", "inspection outcome is not allowed")
    if flight_state not in {"grounded", "airborne", "unknown"}:
        raise fault("invalid_input", "flight state is not allowed")
    frame = _optional_frame(snapshot, payload, source="drone")
    decisions: dict[str, object] = {
        "operation_open": False,
        "inspection_outcome": outcome,
        "flight_state": flight_state,
    }
    evidence = dict(snapshot.evidence)
    if frame is not None:
        evidence["aerial"] = frame
    unknown = flight_state != "grounded"
    if unknown or outcome == "cancelled":
        return _fault_report(
            snapshot,
            "failed" if outcome != "cancelled" else "aborted",
            extra=decisions,
            evidence=evidence,
        )
    if outcome == "captured":
        if frame is None:
            raise fault("rejected", "captured inspection has no frame")
        return _touch(
            snapshot,
            phase="RESOLVE",
            flight_lock=True,
            decisions=decisions,
            evidence=evidence,
        )
    if outcome == "unavailable":
        return _touch(
            snapshot,
            phase="REPORT",
            outcome="unresolved",
            flight_lock=True,
            decisions=decisions,
            evidence=evidence,
        )
    return _touch(
        snapshot,
        phase="REPORT",
        outcome="failed",
        flight_lock=True,
        decisions=decisions,
        evidence=evidence,
    )


def _arrival(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    _require_phase(snapshot, "WAIT_ARRIVAL")
    if snapshot.decisions.get("route_completed") is not True:
        raise fault("rejected", "arrival requires a completed route")
    if snapshot.decisions.get("route_stopped") is not True:
        raise fault("rejected", "arrival requires a stopped route")
    zone = _text(payload, "zone")
    if zone != _incident(snapshot).zone:
        raise fault("rejected", "arrival zone does not match the incident")
    method = _confirmation_method(snapshot, payload, component="dog")
    monotonic = _finite(payload.get("monotonic"), "monotonic")
    return _touch(
        snapshot,
        phase="GROUND_VIEW",
        arrival_confirmed=True,
        arrival_monotonic=monotonic,
        arrival_method=method,
    )


def _arrival_timeout(snapshot: SessionSnapshot) -> SessionSnapshot:
    _require_phase(snapshot, "WAIT_ARRIVAL")
    return _touch(snapshot, phase="REPORT", outcome="unresolved")


def _flight_ready(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    _require_phase(snapshot, "PREFLIGHT")
    if snapshot.readiness_confirmed is True:
        raise fault("rejected", "flight readiness is already confirmed")
    method = _confirmation_method(snapshot, payload, component="drone")
    return _touch(
        snapshot,
        readiness_confirmed=True,
        confirmation_method=method,
        flight_lock=True,
    )


def _flight_ready_timeout(snapshot: SessionSnapshot) -> SessionSnapshot:
    _require_phase(snapshot, "PREFLIGHT")
    return _touch(snapshot, phase="REPORT", outcome="unresolved", flight_lock=True)


def _frame_validated(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    _require_phase(snapshot, "GROUND_VIEW")
    frame = _required_frame(snapshot, payload, source="dog")
    evidence = dict(snapshot.evidence)
    evidence["ground"] = frame
    return _touch(snapshot, evidence=evidence, decisions={"operation_open": False})


def _frame_rejected(snapshot: SessionSnapshot) -> SessionSnapshot:
    _require_phase(snapshot, "GROUND_VIEW")
    return _touch(snapshot, phase="REPORT", outcome="unresolved", decisions={"ground": "rejected"})


def _halt(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    physical = payload.get("physical_state", "known")
    if physical not in {"known", "unknown"}:
        raise fault("invalid_input", "physical state must be known or unknown")
    published = snapshot.decisions.get("publications") == 1 or snapshot.phase == "DONE"
    unknown = physical == "unknown" or snapshot.recovery_required
    if unknown or snapshot.phase == "FAULT":
        phase = "FAULT"
        recovery = True
        flight_lock = True
    elif published:
        phase = snapshot.phase
        recovery = snapshot.recovery_required
        flight_lock = snapshot.flight_lock
    else:
        phase = "ABORTED"
        recovery = False
        flight_lock = snapshot.flight_lock
    outcome = snapshot.outcome
    if phase in {"ABORTED", "FAULT"} and not published:
        outcome = "aborted"
    return _touch(
        snapshot,
        phase=phase,
        outcome=outcome,
        halt_latched=True,
        armed=False,
        recovery_required=recovery,
        flight_lock=flight_lock,
        decisions={"permission": "invalidated"},
    )


def _stop_attempted(snapshot: SessionSnapshot) -> SessionSnapshot:
    return _touch(snapshot, halt_latched=True, decisions={"stop_attempted": True})


def _stop_result(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> SessionSnapshot:
    stopped = _tri_state(payload.get("stopped"), "stopped")
    recovery = snapshot.recovery_required or stopped is not True
    phase = "FAULT" if recovery else snapshot.phase
    if snapshot.phase == "FAULT":
        phase = "FAULT"
    return _touch(
        snapshot,
        phase=phase,
        halt_latched=True,
        recovery_required=recovery,
        flight_lock=snapshot.flight_lock or recovery,
        decisions={"stop_result": stopped},
    )


def _require_recovery(snapshot: SessionSnapshot) -> SessionSnapshot:
    outcome = snapshot.outcome if snapshot.outcome is not None else "failed"
    return _touch(
        snapshot,
        phase="FAULT",
        outcome=outcome,
        recovery_required=True,
        halt_latched=True,
        flight_lock=True,
    )


def _link_lost(snapshot: SessionSnapshot) -> SessionSnapshot:
    published = snapshot.decisions.get("publications") == 1
    outcome = snapshot.outcome if published and snapshot.outcome is not None else "aborted"
    if snapshot.outcome is None:
        outcome = "aborted"
    return _touch(
        snapshot,
        phase="FAULT",
        outcome=outcome,
        recovery_required=True,
        halt_latched=True,
        flight_lock=True,
        decisions={"link_lost": True, "transport_fallback": False},
    )


def _persistence(snapshot: SessionSnapshot) -> SessionSnapshot:
    outcome = snapshot.outcome if snapshot.outcome is not None else "failed"
    return _touch(
        snapshot,
        phase="FAULT",
        outcome=outcome,
        recovery_required=True,
        halt_latched=True,
        decisions={"actions_blocked": True, "persistence_status": "failed"},
    )


def _publish(snapshot: SessionSnapshot) -> SessionSnapshot:
    if snapshot.decisions.get("publications") == 1 or snapshot.phase == "DONE":
        raise fault("rejected", "completion already published")
    _require_phase(snapshot, "REPORT")
    if snapshot.outcome not in OUTCOMES:
        raise fault("rejected", "report has no outcome")
    phase = "FAULT" if snapshot.recovery_required else "DONE"
    return _touch(snapshot, phase=phase, decisions={"publications": 1, "published": True})


def _finish(snapshot: SessionSnapshot) -> SessionSnapshot:
    if snapshot.phase not in {"DONE", "ABORTED", "FAULT"}:
        raise fault("rejected", "mission is not terminal")
    if snapshot.decisions.get("finished") is True:
        raise fault("rejected", "completion already published")
    return _touch(snapshot, decisions={"finished": True})


def _terminal_report(
    snapshot: SessionSnapshot,
    outcome: str,
    scope: str,
    action: str,
    reason: str,
) -> SessionSnapshot:
    return _touch(
        snapshot,
        phase="REPORT",
        outcome=outcome,
        decisions={scope: action, f"{scope}_reason": reason, "operation_open": False},
    )


def _fault_report(
    snapshot: SessionSnapshot,
    outcome: str,
    *,
    extra: Mapping[str, object] | None = None,
    evidence: Mapping[str, object] | None = None,
) -> SessionSnapshot:
    decisions: dict[str, object] = {"operation_open": False}
    if extra is not None:
        decisions.update(dict(extra))
    return _touch(
        snapshot,
        phase="FAULT",
        outcome=outcome,
        recovery_required=True,
        flight_lock=True,
        halt_latched=snapshot.halt_latched,
        decisions=decisions,
        evidence=evidence,
    )


def _reject_cleared_locks(before: SessionSnapshot, after: SessionSnapshot) -> None:
    if before.recovery_required and not after.recovery_required:
        raise fault("rejected", "recovery lock cannot be cleared by an ordinary event")
    if before.flight_lock and not after.flight_lock:
        raise fault("rejected", "flight lock cannot be cleared by an ordinary event")
    if before.halt_latched and not after.halt_latched:
        raise fault("rejected", "halt latch cannot be cleared by an ordinary event")
    if before.phase == "FAULT" and after.phase not in {"FAULT", "REPORT"}:
        raise fault("rejected", "fault cannot return to an ordinary phase")


def _reject_fake_pad(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> None:
    if payload.get("launch_origin") != "dog_pad":
        return
    if snapshot.modes.get("drone") == "real" and snapshot.modes.get("dog") != "real":
        raise fault(
            "unsafe_state",
            "fake dog status cannot authorize a pad launch",
            recovery_required=True,
        )


def _confirmation_method(
    snapshot: SessionSnapshot,
    payload: Mapping[str, object],
    *,
    component: str,
) -> str:
    method = _text(payload, "method")
    if method not in {"operator", "simulated"}:
        raise fault("invalid_input", "confirmation method is not allowed")
    real = snapshot.modes.get(component) == "real"
    if real and method != "operator":
        raise fault("rejected", "real hardware requires operator confirmation")
    return method


def _required_frame(
    snapshot: SessionSnapshot,
    payload: Mapping[str, object],
    *,
    source: str,
) -> Mapping[str, object]:
    frame = _optional_frame(snapshot, payload, source=source)
    if frame is None:
        raise fault("invalid_input", "frame identity is incomplete")
    return frame


def _optional_frame(
    snapshot: SessionSnapshot,
    payload: Mapping[str, object],
    *,
    source: str,
) -> Mapping[str, object] | None:
    source_key = "frame_source" if source == "drone" else "source"
    if source == "drone" and "frame_source" not in payload and "source" not in payload:
        return None
    actual_source = payload.get(source_key)
    zone = payload.get("frame_zone" if source == "drone" else "zone")
    path = payload.get("frame_path" if source == "drone" else "path")
    captured = payload.get("frame_captured_at" if source == "drone" else "captured_at")
    simulated = payload.get("frame_simulated" if source == "drone" else "simulated")
    if actual_source is None and path is None:
        return None
    if actual_source != source:
        raise fault("rejected", "frame source does not match the capture")
    incident = _incident(snapshot)
    if zone != incident.zone:
        raise fault("rejected", "frame zone does not match the incident")
    if not isinstance(path, str) or not path:
        raise fault("invalid_input", "frame path is required")
    if not isinstance(captured, str) or not captured:
        raise fault("invalid_input", "live frame capture time is required")
    if not isinstance(simulated, bool):
        raise fault("invalid_input", "simulated flag must be a boolean")
    mode_name = "dog" if source == "dog" else "drone"
    real = snapshot.modes.get(mode_name) == "real"
    if real and simulated is True:
        raise fault("rejected", "real adapter returned a simulated frame")
    if not real and simulated is not True:
        raise fault("rejected", "fake adapter frame must be marked simulated")
    return {
        "source": source,
        "zone": incident.zone,
        "path": path,
        "captured_at": captured,
        "simulated": simulated,
    }


def _reject_transport_change(snapshot: SessionSnapshot, payload: Mapping[str, object]) -> None:
    if "dog_transport" not in payload:
        return
    if payload.get("dog_transport") != snapshot.dog_transport:
        raise fault("rejected", "dog transport cannot change during a session")


def _touch(
    snapshot: SessionSnapshot,
    *,
    phase: str | None = None,
    outcome: str | None | object = _KEEP,
    stage_id: str | None | object = _KEEP,
    armed: bool | None = None,
    arrival_confirmed: bool | None | object = _KEEP,
    arrival_monotonic: float | None | object = _KEEP,
    arrival_method: str | None | object = _KEEP,
    readiness_confirmed: bool | None | object = _KEEP,
    confirmation_method: str | None | object = _KEEP,
    evidence: Mapping[str, object] | None = None,
    decisions: Mapping[str, object] | None = None,
    flight_lock: bool | None = None,
    recovery_required: bool | None = None,
    halt_latched: bool | None = None,
    epoch: int | None = None,
) -> SessionSnapshot:
    next_outcome = snapshot.outcome if outcome is _KEEP else outcome
    if next_outcome is not None and next_outcome not in OUTCOMES:
        raise fault("invalid_input", "unknown outcome")
    next_phase = snapshot.phase if phase is None else phase
    if next_phase not in PHASES:
        raise fault("invalid_input", "unknown phase")
    merged_decisions = dict(snapshot.decisions)
    if decisions is not None:
        merged_decisions.update(dict(decisions))
    merged_evidence = dict(snapshot.evidence)
    if evidence is not None:
        merged_evidence.update(dict(evidence))
    return replace(
        snapshot,
        phase=next_phase,
        outcome=None if next_outcome is None else str(next_outcome),
        stage_id=_kept_text(snapshot.stage_id, stage_id),
        armed=snapshot.armed if armed is None else armed,
        arrival_confirmed=_kept_bool(snapshot.arrival_confirmed, arrival_confirmed),
        arrival_monotonic=_kept_float(snapshot.arrival_monotonic, arrival_monotonic),
        arrival_method=_kept_text(snapshot.arrival_method, arrival_method),
        readiness_confirmed=_kept_bool(snapshot.readiness_confirmed, readiness_confirmed),
        confirmation_method=_kept_text(snapshot.confirmation_method, confirmation_method),
        evidence=_freeze_dict(merged_evidence),
        decisions=_freeze_dict(merged_decisions),
        flight_lock=snapshot.flight_lock if flight_lock is None else flight_lock,
        recovery_required=(
            snapshot.recovery_required if recovery_required is None else recovery_required
        ),
        halt_latched=snapshot.halt_latched if halt_latched is None else halt_latched,
        epoch=snapshot.epoch if epoch is None else epoch,
    )


def _kept_bool(current: bool | None, incoming: object) -> bool | None:
    if incoming is _KEEP:
        return current
    if incoming is not None and not isinstance(incoming, bool):
        raise fault("invalid_input", "expected a boolean or null")
    return incoming


def _kept_text(current: str | None, incoming: object) -> str | None:
    if incoming is _KEEP:
        return current
    if incoming is not None and not isinstance(incoming, str):
        raise fault("invalid_input", "expected text or null")
    return incoming


def _kept_float(current: float | None, incoming: object) -> float | None:
    if incoming is _KEEP:
        return current
    if incoming is None:
        return None
    if isinstance(incoming, bool) or not isinstance(incoming, (int, float)):
        raise fault("invalid_input", "expected a number or null")
    return float(incoming)


def _incident(snapshot: SessionSnapshot) -> Incident:
    if snapshot.incident is None:
        raise fault("not_admitted", "no mission is admitted")
    return snapshot.incident


def _require_phase(snapshot: SessionSnapshot, phase: str) -> None:
    if snapshot.phase != phase:
        raise fault("rejected", f"event is not valid in {snapshot.phase}")


def _permission(snapshot: SessionSnapshot) -> str:
    value = snapshot.decisions.get("permission", "none")
    return value if isinstance(value, str) else "none"


def _motion_real(snapshot: SessionSnapshot) -> bool:
    return snapshot.modes.get("dog") == "real" or snapshot.modes.get("drone") == "real"


def _actions_blocked(snapshot: SessionSnapshot) -> bool:
    return snapshot.decisions.get("actions_blocked") is True


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{key} is required")
    return value.strip()


def _exact_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise fault("invalid_input", f"{label} must be a boolean")
    return value


def _tri_state(value: object, label: str) -> bool | None:
    if value is None:
        return None
    return _exact_bool(value, label)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", f"{label} must be a real number")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise fault("invalid_input", f"{label} must be finite")
    return number


def _freeze_dict(data: Mapping[str, object]) -> Mapping[str, object]:
    return freeze_map({key: _freeze_value(value) for key, value in data.items()})


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_dict({str(key): item for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value
