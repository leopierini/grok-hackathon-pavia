"""Scripted dog-navigation cases. The harness compares these to the provider."""

from __future__ import annotations

from patrol.ground.extensions.g20.policy import SCHEMA, SLOT
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

CASE_IDS = (
    "example_pair",
    "blocked_empty",
    "expired_candidate",
    "slam_disarmed",
    "standing_null",
    "map_epoch_changed",
    "no_move_local",
    "clearance_separate",
    "transport_mismatch",
    "target_range",
    "wrong_frame",
    "avoidance_null",
    "wifi_profile",
    "blocked_inconsistent",
    "safe_false",
    "string_boolean",
    "lidar_missing",
)

_MOTION = (
    "dog.run_route",
    "dog.move_local",
    "move_local",
    "drone.inspect",
    "reasoner.assess_incident",
)
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)
_HAPPY = (
    "standing:true",
    "stationary:true",
    "avoidance:true",
    "mode:slam_local_planner",
    "slam:localized",
    "transport:ethernet",
    "profile:ethernet",
    "clearance:0.8",
    "target_range:absent",
    "blocked:false",
    "ready:true",
    "ready_to_wait:false",
    "usable:candidate-forward-01",
    "pose_epoch:1",
    "map_epoch:1",
    "command:none",
    "move_local:none",
    "invented:none",
)
_WAIT = (
    "standing:true",
    "stationary:true",
    "avoidance:true",
    "mode:slam_local_planner",
    "slam:localized",
    "transport:ethernet",
    "profile:ethernet",
    "clearance:0.8",
    "target_range:absent",
    "blocked:true",
    "ready:false",
    "ready_to_wait:true",
    "usable:empty",
    "pose_epoch:1",
    "map_epoch:1",
    "command:none",
    "move_local:none",
    "invented:none",
)
_PARSE = (
    "standing:invalid",
    "ready:false",
    "ready_to_wait:false",
    "usable:empty",
    "target_range:absent",
    "command:none",
    "move_local:none",
    "invented:none",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(case_id: str, expected: dict[str, object]) -> SimulationCase:
        merged: dict[str, object] = {
            "status": "ok",
            "error_code": None,
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
            "measurement_clock": "manual",
            "within_limit": True,
            "device_calls": 0,
            "retained": False,
            "authorized": False,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-20",
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

    accepted: dict[str, object] = {"detail": "candidate-forward-01", "trace": _HAPPY}
    waiting: dict[str, object] = {"detail": "ready_to_wait", "trace": _WAIT}
    return (
        make("example_pair", accepted),
        make("blocked_empty", waiting),
        make(
            "expired_candidate",
            {
                "detail": "expired",
                "trace": _with(_HAPPY, ready="false", usable="empty", extra=("dropped:expired",)),
            },
        ),
        make(
            "slam_disarmed",
            {
                "status": "blocked",
                "error_code": "rejected",
                "error_detail": "slam_local_planner was claimed while slam is disarmed",
                "detail": "slam_disarmed",
                "trace": _with(_HAPPY, ready="false", usable="empty"),
            },
        ),
        make(
            "standing_null",
            {
                "detail": "not_ready",
                "trace": _with(
                    _HAPPY,
                    standing="null",
                    ready="false",
                    usable="empty",
                    extra=("withheld:standing",),
                ),
            },
        ),
        make(
            "map_epoch_changed",
            {
                "detail": "epoch_dropped",
                "trace": _with(
                    _HAPPY,
                    ready="false",
                    usable="empty",
                    map_epoch="2",
                    extra=("dropped:map_epoch",),
                ),
            },
        ),
        make("no_move_local", waiting),
        make("clearance_separate", accepted),
        make(
            "transport_mismatch",
            {
                "detail": "transport_mismatch",
                "trace": _with(
                    _HAPPY,
                    profile="wifi",
                    ready="false",
                    usable="empty",
                    extra=("withheld:transport",),
                ),
            },
        ),
        make(
            "target_range",
            {
                "status": "blocked",
                "error_code": "rejected",
                "error_detail": (
                    "a candidate included a target range; clearance is not target range"
                ),
                "detail": "target_range",
                "trace": _with(_HAPPY, ready="false", usable="empty"),
            },
        ),
        make(
            "wrong_frame",
            {
                "detail": "frame_dropped",
                "trace": _with(
                    _HAPPY,
                    ready="false",
                    usable="empty",
                    extra=("dropped:frame",),
                ),
            },
        ),
        make(
            "avoidance_null",
            {
                "detail": "not_ready",
                "trace": _with(
                    _HAPPY,
                    avoidance="null",
                    ready="false",
                    usable="empty",
                    extra=("withheld:avoidance",),
                ),
            },
        ),
        make(
            "wifi_profile",
            {
                "detail": "candidate-forward-01",
                "trace": _with(_HAPPY, transport="wifi", profile="wifi"),
            },
        ),
        make(
            "blocked_inconsistent",
            {
                "status": "blocked",
                "error_code": "rejected",
                "error_detail": "blocked true requires an empty candidate list",
                "detail": "blocked_inconsistent",
                "trace": _with(_HAPPY, blocked="true", ready="false", usable="empty"),
            },
        ),
        make(
            "safe_false",
            {
                "detail": "unsafe_dropped",
                "trace": _with(
                    _HAPPY,
                    ready="false",
                    usable="empty",
                    extra=("dropped:unsafe",),
                ),
            },
        ),
        make(
            "string_boolean",
            {
                "status": "failed",
                "error_code": "invalid_input",
                "error_detail": "standing must be true, false, or null",
                "detail": "standing must be true, false, or null",
                "trace": _PARSE,
            },
        ),
        make(
            "lidar_missing",
            {
                "status": "failed",
                "error_code": "validation_failed",
                "error_detail": (
                    "non-empty candidates require lidar_observed_at and minimum_clearance_m"
                ),
                "detail": "lidar_required",
                "trace": _with(_HAPPY, ready="false", usable="empty"),
            },
        ),
    )


def _with(
    base: tuple[str, ...],
    *,
    standing: str | None = None,
    avoidance: str | None = None,
    transport: str | None = None,
    profile: str | None = None,
    blocked: str | None = None,
    ready: str | None = None,
    usable: str | None = None,
    map_epoch: str | None = None,
    extra: tuple[str, ...] = (),
) -> tuple[str, ...]:
    replaced = {
        "standing": standing,
        "avoidance": avoidance,
        "transport": transport,
        "profile": profile,
        "blocked": blocked,
        "ready": ready,
        "usable": usable,
        "map_epoch": map_epoch,
    }
    rows: list[str] = []
    for item in base:
        name, _value = item.split(":", 1)
        update = replaced.get(name)
        rows.append(item if update is None else f"{name}:{update}")
    rows.extend(extra)
    return tuple(rows)
