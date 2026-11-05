"""Dog command acknowledgement lifecycle. This module never sends a dog.command."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from patrol.ground.kernel.contracts import (
    FeatureResult,
    GroundError,
    GroundEvent,
    Ticket,
)
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_ENVELOPE = frozenset(
    {
        "protocol_version",
        "message_id",
        "mission_id",
        "epoch",
        "seq",
        "sent_at",
        "source",
        "destination",
        "kind",
        "correlation_id",
        "expires_at",
        "simulated",
        "payload",
    }
)
_COMMAND_PAYLOAD = frozenset(
    {
        "command_id",
        "proposal_id",
        "action",
        "lease_ms",
        "motion",
        "track_id",
        "beacon_epoch",
        "safety_snapshot_id",
        "reason",
    }
)
_MOTION = frozenset(
    {
        "frame_id",
        "linear_x_m_s",
        "linear_y_m_s",
        "angular_z_rad_s",
        "duration_ms",
        "candidate_id",
        "snapshot_id",
        "map_epoch",
    }
)
_ACK_PAYLOAD = frozenset(
    {
        "command_id",
        "state",
        "reason_code",
        "observed_at",
        "verified",
        "observed_motion",
        "detail",
    }
)
_SOURCES = frozenset({"ground", "drone", "dog", "pi", "vision", "operator"})
_DESTINATIONS = frozenset({"ground", "drone", "dog", "pi", "vision", "all"})
_ACTIONS = frozenset(
    {
        "stand",
        "move_local",
        "turn",
        "halt",
        "play_warning",
        "follow",
        "stop",
        "return_home",
        "approach",
    }
)
_STILL_ACTIONS = frozenset(
    {"halt", "play_warning", "follow", "stop", "return_home", "approach"}
)
_COMMAND_OPTIONAL = frozenset({"warning_id", "text", "standoff_m"})
_ACK_STATES = frozenset(
    {"accepted", "running", "completed", "rejected", "cancelled", "failed", "unknown"}
)
_TERMINAL = frozenset({"completed", "rejected", "cancelled", "failed", "unknown"})
_MOTIONS = frozenset({"stationary", "moving", "airborne", "grounded", "unknown"})
_MOVING = frozenset({"moving", "airborne"})
_RANK = {"accepted": 1, "running": 2}
_READINESS_KEYS = frozenset({"stationary", "reason_code", "observed_after_window"})


@dataclass(frozen=True)
class IssuedCommand:
    message_id: str
    mission_id: str
    epoch: int
    command_id: str
    action: str
    lease_s: float
    track_id: str | None
    beacon_epoch: int | None
    map_epoch: int | None


@dataclass(frozen=True)
class Ack:
    message_id: str
    mission_id: str
    epoch: int
    seq: int
    correlation_id: str
    command_id: str
    state: str
    reason_code: str
    verified: bool
    observed_motion: str


@dataclass
class CommandRecord:
    command_id: str
    message_id: str
    mission_id: str
    epoch: int
    action: str
    lease_s: float
    deadline_mono: float
    track_id: str | None
    beacon_epoch: int | None
    map_epoch: int | None
    state: str = "pending"
    verified: bool | None = None
    observed_motion: str = ""
    reason_code: str = ""
    stopped: bool = False
    motion_occurred: bool = False
    active_command: bool = True
    query_command: str | None = None
    stop_cause: str = "none"
    event_count: int = 0
    terminal_events: int = 0
    faulted: bool = False
    fingerprint: str = ""
    last_seq: int = -1
    timed_out: bool = False
    ack_message_id: str = ""
    correlation_id: str = ""


@dataclass(frozen=True)
class Outcome:
    status: str
    error: GroundError | None
    data: Mapping[str, object]
    events: tuple[GroundEvent, ...]

    def as_result(self) -> FeatureResult:
        return FeatureResult(self.status, self.data, self.events, self.error)


def as_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise fault("invalid_input", f"{label} must be an object")
    typed: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise fault("invalid_input", f"{label} keys must be strings")
        typed[key] = item
    return typed


class DogAckTracker:
    """One lifecycle per command id. A later ack cannot authorize another move."""

    def __init__(self, monotonic: Callable[[], float]) -> None:
        self._monotonic = monotonic
        self.records: dict[str, CommandRecord] = {}

    def view(self, command_id: str) -> Mapping[str, object] | None:
        record = self.records.get(command_id)
        if record is None:
            return None
        return self._data(record)

    def track(
        self,
        command: object,
        ack: object,
        ticket: Ticket | None,
        readiness: object = None,
    ) -> Outcome:
        issued = parse_command(command)
        parsed = parse_ack(ack)
        problem = _pair_problem(issued, parsed)
        if problem is not None:
            return self._rejected(problem, issued, parsed.command_id)
        ready = None if readiness is None else parse_readiness(readiness)
        existing = self.records.get(issued.command_id)
        if existing is not None and existing.message_id != issued.message_id:
            return self._repeat(existing)
        record = existing if existing is not None else self._bind(issued)
        if ready is not None and not _window_open(record, self._monotonic(), ready):
            ready = None
        return self._apply(record, parsed, ticket, ready)

    def timeout(self, command: object, ticket: Ticket | None) -> Outcome:
        issued = parse_command(command)
        existing = self.records.get(issued.command_id)
        if existing is not None and existing.message_id != issued.message_id:
            return self._repeat(existing)
        record = existing if existing is not None else self._bind(issued)
        if record.faulted:
            return self._fault_outcome(record, idempotent=True)
        if _terminal_settled(record):
            view = self._data(record, idempotent=True)
            return _ok(view, ())
        if self._monotonic() < record.deadline_mono:
            return _ok(self._data(record), ())
        if record.timed_out:
            return _ok(self._data(record, idempotent=True), ())
        record.timed_out = True
        record.query_command = record.command_id
        record.stop_cause = "timeout"
        record.active_command = True
        event = _lifecycle_event(record, ticket, "state_changed", "timed_out")
        record.event_count += 1
        return _ok(self._data(record), (event,))

    def observe(self, command: object, readiness: object, ticket: Ticket | None) -> Outcome:
        issued = parse_command(command)
        ready = parse_readiness(readiness)
        record = self.records.get(issued.command_id)
        if record is None or record.message_id != issued.message_id:
            error = _error("rejected", "readiness does not match a bound dog command")
            return self._rejected(error, issued, issued.command_id)
        if not _window_open(record, self._monotonic(), ready):
            return _ok(self._data(record), ())
        event = self._readiness_event(record, ready, ticket)
        if event is None:
            return _ok(self._data(record), ())
        record.event_count += 1
        return _ok(self._data(record), (event,))

    def _bind(self, issued: IssuedCommand) -> CommandRecord:
        record = CommandRecord(
            command_id=issued.command_id,
            message_id=issued.message_id,
            mission_id=issued.mission_id,
            epoch=issued.epoch,
            action=issued.action,
            lease_s=issued.lease_s,
            deadline_mono=self._monotonic() + issued.lease_s,
            track_id=issued.track_id,
            beacon_epoch=issued.beacon_epoch,
            map_epoch=issued.map_epoch,
        )
        self.records[issued.command_id] = record
        return record

    def _apply(
        self,
        record: CommandRecord,
        ack: Ack,
        ticket: Ticket | None,
        readiness: Readiness | None,
    ) -> Outcome:
        fingerprint = _fingerprint(ack)
        if record.faulted:
            same = fingerprint == record.fingerprint
            return self._fault_outcome(record, idempotent=same)
        if record.fingerprint == fingerprint and record.state == ack.state:
            return _ok(self._data(record, idempotent=True), ())
        if record.last_seq >= 0 and ack.seq < record.last_seq:
            error = _error("rejected", "stale sequence")
            return _failed(error, self._data(record))
        if record.fingerprint and record.state == ack.state and fingerprint != record.fingerprint:
            return self._conflict(record, ack, ticket)
        if ack.state not in _TERMINAL and record.state in _TERMINAL:
            return self._conflict(record, ack, ticket)
        terminal_conflict = (
            record.state in _TERMINAL
            and ack.state in _TERMINAL
            and fingerprint != record.fingerprint
        )
        if terminal_conflict:
            return self._conflict(record, ack, ticket)
        previous = _RANK.get(record.state, 0)
        incoming = _RANK.get(ack.state, 3 if ack.state in _TERMINAL else 0)
        if record.state not in {"", "pending"} and incoming < previous:
            return self._conflict(record, ack, ticket)
        if ack.reason_code == "expired_command" and ack.observed_motion in _MOVING:
            return self._conflict(record, ack, ticket)
        _store_ack(record, ack, fingerprint)
        event = _event_for(record, ticket)
        record.event_count += 1
        if ack.state in _TERMINAL:
            record.terminal_events += 1
        events: list[GroundEvent] = [event]
        if readiness is not None:
            extra = self._readiness_event(record, readiness, ticket)
            if extra is not None:
                record.event_count += 1
                events.append(extra)
        return _ok(self._data(record), tuple(events))

    def _readiness_event(
        self,
        record: CommandRecord,
        readiness: Readiness,
        ticket: Ticket | None,
    ) -> GroundEvent | None:
        if readiness.stationary is False and record.stopped:
            record.stopped = False
            record.stop_cause = "readiness_disagrees"
            record.active_command = True
            return _lifecycle_event(record, ticket, "state_changed", "readiness_disagrees")
        if readiness.reason_code and _lidar(readiness.reason_code) and record.stop_cause != "lidar":
            record.stop_cause = "lidar"
            return _lifecycle_event(record, ticket, "state_changed", "lidar")
        return None

    def _conflict(self, record: CommandRecord, ack: Ack, ticket: Ticket | None) -> Outcome:
        record.faulted = True
        record.fingerprint = _fingerprint(ack)
        record.last_seq = ack.seq
        record.stopped = False
        record.stop_cause = "conflict"
        record.active_command = True
        record.ack_message_id = ack.message_id
        error = _error(
            "unsafe_state",
            "conflicting terminal acknowledgement",
            recovery=True,
        )
        event = _lifecycle_event(record, ticket, "operation_failed", f"{record.state}/{ack.state}")
        record.event_count += 1
        return _failed(error, self._data(record), (event,))

    def _fault_outcome(self, record: CommandRecord, *, idempotent: bool) -> Outcome:
        error = _error(
            "unsafe_state",
            "conflicting terminal acknowledgement",
            recovery=True,
        )
        return _failed(error, self._data(record, idempotent=idempotent))

    def _repeat(self, record: CommandRecord) -> Outcome:
        error = _error("rejected", "repeated command id is not a new move")
        return _failed(error, self._data(record, repeated=True))

    def _rejected(self, error: GroundError, issued: IssuedCommand, command_id: str) -> Outcome:
        existing = self.records.get(issued.command_id)
        if existing is not None and command_id == issued.command_id:
            return _failed(error, self._data(existing))
        return _failed(error, self._data(None, command_id=command_id))

    def _data(
        self,
        record: CommandRecord | None,
        *,
        idempotent: bool = False,
        repeated: bool = False,
        command_id: str = "",
    ) -> Mapping[str, object]:
        if record is None:
            body: dict[str, object] = {
                "command_id": command_id,
                "message_id": "",
                "command_message_id": "",
                "correlation_id": "",
                "mission_id": "",
                "epoch": None,
                "action": "",
                "state": "none",
                "stopped": False,
                "verified": None,
                "observed_motion": "",
                "reason_code": "",
                "motion_occurred": False,
                "active_command": False,
                "query_command": None,
                "stop_cause": "none",
                "event_count": 0,
                "terminal_events": 0,
                "idempotent": False,
                "timed_out": False,
                "faulted": False,
                "bound": False,
                "track_id": None,
                "beacon_epoch": None,
                "map_epoch": None,
            }
        else:
            body = {
                "command_id": record.command_id,
                "message_id": record.ack_message_id or record.message_id,
                "command_message_id": record.message_id,
                "correlation_id": record.correlation_id or record.message_id,
                "mission_id": record.mission_id,
                "epoch": record.epoch,
                "action": record.action,
                "state": record.state,
                "stopped": record.stopped,
                "verified": record.verified,
                "observed_motion": record.observed_motion,
                "reason_code": record.reason_code,
                "motion_occurred": record.motion_occurred,
                "active_command": record.active_command,
                "query_command": record.query_command,
                "stop_cause": record.stop_cause,
                "event_count": record.event_count,
                "terminal_events": record.terminal_events,
                "idempotent": idempotent,
                "timed_out": record.timed_out,
                "faulted": record.faulted,
                "bound": True,
                "track_id": record.track_id,
                "beacon_epoch": record.beacon_epoch,
                "map_epoch": record.map_epoch,
            }
        body.update(_invariants(repeated))
        body["block_next_step"] = self._blocked()
        return freeze_map(body)

    def _blocked(self) -> bool:
        return any(item.faulted or item.active_command for item in self.records.values())


@dataclass(frozen=True)
class Readiness:
    stationary: bool
    reason_code: str
    after_window: bool


def parse_command(value: object) -> IssuedCommand:
    envelope = _envelope(value, "dog.command")
    if envelope["source"] != "ground" or envelope["destination"] != "dog":
        raise fault("invalid_input", "dog command must be sent from ground to the dog")
    payload = as_dict(envelope["payload"], "dog command payload")
    _allow(payload, _COMMAND_PAYLOAD, _COMMAND_OPTIONAL, "dog command payload")
    action = _token(payload["action"], "action", _ACTIONS)
    lease_ms = _bounded_int(payload["lease_ms"], "lease_ms", minimum=1, maximum=500)
    motion = payload["motion"]
    map_epoch: int | None
    if action in _STILL_ACTIONS:
        if motion is not None:
            raise fault("invalid_input", f"{action} motion must be null")
        map_epoch = None
        _presence_fields(payload, action)
    else:
        parsed_motion = _motion(motion)
        map_epoch = parsed_motion
    track = _optional_text(payload["track_id"], "track_id")
    beacon = _optional_int(payload["beacon_epoch"], "beacon_epoch")
    _text(payload["safety_snapshot_id"], "safety_snapshot_id")
    _optional_text(payload["proposal_id"], "proposal_id")
    if not isinstance(payload["reason"], str):
        raise fault("invalid_input", "reason must be a string")
    return IssuedCommand(
        message_id=_text(envelope["message_id"], "message_id"),
        mission_id=_text(envelope["mission_id"], "mission_id"),
        epoch=_whole(envelope["epoch"], "epoch"),
        command_id=_text(payload["command_id"], "command_id"),
        action=action,
        lease_s=lease_ms / 1000.0,
        track_id=track,
        beacon_epoch=beacon,
        map_epoch=map_epoch,
    )


def parse_ack(value: object) -> Ack:
    envelope = _envelope(value, "command.ack")
    if envelope["source"] != "dog" or envelope["destination"] != "ground":
        raise fault("invalid_input", "dog acknowledgement must be sent from the dog to ground")
    correlation = envelope["correlation_id"]
    if not isinstance(correlation, str):
        raise fault("invalid_input", "ack correlation id must match the command message")
    payload = as_dict(envelope["payload"], "command.ack payload")
    _exact(payload, _ACK_PAYLOAD, "command.ack payload")
    verified = payload["verified"]
    if not isinstance(verified, bool):
        raise fault("invalid_input", "verified must be a boolean")
    detail = payload["detail"]
    if detail is not None and not isinstance(detail, str):
        raise fault("invalid_input", "detail must be a string or null")
    return Ack(
        message_id=_text(envelope["message_id"], "message_id"),
        mission_id=_text(envelope["mission_id"], "mission_id"),
        epoch=_whole(envelope["epoch"], "epoch"),
        seq=_whole(envelope["seq"], "seq"),
        correlation_id=correlation,
        command_id=_text(payload["command_id"], "command_id"),
        state=_token(payload["state"], "state", _ACK_STATES),
        reason_code=_text(payload["reason_code"], "reason_code"),
        verified=verified,
        observed_motion=_token(payload["observed_motion"], "observed_motion", _MOTIONS),
    )


def parse_readiness(value: object) -> Readiness:
    if isinstance(value, dict) and value.get("kind") == "dog.observation":
        envelope = _envelope(value, "dog.observation")
        if envelope["source"] != "dog" or envelope["destination"] != "ground":
            raise fault("invalid_input", "dog observation must be sent from the dog to ground")
        payload = as_dict(envelope["payload"], "dog observation payload")
        stationary = payload.get("stationary")
        if not isinstance(stationary, bool):
            raise fault("invalid_input", "stationary must be a boolean")
        return Readiness(stationary, "", True)
    body = as_dict(value, "readiness")
    extra = set(body) - _READINESS_KEYS
    if extra or "stationary" not in body:
        raise fault("invalid_input", "readiness keys do not match the contract")
    stationary = body["stationary"]
    if not isinstance(stationary, bool):
        raise fault("invalid_input", "stationary must be a boolean")
    reason = ""
    if "reason_code" in body:
        reason = _text(body["reason_code"], "reason_code")
    after = False
    if "observed_after_window" in body:
        flag = body["observed_after_window"]
        if not isinstance(flag, bool):
            raise fault("invalid_input", "observed_after_window must be a boolean")
        after = flag
    return Readiness(stationary, reason, after)


def _store_ack(record: CommandRecord, ack: Ack, fingerprint: str) -> None:
    record.state = ack.state
    record.verified = ack.verified
    record.observed_motion = ack.observed_motion
    record.reason_code = ack.reason_code
    record.ack_message_id = ack.message_id
    record.correlation_id = ack.correlation_id
    record.fingerprint = fingerprint
    record.last_seq = ack.seq
    if ack.observed_motion in _MOVING and ack.reason_code != "expired_command":
        record.motion_occurred = True
    if ack.reason_code == "expired_command":
        record.motion_occurred = False
        record.active_command = False
        record.stopped = False
        record.stop_cause = "expired_command"
        return
    if ack.state == "completed" and ack.verified and ack.observed_motion == "stationary":
        record.stopped = True
        record.active_command = False
        record.stop_cause = "lidar" if _lidar(ack.reason_code) else "verified_stationary"
        return
    record.stopped = False
    record.active_command = True
    if ack.state == "completed" and not ack.verified:
        record.stop_cause = "unverified"
    elif ack.state == "completed":
        record.stop_cause = "not_stationary"
    elif ack.state == "rejected":
        record.stop_cause = "rejected"
    elif _lidar(ack.reason_code):
        record.stop_cause = "lidar"
    else:
        record.stop_cause = ack.state


def _event_for(record: CommandRecord, ticket: Ticket | None) -> GroundEvent:
    if record.stopped and record.stop_cause in {"verified_stationary", "lidar"}:
        return _lifecycle_event(record, ticket, "operation_completed", record.stop_cause)
    if record.reason_code == "expired_command":
        return _lifecycle_event(record, ticket, "state_changed", "expired_command")
    return _lifecycle_event(record, ticket, "state_changed", record.state)


def _lifecycle_event(
    record: CommandRecord,
    ticket: Ticket | None,
    kind: str,
    phase: str,
) -> GroundEvent:
    payload: dict[str, object] = {
        "message_id": record.ack_message_id or record.message_id,
        "mission_id": record.mission_id,
        "epoch": record.epoch,
        "command_id": record.command_id,
        "correlation_id": record.correlation_id or record.message_id,
        "state": record.state if phase != "timed_out" else "timed_out",
        "reason_code": record.reason_code or phase,
        "observed_motion": record.observed_motion or "unknown",
        "stop_cause": record.stop_cause,
        "phase": phase,
        "target_arrival": False,
        "demo_goal_reached": False,
        "query_command": record.query_command is not None,
    }
    if record.verified is not None:
        payload["verified"] = record.verified
    if record.track_id is not None:
        payload["track_id"] = record.track_id
    if record.beacon_epoch is not None:
        payload["beacon_epoch"] = record.beacon_epoch
    if record.map_epoch is not None:
        payload["map_epoch"] = record.map_epoch
    return GroundEvent(kind, ticket, freeze_map(payload))


def _pair_problem(issued: IssuedCommand, ack: Ack) -> GroundError | None:
    if ack.command_id != issued.command_id:
        return _error("rejected", "foreign command id")
    if ack.epoch != issued.epoch:
        return _error("epoch_mismatch", "ack epoch does not match the command")
    if ack.mission_id != issued.mission_id:
        return _error("stale_ticket", "ack mission does not match the command")
    if ack.correlation_id != issued.message_id:
        return _error("validation_failed", "ack correlation id does not match the command message")
    return None


def _window_open(record: CommandRecord, now: float, readiness: Readiness) -> bool:
    if readiness.after_window:
        return True
    return now >= record.deadline_mono


def _terminal_settled(record: CommandRecord) -> bool:
    if record.faulted:
        return True
    if record.reason_code == "expired_command":
        return True
    return record.stopped


def _fingerprint(ack: Ack) -> str:
    verified = "true" if ack.verified else "false"
    return f"{ack.state}|{ack.reason_code}|{verified}|{ack.observed_motion}"


def _lidar(reason: str) -> bool:
    token = reason.strip().lower()
    if token in {"lidar_stop", "lidar_clearance", "obstacle", "obstacle_stop", "avoidance_stop"}:
        return True
    return "lidar" in token or "obstacle" in token


def _invariants(repeated: bool) -> dict[str, object]:
    return {
        "proposed_command": None,
        "replacement_command_id": None,
        "commands_issued": 0,
        "demo_goal_reached": False,
        "target_arrival": False,
        "halt_cleared": False,
        "motion_allowed": False,
        "repeated_command": repeated,
    }


def _ok(data: Mapping[str, object], events: tuple[GroundEvent, ...]) -> Outcome:
    return Outcome("ok", None, data, events)


def _failed(
    error: GroundError,
    data: Mapping[str, object],
    events: tuple[GroundEvent, ...] = (),
) -> Outcome:
    return Outcome("failed", error, data, events)


def _error(code: str, detail: str, *, recovery: bool = False) -> GroundError:
    return GroundError(code, detail, recovery)


def _envelope(value: object, kind: str) -> dict[str, object]:
    body = as_dict(value, kind)
    _exact(body, _ENVELOPE, kind)
    if body["protocol_version"] != "2.0-draft":
        raise fault("invalid_input", "protocol_version must be 2.0-draft")
    if body["kind"] != kind:
        raise fault("invalid_input", f"kind must be {kind}")
    source = body["source"]
    destination = body["destination"]
    if source not in _SOURCES or destination not in _DESTINATIONS:
        raise fault("invalid_input", "source or destination is not in the contract")
    _text(body["message_id"], "message_id")
    _text(body["mission_id"], "mission_id")
    _whole(body["epoch"], "epoch")
    _whole(body["seq"], "seq")
    _time(body["sent_at"], "sent_at")
    _optional_time(body["expires_at"], "expires_at")
    correlation = body["correlation_id"]
    if correlation is not None and not isinstance(correlation, str):
        raise fault("invalid_input", "correlation_id must be a string or null")
    if isinstance(correlation, str):
        _text(correlation, "correlation_id")
    if not isinstance(body["simulated"], bool):
        raise fault("invalid_input", "simulated must be a boolean")
    return body


def _motion(value: object) -> int:
    body = as_dict(value, "motion")
    _exact(body, _MOTION, "motion")
    if body["frame_id"] != "dog/base_link":
        raise fault("invalid_input", "motion frame must be dog/base_link")
    _finite(body["linear_x_m_s"], "linear_x_m_s")
    _finite(body["linear_y_m_s"], "linear_y_m_s")
    _finite(body["angular_z_rad_s"], "angular_z_rad_s")
    _bounded_int(body["duration_ms"], "duration_ms", minimum=1, maximum=500)
    _text(body["candidate_id"], "candidate_id")
    _text(body["snapshot_id"], "snapshot_id")
    return _whole(body["map_epoch"], "map_epoch")


def _presence_fields(payload: Mapping[str, object], action: str) -> None:
    if action == "play_warning":
        if "warning_id" in payload:
            _text(payload["warning_id"], "warning_id")
        if "text" in payload:
            _text(payload["text"], "text")
    if action == "follow" and "standoff_m" in payload:
        value = payload["standoff_m"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0
        ):
            raise fault("invalid_input", "standoff_m must be a positive number")


def _allow(
    body: Mapping[str, object],
    required: frozenset[str],
    optional: frozenset[str],
    label: str,
) -> None:
    if set(body) - required - optional or required - set(body):
        raise fault("invalid_input", f"{label} keys do not match the contract")


def _exact(body: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    if set(body) != allowed:
        raise fault("invalid_input", f"{label} keys do not match the contract")


def _token(value: object, label: str, allowed: frozenset[str]) -> str:
    text = _text(value, label)
    if text not in allowed:
        raise fault("invalid_input", f"{label} is not in the contract")
    return text


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise fault("invalid_input", f"{label} must be a short string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _whole(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise fault("invalid_input", f"{label} must be a non-negative integer")
    return value


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _whole(value, label)


def _bounded_int(value: object, label: str, *, minimum: int, maximum: int) -> int:
    number = _whole(value, label)
    if number < minimum or number > maximum:
        raise fault("invalid_input", f"{label} is outside the contract range")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", f"{label} must be numeric")
    if not math.isfinite(float(value)):
        raise fault("invalid_input", f"{label} must be finite")
    return float(value)


def _time(value: object, label: str) -> str:
    text = _text(value, label)
    if _TIME.fullmatch(text) is None:
        raise fault("invalid_input", f"{label} must be an ISO-8601 timestamp")
    return text


def _optional_time(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _time(value, label)

