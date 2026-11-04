"""Seeded drone-ack cases for the task harness."""

from __future__ import annotations

from patrol.ground.extensions.g18.names import SCHEMA, SLOT, TASK_ID
from patrol.ground.extensions.g18.script import (
    ACCEPTED_TRACE,
    CONFLICT_TRACE,
    DOG_TRACE,
    DUPLICATE_TRACE,
    LANDING_TRACE,
    LOCAL_FLAG_TRACE,
    ORDERED_TRACE,
    STALE_TRACE,
    TIMEOUT_TRACE,
    UNKNOWN_COMMAND_TRACE,
    UNVERIFIED_TRACE,
)
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "dog.run_route",
    "drone.inspect",
    "drone.land",
    "drone.takeoff",
    "reasoner.assess_incident",
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
        trace: tuple[str, ...],
        detail: str,
        *,
        status: str = "ok",
        error_code: str | None = None,
    ) -> SimulationCase:
        expected: dict[str, object] = {
            "status": status,
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
            "measurement_clock": "manual",
            "within_limit": True,
            "authorized": False,
            "retained": False,
            "detail": detail,
            "device_calls": 0,
            "trace": trace,
        }
        if error_code is not None:
            expected["error_code"] = error_code
        return SimulationCase(
            task_id=TASK_ID,
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=_FORBIDDEN,
            teardown=_TEARDOWN,
        )

    return (
        make("ordered_acks", ORDERED_TRACE, "track_completed_airborne"),
        make("accepted_only", ACCEPTED_TRACE, "accepted_not_completed"),
        make("reply_timeout", TIMEOUT_TRACE, "query_required"),
        make(
            "landing_unknown",
            LANDING_TRACE,
            "landing_unknown",
            status="blocked",
            error_code="recovery_required",
        ),
        make("duplicate_final", DUPLICATE_TRACE, "idempotent_final"),
        make(
            "conflicting_final",
            CONFLICT_TRACE,
            "conflict_fault",
            status="failed",
            error_code="unsafe_state",
        ),
        make(
            "stale_epoch",
            STALE_TRACE,
            "stale_epoch",
            status="blocked",
            error_code="epoch_mismatch",
        ),
        make("unverified_completion", UNVERIFIED_TRACE, "unverified_completion"),
        make("local_flag_ignored", LOCAL_FLAG_TRACE, "local_flag_ignored"),
        make(
            "unknown_command",
            UNKNOWN_COMMAND_TRACE,
            "unknown_command_id",
            status="blocked",
            error_code="rejected",
        ),
        make(
            "dog_ack",
            DOG_TRACE,
            "dog_lifecycle",
            status="blocked",
            error_code="rejected",
        ),
    )
