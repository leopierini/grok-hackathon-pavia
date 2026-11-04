"""Scripted dog-camera handoff cases for the frozen simulator."""

from __future__ import annotations

from patrol.ground.extensions.g25.samples import CASE_IDS
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_MOTION = ("dog.run_route", "drone.inspect", "dog.capture_frame", "reasoner.assess_incident")
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)
_BASE: dict[str, object] = {
    "status": "ok",
    "simulated": True,
    "live_call_count": 0,
    "slot": "feature.v2_dog_acquire",
    "schema_version": "ground-task-v2",
    "measurement_clock": "manual",
    "within_limit": True,
    "authorized": False,
    "retained": False,
    "device_calls": 0,
}


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    return tuple(_case(seed, case_id, _EXPECTED[case_id]) for case_id in CASE_IDS)


def _case(seed: int, case_id: str, expected: dict[str, object]) -> SimulationCase:
    merged = dict(_BASE)
    merged.update(expected)
    return SimulationCase(
        task_id="GROUND-25",
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


def _ok(detail: str, trace: tuple[str, ...]) -> dict[str, object]:
    return {"detail": detail, "trace": trace}


def _blocked(token: str, trace: tuple[str, ...]) -> dict[str, object]:
    detail = f"rejected:{token}"
    return {
        "status": "blocked",
        "error_code": "rejected" if token != "cancelled" else "cancelled",
        "error_detail": detail,
        "detail": detail,
        "trace": trace,
    }


_VISUAL: tuple[str, ...] = (
    "mode:visual",
    "phase:handed_off",
    "rssi_role:supporting",
    "hits:2",
    "command:none",
    "goal:none",
    "arrival:none",
    "selection:none",
    "frame:dog-front-001",
    "frame:dog-front-002",
    "event:decision_received",
    "rssi_records:1",
)
_ONE: tuple[str, ...] = (
    "mode:rssi",
    "phase:acquiring",
    "rssi_role:primary",
    "hits:1",
    "command:none",
    "goal:none",
    "arrival:none",
    "selection:none",
    "frame:dog-front-001",
    "rssi_records:0",
)

_EXPECTED: dict[str, dict[str, object]] = {
    "two_fresh_hits": _ok("visual", _VISUAL),
    "rssi_records_kept": _ok("visual", _VISUAL),
    "no_goal_no_command": _ok("visual", _VISUAL),
    "one_hit": _ok("acquiring", _ONE),
    "suggestion_ignored": _ok("acquiring", _ONE),
    "example_contract": _ok("acquiring", _ONE),
    "not_visible_resets": _ok(
        "acquiring",
        (
            "mode:rssi",
            "phase:acquiring",
            "rssi_role:primary",
            "hits:1",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "reset:not_visible",
            "ignored:not_visible:dog-front-gap",
            "frame:dog-front-002",
            "rssi_records:0",
        ),
    ),
    "drone_frame": _blocked(
        "drone_camera",
        (
            "rejected",
            "drone_camera",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "ignored:drone:drone-downward-001",
            "rssi_records:0",
        ),
    ),
    "second_track": _ok(
        "review",
        (
            "mode:review",
            "phase:review",
            "rssi_role:primary",
            "hits:0",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "reset:review",
            "ignored:review:dog-front-001",
            "rssi_records:0",
        ),
    ),
    "stale_frame": _ok(
        "rssi",
        (
            "mode:rssi",
            "phase:rssi",
            "rssi_role:primary",
            "hits:0",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "reset:stale",
            "ignored:stale:dog-front-001",
            "rssi_records:0",
        ),
    ),
    "empty_detections": _ok(
        "rssi",
        (
            "mode:rssi",
            "phase:rssi",
            "rssi_role:primary",
            "hits:0",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "reset:empty",
            "ignored:empty:dog-front-001",
            "rssi_records:0",
        ),
    ),
    "multiple_strangers": _ok(
        "review",
        (
            "mode:review",
            "phase:review",
            "rssi_role:primary",
            "hits:0",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "reset:review",
            "ignored:review:dog-front-001",
            "rssi_records:0",
        ),
    ),
    "unlabeled_person": _ok(
        "review",
        (
            "mode:review",
            "phase:review",
            "rssi_role:primary",
            "hits:0",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "reset:review",
            "ignored:review:dog-front-001",
            "rssi_records:0",
        ),
    ),
    "epoch_mismatch": _blocked(
        "camera_epoch",
        (
            "rejected",
            "camera_epoch",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "reset:camera_epoch",
            "ignored:camera_epoch:dog-front-001",
            "rssi_records:0",
        ),
    ),
    "threshold_three": _ok(
        "acquiring",
        (
            "mode:rssi",
            "phase:acquiring",
            "rssi_role:primary",
            "hits:2",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "frame:dog-front-001",
            "frame:dog-front-002",
            "rssi_records:0",
        ),
    ),
    "drone_between_hits": _ok(
        "visual",
        (
            "mode:visual",
            "phase:handed_off",
            "rssi_role:supporting",
            "hits:2",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "ignored:drone:drone-downward-001",
            "frame:dog-front-001",
            "frame:dog-front-002",
            "event:decision_received",
            "rssi_records:0",
        ),
    ),
    "homing_disabled": _ok(
        "review",
        (
            "mode:review",
            "phase:review",
            "rssi_role:primary",
            "hits:0",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "reset:not_visible",
            "ignored:not_visible:dog-front-001",
            "rssi_records:0",
        ),
    ),
    "cancelled": _blocked(
        "cancelled",
        (
            "rejected",
            "cancelled",
            "command:none",
            "goal:none",
            "arrival:none",
            "selection:none",
            "rssi_records:0",
        ),
    ),
}
