"""Dog acknowledgement feature. It records lifecycle facts and never sends a dog.command."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g24.model import (
    DogAckTracker,
    Outcome,
    as_dict,
)
from patrol.ground.extensions.g24.reports import (
    ACCEPTED_TRACE,
    CONFLICT_TRACE,
    EXPIRED_TRACE,
    FOREIGN_TRACE,
    HALT_TRACE,
    LIDAR_TRACE,
    LIFECYCLE_REPORT_TRACE,
    READINESS_TRACE,
    REPEATED_TRACE,
    REPLAY_TRACE,
    STALE_TRACE,
    SUCCESS_TRACE,
    TIMEOUT_TRACE,
    UNVERIFIED_TRACE,
)
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    SessionSnapshot,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_dog_ack"
SCHEMA = "ground-task-v2"
_DIAGNOSTIC_KEYS = frozenset({"seed"})
_TRACK_KEYS = frozenset({"command", "ack", "readiness", "snapshot"})
_TIMEOUT_KEYS = frozenset({"command", "snapshot"})
_READY_KEYS = frozenset({"command", "readiness", "snapshot"})


class DogAckFeature:
    """Track one dog command's acknowledgements. Motion stays with the dog app."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.cleanup_paths: tuple[str, ...] = ()
        self.tracker = DogAckTracker(self._now)

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        try:
            if not isinstance(request, FeatureRequest):
                return _failed("invalid_input", "expected a FeatureRequest")
            if request.kind == "diagnostic":
                return self._diagnostic(request)
            if request.kind not in {"stage", "command"}:
                return _failed("invalid_input", "unsupported dog ack request")
            self._require_ticket(request.ticket)
            if request.name == "track":
                payload = _payload(request, _TRACK_KEYS, required=("command", "ack"))
                _check_snapshot(payload.get("snapshot"))
                outcome = self.tracker.track(
                    payload["command"],
                    payload["ack"],
                    request.ticket,
                    payload.get("readiness"),
                )
            elif request.name == "timeout":
                payload = _payload(request, _TIMEOUT_KEYS, required=("command",))
                _check_snapshot(payload.get("snapshot"))
                outcome = self.tracker.timeout(payload["command"], request.ticket)
            elif request.name == "readiness":
                payload = _payload(request, _READY_KEYS, required=("command", "readiness"))
                _check_snapshot(payload.get("snapshot"))
                outcome = self.tracker.observe(
                    payload["command"],
                    payload["readiness"],
                    request.ticket,
                )
            else:
                return _failed("invalid_input", "unknown dog ack request")
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, exc.error.recovery_required)
        return outcome.as_result()

    def _diagnostic(self, request: FeatureRequest) -> FeatureResult:
        extra = [key for key in request.payload if key not in _DIAGNOSTIC_KEYS]
        if extra:
            return _failed("invalid_input", "unknown diagnostic payload key")
        probe = DogAckTracker(self._now)
        player = _PLAYERS.get(request.name)
        if player is None:
            return _failed("invalid_input", "unknown dog ack case")
        try:
            return player(self, probe)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, exc.error.recovery_required)

    def _now(self) -> float:
        value = self.services.kernel.clock.monotonic()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise fault("invalid_input", "monotonic time must be numeric")
        return float(value)

    def _require_ticket(self, ticket: Ticket | None) -> None:
        authority = self.services.kernel.authority
        if authority.cancelled:
            raise fault("cancelled", "cancellation is latched", recovery_required=True)
        if ticket is not None:
            authority.require_current(ticket)

    def _advance(self, seconds: float) -> None:
        clock = self.services.kernel.clock
        if not isinstance(clock, ManualClock):
            raise fault("unavailable", "this case requires the manual clock")
        clock.advance(seconds)


def create(services: BaseServices) -> DogAckFeature:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "dog ack create expects BaseServices")
    return DogAckFeature(services)


