"""Scripted RSSI cases. The harness runs the real provider against these fixtures."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_TAIL = ("no_heading", "no_range", "no_socket", "no_dog_command")
_MOTION = (
    "dog.run_route",
    "dog.halt",
    "dog.prepare",
    "drone.inspect",
    "drone.land",
    "reasoner.assess_incident",
)
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(case_id: str, expected: dict[str, object]) -> SimulationCase:
        merged: dict[str, object] = {
            "slot": "feature.v2_rssi",
            "schema_version": "ground-task-v2",
            "simulated": True,
            "live_call_count": 0,
            "device_calls": 0,
            "retained": False,
            "measurement_clock": "manual",
            "authorized": False,
            "within_limit": True,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-21",
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

    linked = (
        "quality:valid",
        "epoch:3",
        "beacon_epoch:3",
        "map_epoch:1",
        "median:-60",
        "spread:4",
        "interface:wlan-measurement",
        "clock_error_ms:15",
    )
    return (
        make(
            "example_window",
            {
                "status": "ok",
                "detail": "comparable",
                "trace": (*linked, "follow:true", *_TAIL),
            },
        ),
        make(
            "epoch_changed",
            {
                "status": "blocked",
                "detail": "incomparable",
                "error_code": "epoch_mismatch",
                "trace": (
                    "quality:valid",
                    "epoch:3",
                    "beacon_epoch:2",
                    "map_epoch:1",
                    "median:-60",
                    "spread:4",
                    "interface:wlan-measurement",
                    "clock_error_ms:15",
                    "follow:false",
                    "incomparable",
                    *_TAIL,
                ),
            },
        ),
        make(
            "bssid_swapped",
            {
                "status": "failed",
                "detail": "rejected",
                "error_code": "rejected",
                "trace": (
                    "quality:none",
                    "epoch:3",
                    "map_epoch:1",
                    "median:null",
                    "spread:null",
                    "interface:wlan-measurement",
                    "follow:false",
                    "rejected:bssid",
                    *_TAIL,
                ),
            },
        ),
        make(
            "no_signal",
            {
                "status": "ok",
                "detail": "no_signal",
                "trace": (
                    "quality:unavailable",
                    "epoch:3",
                    "beacon_epoch:3",
                    "map_epoch:1",
                    "median:null",
                    "spread:null",
                    "interface:wlan-measurement",
                    "clock_error_ms:15",
                    "follow:false",
                    "samples:0",
                    *_TAIL,
                ),
            },
        ),
        make(
            "sentinel_zero",
            {
                "status": "failed",
                "detail": "rejected",
                "error_code": "rejected",
                "trace": (
                    "quality:unavailable",
                    "epoch:3",
                    "beacon_epoch:3",
                    "map_epoch:1",
                    "median:0",
                    "spread:null",
                    "interface:wlan-measurement",
                    "clock_error_ms:15",
                    "follow:false",
                    "rejected:sentinel_zero",
                    *_TAIL,
                ),
            },
        ),
        make(
            "clock_error",
            {
                "status": "failed",
                "detail": "rejected",
                "error_code": "rejected",
                "within_limit": False,
                "trace": (
                    "quality:valid",
                    "epoch:3",
                    "beacon_epoch:3",
                    "map_epoch:1",
                    "median:-60",
                    "spread:4",
                    "interface:wlan-measurement",
                    "clock_error_ms:51",
                    "follow:false",
                    "rejected:clock_error",
                    *_TAIL,
                ),
            },
        ),
        make(
            "stale_heartbeat",
            {
                "status": "failed",
                "detail": "rejected",
                "error_code": "rejected",
                "within_limit": False,
                "trace": (*linked, "follow:false", "rejected:stale_heartbeat", *_TAIL),
            },
        ),
        make(
            "foreign_map",
            {
                "status": "failed",
                "detail": "rejected",
                "error_code": "rejected",
                "trace": (*linked, "follow:false", "rejected:map_epoch", *_TAIL),
            },
        ),
        make(
            "moving_hold",
            {
                "status": "blocked",
                "detail": "incomparable",
                "error_code": "epoch_mismatch",
                "trace": (*linked, "follow:false", "hold:moving", *_TAIL),
            },
        ),
        make(
            "laptop_rssi",
            {
                "status": "failed",
                "detail": "rejected",
                "error_code": "rejected",
                "trace": (
                    "quality:none",
                    "epoch:3",
                    "map_epoch:1",
                    "median:null",
                    "spread:null",
                    "follow:false",
                    "rejected:laptop",
                    *_TAIL,
                ),
            },
        ),
    )
