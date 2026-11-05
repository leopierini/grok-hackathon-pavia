"""Scripted proximity cases for the frozen Task 01 harness."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_TAIL = (
    "journal_untouched",
    "state_untouched",
    "flight_state_untouched",
    "recovery_untouched",
    "no_land",
)
_MOTION = (
    "dog.run_route",
    "dog.halt",
    "drone.inspect",
    "drone.land",
    "drone.close",
    "reasoner.assess_incident",
)
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    built = [_case(seed, case_id, **fields) for case_id, fields in _EXPECTATIONS]
    return tuple(built)


def _case(seed: int, case_id: str, **fields: object) -> SimulationCase:
    expected: dict[str, object] = {
        "status": "ok",
        "error_code": None,
        "error_detail": None,
        "simulated": True,
        "live_call_count": 0,
        "slot": "feature.v2_proximity",
        "schema_version": "ground-task-v2",
        "measurement_clock": "manual",
        "within_limit": False,
        "authorized": False,
        "retained": False,
        "device_calls": 0,
        "detail": "unresolved",
        "trace": (),
    }
    expected.update(fields)
    return SimulationCase(
        task_id="GROUND-26",
        case_id=case_id,
        seed=seed,
        setup=freeze_map({"seed": seed}),
        stimuli=(),
        barriers=(),
        faults=(),
        expected=freeze_map(expected),
        forbidden_calls=_MOTION,
        teardown=_TEARDOWN,
    )


def _goal(thresholds: str, dog: str, drone: str) -> dict[str, object]:
    return {
        "status": "ok",
        "detail": "goal_reached",
        "authorized": True,
        "within_limit": True,
        "trace": (
            thresholds,
            dog,
            drone,
            "mission.event",
            "demo_goal_reached",
            *_TAIL,
        ),
    }


def _open(reason: str, thresholds: str = "thresholds:1.5,1.5") -> dict[str, object]:
    return {"trace": (thresholds, reason, "no_goal_event", *_TAIL)}


def _fail(
    detail: str,
    code: str,
    text: str,
    reason: str,
    thresholds: str = "thresholds:1.5,1.5",
) -> dict[str, object]:
    return {
        "status": "failed",
        "detail": detail,
        "error_code": code,
        "error_detail": text,
        "trace": (thresholds, reason, "no_goal_event", *_TAIL),
    }


_EXPECTATIONS: tuple[tuple[str, dict[str, object]], ...] = (
    ("example_accepted", _goal("thresholds:1.5,1.5", "operator_dog_ok", "operator_drone_ok")),
    ("null_drone_offset", _open("unresolved:missing_drone_offset")),
    (
        "full_3d_at_4m",
        _fail(
            "rejected",
            "rejected",
            "a 4 m aircraft height cannot be within 1 m of the person in full 3D",
            "rejected:full_3d_at_4m",
        ),
    ),
    ("moving_dog", _open("unresolved:dog_moving")),
    ("operator_enabled", _goal("thresholds:1.5,1.5", "operator_dog_ok", "operator_drone_ok")),
    ("operator_disabled", _open("unresolved:operator_disabled")),
    ("moving_beacon", _open("unresolved:beacon_moving")),
    (
        "clearance_not_range",
        _fail(
            "rejected",
            "rejected",
            "obstacle clearance is not the dog-to-target range",
            "rejected:clearance",
        ),
    ),
    ("stale_timestamp", _open("unresolved:stale")),
    ("age_boundary", _goal("thresholds:1.5,1.5", "operator_dog_ok", "operator_drone_ok")),
    (
        "single_3d_distance",
        _fail(
            "rejected",
            "rejected",
            "one 3D distance cannot satisfy both the dog range and the drone horizontal offset",
            "rejected:single_3d_distance",
        ),
    ),
    ("operator_one_side", _open("unresolved:operator_incomplete")),
    ("lidar_automatic", _goal("thresholds:1.5,1.5", "dog_range_ok", "drone_horizontal_ok")),
    ("profile_threshold", _open("unresolved:outside_threshold", "thresholds:1,1.5")),
    (
        "rssi_not_range",
        _fail(
            "rejected",
            "rejected",
            "RSSI cannot be converted into dog range",
            "rejected:rssi",
        ),
    ),
    ("person_not_proximity", _open("unresolved:person_detection")),
    ("track_mismatch", _open("unresolved:track_mismatch")),
    ("association_invalid", _open("unresolved:association_invalid")),
    (
        "cancelled",
        {
            "status": "failed",
            "detail": "cancelled",
            "error_code": "cancelled",
            "error_detail": "cancellation is latched",
            "trace": ("cancelled", "no_goal_event", *_TAIL),
        },
    ),
    (
        "string_bool",
        _fail(
            "invalid_input",
            "invalid_input",
            "dog_stopped must be a boolean",
            "invalid_input",
        ),
    ),
    ("timestamp_future", _open("unresolved:timestamp_future")),
    ("thresholds_unset", _open("unresolved:thresholds_unset", "thresholds:unset")),
    (
        "height_without_3d_claim",
        _goal("thresholds:1.5,1.5", "operator_dog_ok", "operator_drone_ok"),
    ),
    ("threshold_equal", _goal("thresholds:1.5,1.5", "dog_range_ok", "drone_horizontal_ok")),
)
