"""Expected simulation rows. The provider and the scenario module share this list."""

from __future__ import annotations

from dataclasses import dataclass

SLOT = "feature.v2_safety"
SCHEMA = "ground-task-v2"


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    status: str
    detail: str
    trace: tuple[str, ...]
    authorized: bool = False
    retained: bool = True
    error_code: str | None = None


def _case(
    case_id: str,
    detail: str,
    trace: tuple[str, ...],
    *,
    status: str = "ok",
    retained: bool = True,
    error_code: str | None = None,
) -> CaseSpec:
    return CaseSpec(
        case_id=case_id,
        status=status,
        detail=detail,
        trace=trace,
        authorized=False,
        retained=retained,
        error_code=error_code,
    )


SPECS: tuple[CaseSpec, ...] = (
    _case(
        "halt_during_vision_timeout",
        "dog_halt_drone_hover_no_model",
        (
            "stimulus:operator_halt",
            "dog:halt",
            "drone:hover",
            "model_calls:0",
            "vision_not_awaited",
            "clock_delta:0",
            "motor_cut:false",
        ),
    ),
    _case(
        "late_decision",
        "latch_still_set",
        (
            "stimulus:operator_halt",
            "late:person_visible",
            "latch_set",
            "cleared:false",
            "model_calls:0",
        ),
    ),
    _case(
        "expired_lease",
        "unstarted_refused_execution_unknown",
        (
            "stimulus:expired_lease",
            "started:false",
            "command_refused",
            "execution:unknown",
            "query:feature.v2_dog_ack",
            "query_task:24",
            "dog:halt",
            "drone:hover",
        ),
    ),
    _case(
        "link_loss",
        "unknown_delivery_local_failsafe",
        (
            "stimulus:link_loss",
            "dog:halt",
            "drone:hover",
            "delivery:unknown",
            "physical_stop:unclaimed",
            "local_failsafe:true",
            "delivery_guaranteed:false",
        ),
    ),
    _case(
        "obstacle_block",
        "halt_not_detour",
        (
            "stimulus:obstacle_block",
            "dog:halt",
            "drone:hover",
            "detour:false",
            "arrival:false",
        ),
    ),
    _case(
        "noisy_rssi",
        "stop_not_goal_reached",
        (
            "stimulus:noisy_rssi",
            "dog:halt",
            "drone:hover",
            "goal_reached:false",
            "arrival:false",
        ),
    ),
    _case(
        "replay_halt",
        "one_handle",
        (
            "same_handle",
            "safety_requests:1",
            "dog_halt_emissions:1",
            "drone_hover_emissions:1",
        ),
    ),
    _case(
        "reset_without_token",
        "reset_rejected",
        ("reset_rejected", "token:missing", "latch_set"),
        status="failed",
        error_code="rejected",
    ),
    _case(
        "superseded_ids",
        "superseded_command_ids_saved",
        ("superseded:cmd-dog-001,cmd-drone-001", "journaled"),
    ),
    _case(
        "explicit_land",
        "explicit_land",
        (
            "stimulus:explicit_land",
            "dog:halt",
            "drone:land",
            "motor_cut:false",
        ),
    ),
    _case(
        "lost_track",
        "lost_track_not_arrival",
        (
            "stimulus:lost_track",
            "dog:halt",
            "goal_reached:false",
            "arrival:false",
        ),
    ),
    _case(
        "reset_pending_workers",
        "reset_rejected_workers",
        ("reset_rejected", "workers:pending", "latch_set"),
        status="failed",
        error_code="rejected",
    ),
    _case(
        "motor_cut_rejected",
        "motor_cut_not_emitted",
        (
            "profile_rejected:emergency",
            "dog:halt",
            "drone:hover",
            "motor_cut:false",
        ),
    ),
    _case(
        "stale_frame",
        "stale_vision_cannot_clear",
        (
            "stimulus:stale_frame",
            "dog:halt",
            "late:person_visible",
            "cleared:false",
        ),
    ),
    _case(
        "link_loss_land_profile",
        "link_loss_land_profile",
        (
            "stimulus:link_loss",
            "drone:land",
            "delivery:unknown",
            "local_failsafe:true",
        ),
    ),
    _case(
        "ordinary_proposals",
        "ordinary_proposals_refused",
        (
            "proposal:search",
            "proposal:track",
            "proposal:homing",
            "refused",
            "latch_set",
        ),
    ),
    _case(
        "reset_with_token",
        "reset_accepted",
        ("reset_accepted", "latch_cleared", "workers:quiescent"),
        retained=False,
    ),
)

SPEC_BY_ID: dict[str, CaseSpec] = {spec.case_id: spec for spec in SPECS}
