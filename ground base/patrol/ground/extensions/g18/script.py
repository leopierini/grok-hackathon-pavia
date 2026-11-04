"""Scripted drone-ack cases. The frozen harness only passes the case name and seed."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g18.lifecycle import Outcome, Tracker
from patrol.ground.extensions.g18.messages import load_fixture
from patrol.ground.extensions.g18.names import SCHEMA, SLOT
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import FeatureResult, GroundError
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

ORDERED_TRACE = (
    "accepted",
    "running",
    "completed",
    "airborne",
    "one_lifecycle",
    "one_completion",
    "not_grounded",
    "no_takeoff",
    "projection_saved",
)
ACCEPTED_TRACE = ("accepted", "non_terminal", "not_completed", "no_takeoff", "projection_saved")
TIMEOUT_TRACE = (
    "accepted",
    "query_command",
    "cmd-drone-001",
    "unresolved",
    "no_second_command",
    "no_takeoff",
    "projection_saved",
)
LANDING_TRACE = (
    "unknown",
    "recovery_required",
    "blocks_next_mission",
    "not_grounded",
    "no_takeoff",
    "projection_saved",
)
DUPLICATE_TRACE = ("completed", "duplicate", "one_completion", "no_takeoff", "projection_saved")
CONFLICT_TRACE = (
    "completed",
    "conflict",
    "state_unchanged",
    "no_takeoff",
    "projection_saved",
)
STALE_TRACE = ("stale", "epoch_mismatch", "no_takeoff", "projection_saved")
UNVERIFIED_TRACE = (
    "completed",
    "verified_false",
    "not_verified_completion",
    "not_grounded",
    "no_takeoff",
    "projection_saved",
)
LOCAL_FLAG_TRACE = (
    "is_flying_ignored",
    "airborne",
    "not_grounded",
    "no_takeoff",
    "projection_saved",
)
UNKNOWN_COMMAND_TRACE = ("rejected", "unknown_command_id", "no_takeoff", "projection_saved")
DOG_TRACE = ("rejected", "dog_lifecycle", "no_takeoff", "projection_saved")


def run_case(name: str, tracker: Tracker, clock: object) -> FeatureResult:
    handler = _HANDLERS.get(name)
    if handler is None:
        return _foundation(
            status="failed",
            detail=f"unknown drone ack case {name}",
            trace=("failed", "invalid_input"),
            error=GroundError("invalid_input", f"unknown drone ack case {name}", False),
        )
    try:
        return handler(tracker, clock)
    except GroundFault as exc:
        return _foundation(
            status="failed",
            detail=exc.error.detail,
            trace=("failed", exc.error.code),
            error=exc.error,
        )


def _ordered(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    outcomes = _play(tracker, _TRACK_ACKS, manual.monotonic() + 10)
    last = outcomes[-1]
    completions = _count(outcomes, "operation_completed")
    ok = (
        [item.data["state"] for item in outcomes] == ["accepted", "running", "completed"]
        and last.data["history"] == ("accepted", "running", "completed")
        and last.data["flight_state"] == "airborne"
        and last.data["grounded"] is False
        and last.data["verified_completion"] is True
        and last.data["completion_events"] == 1
        and completions == 1
        and last.data["issued_command_ids"] == ("cmd-drone-001",)
        and last.data["proposed_commands"] == ()
        and last.data["demo_goal_cleared"] is False
    )
    _save("ordered_acks", last)
    return _gate(
        ok,
        "ordered track acks did not stay one airborne lifecycle",
        ORDERED_TRACE,
        "track_completed_airborne",
    )


def _accepted(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    outcome = _apply(tracker, "drone-ack-accepted.json", _track(), manual.monotonic() + 10)
    ok = (
        outcome.status == "ok"
        and outcome.data["state"] == "accepted"
        and outcome.data["terminal"] is False
        and outcome.data["completed"] is False
        and outcome.data["verified"] is False
        and outcome.data["verified_completion"] is False
        and outcome.data["observed_motion"] == "unknown"
        and outcome.data["proposed_commands"] == ()
    )
    _save("accepted_only", outcome)
    return _gate(ok, "accepted was treated as completed", ACCEPTED_TRACE, "accepted_not_completed")


def _timeout(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    deadline = manual.monotonic() + 0.25
    command = _track()
    registered = tracker.register(command, deadline, None)
    accepted = _apply(tracker, "drone-ack-accepted.json", command, deadline)
    manual.advance(0.25)
    expired = tracker.expire("cmd-drone-001", manual.monotonic(), None)
    ok = (
        registered.status == "ok"
        and accepted.data["state"] == "accepted"
        and accepted.data["terminal"] is False
        and expired.status == "ok"
        and expired.data["query_command"] == "cmd-drone-001"
        and expired.data["query_required"] is True
        and expired.data["unresolved"] is True
        and expired.data["state"] == "accepted"
        and expired.data["issued_command_ids"] == ("cmd-drone-001",)
        and expired.data["proposed_commands"] == ()
        and expired.data["completion_events"] == 0
    )
    _save("reply_timeout", expired)
    return _gate(ok, "timeout did not query the original command", TIMEOUT_TRACE, "query_required")


def _landing(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    outcome = _apply(
        tracker,
        "drone-landing-unknown.json",
        load_fixture("ground-to-drone-land.json"),
        manual.monotonic() + 10,
    )
    ok = (
        outcome.status == "blocked"
        and outcome.code == "recovery_required"
        and outcome.recovery is True
        and outcome.data["state"] == "unknown"
        and outcome.data["recovery_required"] is True
        and outcome.data["blocks_next_mission"] is True
        and outcome.data["grounded"] is False
        and outcome.data["landing_proof"] is False
        and outcome.data["flight_state"] == "unknown"
        and outcome.data["command_id"] == "cmd-drone-land-001"
        and outcome.data["proposed_commands"] == ()
        and outcome.data["demo_goal_cleared"] is False
    )
    _save("landing_unknown", outcome)
    return _gate(
        ok,
        "unknown landing did not require recovery",
        LANDING_TRACE,
        "landing_unknown",
        status="blocked",
        code="recovery_required",
        recovery=True,
    )


def _duplicate(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    outcomes = _play(tracker, _TRACK_ACKS, manual.monotonic() + 10)
    replay = _apply(tracker, "drone-ack-completed.json", _track(), manual.monotonic() + 10)
    completions = _count([*outcomes, replay], "operation_completed")
    ok = (
        replay.status == "ok"
        and replay.data["duplicate"] is True
        and replay.events == ()
        and replay.data["completion_events"] == 1
        and replay.data["state"] == "completed"
        and replay.data["history"] == ("accepted", "running", "completed")
        and completions == 1
        and replay.data["proposed_commands"] == ()
    )
    _save("duplicate_final", replay)
    return _gate(
        ok,
        "duplicate final ack created another completion",
        DUPLICATE_TRACE,
        "idempotent_final",
    )


def _conflict(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    _play(tracker, _TRACK_ACKS, manual.monotonic() + 10)
    failed = _retitle(
        load_fixture("drone-ack-completed.json"),
        state="failed",
        verified=False,
        reason_code="conflict",
        detail="Conflicting final state.",
    )
    failed["message_id"] = "msg-drone-ack-conflict"
    failed["seq"] = 6
    outcome = tracker.apply(failed, _track(), _observation(), manual.monotonic() + 10, None)
    ok = (
        outcome.status == "failed"
        and outcome.code == "unsafe_state"
        and outcome.data["conflict"] is True
        and outcome.data["state"] == "completed"
        and outcome.data["history"] == ("accepted", "running", "completed")
        and outcome.data["completion_events"] == 1
        and outcome.data["flight_state"] == "airborne"
        and outcome.data["grounded"] is False
        and outcome.data["proposed_commands"] == ()
    )
    _save("conflicting_final", outcome)
    return _gate(
        ok,
        "conflicting final ack was accepted",
        CONFLICT_TRACE,
        "conflict_fault",
        status="failed",
        code="unsafe_state",
        recovery=True,
    )


def _stale(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    ack = load_fixture("drone-ack-accepted.json")
    ack["epoch"] = 9
    ack["message_id"] = "msg-drone-ack-stale"
    outcome = tracker.apply(ack, _track(), _observation(), manual.monotonic() + 10, None)
    ok = (
        outcome.status == "blocked"
        and outcome.code == "epoch_mismatch"
        and outcome.data["state"] is None
        and outcome.data["issued_command_ids"] == ()
        and outcome.data["proposed_commands"] == ()
    )
    _save("stale_epoch", outcome)
    return _gate(
        ok,
        "foreign epoch was applied",
        STALE_TRACE,
        "stale_epoch",
        status="blocked",
        code="epoch_mismatch",
    )


def _unverified(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    ack = _retitle(load_fixture("drone-ack-completed.json"), verified=False)
    outcome = tracker.apply(ack, _track(), _observation(), manual.monotonic() + 10, None)
    ok = (
        outcome.status == "ok"
        and outcome.data["state"] == "completed"
        and outcome.data["verified"] is False
        and outcome.data["verified_completion"] is False
        and outcome.data["completed"] is True
        and outcome.data["grounded"] is False
        and outcome.data["flight_state"] == "airborne"
        and outcome.data["proposed_commands"] == ()
    )
    _save("unverified_completion", outcome)
    return _gate(
        ok,
        "unverified completion counted as verified",
        UNVERIFIED_TRACE,
        "unverified_completion",
    )


def _local_flag(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    ack = _retitle(load_fixture("drone-ack-completed.json"), detail="is_flying=false")
    outcome = tracker.apply(ack, _track(), _observation(), manual.monotonic() + 10, None)
    ok = (
        outcome.status == "ok"
        and outcome.data["ignored_local_flag"] is True
        and outcome.data["grounded"] is False
        and outcome.data["landing_proof"] is False
        and outcome.data["flight_state"] == "airborne"
        and outcome.data["action"] == "track_step"
        and outcome.data["proposed_commands"] == ()
    )
    _save("local_flag_ignored", outcome)
    return _gate(
        ok,
        "is_flying in the detail was treated as grounded",
        LOCAL_FLAG_TRACE,
        "local_flag_ignored",
    )


def _unknown_command(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    ack = _retitle(load_fixture("drone-ack-accepted.json"), command_id="cmd-not-issued")
    ack["message_id"] = "msg-drone-ack-foreign"
    outcome = tracker.apply(ack, _track(), None, manual.monotonic() + 10, None)
    ok = (
        outcome.status == "blocked"
        and outcome.code == "rejected"
        and outcome.detail == "unknown command_id"
        and outcome.data["issued_command_ids"] == ()
        and outcome.data["proposed_commands"] == ()
    )
    _save("unknown_command", outcome)
    return _gate(
        ok,
        "unknown command_id was accepted",
        UNKNOWN_COMMAND_TRACE,
        "unknown_command_id",
        status="blocked",
        code="rejected",
    )


def _dog(tracker: Tracker, clock: object) -> FeatureResult:
    manual = _manual(clock)
    outcome = tracker.apply(
        load_fixture("dog-ack-accepted.json"),
        _track(),
        None,
        manual.monotonic() + 10,
        None,
    )
    ok = (
        outcome.status == "blocked"
        and outcome.code == "rejected"
        and outcome.detail == "dog acknowledgements are tracked by task 24"
        and outcome.data["issued_command_ids"] == ()
        and outcome.data["proposed_commands"] == ()
    )
    _save("dog_ack", outcome)
    return _gate(
        ok,
        "dog acknowledgement was tracked here",
        DOG_TRACE,
        "dog_lifecycle",
        status="blocked",
        code="rejected",
    )


def _play(tracker: Tracker, names: tuple[str, ...], deadline: float) -> list[Outcome]:
    command = _track()
    return [_apply(tracker, name, command, deadline) for name in names]


def _apply(tracker: Tracker, name: str, command: Mapping[str, object], deadline: float) -> Outcome:
    return tracker.apply(load_fixture(name), command, _observation(), deadline, None)


def _track() -> dict[str, object]:
    return load_fixture("ground-to-drone-command.json")


def _observation() -> dict[str, object]:
    return load_fixture("drone-observation.json")


def _retitle(message: dict[str, object], **fields: object) -> dict[str, object]:
    payload = message["payload"]
    if not isinstance(payload, dict):
        raise GroundFault(GroundError("invalid_input", "ack payload must be an object", False))
    updated = dict(payload)
    updated.update(fields)
    cloned = dict(message)
    cloned["payload"] = updated
    return cloned


def _count(outcomes: list[Outcome], kind: str) -> int:
    return sum(1 for outcome in outcomes for event in outcome.events if event.kind == kind)


def _manual(clock: object) -> ManualClock:
    if not isinstance(clock, ManualClock):
        raise GroundFault(
            GroundError("invalid_input", "reply deadline needs the manual clock", False)
        )
    return clock


def _gate(
    ok: bool,
    reason: str,
    trace: tuple[str, ...],
    detail: str,
    *,
    status: str = "ok",
    code: str | None = None,
    recovery: bool = False,
) -> FeatureResult:
    if not ok:
        return _foundation(
            status="failed",
            detail=reason,
            trace=("check_failed", reason),
            error=GroundError("validation_failed", reason, False),
        )
    error = None if status == "ok" else GroundError(code or "internal", detail, recovery)
    return _foundation(status=status, detail=detail, trace=trace, error=error)


def _foundation(
    *,
    status: str,
    detail: str,
    trace: tuple[str, ...],
    error: GroundError | None,
) -> FeatureResult:
    data = freeze_map(
        {
            "authorized": False,
            "retained": False,
            "detail": detail,
            "trace": trace,
            "device_calls": 0,
            "measurement_clock": "manual",
            "within_limit": True,
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
    )
    return FeatureResult(status, data, (), error)


def _save(case_id: str, outcome: Outcome) -> None:
    directory = repo_root() / "artifacts" / "task-18" / "projections"
    directory.mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {
        "case_id": case_id,
        "evidence": "simulated",
        "status": outcome.status,
        "code": outcome.code,
        "detail": outcome.detail,
    }
    body.update(outcome.data)
    path = directory / f"{case_id}.json"
    path.write_text(json.dumps(_jsonable(body), indent=2) + "\n", encoding="utf-8")
    if not path.is_file():
        raise GroundFault(GroundError("io_fault", "lifecycle projection was not saved", True))


def _jsonable(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


_TRACK_ACKS = (
    "drone-ack-accepted.json",
    "drone-ack-running.json",
    "drone-ack-completed.json",
)
_HANDLERS = {
    "ordered_acks": _ordered,
    "accepted_only": _accepted,
    "reply_timeout": _timeout,
    "landing_unknown": _landing,
    "duplicate_final": _duplicate,
    "conflicting_final": _conflict,
    "stale_epoch": _stale,
    "unverified_completion": _unverified,
    "local_flag_ignored": _local_flag,
    "unknown_command": _unknown_command,
    "dog_ack": _dog,
}


def projection_dir() -> Path:
    return repo_root() / "artifacts" / "task-18" / "projections"
