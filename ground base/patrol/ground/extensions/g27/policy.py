"""Separate a reached demo goal from aircraft landing recovery.

Geometry is not recomputed here. A goal fixture is recorded as given.
Landing is verified only from a matching land acknowledgement plus a
grounded observation. This module never calls land or a search primitive.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map, require_bool

SLOT = "feature.v2_recovery"
SCHEMA = "ground-task-v2"
DOG_HOLD = "hold_stop"
PHYSICAL_RETRIEVAL = "operator_step"

_ACK_STATES = frozenset(
    {"accepted", "running", "completed", "rejected", "cancelled", "failed", "unknown"}
)
_MOTIONS = frozenset({"stationary", "moving", "airborne", "grounded", "unknown"})
_FLIGHT = frozenset({"grounded", "airborne", "unknown"})
_FAILED_ACK = frozenset({"failed", "rejected", "cancelled"})
_UNKNOWN_REASON = "Goal record cannot clear unknown aircraft state."
_CLEAR_REASON = "recovery cannot be cleared without a new grounded observation"


@dataclass(frozen=True)
class Incoming:
    goal_event: Mapping[str, object] | None
    land_command: Mapping[str, object] | None
    land_ack: Mapping[str, object] | None
    observation: Mapping[str, object] | None
    attempt_clear: bool
    ignored_actions: tuple[str, ...]


@dataclass(frozen=True)
class Outcome:
    status: str
    error_code: str | None
    error_detail: str | None
    goal_status: str
    landing_status: str
    recovery_required: bool
    device_recovery_required: bool
    next_mission_blocked: bool
    dog_recommendation: str
    issued_commands: tuple[str, ...]
    search_commands: tuple[str, ...]
    record_id: str
    record_count: int
    replayed: bool
    clear_rejected: bool
    cleared: bool
    goal_event_id: str | None
    land_command_id: str | None
    land_message_id: str | None
    mission_id: str | None
    epoch: int | None
    track_id: str | None
    beacon_epoch: int | None
    frame_id: str | None
    camera_epoch: int | None
    map_epoch: int | None
    goal_sent_at: str | None
    observation_id: str | None
    picture_ignored: bool
    goal_timestamp_ignored: bool
    goal_invented: bool
    landing_event_name: str | None
    fault_name: str | None
    land_ack_accepted: bool
    foreign_command_id: str | None
    observation_not_landing: bool
    record: Mapping[str, object]
    signature: str


@dataclass(frozen=True)
class _Goal:
    reached: bool
    message_id: str | None
    mission_id: str | None
    epoch: int | None
    sent_at: str | None
    track_id: str | None
    stated_recovery: bool | None


@dataclass(frozen=True)
class _Land:
    issued: bool
    command_id: str | None
    message_id: str | None
    mission_id: str | None
    epoch: int | None
    beacon_epoch: int | None
    track_id: str | None
    foreign_command_id: str | None
    foreign_action: str | None


@dataclass(frozen=True)
class _Ack:
    present: bool
    matches: bool
    message_id: str | None
    mission_id: str | None
    command_id: str | None
    state: str | None
    verified: bool | None
    observed_motion: str | None
    observed_at: str | None


@dataclass(frozen=True)
class _Obs:
    present: bool
    message_id: str | None
    mission_id: str | None
    flight_state: str | None
    frame_id: str | None
    camera_epoch: int | None
    beacon_epoch: int | None
    map_epoch: int | None


@dataclass(frozen=True)
class _Stored:
    signature: str
    observation_id: str | None
    outcome: Outcome


def load_fixture(name: str) -> dict[str, object]:
    """Load one task-owned JSON fixture. Names cannot escape the directory."""
    if not isinstance(name, str) or Path(name).name != name or not name.endswith(".json"):
        raise fault("path_escape", "fixture name escapes the task directory")
    root = (repo_root() / "fixtures" / "ground" / "g27").resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise fault("path_escape", "fixture path escapes the task directory") from exc
    if not path.is_file():
        raise fault("invalid_input", f"fixture {name} is missing")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise fault("io_fault", "fixture could not be read", recovery_required=True) from exc
    try:
        raw = json.loads(text, object_pairs_hook=_pairs)
    except GroundFault:
        raise
    except ValueError as exc:
        raise fault("invalid_input", "fixture is not valid json") from exc
    if not isinstance(raw, dict):
        raise fault("invalid_input", "fixture must be an object")
    return {str(key): value for key, value in raw.items()}


def verified_inputs() -> Incoming:
    return Incoming(
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation-grounded.json"),
        attempt_clear=False,
        ignored_actions=(),
    )


def unknown_inputs(*, observation: bool) -> Incoming:
    return Incoming(
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("drone-landing-unknown.json"),
        observation=load_fixture("drone-observation.json") if observation else None,
        attempt_clear=False,
        ignored_actions=(),
    )


class RecoveryBook:
    """One in-memory recovery record per land command, or per goal if no land."""

    def __init__(self) -> None:
        self._stored: dict[str, _Stored] = {}

    def evaluate(self, incoming: Incoming) -> Outcome:
        goal, land, ack, obs = _views(incoming)
        _same_mission(goal, land, ack, obs)
        fresh = _classify(goal, land, ack, obs, incoming)
        key = _storage_key(land, goal)
        signature = _signature(incoming, goal, land, ack, obs)
        existing = self._stored.get(key)
        if incoming.attempt_clear:
            return self._clear(key, existing, fresh, obs, signature)
        if existing is None:
            return self._keep(key, fresh, signature, obs.message_id)
        if existing.signature == signature:
            replayed = replace(existing.outcome, replayed=True, record_count=len(self._stored))
            return replayed
        if existing.outcome.recovery_required:
            if _new_verified_landing(existing, fresh, obs):
                return self._clear(key, existing, fresh, obs, signature)
            return self._keep_fault(key, existing, fresh, signature)
        return self._keep(key, fresh, signature, obs.message_id)

    def _clear(
        self,
        key: str,
        existing: _Stored | None,
        fresh: Outcome,
        obs: _Obs,
        signature: str,
    ) -> Outcome:
        if existing is None or not existing.outcome.recovery_required:
            raise fault("rejected", "no latched recovery to clear")
        new_ground = (
            obs.present
            and obs.flight_state == "grounded"
            and isinstance(obs.message_id, str)
            and obs.message_id != ""
            and obs.message_id != existing.observation_id
        )
        if not new_ground or fresh.landing_status != "verified" or fresh.recovery_required:
            rejected = replace(
                existing.outcome,
                status="failed",
                error_code="rejected",
                error_detail=_CLEAR_REASON,
                clear_rejected=True,
                cleared=False,
                replayed=False,
                record_count=len(self._stored),
            )
            return rejected
        cleared = replace(
            fresh,
            record_id=existing.outcome.record_id,
            goal_event_id=existing.outcome.goal_event_id or fresh.goal_event_id,
            goal_status=existing.outcome.goal_status
            if existing.outcome.goal_status == "reached"
            else fresh.goal_status,
            cleared=True,
            clear_rejected=False,
            replayed=False,
            record_count=len(self._stored),
        )
        cleared = _with_record(cleared)
        self._stored[key] = _Stored(signature, obs.message_id, cleared)
        return replace(cleared, record_count=len(self._stored))

    def _keep_fault(
        self,
        key: str,
        existing: _Stored,
        fresh: Outcome,
        signature: str,
    ) -> Outcome:
        """A later goal or picture updates the same record and leaves the fault."""
        goal_status = existing.outcome.goal_status
        goal_event_id = existing.outcome.goal_event_id
        goal_sent_at = existing.outcome.goal_sent_at
        if fresh.goal_status == "reached":
            goal_status = "reached"
            goal_event_id = fresh.goal_event_id
            goal_sent_at = fresh.goal_sent_at
        merged = replace(
            existing.outcome,
            goal_status=goal_status,
            goal_event_id=goal_event_id,
            goal_sent_at=goal_sent_at,
            goal_timestamp_ignored=goal_sent_at is not None,
            picture_ignored=existing.outcome.picture_ignored or fresh.picture_ignored,
            replayed=False,
            record_count=len(self._stored),
        )
        merged = _with_record(merged)
        self._stored[key] = _Stored(signature, existing.observation_id, merged)
        return merged

    def _keep(
        self,
        key: str,
        fresh: Outcome,
        signature: str,
        observation_id: str | None,
    ) -> Outcome:
        self._stored[key] = _Stored(signature, observation_id, fresh)
        stored = replace(fresh, record_count=len(self._stored))
        stored = _with_record(stored)
        self._stored[key] = _Stored(signature, observation_id, stored)
        return stored


def _views(incoming: Incoming) -> tuple[_Goal, _Land, _Ack, _Obs]:
    goal = _goal(incoming.goal_event)
    land = _land(incoming.land_command)
    ack = _ack(incoming.land_ack, land)
    obs = _observation(incoming.observation)
    return goal, land, ack, obs


def _classify(
    goal: _Goal,
    land: _Land,
    ack: _Ack,
    obs: _Obs,
    incoming: Incoming,
) -> Outcome:
    goal_status = "reached" if goal.reached else "not_reached"
    command_id = land.command_id if land.issued else None
    identity = _record_id(goal.message_id if goal.reached else None, command_id)
    mission_id = goal.mission_id or land.mission_id or obs.mission_id
    epoch = goal.epoch if goal.reached else land.epoch
    if epoch is None:
        epoch = land.epoch
    track_id = goal.track_id or land.track_id
    beacon_epoch = land.beacon_epoch if land.beacon_epoch is not None else obs.beacon_epoch
    landing_status, recovery, device_recovery, detail, fault_name, event_name = _landing(
        land, ack, obs
    )
    picture_ignored = recovery and obs.frame_id is not None
    timestamp_ignored = recovery and goal.sent_at is not None
    blocked = recovery
    status = "blocked" if blocked else "ok"
    error_code = "recovery_required" if blocked else None
    outcome = Outcome(
        status=status,
        error_code=error_code,
        error_detail=detail if blocked else None,
        goal_status=goal_status,
        landing_status=landing_status,
        recovery_required=recovery,
        device_recovery_required=device_recovery,
        next_mission_blocked=recovery,
        dog_recommendation=DOG_HOLD,
        issued_commands=(),
        search_commands=(),
        record_id=identity,
        record_count=0,
        replayed=False,
        clear_rejected=False,
        cleared=False,
        goal_event_id=goal.message_id if goal.reached else None,
        land_command_id=command_id,
        land_message_id=land.message_id if land.issued else None,
        mission_id=mission_id,
        epoch=epoch,
        track_id=track_id,
        beacon_epoch=beacon_epoch,
        frame_id=obs.frame_id,
        camera_epoch=obs.camera_epoch,
        map_epoch=obs.map_epoch,
        goal_sent_at=goal.sent_at if goal.reached else None,
        observation_id=obs.message_id,
        picture_ignored=picture_ignored,
        goal_timestamp_ignored=timestamp_ignored,
        goal_invented=False,
        landing_event_name=event_name,
        fault_name=fault_name,
        land_ack_accepted=ack.matches and landing_status == "verified",
        foreign_command_id=land.foreign_command_id,
        observation_not_landing=not land.issued and obs.present,
        record={},
        signature="",
    )
    signed = replace(outcome, signature=_signature(incoming, goal, land, ack, obs))
    return _with_record(signed)


def _landing(
    land: _Land,
    ack: _Ack,
    obs: _Obs,
) -> tuple[str, bool, bool, str | None, str | None, str | None]:
    if not land.issued:
        return "not_attempted", False, False, None, None, None
    if not ack.matches or ack.state is None:
        return (
            "unverified",
            True,
            True,
            "land command has no matching acknowledgement",
            "missing_land_ack",
            "landing_unverified",
        )
    if ack.state == "unknown":
        return (
            "unverified",
            True,
            True,
            _UNKNOWN_REASON,
            "landing_unknown",
            "landing_unverified",
        )
    if ack.state in _FAILED_ACK:
        return (
            "failed",
            True,
            True,
            "land acknowledgement failed",
            "landing_failed",
            "landing_failed",
        )
    completed = ack.state == "completed" and ack.verified is True
    if not completed or ack.observed_motion != "grounded":
        if obs.flight_state == "airborne" or ack.observed_motion == "airborne":
            return (
                "contradicted",
                True,
                True,
                "flight_state contradicts the completed land acknowledgement",
                "flight_state_airborne",
                "landing_unverified",
            )
        return (
            "unverified",
            True,
            True,
            "land acknowledgement is not verified grounded",
            "landing_unverified",
            "landing_unverified",
        )
    if not obs.present or obs.flight_state is None:
        return (
            "unverified",
            True,
            True,
            "flight_state was not observed",
            "flight_state_missing",
            "landing_unverified",
        )
    if obs.flight_state == "grounded":
        return "verified", False, False, None, None, None
    if obs.flight_state == "airborne":
        return (
            "contradicted",
            True,
            True,
            "flight_state contradicts the completed land acknowledgement",
            "flight_state_airborne",
            "landing_unverified",
        )
    return (
        "unverified",
        True,
        True,
        "flight_state is unknown",
        "flight_state_unknown",
        "landing_unverified",
    )


def _with_record(outcome: Outcome) -> Outcome:
    message_id = outcome.goal_event_id or outcome.land_message_id
    record = freeze_map(
        {
            "record_id": outcome.record_id,
            "message_id": message_id,
            "mission_id": outcome.mission_id,
            "epoch": outcome.epoch,
            "command_id": outcome.land_command_id,
            "goal_event_id": outcome.goal_event_id,
            "land_command_id": outcome.land_command_id,
            "land_message_id": outcome.land_message_id,
            "goal_status": outcome.goal_status,
            "landing_status": outcome.landing_status,
            "recovery_required": outcome.recovery_required,
            "device_recovery_required": outcome.device_recovery_required,
            "track_id": outcome.track_id,
            "beacon_epoch": outcome.beacon_epoch,
            "frame_id": outcome.frame_id,
            "camera_epoch": outcome.camera_epoch,
            "map_epoch": outcome.map_epoch,
            "request_id": None,
            "goal_sent_at": outcome.goal_sent_at,
            "observation_id": outcome.observation_id,
            "physical_retrieval": PHYSICAL_RETRIEVAL,
            "software_retrieved": False,
        }
    )
    return replace(outcome, record=record)


def _new_verified_landing(existing: _Stored, fresh: Outcome, obs: _Obs) -> bool:
    """A new grounded observation can verify landing. The old picture cannot."""
    return (
        fresh.landing_status == "verified"
        and fresh.recovery_required is False
        and obs.present
        and obs.flight_state == "grounded"
        and isinstance(obs.message_id, str)
        and obs.message_id != ""
        and obs.message_id != existing.observation_id
    )


def _storage_key(land: _Land, goal: _Goal) -> str:
    if land.issued and land.command_id is not None:
        return f"land:{land.command_id}"
    if goal.reached and goal.message_id is not None:
        return f"goal:{goal.message_id}"
    return "idle"


def _record_id(goal_id: str | None, command_id: str | None) -> str:
    return f"recovery:{goal_id or '-'}:{command_id or '-'}"


def _signature(
    incoming: Incoming,
    goal: _Goal,
    land: _Land,
    ack: _Ack,
    obs: _Obs,
) -> str:
    parts = (
        goal.message_id or "",
        "1" if goal.reached else "0",
        land.command_id or "",
        land.foreign_command_id or "",
        "1" if land.issued else "0",
        ack.message_id or "",
        ack.state or "",
        "" if ack.verified is None else ("1" if ack.verified else "0"),
        ack.observed_motion or "",
        "1" if ack.matches else "0",
        obs.message_id or "",
        obs.flight_state or "",
        "1" if incoming.attempt_clear else "0",
        ",".join(incoming.ignored_actions),
    )
    return "|".join(parts)


def _same_mission(goal: _Goal, land: _Land, ack: _Ack, obs: _Obs) -> None:
    missions = [
        item
        for item in (goal.mission_id, land.mission_id, ack.mission_id, obs.mission_id)
        if item is not None
    ]
    if len(set(missions)) > 1:
        raise fault("invalid_input", "recovery messages name more than one mission")
    if goal.reached and land.issued and goal.epoch is not None and land.epoch is not None:
        if goal.epoch != land.epoch:
            raise fault("invalid_input", "goal and land command epochs differ")


def _goal(message: Mapping[str, object] | None) -> _Goal:
    if message is None:
        return _Goal(False, None, None, None, None, None, None)
    envelope = _envelope(message, "mission.event", "goal_event")
    payload = _payload(envelope)
    event = _text(payload.get("event"), "goal event")
    outcome = payload.get("outcome")
    if outcome is not None and not isinstance(outcome, str):
        raise fault("invalid_input", "goal outcome must be a string or null")
    reached = event == "demo_goal_reached" and outcome == "completed"
    stated = payload.get("device_recovery_required")
    if stated is not None:
        stated = require_bool(stated, label="device_recovery_required")
    track = _optional_text(_details(payload).get("track_id"), "track_id")
    return _Goal(
        reached=reached,
        message_id=_text(envelope.get("message_id"), "message_id"),
        mission_id=_text(envelope.get("mission_id"), "mission_id"),
        epoch=_whole(envelope.get("epoch"), "epoch"),
        sent_at=_text(envelope.get("sent_at"), "sent_at"),
        track_id=track,
        stated_recovery=stated,
    )


def _land(message: Mapping[str, object] | None) -> _Land:
    empty = _Land(False, None, None, None, None, None, None, None, None)
    if message is None:
        return empty
    envelope = _envelope(message, "drone.command", "land_command")
    payload = _payload(envelope)
    action = _text(payload.get("action"), "action")
    command_id = _text(payload.get("command_id"), "command_id")
    if action != "land":
        return _Land(
            False,
            None,
            None,
            _text(envelope.get("mission_id"), "mission_id"),
            _whole(envelope.get("epoch"), "epoch"),
            _optional_whole(payload.get("beacon_epoch"), "beacon_epoch"),
            _optional_text(payload.get("track_id"), "track_id"),
            command_id,
            action,
        )
    return _Land(
        True,
        command_id,
        _text(envelope.get("message_id"), "message_id"),
        _text(envelope.get("mission_id"), "mission_id"),
        _whole(envelope.get("epoch"), "epoch"),
        _optional_whole(payload.get("beacon_epoch"), "beacon_epoch"),
        _optional_text(payload.get("track_id"), "track_id"),
        None,
        None,
    )


def _ack(message: Mapping[str, object] | None, land: _Land) -> _Ack:
    if message is None:
        return _Ack(False, False, None, None, None, None, None, None, None)
    envelope = _envelope(message, "command.ack", "land_ack")
    payload = _payload(envelope)
    command_id = _text(payload.get("command_id"), "command_id")
    state = _text(payload.get("state"), "state")
    if state not in _ACK_STATES:
        raise fault("invalid_input", "ack state is not allowed")
    if "verified" not in payload:
        raise fault("invalid_input", "ack verified is required")
    verified = require_bool(payload.get("verified"), label="verified")
    motion = _text(payload.get("observed_motion"), "observed_motion")
    if motion not in _MOTIONS:
        raise fault("invalid_input", "observed_motion is not allowed")
    correlation = envelope.get("correlation_id")
    if correlation is not None and not isinstance(correlation, str):
        raise fault("invalid_input", "correlation_id must be a string or null")
    matches = bool(
        land.issued
        and land.command_id == command_id
        and (correlation is None or correlation == land.message_id)
    )
    return _Ack(
        True,
        matches,
        _text(envelope.get("message_id"), "message_id"),
        _text(envelope.get("mission_id"), "mission_id"),
        command_id,
        state,
        verified,
        motion,
        _text(payload.get("observed_at"), "observed_at"),
    )


def _observation(message: Mapping[str, object] | None) -> _Obs:
    if message is None:
        return _Obs(False, None, None, None, None, None, None, None)
    envelope = _envelope(message, "drone.observation", "observation")
    payload = _payload(envelope)
    flight = _text(payload.get("flight_state"), "flight_state")
    if flight not in _FLIGHT:
        raise fault("invalid_input", "flight_state is not allowed")
    frame = payload.get("frame")
    frame_id: str | None = None
    camera_epoch: int | None = None
    if frame is not None:
        frame_map = _object(frame, "frame")
        frame_id = _optional_text(frame_map.get("frame_id"), "frame_id")
        camera_epoch = _optional_whole(frame_map.get("camera_epoch"), "camera_epoch")
    beacon = payload.get("beacon")
    beacon_epoch: int | None = None
    if isinstance(beacon, Mapping):
        beacon_epoch = _optional_whole(beacon.get("beacon_epoch"), "beacon_epoch")
    pose = payload.get("pose")
    map_epoch: int | None = None
    if isinstance(pose, Mapping):
        map_epoch = _optional_whole(pose.get("map_epoch"), "map_epoch")
    return _Obs(
        True,
        _text(envelope.get("message_id"), "message_id"),
        _text(envelope.get("mission_id"), "mission_id"),
        flight,
        frame_id,
        camera_epoch,
        beacon_epoch,
        map_epoch,
    )


def _envelope(message: Mapping[str, object], kind: str, label: str) -> Mapping[str, object]:
    if isinstance(message, str) or not isinstance(message, Mapping):
        raise fault("invalid_input", f"{label} must be an object")
    if message.get("protocol_version") != "2.0-draft":
        raise fault("invalid_input", f"{label} protocol_version must be 2.0-draft")
    found = _text(message.get("kind"), "kind")
    if found != kind:
        raise fault("invalid_input", f"{label} kind must be {kind}")
    if "simulated" in message:
        require_bool(message.get("simulated"), label="simulated")
    return message


def _payload(message: Mapping[str, object]) -> Mapping[str, object]:
    return _object(message.get("payload"), "payload")


def _details(payload: Mapping[str, object]) -> Mapping[str, object]:
    raw = payload.get("details")
    if raw is None:
        return {}
    return _object(raw, "details")


def _object(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, str) or not isinstance(value, Mapping):
        raise fault("invalid_input", f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{label} must be a string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _whole(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise fault("invalid_input", f"{label} must be an integer")
    return value


def _optional_whole(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _whole(value, label)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise fault("invalid_input", "duplicate json key")
        found[key] = value
    return found


def ignored_actions(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise fault("invalid_input", "ignored_actions must be a list of strings")
    names: list[str] = []
    for item in value:
        names.append(_text(item, "ignored action"))
    return tuple(names)
