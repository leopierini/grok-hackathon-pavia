"""Drone command lifecycle. Accepted, running, and final states stay distinct."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from patrol.ground.extensions.g18.messages import (
    AckBody,
    CommandBody,
    Envelope,
    ObservationView,
    parse_ack,
    parse_command,
    parse_observation,
)
from patrol.ground.kernel.contracts import GroundEvent, Ticket
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

_TERMINAL = frozenset({"completed", "rejected", "cancelled", "failed", "unknown"})
_Signature = tuple[str, bool, str, str, str | None, str]


@dataclass
class _Life:
    command_id: str
    command_message_id: str
    mission_id: str
    epoch: int
    action: str
    reply_deadline: float | None = None
    state: str | None = None
    verified: bool | None = None
    observed_motion: str | None = None
    reason_code: str | None = None
    detail: str | None = None
    last_seq: int | None = None
    correlation_id: str | None = None
    ack_message_id: str | None = None
    ack_message_ids: list[str] = field(default_factory=list)
    signatures: dict[str, _Signature] = field(default_factory=dict)
    conflicts: dict[str, _Signature] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    completion_events: int = 0
    query_count: int = 0
    query_open: bool = False
    ignored_local_flag: bool = False
    observation_stale: bool = False
    observation_flight_state: str | None = None
    terminal: bool = False
    recovery_required: bool = False
    blocks_next_mission: bool = False
    grounded: bool = False
    flight_state: str = "unknown"


@dataclass(frozen=True)
class Outcome:
    status: str
    code: str | None
    detail: str
    recovery: bool
    events: tuple[GroundEvent, ...]
    data: Mapping[str, object]


class Tracker:
    """One record per issued drone command_id. This object never sends a command."""

    def __init__(self) -> None:
        self._records: dict[str, _Life] = {}

    def command_ids(self) -> tuple[str, ...]:
        return tuple(self._records)

    def register(
        self,
        command: Mapping[str, object],
        deadline: float,
        ticket: Ticket | None,
    ) -> Outcome:
        _finite(deadline, "reply deadline")
        envelope, body = parse_command(command)
        role = _command_role(envelope)
        if role is not None:
            return self._reject(role[0], role[1], role[2], command_id=body.command_id)
        existing = self._records.get(body.command_id)
        if existing is None:
            created = _new_life(envelope, body, deadline)
            self._records[body.command_id] = created
            return self._finish(created, status="ok", detail="command registered", ticket=ticket)
        if existing.command_message_id != envelope.message_id:
            return self._reject(
                "contract_mismatch",
                "command_id is already bound",
                False,
                command_id=body.command_id,
            )
        return self._finish(
            existing,
            status="ok",
            detail="command already registered",
            duplicate=True,
            ticket=ticket,
        )

    def apply(
        self,
        ack: Mapping[str, object],
        command: Mapping[str, object],
        observation: Mapping[str, object] | None,
        deadline: float | None,
        ticket: Ticket | None,
    ) -> Outcome:
        envelope, body = parse_ack(ack)
        if envelope.source == "dog":
            return self._reject(
                "rejected",
                "dog acknowledgements are tracked by task 24",
                False,
                command_id=body.command_id,
            )
        if envelope.source != "drone" or envelope.destination != "ground":
            return self._reject(
                "contract_mismatch",
                "ack must come from the drone to ground",
                False,
                command_id=body.command_id,
            )
        command_envelope, command_body = parse_command(command)
        role = _command_role(command_envelope)
        if role is not None:
            return self._reject(role[0], role[1], role[2], command_id=body.command_id)
        if body.command_id != command_body.command_id:
            return self._reject(
                "rejected",
                "unknown command_id",
                False,
                command_id=body.command_id,
            )
        if envelope.correlation_id != command_envelope.message_id:
            return self._reject(
                "contract_mismatch",
                "ack is not correlated to the command message",
                False,
                command_id=body.command_id,
            )
        if envelope.mission_id != command_envelope.mission_id:
            return self._reject(
                "contract_mismatch",
                "ack mission does not match the command",
                False,
                command_id=body.command_id,
            )
        if envelope.epoch != command_envelope.epoch:
            return self._reject(
                "epoch_mismatch",
                "ack epoch is stale",
                False,
                command_id=body.command_id,
            )
        observed = _view_observation(observation)
        record = self._bind(command_envelope, command_body, deadline)
        if isinstance(record, Outcome):
            return record
        return self._advance(record, envelope, body, observed, ticket)

    def expire(self, command_id: str, now: float, ticket: Ticket | None) -> Outcome:
        _finite(now, "clock")
        record = self._records.get(command_id)
        if record is None:
            return self._reject("rejected", "unknown command_id", False, command_id=command_id)
        if record.reply_deadline is None:
            return self._reject(
                "invalid_input",
                "reply deadline was not set",
                False,
                command_id=command_id,
                failed=True,
            )
        if record.terminal:
            return self._finish(
                record,
                status="ok",
                detail="command is already terminal",
                ticket=ticket,
            )
        if now < record.reply_deadline:
            return self._finish(record, status="ok", detail="deadline still open", ticket=ticket)
        if record.query_open:
            return self._finish(
                record,
                status="ok",
                detail="query already required",
                duplicate=True,
                ticket=ticket,
            )
        record.query_count += 1
        record.query_open = True
        event = _event(
            "state_changed",
            ticket,
            {
                "command_id": record.command_id,
                "command_message_id": record.command_message_id,
                "query_command": record.command_id,
                "state": record.state,
                "unresolved": True,
            },
        )
        return self._finish(
            record,
            status="ok",
            detail="query required",
            events=(event,),
            ticket=ticket,
        )

    def project(self, command_id: str, ticket: Ticket | None) -> Outcome:
        record = self._records.get(command_id)
        if record is None:
            return self._reject("rejected", "unknown command_id", False, command_id=command_id)
        return self._finish(record, status="ok", detail="lifecycle projection", ticket=ticket)

    def _bind(
        self,
        envelope: Envelope,
        body: CommandBody,
        deadline: float | None,
    ) -> _Life | Outcome:
        if deadline is not None:
            _finite(deadline, "reply deadline")
        existing = self._records.get(body.command_id)
        if existing is None:
            created = _new_life(envelope, body, deadline)
            self._records[body.command_id] = created
            return created
        if existing.command_message_id != envelope.message_id:
            return self._reject(
                "contract_mismatch",
                "command_id is already bound",
                False,
                command_id=body.command_id,
            )
        if existing.reply_deadline is None and deadline is not None:
            existing.reply_deadline = deadline
        return existing

    def _advance(
        self,
        record: _Life,
        envelope: Envelope,
        body: AckBody,
        observation: ObservationView | None,
        ticket: Ticket | None,
    ) -> Outcome:
        signature = _signature(body)
        if envelope.message_id in record.conflicts:
            same = record.conflicts[envelope.message_id] == signature
            return self._finish(
                record,
                status="failed",
                detail="conflicting acknowledgement",
                code="unsafe_state",
                recovery=True,
                conflict=True,
                duplicate=same,
                ticket=ticket,
            )
        previous = record.signatures.get(envelope.message_id)
        if previous is not None:
            if previous != signature:
                record.conflicts[envelope.message_id] = signature
                return self._conflict(record, ticket)
            return self._finish(
                record,
                status="ok",
                detail="duplicate acknowledgement",
                duplicate=True,
                ticket=ticket,
            )
        if record.state is not None and signature == _current_signature(record):
            _remember(record, envelope, signature)
            return self._finish(
                record,
                status="ok",
                detail="duplicate acknowledgement",
                duplicate=True,
                ticket=ticket,
            )
        if record.last_seq is not None and envelope.seq <= record.last_seq:
            return self._reject(
                "stale_ticket",
                "stale sequence",
                False,
                command_id=record.command_id,
            )
        if not _allows(record.state, body.state):
            record.conflicts[envelope.message_id] = signature
            return self._conflict(record, ticket)
        previous_state = record.state
        _remember(record, envelope, signature)
        _store_ack(record, envelope, body, observation)
        events = _transition_events(record, previous_state, body, envelope, ticket)
        if body.state == "unknown":
            if record.blocks_next_mission:
                detail = "landing state is unknown"
            else:
                detail = "execution is unknown"
            return self._finish(
                record,
                status="blocked",
                detail=detail,
                code="recovery_required",
                recovery=True,
                events=events,
                ticket=ticket,
            )
        return self._finish(
            record,
            status="ok",
            detail="acknowledgement recorded",
            events=events,
            ticket=ticket,
        )

    def _conflict(self, record: _Life, ticket: Ticket | None) -> Outcome:
        event = _event(
            "operation_failed",
            ticket,
            {
                "command_id": record.command_id,
                "command_message_id": record.command_message_id,
                "state": record.state,
                "reason": "conflicting final state",
            },
        )
        return self._finish(
            record,
            status="failed",
            detail="conflicting acknowledgement",
            code="unsafe_state",
            recovery=True,
            events=(event,),
            conflict=True,
            ticket=ticket,
        )

    def _reject(
        self,
        code: str,
        detail: str,
        recovery: bool,
        *,
        command_id: str | None,
        failed: bool = False,
    ) -> Outcome:
        status = "failed" if failed or code == "invalid_input" else "blocked"
        record = None if command_id is None else self._records.get(command_id)
        return self._finish(
            record,
            status=status,
            detail=detail,
            code=code,
            recovery=recovery,
            command_id=command_id,
            ticket=None,
        )

    def _finish(
        self,
        record: _Life | None,
        *,
        status: str,
        detail: str,
        ticket: Ticket | None,
        code: str | None = None,
        recovery: bool = False,
        events: tuple[GroundEvent, ...] = (),
        duplicate: bool = False,
        conflict: bool = False,
        command_id: str | None = None,
    ) -> Outcome:
        data = _snapshot(
            record,
            command_ids=tuple(self._records),
            duplicate=duplicate,
            conflict=conflict,
            command_id=command_id,
        )
        return Outcome(status, code, detail, recovery, events, data)


def _new_life(envelope: Envelope, body: CommandBody, deadline: float | None) -> _Life:
    return _Life(
        command_id=body.command_id,
        command_message_id=envelope.message_id,
        mission_id=envelope.mission_id,
        epoch=envelope.epoch,
        action=body.action,
        reply_deadline=deadline,
        correlation_id=envelope.message_id,
    )


def _command_role(envelope: Envelope) -> tuple[str, str, bool] | None:
    if envelope.source != "ground" or envelope.destination != "drone":
        return ("contract_mismatch", "command must come from ground to the drone", False)
    return None


def _view_observation(value: Mapping[str, object] | None) -> ObservationView | None:
    if value is None:
        return None
    return parse_observation(value)


def _signature(body: AckBody) -> _Signature:
    return (
        body.state,
        body.verified,
        body.observed_motion,
        body.reason_code,
        body.detail,
        body.command_id,
    )


def _current_signature(record: _Life) -> _Signature | None:
    if record.state is None or record.verified is None or record.observed_motion is None:
        return None
    if record.reason_code is None:
        return None
    return (
        record.state,
        record.verified,
        record.observed_motion,
        record.reason_code,
        record.detail,
        record.command_id,
    )


def _allows(current: str | None, new: str) -> bool:
    if current is None:
        return True
    if current in _TERMINAL:
        return False
    if current == "accepted":
        return new == "accepted" or new == "running" or new in _TERMINAL
    if current == "running":
        return new == "running" or new in _TERMINAL
    return False


def _remember(record: _Life, envelope: Envelope, signature: _Signature) -> None:
    record.signatures[envelope.message_id] = signature
    if envelope.message_id not in record.ack_message_ids:
        record.ack_message_ids.append(envelope.message_id)
    if record.last_seq is None or envelope.seq > record.last_seq:
        record.last_seq = envelope.seq


def _store_ack(
    record: _Life,
    envelope: Envelope,
    body: AckBody,
    observation: ObservationView | None,
) -> None:
    record.state = body.state
    record.verified = body.verified
    record.observed_motion = body.observed_motion
    record.reason_code = body.reason_code
    record.detail = body.detail
    record.ack_message_id = envelope.message_id
    record.correlation_id = envelope.correlation_id
    record.terminal = body.state in _TERMINAL
    if record.terminal:
        record.query_open = False
    if not record.history or record.history[-1] != body.state:
        record.history.append(body.state)
    stale = False
    observed_flag = False
    observed_flight: str | None = None
    if observation is not None:
        if observation.epoch != record.epoch or observation.mission_id != record.mission_id:
            stale = True
        else:
            observed_flag = observation.ignored_local_flag
            observed_flight = observation.flight_state
    record.observation_stale = stale
    record.observation_flight_state = observed_flight
    text = body.detail or ""
    record.ignored_local_flag = "is_flying" in text.lower() or observed_flag
    if body.state == "completed" and record.completion_events == 0:
        record.completion_events = 1
    _derive(record)


def _derive(record: _Life) -> None:
    motion = record.observed_motion
    record.grounded = False
    record.flight_state = "unknown"
    record.recovery_required = record.state == "unknown"
    record.blocks_next_mission = record.state == "unknown" and (
        record.action == "land" or record.reason_code == "landing_not_verified"
    )
    if record.action == "track_step":
        if motion == "airborne":
            record.flight_state = "airborne"
        elif motion in {"moving", "stationary"}:
            record.flight_state = motion
        else:
            record.flight_state = "unknown"
        return
    if (
        record.action == "land"
        and record.state == "completed"
        and record.verified is True
        and motion == "grounded"
    ):
        record.flight_state = "grounded"
        record.grounded = True
        return
    if motion == "airborne":
        record.flight_state = "airborne"
    if record.state == "unknown":
        record.flight_state = "unknown"
        record.grounded = False


def _transition_events(
    record: _Life,
    previous: str | None,
    body: AckBody,
    envelope: Envelope,
    ticket: Ticket | None,
) -> tuple[GroundEvent, ...]:
    payload: dict[str, object] = {
        "command_id": record.command_id,
        "command_message_id": record.command_message_id,
        "ack_message_id": envelope.message_id,
        "state": body.state,
        "verified": body.verified,
        "observed_motion": body.observed_motion,
        "flight_state": record.flight_state,
        "grounded": record.grounded,
        "action": record.action,
    }
    events = [_event("state_changed", ticket, payload)]
    if body.state == "completed" and previous != "completed":
        events.append(
            _event(
                "operation_completed",
                ticket,
                {
                    "command_id": record.command_id,
                    "command_message_id": record.command_message_id,
                    "ack_message_id": envelope.message_id,
                    "verified_completion": body.verified is True,
                    "grounded": record.grounded,
                    "flight_state": record.flight_state,
                    "action": record.action,
                },
            )
        )
    elif body.state == "unknown":
        events.append(
            _event(
                "recovery_required",
                ticket,
                {
                    "command_id": record.command_id,
                    "command_message_id": record.command_message_id,
                    "ack_message_id": envelope.message_id,
                    "blocks_next_mission": record.blocks_next_mission,
                    "reason_code": body.reason_code,
                    "flight_state": "unknown",
                    "grounded": False,
                },
            )
        )
    elif body.state in {"failed", "rejected"} and previous not in {"failed", "rejected"}:
        events.append(
            _event(
                "operation_failed",
                ticket,
                {
                    "command_id": record.command_id,
                    "command_message_id": record.command_message_id,
                    "ack_message_id": envelope.message_id,
                    "state": body.state,
                    "reason_code": body.reason_code,
                },
            )
        )
    return tuple(events)


def _event(kind: str, ticket: Ticket | None, payload: dict[str, object]) -> GroundEvent:
    return GroundEvent(kind, ticket, freeze_map(payload))


def _snapshot(
    record: _Life | None,
    *,
    command_ids: tuple[str, ...],
    duplicate: bool,
    conflict: bool,
    command_id: str | None,
) -> Mapping[str, object]:
    proposed: tuple[str, ...] = ()
    if record is None:
        raw: dict[str, object] = {
            "command_id": command_id,
            "command_message_id": None,
            "ack_message_id": None,
            "ack_message_ids": (),
            "correlation_id": None,
            "mission_id": None,
            "epoch": None,
            "action": None,
            "state": None,
            "terminal": False,
            "completed": False,
            "verified": None,
            "verified_completion": False,
            "observed_motion": None,
            "flight_state": "unknown",
            "grounded": False,
            "landing_proof": False,
            "recovery_required": False,
            "blocks_next_mission": False,
            "unresolved": True,
            "query_required": False,
            "query_command": None,
            "query_count": 0,
            "proposed_commands": proposed,
            "issued_command_ids": command_ids,
            "completion_events": 0,
            "history": (),
            "duplicate": duplicate,
            "conflict": conflict,
            "ignored_local_flag": False,
            "observation_stale": False,
            "observation_flight_state": None,
            "demo_goal_cleared": False,
            "reason_code": None,
            "reported_detail": None,
        }
        return freeze_map(raw)
    verified_completion = record.state == "completed" and record.verified is True
    raw = {
        "command_id": record.command_id,
        "command_message_id": record.command_message_id,
        "ack_message_id": record.ack_message_id,
        "ack_message_ids": tuple(record.ack_message_ids),
        "correlation_id": record.correlation_id,
        "mission_id": record.mission_id,
        "epoch": record.epoch,
        "action": record.action,
        "state": record.state,
        "terminal": record.terminal,
        "completed": record.state == "completed",
        "verified": record.verified,
        "verified_completion": verified_completion,
        "observed_motion": record.observed_motion,
        "flight_state": record.flight_state,
        "grounded": record.grounded,
        "landing_proof": record.grounded,
        "recovery_required": record.recovery_required,
        "blocks_next_mission": record.blocks_next_mission,
        "unresolved": not record.terminal,
        "query_required": record.query_open,
        "query_command": record.command_id if record.query_open else None,
        "query_count": record.query_count,
        "proposed_commands": proposed,
        "issued_command_ids": command_ids,
        "completion_events": record.completion_events,
        "history": tuple(record.history),
        "duplicate": duplicate,
        "conflict": conflict,
        "ignored_local_flag": record.ignored_local_flag,
        "observation_stale": record.observation_stale,
        "observation_flight_state": record.observation_flight_state,
        "demo_goal_cleared": False,
        "reason_code": record.reason_code,
        "reported_detail": record.detail,
    }
    return freeze_map(raw)


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", f"{label} must be a real number")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise fault("invalid_input", f"{label} must be finite")
