"""Scripted journal cases. The harness runs LogFeature against kernel doubles."""

from __future__ import annotations

from patrol.ground.extensions.g29.classify import SLOT, TASK_SCHEMA
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_MOTION = ("dog.run_route", "drone.inspect", "reasoner.assess_incident")
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(case_id: str, expected: dict[str, object]) -> SimulationCase:
        merged: dict[str, object] = {
            "status": "ok",
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": TASK_SCHEMA,
            "measurement_clock": "manual",
            "within_limit": True,
            "authorized": True,
            "retained": False,
            "device_calls": 0,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-29",
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
        make(
            "each_kind",
            {"detail": "kinds_journaled", "trace": ("ids_copied", "categories_assigned")},
        ),
        make(
            "missing_command_id",
            {
                "status": "failed",
                "error_code": "rejected",
                "error_detail": "command record is missing command_id",
                "authorized": False,
                "detail": "command record is missing command_id",
                "trace": ("rejected", "command_id"),
            },
        ),
        make(
            "goal_and_landing",
            {
                "detail": "distinct_events",
                "trace": ("demo_goal_reached", "landing_unverified"),
            },
        ),
        make(
            "secret_redacted",
            {
                "detail": "api_key_absent",
                "trace": ("redacted:api_key", "value_absent"),
            },
        ),
        make(
            "flush_failed",
            {
                "authorized": False,
                "detail": "not_published",
                "trace": ("persistence_fault", "published_false"),
            },
        ),
        make(
            "replay_once",
            {"detail": "one_record", "trace": ("replayed", "one_record")},
        ),
        make(
            "image_hash",
            {"detail": "bytes_absent", "trace": ("hash_present", "bytes_absent")},
        ),
        make(
            "null_rssi",
            {"detail": "median_null", "trace": ("null_not_zero",)},
        ),
    )
