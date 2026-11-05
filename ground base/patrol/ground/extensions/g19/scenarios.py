"""Scripted beacon cases. The harness compares these to the provider result."""

from __future__ import annotations

from patrol.ground.extensions.g19.policy import SCHEMA, SLOT
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
            "error_code": None,
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
            "measurement_clock": "manual",
            "within_limit": True,
            "device_calls": 0,
            "retained": False,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-19",
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

    kept = (
        "hold:stable",
        "dog_motion_allowed:true",
        "reason:stable_hold",
        "beacon_epoch:3",
        "comparable_epoch:3",
        "window:pi-window-1:current:retained",
        "dog_command:none",
    )
    return (
        make(
            "stable_hold",
            {"authorized": True, "detail": "stable_hold", "trace": kept},
        ),
        make(
            "moving_hold",
            {
                "authorized": False,
                "detail": "moving",
                "trace": (
                    "hold:moving",
                    "dog_motion_allowed:false",
                    "reason:moving",
                    "beacon_epoch:3",
                    "window:pi-window-1:withheld:retained",
                    "dog_command:none",
                ),
            },
        ),
        make(
            "expired_hold",
            {
                "authorized": False,
                "detail": "expired",
                "trace": (
                    "hold:stable",
                    "dog_motion_allowed:false",
                    "reason:expired",
                    "beacon_epoch:3",
                    "window:pi-window-1:withheld:retained",
                    "dog_command:none",
                ),
            },
        ),
        make(
            "reposition_old_epoch",
            {
                "authorized": False,
                "detail": "epoch_pending",
                "trace": (
                    "hold:stable",
                    "dog_motion_allowed:false",
                    "reason:epoch_pending",
                    "beacon_epoch:3",
                    "prior_epoch:3",
                    "commanded_epoch:4",
                    "required_epoch:4",
                    "window:pi-window-old:invalid:retained",
                    "dog_command:none",
                ),
            },
        ),
        make(
            "reposition_next_epoch",
            {
                "authorized": True,
                "detail": "stable_hold",
                "trace": (
                    "hold:stable",
                    "dog_motion_allowed:true",
                    "reason:stable_hold",
                    "beacon_epoch:4",
                    "prior_epoch:3",
                    "commanded_epoch:4",
                    "comparable_epoch:4",
                    "window:pi-window-old:invalid:retained",
                    "window:pi-window-new:current:retained",
                    "dog_command:none",
                ),
            },
        ),
        make(
            "bssid_mismatch",
            {
                "status": "blocked",
                "error_code": "rejected",
                "error_detail": "beacon BSSID does not match the armed drone",
                "authorized": False,
                "detail": "bssid_mismatch",
                "trace": (
                    "hold:stable",
                    "dog_motion_allowed:false",
                    "reason:bssid_mismatch",
                    "beacon_epoch:3",
                    "window:pi-window-1:invalid:retained",
                    "dog_command:none",
                ),
            },
        ),
        make(
            "no_dog_execute",
            {"authorized": True, "detail": "stable_hold", "trace": kept},
        ),
        make(
            "running_command",
            {
                "authorized": False,
                "detail": "running_reposition",
                "trace": (
                    "hold:moving",
                    "dog_motion_allowed:false",
                    "reason:running_reposition",
                    "beacon_epoch:3",
                    "prior_epoch:3",
                    "commanded_epoch:4",
                    "window:pi-window-1:suspended:retained",
                    "dog_command:none",
                ),
            },
        ),
        make(
            "unknown_flight",
            {
                "authorized": False,
                "detail": "flight_unknown",
                "trace": (
                    "hold:stable",
                    "dog_motion_allowed:false",
                    "reason:flight_unknown",
                    "beacon_epoch:3",
                    "window:pi-window-1:withheld:retained",
                    "dog_command:none",
                ),
            },
        ),
        make(
            "hover_keeps_epoch",
            {
                "authorized": True,
                "detail": "stable_hold",
                "trace": (
                    "hold:stable",
                    "dog_motion_allowed:true",
                    "reason:stable_hold",
                    "beacon_epoch:3",
                    "prior_epoch:3",
                    "commanded_epoch:4",
                    "comparable_epoch:3",
                    "window:pi-window-1:current:retained",
                    "dog_command:none",
                ),
            },
        ),
    )
