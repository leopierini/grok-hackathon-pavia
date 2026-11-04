"""Scripted recovery cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_SLOT = "feature.v2_recovery"
_SCHEMA = "ground-task-v2"
_MOTION = ("dog.run_route", "drone.inspect", "drone.land", "reasoner.assess_incident")


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(
        case_id: str,
        expected: dict[str, object],
        forbidden: tuple[str, ...] = _MOTION,
    ) -> SimulationCase:
        return SimulationCase(
            task_id="GROUND-27",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=forbidden,
            teardown=("release_barriers", "collect_tasks", "remove_owned_temp", "assert_no_socket"),
        )

    common = {
        "slot": _SLOT,
        "schema_version": _SCHEMA,
        "device_calls": 0,
        "live_call_count": 0,
        "simulated": True,
        "authorized": False,
    }
    return (
        make(
            "goal_and_verified_landing",
            {
                **common,
                "status": "ok",
                "trace": (
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
                ),
            },
        ),
        make(
            "goal_and_unknown_landing",
            {
                **common,
                "status": "blocked",
                "error_code": "recovery_required",
                "error_detail": "Goal record cannot clear unknown aircraft state.",
                "trace": (
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
                ),
            },
        ),
        make(
            "land_not_attempted",
            {
                **common,
                "status": "ok",
                "trace": (
                    "goal_status:reached",
                    "landing_status:not_attempted",
                    "recovery_required:false",
                    "next_mission_blocked:false",
                    "dog:hold_stop",
                    "search_commands:0",
                    "land_ack_accepted:false",
                    "observation_not_landing:true",
                ),
            },
        ),
        make(
            "flight_state_contradiction",
            {
                **common,
                "status": "blocked",
                "error_code": "recovery_required",
                "error_detail": "flight_state contradicts the completed land acknowledgement",
                "trace": (
                    "goal_status:reached",
                    "landing_status:contradicted",
                    "recovery_required:true",
                    "device_recovery_required:true",
                    "fault:flight_state_airborne",
                    "dog:hold_stop",
                    "search_commands:0",
                    "goal_kept:true",
                ),
            },
        ),
        make(
            "replay_one_record",
            {
                **common,
                "status": "ok",
                "trace": (
                    "goal_status:reached",
                    "landing_status:verified",
                    "replayed:true",
                    "record_count:1",
                    "record_id:recovery:msg-event-demo_goal_reached:cmd-drone-land-001",
                    "search_commands:0",
                ),
            },
        ),
        make(
            "clear_without_observation",
            {
                **common,
                "status": "failed",
                "error_code": "rejected",
                "error_detail": "recovery cannot be cleared without a new grounded observation",
                "trace": (
                    "clear:rejected",
                    "recovery_required:true",
                    "landing_status:unverified",
                    "goal_status:reached",
                    "record_count:1",
                    "new_observation:false",
                ),
            },
        ),
        make(
            "no_search_command",
            {
                **common,
                "status": "ok",
                "trace": (
                    "search_commands:0",
                    "issued_commands:0",
                    "dog:hold_stop",
                    "proposal_ignored:search",
                    "device_calls:0",
                ),
            },
        ),
        make(
            "save_both_statuses",
            {
                **common,
                "status": "ok",
                "trace": (
                    "saved:goal_status:reached",
                    "saved:landing_status:verified",
                    "record_has_both:true",
                ),
            },
        ),
        make(
            "goal_false_verified_landing",
            {
                **common,
                "status": "ok",
                "trace": (
                    "goal_status:not_reached",
                    "landing_status:verified",
                    "goal_invented:false",
                    "recovery_required:false",
                    "search_commands:0",
                ),
            },
        ),
        make(
            "track_not_land",
            {
                **common,
                "status": "ok",
                "trace": (
                    "landing_status:not_attempted",
                    "land_ack_accepted:false",
                    "track_command:cmd-drone-001",
                    "goal_status:not_reached",
                    "search_commands:0",
                ),
            },
        ),
    )
