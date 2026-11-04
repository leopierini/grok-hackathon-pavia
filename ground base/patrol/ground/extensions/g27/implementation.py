"""Recovery feature. A reached goal does not verify the landing, and this
provider does not call land or emit a search command.
"""

from __future__ import annotations

from collections.abc import Mapping

from patrol.ground.extensions.g27.policy import (
    DOG_HOLD,
    SCHEMA,
    SLOT,
    Incoming,
    Outcome,
    RecoveryBook,
    ignored_actions,
    load_fixture,
    unknown_inputs,
    verified_inputs,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map, require_bool

_MOTION = ("dog.run_route", "drone.inspect", "drone.land", "reasoner.assess_incident")


class RecoveryFeature:
    """Proposes recovery events. The workflow commits them after its own checks."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.cleanup_paths: tuple[str, ...] = ()
        self._book = RecoveryBook()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest", self._calls())
        if request.ticket is not None and not isinstance(request.ticket, Ticket):
            return _failed("invalid_input", "ticket must be a Ticket", self._calls())
        before = self._calls()
        try:
            if request.name in _CASES and "goal_event" not in request.payload:
                result = self._script(request)
            else:
                result = self._from_payload(request)
        except GroundFault as exc:
            return _failed(
                exc.error.code,
                exc.error.detail,
                self._calls(),
                exc.error.recovery_required,
            )
        if self._calls() != before:
            return _failed(
                "unsafe_state",
                "recovery issued a device command",
                self._calls(),
                True,
            )
        return result

    def _script(self, request: FeatureRequest) -> FeatureResult:
        handler = _CASES[request.name]
        outcome, trace, detail = handler(self._book)
        return _foundation(request, outcome, trace, detail, self._calls())

    def _from_payload(self, request: FeatureRequest) -> FeatureResult:
        payload = request.payload
        attempt = False
        if "attempt_clear" in payload:
            attempt = require_bool(payload.get("attempt_clear"), label="attempt_clear")
        incoming = Incoming(
            goal_event=_message(payload, "goal_event"),
            land_command=_message(payload, "land_command"),
            land_ack=_message(payload, "land_ack"),
            observation=_message(payload, "observation"),
            attempt_clear=attempt,
            ignored_actions=ignored_actions(payload.get("ignored_actions")),
        )
        outcome = self._book.evaluate(incoming)
        return _domain(request, outcome, self._calls())

    def _calls(self) -> int:
        return len(self._call_names())

    def _call_names(self) -> tuple[str, ...]:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", ())
        if isinstance(calls, list):
            return tuple(str(item) for item in calls)
        return ()


def create(services: BaseServices) -> RecoveryFeature:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "recovery create expects base services")
    return RecoveryFeature(services)


def _goal_and_verified(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    outcome = book.evaluate(verified_inputs())
    trace = (
        "goal_status:reached",
        "landing_status:verified",
        "recovery_required:false",
        "device_recovery_required:false",
        "next_mission_blocked:false",
        "dog:hold_stop",
        "search_commands:0",
        "issued_commands:0",
        "record_count:1",
        "goal_event:msg-event-demo_goal_reached",
        "land_command:cmd-drone-land-001",
        "physical_retrieval:operator_step",
    )
    _expect(
        outcome,
        goal_status="reached",
        landing_status="verified",
        recovery_required=False,
        record_count=1,
    )
    return outcome, trace, "goal_status=reached landing_status=verified"


def _goal_and_unknown(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    outcome = book.evaluate(unknown_inputs(observation=True))
    trace = (
        "goal_status:reached",
        "landing_status:unverified",
        "recovery_required:true",
        "device_recovery_required:true",
        "next_mission_blocked:true",
        "dog:hold_stop",
        "search_commands:0",
        "goal_kept:true",
        "landing_event:landing_unverified",
        "picture_ignored:true",
        "goal_timestamp_ignored:true",
    )
    _expect(
        outcome,
        goal_status="reached",
        landing_status="unverified",
        recovery_required=True,
        record_count=1,
    )
    if not outcome.picture_ignored or not outcome.goal_timestamp_ignored:
        raise fault("validation_failed", "a picture or goal timestamp cleared recovery")
    if outcome.landing_event_name != "landing_unverified":
        raise fault("validation_failed", "unknown landing did not record landing_unverified")
    return outcome, trace, "goal reached and landing unverified"


def _not_attempted(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    outcome = book.evaluate(
        Incoming(
            load_fixture("event-demo_goal_reached.json"),
            None,
            load_fixture("drone-ack-completed.json"),
            load_fixture("drone-observation-grounded.json"),
            False,
            (),
        )
    )
    trace = (
        "goal_status:reached",
        "landing_status:not_attempted",
        "recovery_required:false",
        "next_mission_blocked:false",
        "dog:hold_stop",
        "search_commands:0",
        "land_ack_accepted:false",
        "observation_not_landing:true",
    )
    _expect(
        outcome,
        goal_status="reached",
        landing_status="not_attempted",
        recovery_required=False,
        record_count=1,
    )
    if outcome.land_ack_accepted or not outcome.observation_not_landing:
        raise fault("validation_failed", "missing land command was treated as grounded")
    return outcome, trace, "landing_status=not_attempted"


def _contradiction(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    outcome = book.evaluate(
        Incoming(
            load_fixture("event-demo_goal_reached.json"),
            load_fixture("ground-to-drone-land.json"),
            load_fixture("land-ack-verified.json"),
            load_fixture("drone-observation.json"),
            False,
            (),
        )
    )
    trace = (
        "goal_status:reached",
        "landing_status:contradicted",
        "recovery_required:true",
        "device_recovery_required:true",
        "fault:flight_state_airborne",
        "dog:hold_stop",
        "search_commands:0",
        "goal_kept:true",
    )
    _expect(
        outcome,
        goal_status="reached",
        landing_status="contradicted",
        recovery_required=True,
        record_count=1,
    )
    if outcome.fault_name != "flight_state_airborne":
        raise fault("validation_failed", "airborne flight_state was not a fault")
    return outcome, trace, "flight_state contradicts the land acknowledgement"


def _replay(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    first = book.evaluate(verified_inputs())
    second = book.evaluate(verified_inputs())
    trace = (
        "goal_status:reached",
        "landing_status:verified",
        "replayed:true",
        "record_count:1",
        "record_id:recovery:msg-event-demo_goal_reached:cmd-drone-land-001",
        "search_commands:0",
    )
    same = (
        second.replayed
        and second.record_id == first.record_id
        and second.record_count == 1
        and first.record_count == 1
        and second.record_id == "recovery:msg-event-demo_goal_reached:cmd-drone-land-001"
    )
    if not same:
        raise fault("validation_failed", "replay created another recovery record")
    return second, trace, "one recovery record"


def _clear_rejected(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    book.evaluate(unknown_inputs(observation=False))
    outcome = book.evaluate(
        Incoming(
            load_fixture("event-demo_goal_reached.json"),
            load_fixture("ground-to-drone-land.json"),
            load_fixture("drone-landing-unknown.json"),
            None,
            True,
            (),
        )
    )
    trace = (
        "clear:rejected",
        "recovery_required:true",
        "landing_status:unverified",
        "goal_status:reached",
        "record_count:1",
        "new_observation:false",
    )
    kept = (
        outcome.clear_rejected
        and outcome.status == "failed"
        and outcome.error_code == "rejected"
        and outcome.recovery_required
        and outcome.record_count == 1
        and outcome.landing_status == "unverified"
    )
    if not kept:
        raise fault("validation_failed", "recovery was cleared without a new observation")
    return outcome, trace, outcome.error_detail or "clear rejected"


def _no_search(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    incoming = verified_inputs()
    outcome = book.evaluate(
        Incoming(
            incoming.goal_event,
            incoming.land_command,
            incoming.land_ack,
            incoming.observation,
            False,
            ("search",),
        )
    )
    trace = (
        "search_commands:0",
        "issued_commands:0",
        "dog:hold_stop",
        "proposal_ignored:search",
        "device_calls:0",
    )
    if outcome.search_commands or outcome.issued_commands or outcome.dog_recommendation != DOG_HOLD:
        raise fault("validation_failed", "a search or move command was emitted")
    return outcome, trace, "no search command"


def _save_statuses(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    outcome = book.evaluate(verified_inputs())
    record = outcome.record
    trace = (
        "saved:goal_status:reached",
        "saved:landing_status:verified",
        "record_has_both:true",
    )
    if record.get("goal_status") != "reached" or record.get("landing_status") != "verified":
        raise fault("validation_failed", "the recovery record did not save both statuses")
    return outcome, trace, "saved goal_status and landing_status"


def _goal_false(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    outcome = book.evaluate(
        Incoming(
            None,
            load_fixture("ground-to-drone-land.json"),
            load_fixture("land-ack-verified.json"),
            load_fixture("drone-observation-grounded.json"),
            False,
            (),
        )
    )
    trace = (
        "goal_status:not_reached",
        "landing_status:verified",
        "goal_invented:false",
        "recovery_required:false",
        "search_commands:0",
    )
    _expect(
        outcome,
        goal_status="not_reached",
        landing_status="verified",
        recovery_required=False,
        record_count=1,
    )
    if outcome.goal_event_id is not None or outcome.goal_invented:
        raise fault("validation_failed", "a goal was invented from the landing")
    return outcome, trace, "goal not invented"


def _track_not_land(book: RecoveryBook) -> tuple[Outcome, tuple[str, ...], str]:
    outcome = book.evaluate(
        Incoming(
            None,
            load_fixture("ground-to-drone-command.json"),
            load_fixture("drone-ack-completed.json"),
            load_fixture("drone-observation.json"),
            False,
            (),
        )
    )
    trace = (
        "landing_status:not_attempted",
        "land_ack_accepted:false",
        "track_command:cmd-drone-001",
        "goal_status:not_reached",
        "search_commands:0",
    )
    accepted = (
        outcome.landing_status != "not_attempted"
        or outcome.land_ack_accepted
        or outcome.foreign_command_id != "cmd-drone-001"
        or outcome.goal_status != "not_reached"
    )
    if accepted:
        raise fault("validation_failed", "a track completion was accepted as landing")
    return outcome, trace, "track completion is not a land acknowledgement"


_CASES = {
    "goal_and_verified_landing": _goal_and_verified,
    "goal_and_unknown_landing": _goal_and_unknown,
    "land_not_attempted": _not_attempted,
    "flight_state_contradiction": _contradiction,
    "replay_one_record": _replay,
    "clear_without_observation": _clear_rejected,
    "no_search_command": _no_search,
    "save_both_statuses": _save_statuses,
    "goal_false_verified_landing": _goal_false,
    "track_not_land": _track_not_land,
}


def _expect(
    outcome: Outcome,
    *,
    goal_status: str,
    landing_status: str,
    recovery_required: bool,
    record_count: int,
) -> None:
    matches = (
        outcome.goal_status == goal_status
        and outcome.landing_status == landing_status
        and outcome.recovery_required is recovery_required
        and outcome.record_count == record_count
        and outcome.issued_commands == ()
        and outcome.search_commands == ()
        and outcome.dog_recommendation == DOG_HOLD
        and outcome.record.get("physical_retrieval") == "operator_step"
        and outcome.record.get("software_retrieved") is False
    )
    if not matches:
        raise fault("validation_failed", "recovery outcome did not match the case")


def _foundation(
    request: FeatureRequest,
    outcome: Outcome,
    trace: tuple[str, ...],
    detail: str,
    device_calls: int,
) -> FeatureResult:
    error: GroundError | None = None
    status = "failed" if outcome.clear_rejected else outcome.status
    if status != "ok":
        error = GroundError(
            outcome.error_code or "recovery_required",
            outcome.error_detail or detail,
            True,
        )
    data = freeze_map(
        {
            "authorized": False,
            "retained": False,
            "detail": detail,
            "trace": trace,
            "device_calls": device_calls,
            "measurement_clock": "manual",
            "within_limit": True,
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
    )
    events = () if outcome.replayed else _events(request, outcome)
    return FeatureResult(status, data, events, error)


def _domain(request: FeatureRequest, outcome: Outcome, device_calls: int) -> FeatureResult:
    error: GroundError | None = None
    if outcome.status != "ok":
        error = GroundError(
            outcome.error_code or "recovery_required",
            outcome.error_detail or "recovery required",
            True,
        )
    landing_event = None if outcome.replayed else _landing_event(outcome)
    data = freeze_map(
        {
            "slot": SLOT,
            "schema_version": SCHEMA,
            "goal_status": outcome.goal_status,
            "landing_status": outcome.landing_status,
            "recovery_required": outcome.recovery_required,
            "device_recovery_required": outcome.device_recovery_required,
            "next_mission_blocked": outcome.next_mission_blocked,
            "dog_recommendation": outcome.dog_recommendation,
            "issued_commands": outcome.issued_commands,
            "search_commands": outcome.search_commands,
            "recovery_record": outcome.record,
            "recovery_record_count": outcome.record_count,
            "replayed": outcome.replayed,
            "landing_event": landing_event,
            "physical_retrieval": "operator_step",
            "picture_ignored": outcome.picture_ignored,
            "goal_timestamp_ignored": outcome.goal_timestamp_ignored,
            "goal_invented": outcome.goal_invented,
            "land_ack_accepted": outcome.land_ack_accepted,
            "foreign_command_id": outcome.foreign_command_id,
            "fault_name": outcome.fault_name,
            "clear_rejected": outcome.clear_rejected,
            "cleared": outcome.cleared,
            "statuses": freeze_map(
                {
                    "goal_status": outcome.goal_status,
                    "landing_status": outcome.landing_status,
                }
            ),
            "device_calls": device_calls,
            "live_call_count": 0,
            "simulated": True,
            "trace": _domain_trace(outcome),
        }
    )
    events = () if outcome.replayed or outcome.clear_rejected else _events(request, outcome)
    return FeatureResult(outcome.status, data, events, error)


def _events(request: FeatureRequest, outcome: Outcome) -> tuple[GroundEvent, ...]:
    found: list[GroundEvent] = []
    if outcome.goal_status == "reached":
        found.append(
            GroundEvent(
                "state_changed",
                request.ticket,
                freeze_map(
                    {
                        "goal_status": "reached",
                        "goal_event_id": outcome.goal_event_id,
                        "landing_status": outcome.landing_status,
                    }
                ),
            )
        )
    if outcome.cleared:
        found.append(
            GroundEvent(
                "recovery_cleared",
                request.ticket,
                freeze_map(
                    {
                        "record_id": outcome.record_id,
                        "physical_retrieval": "operator_step",
                    }
                ),
            )
        )
    elif outcome.recovery_required and outcome.landing_event_name is not None:
        found.append(
            GroundEvent(
                "recovery_required",
                request.ticket,
                freeze_map(
                    {
                        "event": outcome.landing_event_name,
                        "device_recovery_required": True,
                        "goal_status": outcome.goal_status,
                        "landing_status": outcome.landing_status,
                    }
                ),
            )
        )
    elif outcome.landing_status == "verified":
        found.append(
            GroundEvent(
                "operation_completed",
                request.ticket,
                freeze_map(
                    {
                        "landing_status": "verified",
                        "physical_retrieval": "operator_step",
                    }
                ),
            )
        )
    return tuple(found)


def _landing_event(outcome: Outcome) -> Mapping[str, object] | None:
    if outcome.landing_event_name is None:
        return None
    return freeze_map(
        {
            "protocol_version": "2.0-draft",
            "message_id": f"msg-event-{outcome.landing_event_name}",
            "mission_id": outcome.mission_id,
            "epoch": outcome.epoch if outcome.epoch is not None else 0,
            "seq": 12,
            "sent_at": outcome.goal_sent_at or "2026-11-04T13:00:12.000Z",
            "source": "ground",
            "destination": "all",
            "kind": "mission.event",
            "correlation_id": outcome.land_message_id,
            "expires_at": None,
            "simulated": True,
            "payload": freeze_map(
                {
                    "event": outcome.landing_event_name,
                    "phase": "recover",
                    "outcome": "failed",
                    "device_recovery_required": True,
                    "reason": outcome.error_detail or "landing is not verified",
                    "details": freeze_map(
                        {
                            "logs_requirements_status": "proposed_pending_team",
                            "track_id": outcome.track_id,
                            "goal_event_id": outcome.goal_event_id,
                            "command_id": outcome.land_command_id,
                            "landing_status": outcome.landing_status,
                        }
                    ),
                }
            ),
        }
    )


def _domain_trace(outcome: Outcome) -> tuple[str, ...]:
    recovery = str(outcome.recovery_required).lower()
    return (
        f"goal_status:{outcome.goal_status}",
        f"landing_status:{outcome.landing_status}",
        f"recovery_required:{recovery}",
        f"search_commands:{len(outcome.search_commands)}",
        f"issued_commands:{len(outcome.issued_commands)}",
        f"dog:{outcome.dog_recommendation}",
        f"record_count:{outcome.record_count}",
        f"record_id:{outcome.record_id}",
    )


def _message(payload: Mapping[str, object], key: str) -> Mapping[str, object] | None:
    if key not in payload:
        return None
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, Mapping):
        raise fault("invalid_input", f"{key} must be a message object")
    return value


def _failed(
    code: str,
    detail: str,
    device_calls: int,
    recovery_required: bool = False,
) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "slot": SLOT,
                "schema_version": SCHEMA,
                "detail": detail,
                "device_calls": device_calls,
                "live_call_count": 0,
                "simulated": True,
                "authorized": False,
                "trace": (),
            }
        ),
        (),
        GroundError(code, detail, recovery_required),
    )
