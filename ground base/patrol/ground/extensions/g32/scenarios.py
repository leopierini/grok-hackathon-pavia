"""Scripted rehearsal cases. The harness compares foundation result keys."""

from __future__ import annotations

from patrol.ground.extensions.g32.rehearsal import (
    BLOCKED_TRACE,
    HAPPY_TRACE,
    NOISY_TRACE,
    SECOND_TRACE,
    STALE_TRACE,
    UNCONTROLLED_TRACE,
    UNKNOWN_TRACE,
    distinct_ids,
)
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "dog.run_route",
    "drone.inspect",
    "takeoff_attempt",
    "reasoner.assess_incident",
    "reasoner.assess_ground_view",
)
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(
        case_id: str,
        expected: dict[str, object],
        *,
        teardown: tuple[str, ...] = _TEARDOWN,
    ) -> SimulationCase:
        merged: dict[str, object] = {
            "simulated": True,
            "live_call_count": 0,
            "slot": "feature.v2_rehearsal",
            "schema_version": "ground-task-v2",
            "measurement_clock": "manual",
            "within_limit": True,
            "authorized": False,
            "device_calls": 0,
            "retained": False,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-32",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(merged),
            forbidden_calls=_FORBIDDEN,
            teardown=teardown,
        )

    left, right = distinct_ids(seed)
    return (
        make(
            "happy_path",
            {"status": "ok", "detail": "happy_path", "trace": HAPPY_TRACE},
        ),
        make(
            "unknown_landing",
            {
                "status": "failed",
                "error_code": "validation_failed",
                "error_detail": "goal_reached;landing_unverified",
                "detail": "goal_reached;landing_unverified",
                "trace": UNKNOWN_TRACE,
            },
        ),
        make(
            "blocked_planner",
            {
                "status": "blocked",
                "error_code": "rejected",
                "error_detail": "stopped_no_candidate",
                "detail": "stopped_no_candidate",
                "trace": BLOCKED_TRACE,
            },
        ),
        make(
            "noisy_rssi",
            {
                "status": "blocked",
                "error_code": "rejected",
                "error_detail": "noisy_rssi_stop",
                "detail": "noisy_rssi_stop",
                "trace": NOISY_TRACE,
            },
        ),
        make(
            "stale_frame",
            {
                "status": "failed",
                "error_code": "validation_failed",
                "error_detail": "stale_frame_dropped",
                "detail": "stale_frame_dropped",
                "trace": STALE_TRACE,
            },
        ),
        make(
            "uncontrolled_motion",
            {
                "status": "ok",
                "detail": "supervised_or_stopped",
                "trace": UNCONTROLLED_TRACE,
            },
        ),
        make(
            "real_mode",
            {
                "status": "failed",
                "error_code": "invalid_input",
                "error_detail": "real_mode_rejected",
                "detail": "real_mode_rejected",
                "trace": (),
            },
        ),
        make(
            "string_simulated",
            {
                "status": "failed",
                "error_code": "invalid_input",
                "error_detail": "simulated_flag_rejected",
                "detail": "simulated_flag_rejected",
                "trace": (),
            },
        ),
        make(
            "catalog_mission",
            {
                "status": "failed",
                "error_code": "validation_failed",
                "error_detail": "causal_order",
                "detail": "causal_order",
                "trace": ("causal_order",),
            },
        ),
        make(
            "second_takeoff",
            {
                "status": "failed",
                "error_code": "unsafe_state",
                "error_detail": "second_takeoff_rejected",
                "detail": "second_takeoff_rejected",
                "trace": SECOND_TRACE,
            },
        ),
        make(
            "distinct_runs",
            {
                "status": "ok",
                "detail": "two_directories",
                "trace": (f"directory:{left}", f"directory:{right}"),
            },
        ),
        make(
            "overwrite_rejected",
            {
                "status": "failed",
                "error_code": "rejected",
                "error_detail": "overwrite_rejected",
                "detail": "overwrite_rejected",
                "trace": ("run_created", "overwrite_rejected"),
            },
        ),
        make(
            "barrier_release",
            {
                "status": "ok",
                "detail": "barrier_released",
                "trace": ("barrier_held",),
                "retained": True,
            },
            teardown=_TEARDOWN + ("assert_released",),
        ),
    )
