"""Halt, link loss, and lease expiry without waiting for a model.

``create(services)`` is the Task 01 harness entry. It calls the base safety
port and proposes events. It does not apply those events itself, and it does
not call a vision model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from patrol.ground.extensions.g28.casespec import SCHEMA, SLOT, SPEC_BY_ID, CaseSpec
from patrol.ground.extensions.g28.messages import (
    Examples,
    clone_message,
    command_action,
    command_id,
    correlation,
    destination,
    load_examples,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    EventRecord,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    SafetyHandle,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

_LATCHING = frozenset(
    {
        "operator_halt",
        "link_loss",
        "stale_frame",
        "expired_lease",
        "obstacle_block",
        "lost_track",
        "noisy_rssi",
        "explicit_land",
    }
)
_PROPOSALS = frozenset({"search", "track", "homing"})
_PROFILES = frozenset({"hover", "land"})
_FORBIDDEN = frozenset({"emergency", "motor_cut", "power_off", "cut_motors"})
_JOURNAL = {
    "operator_halt": "halt_requested",
    "link_loss": "link_lost",
    "stale_frame": "halt_requested",
    "expired_lease": "halt_requested",
    "obstacle_block": "halt_requested",
    "lost_track": "arrival_rejected",
    "noisy_rssi": "arrival_rejected",
    "explicit_land": "halt_requested",
}
_NOT_ARRIVAL = frozenset({"obstacle_block", "lost_track", "noisy_rssi", "stale_frame"})
_MODES = {"dog": "fake", "drone": "fake", "grok": "fake"}


@dataclass(frozen=True)
class _Stimulus:
    name: str
    profile: str
    link_loss_action: str | None
    rejected_profile: str | None
    active_commands: tuple[Mapping[str, object], ...]
    command: Mapping[str, object] | None
    started: bool | None
    workers_pending: bool | None
    recovery_token: str | None
    proposal_action: str | None
    decision_label: str | None
    vision_pending: bool


def create(services: BaseServices) -> SafetyFeature:
    """Build the safety feature from Task 01 doubles. Nothing moves yet."""
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "safety feature create expects base services")
    examples = load_examples(repo_root() / "fixtures" / "ground" / "g28")
    return SafetyFeature(services, examples)


class SafetyFeature:
    """One latched handle. A second halt returns it and does not emit again."""

    def __init__(self, services: BaseServices, examples: Examples) -> None:
        self.services = services
        self.examples = examples
        self.handle: SafetyHandle | None = None
        self.safety_calls = 0
        self.model_calls = 0
        self.dog_halt_count = 0
        self.drone_hover_count = 0
        self.drone_land_count = 0
        self.superseded: tuple[str, ...] = ()
        self.latch_monotonic: float | None = None
        self.issued_dog: Mapping[str, object] | None = None
        self.issued_drone: Mapping[str, object] | None = None
        self.last_events: tuple[GroundEvent, ...] = ()
        self._sequence = 1

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if request.kind == "diagnostic" and request.name in SPEC_BY_ID:
            return await self._simulate(request.name)
        if request.kind not in {"guard", "command"}:
            return _failed(fault("invalid_input", "safety feature kind must be guard or command"))
        try:
            return await self._apply(request)
        except GroundFault as exc:
            return _failed(exc, latched=self.handle is not None)

    async def _apply(self, request: FeatureRequest) -> FeatureResult:
        stimulus = _parse(request.payload)
        return await self._dispatch(request, stimulus)

    async def _simulate(self, name: str) -> FeatureResult:
        spec = SPEC_BY_ID[name]
        try:
            trace = await self._run_case(name)
        except GroundFault as exc:
            trace = ("case_failed", exc.error.detail)
        ok = trace == spec.trace and self.model_calls == 0 and _live_calls(self.services) == 0
        return _foundation(ok=ok, spec=spec, trace=trace, events=self.last_events if ok else ())

    async def _run_case(self, name: str) -> tuple[str, ...]:
        if name == "halt_during_vision_timeout":
            return await self._case_halt_during_vision()
        if name == "late_decision":
            return await self._case_late_decision()
        if name == "expired_lease":
            return await self._case_expired_lease()
        if name == "link_loss":
            return await self._case_link_loss()
        if name == "obstacle_block":
            return await self._case_obstacle()
        if name == "noisy_rssi":
            return await self._case_noisy()
        if name == "replay_halt":
            return await self._case_replay()
        if name == "reset_without_token":
            return await self._case_reset_without_token()
        if name == "superseded_ids":
            return await self._case_superseded()
        if name == "explicit_land":
            return await self._case_explicit_land()
        if name == "lost_track":
            return await self._case_lost_track()
        if name == "reset_pending_workers":
            return await self._case_reset_pending()
        if name == "motor_cut_rejected":
            return await self._case_motor_cut()
        if name == "stale_frame":
            return await self._case_stale()
        if name == "link_loss_land_profile":
            return await self._case_link_loss_land()
        if name == "ordinary_proposals":
            return await self._case_ordinary()
        if name == "reset_with_token":
            return await self._case_reset_with_token()
        raise fault("invalid_input", f"unknown safety case {name}")

    async def _case_halt_during_vision(self) -> tuple[str, ...]:
        clock = self.services.kernel.clock
        start = clock.monotonic()
        result = await self.execute(
            _request(
                "operator_halt",
                {
                    "vision_pending": True,
                    "active_commands": [self.examples.dog_move, self.examples.drone_move],
                },
            )
        )
        delta = clock.monotonic() - start
        dog = _action_of(result, "dog_command")
        drone = _action_of(result, "drone_command")
        if not (
            result.status == "ok"
            and dog == "halt"
            and drone == "hover"
            and self.model_calls == 0
            and delta == 0
            and result.data.get("motor_cut") is False
            and result.data.get("vision_cleared") is False
        ):
            return ("case_failed", "halt during vision")
        return (
            "stimulus:operator_halt",
            "dog:halt",
            "drone:hover",
            "model_calls:0",
            "vision_not_awaited",
            "clock_delta:0",
            "motor_cut:false",
        )

    async def _case_late_decision(self) -> tuple[str, ...]:
        await self.execute(_request("operator_halt", {}))
        result = await self.execute(
            _request("late_decision", {"decision": {"label": "person_visible"}})
        )
        if not (
            self.handle is not None
            and result.status == "blocked"
            and result.data.get("vision_cleared") is False
            and result.data.get("latch_set") is True
            and self.model_calls == 0
        ):
            return ("case_failed", "late decision")
        return (
            "stimulus:operator_halt",
            "late:person_visible",
            "latch_set",
            "cleared:false",
            "model_calls:0",
        )

    async def _case_expired_lease(self) -> tuple[str, ...]:
        result = await self.execute(
            _request(
                "expired_lease",
                {"command": self.examples.dog_move, "started": False},
            )
        )
        if not (
            result.status == "blocked"
            and result.data.get("command_refused") is True
            and result.data.get("execution") == "unknown"
            and result.data.get("query_path") == "feature.v2_dog_ack"
            and result.data.get("query_task") == "24"
            and result.data.get("started") is False
            and _action_of(result, "dog_command") == "halt"
            and _action_of(result, "drone_command") == "hover"
        ):
            return ("case_failed", "expired lease")
        return (
            "stimulus:expired_lease",
            "started:false",
            "command_refused",
            "execution:unknown",
            "query:feature.v2_dog_ack",
            "query_task:24",
            "dog:halt",
            "drone:hover",
        )

    async def _case_link_loss(self) -> tuple[str, ...]:
        result = await self.execute(_request("link_loss", {}))
        if not (
            result.status == "ok"
            and _action_of(result, "dog_command") == "halt"
            and _action_of(result, "drone_command") == "hover"
            and result.data.get("delivery") == "unknown"
            and result.data.get("physical_stop_claimed") is False
            and result.data.get("local_failsafe") is True
            and result.data.get("delivery_guaranteed") is False
        ):
            return ("case_failed", "link loss")
        return (
            "stimulus:link_loss",
            "dog:halt",
            "drone:hover",
            "delivery:unknown",
            "physical_stop:unclaimed",
            "local_failsafe:true",
            "delivery_guaranteed:false",
        )

    async def _case_obstacle(self) -> tuple[str, ...]:
        result = await self.execute(_request("obstacle_block", {"detour": True}))
        if not (
            _action_of(result, "dog_command") == "halt"
            and result.data.get("detour") is False
            and result.data.get("arrival_confirmed") is False
        ):
            return ("case_failed", "obstacle")
        return (
            "stimulus:obstacle_block",
            "dog:halt",
            "drone:hover",
            "detour:false",
            "arrival:false",
        )

    async def _case_noisy(self) -> tuple[str, ...]:
        result = await self.execute(_request("noisy_rssi", {"goal_reached": True}))
        if not (
            _action_of(result, "dog_command") == "halt"
            and result.data.get("goal_reached") is False
            and result.data.get("arrival_confirmed") is False
        ):
            return ("case_failed", "noisy rssi")
        return (
            "stimulus:noisy_rssi",
            "dog:halt",
            "drone:hover",
            "goal_reached:false",
            "arrival:false",
        )

    async def _case_replay(self) -> tuple[str, ...]:
        await self.execute(_request("operator_halt", {}))
        first = self.handle
        await self.execute(_request("operator_halt", {}))
        if not (
            first is not None
            and self.handle is first
            and self.safety_calls == 1
            and self.dog_halt_count == 1
            and self.drone_hover_count == 1
        ):
            return ("case_failed", "replay halt")
        return (
            "same_handle",
            "safety_requests:1",
            "dog_halt_emissions:1",
            "drone_hover_emissions:1",
        )

    async def _case_reset_without_token(self) -> tuple[str, ...]:
        await self.execute(_request("operator_halt", {}))
        result = await self.execute(_request("reset", {}))
        error = result.error
        if not (
            result.status == "failed"
            and error is not None
            and error.code == "rejected"
            and self.handle is not None
            and "safety.reset" not in _safety_trace(self.services)
        ):
            return ("case_failed", "reset without token")
        return ("reset_rejected", "token:missing", "latch_set")

    async def _case_superseded(self) -> tuple[str, ...]:
        await self.execute(
            _request(
                "operator_halt",
                {"active_commands": [self.examples.dog_move, self.examples.drone_move]},
            )
        )
        saved = _journal_ids(self.services)
        if saved != ("cmd-dog-001", "cmd-drone-001"):
            return ("case_failed", "superseded ids")
        return ("superseded:cmd-dog-001,cmd-drone-001", "journaled")

    async def _case_explicit_land(self) -> tuple[str, ...]:
        result = await self.execute(_request("explicit_land", {"profile": "hover"}))
        if not (
            _action_of(result, "dog_command") == "halt"
            and _action_of(result, "drone_command") == "land"
            and result.data.get("motor_cut") is False
        ):
            return ("case_failed", "explicit land")
        return (
            "stimulus:explicit_land",
            "dog:halt",
            "drone:land",
            "motor_cut:false",
        )

    async def _case_lost_track(self) -> tuple[str, ...]:
        result = await self.execute(_request("lost_track", {}))
        if not (
            _action_of(result, "dog_command") == "halt"
            and result.data.get("goal_reached") is False
            and result.data.get("arrival_confirmed") is False
        ):
            return ("case_failed", "lost track")
        return (
            "stimulus:lost_track",
            "dog:halt",
            "goal_reached:false",
            "arrival:false",
        )

    async def _case_reset_pending(self) -> tuple[str, ...]:
        await self.execute(_request("operator_halt", {}))
        result = await self.execute(
            _request(
                "reset",
                {
                    "recovery_token": self.examples.recovery_token,
                    "workers_pending": True,
                },
            )
        )
        error = result.error
        if not (
            result.status == "failed"
            and error is not None
            and error.code == "rejected"
            and self.handle is not None
        ):
            return ("case_failed", "reset pending")
        return ("reset_rejected", "workers:pending", "latch_set")

    async def _case_motor_cut(self) -> tuple[str, ...]:
        result = await self.execute(_request("operator_halt", {"profile": "emergency"}))
        if not (
            result.data.get("profile_rejected") == "emergency"
            and result.data.get("motor_cut") is False
            and _action_of(result, "dog_command") == "halt"
            and _action_of(result, "drone_command") == "hover"
        ):
            return ("case_failed", "motor cut")
        return (
            "profile_rejected:emergency",
            "dog:halt",
            "drone:hover",
            "motor_cut:false",
        )

    async def _case_stale(self) -> tuple[str, ...]:
        result = await self.execute(
            _request(
                "stale_frame",
                {"decision": {"label": "person_visible"}, "vision_pending": True},
            )
        )
        if not (
            _action_of(result, "dog_command") == "halt"
            and result.data.get("vision_cleared") is False
            and result.data.get("latch_set") is True
            and self.model_calls == 0
        ):
            return ("case_failed", "stale frame")
        return (
            "stimulus:stale_frame",
            "dog:halt",
            "late:person_visible",
            "cleared:false",
        )

    async def _case_link_loss_land(self) -> tuple[str, ...]:
        result = await self.execute(
            _request("link_loss", {"profile": "hover", "link_loss_action": "land"})
        )
        if not (
            _action_of(result, "drone_command") == "land"
            and result.data.get("delivery") == "unknown"
            and result.data.get("local_failsafe") is True
            and result.data.get("motor_cut") is False
        ):
            return ("case_failed", "link loss land")
        return (
            "stimulus:link_loss",
            "drone:land",
            "delivery:unknown",
            "local_failsafe:true",
        )

    async def _case_ordinary(self) -> tuple[str, ...]:
        await self.execute(_request("operator_halt", {}))
        refused = True
        for action in ("search", "track", "homing"):
            result = await self.execute(
                _request("ordinary_proposal", {"proposal_action": action})
            )
            if result.status != "blocked" or result.data.get("ordinary_refused") is not True:
                refused = False
        if not (refused and self.handle is not None and self.dog_halt_count == 1):
            return ("case_failed", "ordinary proposals")
        return (
            "proposal:search",
            "proposal:track",
            "proposal:homing",
            "refused",
            "latch_set",
        )

    async def _case_reset_with_token(self) -> tuple[str, ...]:
        await self.execute(_request("operator_halt", {}))
        result = await self.execute(
            _request(
                "reset",
                {
                    "recovery_token": self.examples.recovery_token,
                    "workers_pending": False,
                },
            )
        )
        if not (
            result.status == "ok"
            and result.data.get("reset_accepted") is True
            and self.handle is None
            and self.services.kernel.authority.cancelled is False
            and self.services.kernel.tasks.pending() == ()
        ):
            return ("case_failed", "reset with token")
        return ("reset_accepted", "latch_cleared", "workers:quiescent")

    async def _dispatch(self, request: FeatureRequest, stimulus: _Stimulus) -> FeatureResult:
        if stimulus.vision_pending and self.model_calls != 0:
            raise fault(
                "unsafe_state",
                "a pending vision request cannot delay the latch",
                recovery_required=True,
            )
        if stimulus.name == "ordinary_proposal":
            return self._ordinary(stimulus)
        if stimulus.name == "late_decision":
            return self._late(stimulus)
        if stimulus.name == "reset":
            return await self._reset(stimulus)
        if stimulus.name not in _LATCHING:
            raise fault("invalid_input", "unknown safety stimulus")
        if self.handle is not None:
            return self._duplicate(stimulus)
        return self._latch(request, stimulus)

    def _ordinary(self, stimulus: _Stimulus) -> FeatureResult:
        action = stimulus.proposal_action
        if action not in _PROPOSALS:
            raise fault("invalid_input", "proposal action must be search, track, or homing")
        latched = self.handle is not None
        if latched:
            self._journal(
                "operation_failed",
                _ticket_of(self.handle),
                {
                    "stimulus": stimulus.name,
                    "proposal_action": action,
                    "ordinary_refused": True,
                    "superseded_command_ids": self.superseded,
                    "model_called": False,
                },
            )
        error = GroundError(
            "rejected",
            "ordinary proposal refused while the safety latch is set"
            if latched
            else "safety does not grant ordinary motion",
            latched,
        )
        return self._result(
            "blocked",
            error=error,
            events=(
                self._event(
                    "operation_failed",
                    _ticket_of(self.handle),
                    {"stimulus": action},
                ),
            ),
            stimulus=stimulus.name,
            ordinary_refused=latched,
        )

    def _late(self, stimulus: _Stimulus) -> FeatureResult:
        if stimulus.decision_label is None:
            raise fault("invalid_input", "decision label is required")
        if self.handle is None:
            error = GroundError("rejected", "no safety latch is set", False)
            return self._result("blocked", error=error, events=(), stimulus=stimulus.name)
        self._journal(
            "decision_received",
            self.handle.ticket,
            {
                "stimulus": stimulus.name,
                "label": stimulus.decision_label,
                "vision_cleared": False,
                "latch_monotonic": self.latch_monotonic,
                "model_called": False,
            },
        )
        event = self._event(
            "decision_received",
            self.handle.ticket,
            {"stimulus": stimulus.name, "label": stimulus.decision_label, "vision_cleared": False},
        )
        error = GroundError("rejected", "late vision cannot clear the latch", True)
        return self._result(
            "blocked",
            error=error,
            events=(event,),
            stimulus=stimulus.name,
            dog_command=self.issued_dog,
            drone_command=self.issued_drone,
        )

    async def _reset(self, stimulus: _Stimulus) -> FeatureResult:
        if self.handle is None:
            raise fault("rejected", "reset requires a safety latch")
        token = stimulus.recovery_token
        if token is None:
            self._journal_reset(False, "missing")
            raise fault("rejected", "recovery token is required", recovery_required=True)
        if token != self.examples.recovery_token:
            self._journal_reset(False, "rejected")
            raise fault("rejected", "recovery token was rejected", recovery_required=True)
        if stimulus.workers_pending is True or self.services.kernel.tasks.pending():
            self._journal_reset(False, "pending")
            raise fault("rejected", "reset requires quiescent workers", recovery_required=True)
        await self.services.safety.reset({"verified": True})
        monotonic = self.latch_monotonic
        superseded = self.superseded
        ticket = self.handle.ticket
        self.handle = None
        self.issued_dog = None
        self.issued_drone = None
        self._journal(
            "reset_requested",
            ticket,
            {
                "stimulus": "reset",
                "accepted": True,
                "latch_monotonic": monotonic,
                "superseded_command_ids": superseded,
                "workers": "quiescent",
            },
        )
        event = self._event("reset_requested", ticket, {"stimulus": "reset", "accepted": True})
        return self._result(
            "ok",
            error=None,
            events=(event,),
            stimulus="reset",
            reset_accepted=True,
        )

    def _journal_reset(self, accepted: bool, reason: str) -> None:
        self._journal(
            "reset_requested",
            _ticket_of(self.handle),
            {
                "stimulus": "reset",
                "accepted": accepted,
                "reason": reason,
                "latch_monotonic": self.latch_monotonic,
                "superseded_command_ids": self.superseded,
            },
        )

    def _duplicate(self, stimulus: _Stimulus) -> FeatureResult:
        handle = self.handle
        if handle is None:
            raise fault("internal", "duplicate halt has no handle")
        fields = _lease_fields(stimulus)
        self._journal(
            _JOURNAL.get(stimulus.name, "halt_requested"),
            handle.ticket,
            {
                "stimulus": stimulus.name,
                "duplicate": True,
                "latch_monotonic": self.latch_monotonic,
                "superseded_command_ids": self.superseded,
                "model_called": False,
                **fields,
            },
        )
        status = "blocked" if stimulus.name == "expired_lease" else "ok"
        error = None
        if stimulus.name == "expired_lease":
            error = GroundError("rejected", "expired lease refuses a late start", True)
        event = self._event(
            "halt_requested",
            handle.ticket,
            {"stimulus": stimulus.name, "duplicate": True},
        )
        return self._result(
            status,
            error=error,
            events=(event,),
            stimulus=stimulus.name,
            dog_command=self.issued_dog,
            drone_command=self.issued_drone,
            same_handle=True,
            command_refused=stimulus.name == "expired_lease",
            execution="unknown" if stimulus.name in {"expired_lease", "link_loss"} else None,
            delivery="unknown" if stimulus.name in {"expired_lease", "link_loss"} else "issued",
            local_failsafe=stimulus.name in {"link_loss", "expired_lease", "obstacle_block"},
            query_path=_text_field(fields, "query_path"),
            query_task=_text_field(fields, "query_task"),
            query_command_id=_text_field(fields, "query_command_id"),
            profile_rejected=stimulus.rejected_profile,
        )

    def _latch(self, request: FeatureRequest, stimulus: _Stimulus) -> FeatureResult:
        fields = _lease_fields(stimulus)
        ticket = request.ticket or self.services.kernel.authority.issue("safety-28", stimulus.name)
        reason = f"{stimulus.name}: stop without waiting for a model"
        handle = self.services.safety.request(reason, ticket)
        self.safety_calls += 1
        self.handle = handle
        self.latch_monotonic = self.services.kernel.clock.monotonic()
        self.superseded = tuple(command_id(item) for item in stimulus.active_commands)
        dog = clone_message(self.examples.dog_halt)
        drone_name = _drone_action(stimulus)
        if drone_name == "land":
            drone_source = self.examples.drone_land
        else:
            drone_source = self.examples.drone_hover
        drone = clone_message(drone_source)
        command_action(dog)
        command_action(drone)
        self.issued_dog = dog
        self.issued_drone = drone
        self.dog_halt_count += 1
        if drone_name == "land":
            self.drone_land_count += 1
        else:
            self.drone_hover_count += 1
        delivery = "unknown" if stimulus.name in {"link_loss", "expired_lease"} else "issued"
        local_failsafe = stimulus.name in {"link_loss", "expired_lease", "obstacle_block"}
        self._journal(
            _JOURNAL[stimulus.name],
            handle.ticket,
            {
                "stimulus": stimulus.name,
                "duplicate": False,
                "latch_monotonic": self.latch_monotonic,
                "superseded_command_ids": self.superseded,
                "model_called": False,
                "delivery": delivery,
                "physical_stop_claimed": False,
                "local_failsafe": local_failsafe,
                "delivery_guaranteed": False,
                "dog": correlation(dog),
                "drone": correlation(drone),
                **fields,
            },
        )
        events = self._latch_events(stimulus, handle.ticket, drone_name)
        status = "blocked" if stimulus.name == "expired_lease" else "ok"
        error = None
        if stimulus.name == "expired_lease":
            detail = (
                "expired lease refuses an unstarted command"
                if stimulus.started is False
                else "expired lease preserves unknown execution"
            )
            error = GroundError("rejected", detail, True)
        return self._result(
            status,
            error=error,
            events=events,
            stimulus=stimulus.name,
            dog_command=dog,
            drone_command=drone,
            delivery=delivery,
            local_failsafe=local_failsafe,
            command_refused=stimulus.name == "expired_lease",
            execution="unknown" if stimulus.name in {"expired_lease", "link_loss"} else None,
            query_path=_text_field(fields, "query_path"),
            query_task=_text_field(fields, "query_task"),
            query_command_id=_text_field(fields, "query_command_id"),
            profile_rejected=stimulus.rejected_profile,
            started=stimulus.started,
        )

    def _latch_events(
        self,
        stimulus: _Stimulus,
        ticket: Ticket,
        drone_name: str,
    ) -> tuple[GroundEvent, ...]:
        body: dict[str, object] = {"stimulus": stimulus.name, "motor_cut": False}
        events = [
            self._event("halt_requested", ticket, body),
            self._event(
                "stop_attempted",
                ticket,
                {"stimulus": stimulus.name, "dog": "halt", "drone": drone_name, "motor_cut": False},
            ),
            self._event("recovery_required", ticket, {"stimulus": stimulus.name}),
        ]
        if stimulus.name == "link_loss":
            events.append(
                self._event(
                    "link_lost",
                    ticket,
                    {
                        "stimulus": stimulus.name,
                        "delivery": "unknown",
                        "local_failsafe": True,
                        "delivery_guaranteed": False,
                    },
                )
            )
        if stimulus.name in _NOT_ARRIVAL:
            events.append(
                self._event(
                    "arrival_rejected",
                    ticket,
                    {"stimulus": stimulus.name, "arrival_confirmed": False, "goal_reached": False},
                )
            )
        if stimulus.name == "expired_lease":
            events.append(
                self._event(
                    "operation_failed",
                    ticket,
                    {"stimulus": stimulus.name, "execution": "unknown"},
                )
            )
        if stimulus.decision_label is not None:
            events.append(
                self._event(
                    "decision_received",
                    ticket,
                    {
                        "stimulus": stimulus.name,
                        "label": stimulus.decision_label,
                        "vision_cleared": False,
                    },
                )
            )
        return tuple(events)

    def _result(
        self,
        status: str,
        *,
        error: GroundError | None,
        events: tuple[GroundEvent, ...],
        stimulus: str,
        dog_command: Mapping[str, object] | None = None,
        drone_command: Mapping[str, object] | None = None,
        delivery: str = "issued",
        local_failsafe: bool = False,
        command_refused: bool = False,
        execution: str | None = None,
        query_path: str | None = None,
        query_task: str | None = None,
        query_command_id: str | None = None,
        same_handle: bool = False,
        reset_accepted: bool = False,
        ordinary_refused: bool = False,
        profile_rejected: str | None = None,
        started: bool | None = None,
    ) -> FeatureResult:
        self.last_events = events
        data = _compact(
            {
                "block_actions": self.handle is not None,
                "request_safety": self.safety_calls > 0 and self.handle is not None,
                "latch_set": self.handle is not None,
                "stimulus": stimulus,
                "handle": _handle_view(self.handle),
                "dog_command": dog_command,
                "drone_command": drone_command,
                "delivery": delivery,
                "physical_stop_claimed": False,
                "local_failsafe": local_failsafe,
                "delivery_guaranteed": False,
                "arrival_confirmed": False,
                "goal_reached": False,
                "detour": False,
                "motor_cut": False,
                "model_called": self.model_calls > 0,
                "command_refused": command_refused,
                "execution": execution,
                "query_path": query_path,
                "query_task": query_task,
                "query_command_id": query_command_id,
                "superseded_command_ids": self.superseded,
                "same_handle": same_handle,
                "reset_accepted": reset_accepted,
                "ordinary_refused": ordinary_refused,
                "vision_cleared": False,
                "profile_rejected": profile_rejected,
                "safety_requests": self.safety_calls,
                "started": started,
            }
        )
        return FeatureResult(status, freeze_map(data), events, error)

    def _journal(self, event: str, ticket: Ticket | None, data: dict[str, object]) -> None:
        records = getattr(self.services.journal, "records", None)
        sequence = len(records) + 1 if isinstance(records, list) else self._sequence
        self._sequence += 1
        clock = self.services.kernel.clock
        record = EventRecord(
            sequence=sequence,
            timestamp_utc=clock.utc_now().isoformat(),
            elapsed_s=clock.monotonic(),
            mission_id=None if ticket is None else ticket.mission_id,
            ticket=ticket,
            state="FAULT" if self.handle is not None else "IDLE",
            event=event,
            zone=None,
            target=None,
            modes=_MODES,
            data=freeze_map(_compact(data)),
        )
        self.services.journal.emit(record)

    def _event(self, kind: str, ticket: Ticket | None, payload: dict[str, object]) -> GroundEvent:
        return GroundEvent(kind, ticket, freeze_map(payload))


def _parse(payload: Mapping[str, object]) -> _Stimulus:
    name = _text(payload.get("stimulus"), "stimulus")
    profile, rejected_profile = _choice(payload, "profile", default="hover")
    link_loss_action, rejected_link = _choice(payload, "link_loss_action", default=None)
    rejected = rejected_profile or rejected_link
    if link_loss_action is None and rejected_link is not None:
        link_loss_action = "hover"
    return _Stimulus(
        name=name,
        profile=profile or "hover",
        link_loss_action=link_loss_action,
        rejected_profile=rejected,
        active_commands=_messages(payload, "active_commands"),
        command=_message(payload, "command"),
        started=_flag(payload, "started"),
        workers_pending=_flag(payload, "workers_pending"),
        recovery_token=_token(payload),
        proposal_action=_proposal(payload),
        decision_label=_label(payload),
        vision_pending=_flag(payload, "vision_pending") is True,
    )


def _choice(
    payload: Mapping[str, object],
    key: str,
    *,
    default: str | None,
) -> tuple[str | None, str | None]:
    if key not in payload:
        return default, None
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{key} must be a string")
    cleaned = value.strip()
    if cleaned in _FORBIDDEN:
        return default if default is not None else "hover", cleaned
    if cleaned not in _PROFILES:
        raise fault("invalid_input", f"{key} must be hover or land")
    return cleaned, None


def _flag(payload: Mapping[str, object], key: str) -> bool | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, bool):
        raise fault("invalid_input", f"{key} must be a boolean")
    return value


def _token(payload: Mapping[str, object]) -> str | None:
    if "recovery_token" not in payload:
        return None
    value = payload["recovery_token"]
    if isinstance(value, bool) or not isinstance(value, str) or value == "":
        raise fault("invalid_input", "recovery_token must be a string")
    return value


def _label(payload: Mapping[str, object]) -> str | None:
    if "decision" not in payload:
        return None
    value = payload["decision"]
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise fault("invalid_input", "decision must be an object")
    label = value.get("label")
    if not isinstance(label, str) or not label.strip():
        raise fault("invalid_input", "decision label must be a string")
    return label.strip()


def _proposal(payload: Mapping[str, object]) -> str | None:
    if "proposal_action" not in payload:
        return None
    value = payload["proposal_action"]
    if not isinstance(value, str) or value not in _PROPOSALS:
        raise fault("invalid_input", "proposal action must be search, track, or homing")
    return value


def _messages(payload: Mapping[str, object], key: str) -> tuple[Mapping[str, object], ...]:
    if key not in payload:
        return ()
    value = payload[key]
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise fault("invalid_input", f"{key} must be a list")
    found: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, (str, bytes)) or not isinstance(item, Mapping):
            raise fault("invalid_input", f"{key} entries must be objects")
        found.append(item)
    return tuple(found)


def _message(payload: Mapping[str, object], key: str) -> Mapping[str, object] | None:
    if key not in payload:
        return None
    value = payload[key]
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise fault("invalid_input", f"{key} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{label} must be a string")
    return value.strip()


def _lease_fields(stimulus: _Stimulus) -> dict[str, object]:
    if stimulus.name != "expired_lease":
        return {}
    command = stimulus.command
    if command is None:
        raise fault("invalid_input", "expired lease requires the command that did not start")
    if stimulus.started is None:
        raise fault("invalid_input", "started must be a boolean")
    target = destination(command)
    if target == "dog":
        path = "feature.v2_dog_ack"
        task = "24"
    else:
        path = "feature.v2_drone_ack"
        task = "18"
    return {
        "execution": "unknown",
        "query_path": path,
        "query_task": task,
        "query_command_id": command_id(command),
        "started": stimulus.started,
    }


def _drone_action(stimulus: _Stimulus) -> str:
    if stimulus.name == "explicit_land":
        return "land"
    if stimulus.name == "link_loss":
        chosen = stimulus.link_loss_action or stimulus.profile
        return "land" if chosen == "land" else "hover"
    return "land" if stimulus.profile == "land" else "hover"


def _request(name: str, extra: dict[str, object]) -> FeatureRequest:
    payload: dict[str, object] = {"stimulus": name}
    payload.update(extra)
    return FeatureRequest("guard", name, None, freeze_map(payload))


def _failed(exc: GroundFault, *, latched: bool = False) -> FeatureResult:
    data = freeze_map(
        {
            "block_actions": latched,
            "request_safety": latched,
            "latch_set": latched,
            "motor_cut": False,
            "model_called": False,
            "physical_stop_claimed": False,
            "vision_cleared": False,
        }
    )
    return FeatureResult("failed", data, (), exc.error)


def _foundation(
    *,
    ok: bool,
    spec: CaseSpec,
    trace: tuple[str, ...],
    events: tuple[GroundEvent, ...],
) -> FeatureResult:
    shown = spec.trace if ok else trace
    detail = spec.detail if ok else "case failed"
    data = freeze_map(
        {
            "authorized": spec.authorized,
            "retained": spec.retained if ok else True,
            "detail": detail,
            "trace": shown,
            "device_calls": 0,
            "measurement_clock": "manual",
            "within_limit": ok,
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
    )
    if not ok:
        return FeatureResult(
            "failed",
            data,
            (),
            GroundError("validation_failed", "case failed", True),
        )
    if spec.status == "ok":
        return FeatureResult("ok", data, events, None)
    code = spec.error_code or "rejected"
    return FeatureResult(spec.status, data, events, GroundError(code, spec.detail, True))


def _compact(data: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in data.items() if value is not None}


def _handle_view(handle: SafetyHandle | None) -> dict[str, object] | None:
    if handle is None:
        return None
    return {
        "mission_id": handle.ticket.mission_id,
        "epoch": handle.ticket.epoch,
        "stage_id": handle.ticket.stage_id,
        "reason": handle.reason,
        "generation": handle.generation,
    }


def _ticket_of(handle: SafetyHandle | None) -> Ticket | None:
    if handle is None:
        return None
    return handle.ticket


def _text_field(fields: Mapping[str, object], key: str) -> str | None:
    value = fields.get(key)
    if isinstance(value, str):
        return value
    return None


def _action_of(result: FeatureResult, key: str) -> str:
    value = result.data.get(key)
    if not isinstance(value, Mapping):
        return ""
    return command_action(value)


def _safety_trace(services: BaseServices) -> tuple[str, ...]:
    trace = getattr(services.safety, "trace", ())
    if isinstance(trace, list):
        return tuple(str(item) for item in trace)
    return ()


def _journal_ids(services: BaseServices) -> tuple[str, ...] | None:
    records = getattr(services.journal, "records", None)
    if not isinstance(records, list) or not records:
        return None
    data = getattr(records[-1], "data", None)
    if not isinstance(data, Mapping):
        return None
    value = data.get("superseded_command_ids")
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return None


def _live_calls(services: BaseServices) -> int:
    devices = getattr(services.adapters, "devices", None)
    value = getattr(devices, "live_call_count", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value