def _play_success(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    outcome, events = _success(tracker)
    return _checked(
        outcome,
        events,
        detail="verified_stationary",
        expected=SUCCESS_TRACE,
        actual=_success_trace(outcome.data),
    )


def _play_accepted(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    outcome = tracker.track(
        _load("ground-to-dog-command.json"),
        _load("dog-ack-accepted.json"),
        None,
    )
    return _checked(
        outcome,
        outcome.events,
        detail="accepted_not_stopped",
        expected=ACCEPTED_TRACE,
        actual=_accepted_trace(outcome.data),
    )


def _play_expired(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    outcome = tracker.track(
        _load("expired-dog-command.json"),
        _load("dog-command-rejected.json"),
        None,
    )
    data = outcome.data
    actual = (
        f"state:{data['state']}",
        f"reason:{data['reason_code']}",
        f"stopped:{_bit(data['stopped'])}",
        f"motion_occurred:{_bit(data['motion_occurred'])}",
        f"active_command:{_bit(data['active_command'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
        "replacement:none",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="expired_no_motion",
        expected=EXPIRED_TRACE,
        actual=actual,
    )


def _play_timeout(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    command = _load("ground-to-dog-command.json")
    early = tracker.timeout(command, None)
    if early.data["timed_out"] is not False or early.data["query_command"] is not None:
        return _mismatch("timeout_query", ("early-query",))
    feature._advance(0.3)
    outcome = tracker.timeout(command, None)
    data = outcome.data
    query = data["query_command"]
    actual = (
        f"state:{data['state']}",
        f"timed_out:{_bit(data['timed_out'])}",
        f"query_command:{query}",
        "replacement:none",
        "issued:cmd-dog-002:false",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
        f"motion_occurred:{_bit(data['motion_occurred'])}",
        f"stopped:{_bit(data['stopped'])}",
    )
    if query == "cmd-dog-002":
        return _mismatch("timeout_query", actual)
    return _checked(
        outcome,
        outcome.events,
        detail="timeout_query",
        expected=TIMEOUT_TRACE,
        actual=actual,
    )


def _play_unverified(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    command = _load("ground-to-dog-command.json")
    ack = _rewrite_payload(
        _load("dog-ack-completed.json"),
        verified=False,
        message_id="msg-dog-ack-completed-unverified",
    )
    outcome = tracker.track(command, ack, None)
    data = outcome.data
    actual = (
        f"state:{data['state']}",
        f"verified:{_bit(data['verified'])}",
        f"stopped:{_bit(data['stopped'])}",
        f"motion:{data['observed_motion']}",
        f"active_command:{_bit(data['active_command'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="unverified_not_stopped",
        expected=UNVERIFIED_TRACE,
        actual=actual,
    )


def _play_halt(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    command = _load("ground-to-dog-command.json")
    tracker.track(command, _load("dog-ack-accepted.json"), None)
    tracker.track(command, _load("dog-ack-running.json"), None)
    halt = _load("ground-to-dog-halt.json")
    outcome = tracker.track(halt, _halt_ack(halt), None)
    move = tracker.view("cmd-dog-001")
    if move is None:
        return _mismatch("halt_separate", ("move-missing",))
    data = outcome.data
    actual = (
        f"move:{move['command_id']}:{move['state']}",
        "move_complete:false",
        f"move_stopped:{_bit(move['stopped'])}",
        f"halt:{data['command_id']}:{data['state']}",
        "halt_terminal:true",
        f"halt_stopped:{_bit(data['stopped'])}",
        f"halt_cleared:{_bit(data['halt_cleared'])}",
        f"block_next_step:{_bit(data['block_next_step'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
        f"demo_goal:{_bit(data['demo_goal_reached'])}",
    )
    if move["state"] == "completed" or move["stopped"] is not False:
        return _mismatch("halt_separate", actual)
    return _checked(
        outcome,
        outcome.events,
        detail="halt_separate",
        expected=HALT_TRACE,
        actual=actual,
    )


def _play_replay(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    _success(tracker)
    outcome = tracker.track(
        _load("ground-to-dog-command.json"),
        _load("dog-ack-completed.json"),
        None,
    )
    data = outcome.data
    actual = (
        f"state:{data['state']}",
        f"stopped:{_bit(data['stopped'])}",
        f"terminal_events:{data['terminal_events']}",
        f"replay_events:{len(outcome.events)}",
        f"event_count:{data['event_count']}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="idempotent_one_event",
        expected=REPLAY_TRACE,
        actual=actual,
    )


def _play_report(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    outcome, events = _success(tracker)
    data = outcome.data
    report = f"report:{data['command_id']}:{data['state']}:stopped:{_bit(data['stopped'])}"
    actual = _success_trace(data) + (report,)
    return _checked(
        outcome,
        events,
        detail="lifecycle_report",
        expected=LIFECYCLE_REPORT_TRACE,
        actual=actual,
    )


def _play_conflict(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    _success(tracker)
    failed = _rewrite_payload(
        _load("dog-ack-completed.json"),
        state="failed",
        reason_code="execution_failed",
        verified=False,
        observed_motion="stationary",
        detail="Conflicting terminal acknowledgement.",
        message_id="msg-dog-ack-failed",
        seq=8,
    )
    outcome = tracker.track(_load("ground-to-dog-command.json"), failed, None)
    data = outcome.data
    actual = (
        f"conflict:{data['state']}/failed",
        f"stopped:{_bit(data['stopped'])}",
        f"faulted:{_bit(data['faulted'])}",
        f"block_next_step:{_bit(data['block_next_step'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
        f"demo_goal:{_bit(data['demo_goal_reached'])}",
        f"halt_cleared:{_bit(data['halt_cleared'])}",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="conflict",
        expected=CONFLICT_TRACE,
        actual=actual,
        status="failed",
        error_code="unsafe_state",
    )


def _play_stale(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    ack = _rewrite_fields(_load("dog-ack-accepted.json"), epoch=9)
    outcome = tracker.track(_load("ground-to-dog-command.json"), ack, None)
    data = outcome.data
    actual = (
        f"state:{data['state']}",
        f"bound:{_bit(data['bound'])}",
        f"motion_occurred:{_bit(data['motion_occurred'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
        f"stopped:{_bit(data['stopped'])}",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="stale_epoch",
        expected=STALE_TRACE,
        actual=actual,
        status="failed",
        error_code="epoch_mismatch",
    )


def _play_lidar(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    command = _load("ground-to-dog-command.json")
    tracker.track(command, _load("dog-ack-accepted.json"), None)
    tracker.track(command, _load("dog-ack-running.json"), None)
    ack = _rewrite_payload(
        _load("dog-ack-completed.json"),
        reason_code="lidar_stop",
        detail="LiDAR clearance stop. This is not target arrival.",
        message_id="msg-dog-ack-lidar",
    )
    outcome = tracker.track(command, ack, None)
    data = outcome.data
    actual = (
        f"state:{data['state']}",
        f"stopped:{_bit(data['stopped'])}",
        f"stop_cause:{data['stop_cause']}",
        f"target_arrival:{_bit(data['target_arrival'])}",
        f"demo_goal:{_bit(data['demo_goal_reached'])}",
        f"verified:{_bit(data['verified'])}",
        f"motion:{data['observed_motion']}",
        "proposed_command:none",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="lidar_not_arrival",
        expected=LIDAR_TRACE,
        actual=actual,
    )


def _play_foreign(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    ack = _rewrite_payload(_load("dog-ack-accepted.json"), command_id="cmd-dog-999")
    outcome = tracker.track(_load("ground-to-dog-command.json"), ack, None)
    data = outcome.data
    actual = (
        f"state:{data['state']}",
        f"bound:{_bit(data['bound'])}",
        f"command_id:{data['command_id']}",
        f"motion_occurred:{_bit(data['motion_occurred'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="foreign_command",
        expected=FOREIGN_TRACE,
        actual=actual,
        status="failed",
        error_code="rejected",
    )


def _play_repeated(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    del feature
    _success(tracker)
    command = _rewrite_fields(
        _load("ground-to-dog-command.json"),
        message_id="msg-ground-to-dog-command-repeat",
    )
    ack = _rewrite_fields(
        _load("dog-ack-accepted.json"),
        message_id="msg-dog-ack-repeat",
        correlation_id="msg-ground-to-dog-command-repeat",
    )
    outcome = tracker.track(command, ack, None)
    data = outcome.data
    actual = (
        f"repeated:{_bit(data['repeated_command'])}",
        f"state:{data['state']}",
        f"stopped:{_bit(data['stopped'])}",
        f"motion_allowed:{_bit(data['motion_allowed'])}",
        f"faulted:{_bit(data['faulted'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="repeated_command",
        expected=REPEATED_TRACE,
        actual=actual,
        status="failed",
        error_code="rejected",
    )


def _play_readiness(feature: DogAckFeature, tracker: DogAckTracker) -> FeatureResult:
    command = _load("ground-to-dog-command.json")
    _success(tracker)
    feature._advance(0.3)
    outcome = tracker.observe(
        command,
        {"stationary": False, "observed_after_window": True},
        None,
    )
    data = outcome.data
    actual = (
        f"state:{data['state']}",
        f"stopped:{_bit(data['stopped'])}",
        f"stop_cause:{data['stop_cause']}",
        f"verified:{_bit(data['verified'])}",
        f"motion:{data['observed_motion']}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
        f"demo_goal:{_bit(data['demo_goal_reached'])}",
        f"target_arrival:{_bit(data['target_arrival'])}",
    )
    return _checked(
        outcome,
        outcome.events,
        detail="readiness_disagrees",
        expected=READINESS_TRACE,
        actual=actual,
    )


_PLAYERS = {
    "success_sequence": _play_success,
    "accepted_only": _play_accepted,
    "expired_rejection": _play_expired,
    "timeout_query": _play_timeout,
    "unverified_completed": _play_unverified,
    "halt_separate": _play_halt,
    "replay_terminal": _play_replay,
    "lifecycle_report": _play_report,
    "conflict_terminal": _play_conflict,
    "stale_epoch": _play_stale,
    "lidar_stop": _play_lidar,
    "foreign_command": _play_foreign,
    "repeated_command": _play_repeated,
    "readiness_disagrees": _play_readiness,
}


def _success(tracker: DogAckTracker) -> tuple[Outcome, tuple[GroundEvent, ...]]:
    command = _load("ground-to-dog-command.json")
    first = tracker.track(command, _load("dog-ack-accepted.json"), None)
    second = tracker.track(command, _load("dog-ack-running.json"), None)
    third = tracker.track(command, _load("dog-ack-completed.json"), None)
    return third, first.events + second.events + third.events


def _success_trace(data: Mapping[str, object]) -> tuple[str, ...]:
    return (
        f"state:{data['state']}",
        f"stopped:{_bit(data['stopped'])}",
        f"verified:{_bit(data['verified'])}",
        f"motion:{data['observed_motion']}",
        f"motion_occurred:{_bit(data['motion_occurred'])}",
        f"active_command:{_bit(data['active_command'])}",
        f"block_next_step:{_bit(data['block_next_step'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
        f"demo_goal:{_bit(data['demo_goal_reached'])}",
        f"target_arrival:{_bit(data['target_arrival'])}",
        f"halt_cleared:{_bit(data['halt_cleared'])}",
    )


def _accepted_trace(data: Mapping[str, object]) -> tuple[str, ...]:
    return (
        f"state:{data['state']}",
        f"stopped:{_bit(data['stopped'])}",
        f"verified:{_bit(data['verified'])}",
        f"motion:{data['observed_motion']}",
        f"motion_occurred:{_bit(data['motion_occurred'])}",
        f"active_command:{_bit(data['active_command'])}",
        f"block_next_step:{_bit(data['block_next_step'])}",
        "proposed_command:none",
        f"commands_issued:{data['commands_issued']}",
    )


def _checked(
    outcome: Outcome,
    events: tuple[GroundEvent, ...],
    *,
    detail: str,
    expected: tuple[str, ...],
    actual: tuple[str, ...],
    status: str = "ok",
    error_code: str | None = None,
) -> FeatureResult:
    problem = _invariant_error(outcome.data)
    if problem is not None:
        return _foundation("failed", "invariant", actual, problem, ())
    if outcome.status != status:
        return _mismatch(detail, actual)
    if error_code is None and outcome.error is not None:
        return _mismatch(detail, actual)
    if error_code is not None and (outcome.error is None or outcome.error.code != error_code):
        return _mismatch(detail, actual)
    if actual != expected:
        return _mismatch(detail, actual)
    return _foundation(status, detail, actual, outcome.error, events)


def _invariant_error(data: Mapping[str, object]) -> GroundError | None:
    if data.get("commands_issued") != 0 or data.get("proposed_command") is not None:
        return GroundError("unsafe_state", "a dog command was issued", True)
    if data.get("replacement_command_id") is not None:
        return GroundError("unsafe_state", "a replacement command was allocated", True)
    if data.get("motion_allowed") is not False:
        return GroundError("unsafe_state", "an acknowledgement granted motion", True)
    if data.get("demo_goal_reached") is not False:
        return GroundError("unsafe_state", "demo goal was marked from an acknowledgement", True)
    if data.get("target_arrival") is not False:
        return GroundError(
            "unsafe_state",
            "target arrival was marked from an acknowledgement",
            True,
        )
    if data.get("halt_cleared") is not False:
        return GroundError("unsafe_state", "a halt was cleared", True)
    return None


def _foundation(
    status: str,
    detail: str,
    trace: tuple[str, ...],
    error: GroundError | None,
    events: tuple[GroundEvent, ...],
) -> FeatureResult:
    if status == "ok":
        error = None
    elif error is None:
        error = GroundError("validation_failed", detail, True)
    return FeatureResult(
        status,
        freeze_map(
            {
                "live_call_count": 0,
                "simulated": True,
                "trace": trace,
                "within_limit": True,
                "device_calls": 0,
                "retained": False,
                "measurement_clock": "manual",
                "slot": SLOT,
                "schema_version": SCHEMA,
                "authorized": False,
                "detail": detail,
            }
        ),
        events,
        error,
    )


def _mismatch(detail: str, actual: tuple[str, ...]) -> FeatureResult:
    return _foundation(
        "failed",
        "trace_mismatch",
        actual,
        GroundError("validation_failed", f"{detail} trace drifted", True),
        (),
    )


def _failed(code: str, detail: str, recovery_required: bool = False) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "live_call_count": 0,
                "simulated": True,
                "trace": (),
                "within_limit": True,
                "device_calls": 0,
                "retained": False,
                "measurement_clock": "manual",
                "slot": SLOT,
                "schema_version": SCHEMA,
                "authorized": False,
                "detail": code,
            }
        ),
        (),
        GroundError(code, detail, recovery_required),
    )


def _payload(
    request: FeatureRequest,
    allowed: frozenset[str],
    *,
    required: tuple[str, ...],
) -> Mapping[str, object]:
    extra = [key for key in request.payload if key not in allowed]
    if extra:
        raise fault("invalid_input", "unknown dog ack payload key")
    missing = [key for key in required if key not in request.payload]
    if missing:
        raise fault("invalid_input", "dog ack payload is missing a required field")
    return request.payload


def _check_snapshot(value: object) -> None:
    if value is None:
        return
    if isinstance(value, SessionSnapshot):
        return
    body = as_dict(value, "snapshot")
    flag = body.get("halt_latched")
    if flag is not None and not isinstance(flag, bool):
        raise fault("invalid_input", "halt_latched must be a boolean")


def _halt_ack(halt: Mapping[str, object]) -> dict[str, object]:
    message_id = halt["message_id"]
    mission_id = halt["mission_id"]
    if not isinstance(message_id, str) or not isinstance(mission_id, str):
        raise fault("invalid_input", "halt command identity is not text")
    return {
        "protocol_version": "2.0-draft",
        "message_id": "msg-dog-ack-halt-completed",
        "mission_id": mission_id,
        "epoch": 1,
        "seq": 8,
        "sent_at": "2026-11-04T13:00:11.200Z",
        "source": "dog",
        "destination": "ground",
        "kind": "command.ack",
        "correlation_id": message_id,
        "expires_at": None,
        "simulated": True,
        "payload": {
            "command_id": "cmd-dog-halt-001",
            "state": "completed",
            "reason_code": "ok",
            "observed_at": "2026-11-04T13:00:11.200Z",
            "verified": True,
            "observed_motion": "stationary",
            "detail": "Halt settled. The earlier move is not complete.",
        },
    }


def _load(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g24" / name
    return _read_json(path)


def _read_json(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise fault("invalid_input", "dog ack fixture could not be read") from exc
    return as_dict(raw, "fixture")


def _copy(message: Mapping[str, object]) -> dict[str, object]:
    parsed = json.loads(json.dumps(dict(message)))
    return as_dict(parsed, "message")


def _rewrite_fields(message: Mapping[str, object], **changes: object) -> dict[str, object]:
    copied = _copy(message)
    copied.update(changes)
    return copied


def _rewrite_payload(message: Mapping[str, object], **changes: object) -> dict[str, object]:
    copied = _copy(message)
    envelope_keys = {"message_id", "seq", "correlation_id", "epoch"}
    payload_changes = {key: value for key, value in changes.items() if key not in envelope_keys}
    envelope_changes = {key: value for key, value in changes.items() if key in envelope_keys}
    payload = as_dict(copied["payload"], "payload")
    payload.update(payload_changes)
    copied["payload"] = payload
    copied.update(envelope_changes)
    return copied


def _bit(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "none"
    return str(value)
