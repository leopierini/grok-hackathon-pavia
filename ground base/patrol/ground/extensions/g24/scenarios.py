"""Scripted dog-ack cases. The harness compares these traces with the live provider."""

from __future__ import annotations

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
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_MOTION = (
    "dog.run_route",
    "dog.halt",
    "dog.prepare",
    "dog.capture_frame",
    "drone.inspect",
    "drone.land",
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
        status: str = "ok",
        error_code: str | None = None,
    ) -> SimulationCase:
        merged: dict[str, object] = {
            "status": status,
            "simulated": True,
            "live_call_count": 0,
            "slot": "feature.v2_dog_ack",
            "schema_version": "ground-task-v2",
            "measurement_clock": "manual",
            "within_limit": True,
            "authorized": False,
            "device_calls": 0,
            "retained": False,
        }
        if error_code is not None:
            merged["error_code"] = error_code
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-24",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(merged),
            forbidden_calls=_MOTION,
            teardown=_TEARDOWN,
        )

    return (
        make("success_sequence", {"detail": "verified_stationary", "trace": SUCCESS_TRACE}),
        make("accepted_only", {"detail": "accepted_not_stopped", "trace": ACCEPTED_TRACE}),
        make("expired_rejection", {"detail": "expired_no_motion", "trace": EXPIRED_TRACE}),
        make("timeout_query", {"detail": "timeout_query", "trace": TIMEOUT_TRACE}),
        make(
            "unverified_completed",
            {"detail": "unverified_not_stopped", "trace": UNVERIFIED_TRACE},
        ),
        make("halt_separate", {"detail": "halt_separate", "trace": HALT_TRACE}),
        make("replay_terminal", {"detail": "idempotent_one_event", "trace": REPLAY_TRACE}),
        make(
            "lifecycle_report",
            {"detail": "lifecycle_report", "trace": LIFECYCLE_REPORT_TRACE},
        ),
        make(
            "conflict_terminal",
            {"detail": "conflict", "trace": CONFLICT_TRACE},
            status="failed",
            error_code="unsafe_state",
        ),
        make(
            "stale_epoch",
            {"detail": "stale_epoch", "trace": STALE_TRACE},
            status="failed",
            error_code="epoch_mismatch",
        ),
        make("lidar_stop", {"detail": "lidar_not_arrival", "trace": LIDAR_TRACE}),
        make(
            "foreign_command",
            {"detail": "foreign_command", "trace": FOREIGN_TRACE},
            status="failed",
            error_code="rejected",
        ),
        make(
            "repeated_command",
            {"detail": "repeated_command", "trace": REPEATED_TRACE},
            status="failed",
            error_code="rejected",
        ),
        make(
            "readiness_disagrees",
            {"detail": "readiness_disagrees", "trace": READINESS_TRACE},
        ),
    )
