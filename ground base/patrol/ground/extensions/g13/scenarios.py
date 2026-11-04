"""Scripted drone-observation cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "drone.connect",
    "drone.get_status",
    "drone.inspect",
    "drone.land",
    "drone.close",
    "dog.run_route",
    "dog.prepare",
    "reasoner.assess_incident",
)
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)
_RECEIVED = "2026-01-01T00:00:00+00:00"


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(case_id: str, expected: dict[str, object]) -> SimulationCase:
        body = {
            "device_calls": 0,
            "live_call_count": 0,
            "slot": "feature.v2_drone_observation",
            "schema_version": "ground-task-v2",
            **expected,
        }
        return SimulationCase(
            task_id="GROUND-13",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(body),
            forbidden_calls=_FORBIDDEN,
            teardown=_TEARDOWN,
        )

    shared = (
        "beacon_epoch=3",
        "pose=null",
        "battery_percent=74",
        "sent_at=2026-11-04T13:00:10.000Z",
        f"received_utc={_RECEIVED}",
        "received_monotonic=0.0",
        "state_writes=0",
        "command_methods=",
        "frame_id=drone-downward-001",
        "camera_epoch=1",
        "active_command_id=null",
    )
    return (
        make(
            "accept_example",
            {
                "status": "ok",
                "trace": (
                    "flight_state=airborne",
                    "height_estimate_m=4.0",
                    "height_reference=floor_agl",
                    "floor_agl_claim=true",
                    *shared,
                ),
            },
        ),
        make(
            "reference_unknown",
            {
                "status": "ok",
                "trace": (
                    "flight_state=airborne",
                    "height_estimate_m=4.0",
                    "height_reference=unknown",
                    "floor_agl_claim=false",
                    *shared,
                ),
            },
        ),
        make(
            "pose_null",
            {
                "status": "ok",
                "trace": (
                    "pose=null",
                    "x_m=",
                    "y_m=",
                    "yaw_rad=",
                    "state_writes=0",
                    "command_methods=",
                ),
            },
        ),
        make(
            "bad_bssid",
            {
                "status": "failed",
                "error_code": "invalid_input",
                "trace": (
                    "state_writes=0",
                    "command_methods=",
                    "rejected=bssid",
                ),
            },
        ),
        make(
            "stale_epoch",
            {
                "status": "blocked",
                "error_code": "stale_ticket",
                "trace": (
                    "state_writes=0",
                    "command_methods=",
                    "rejected=stale",
                    "applied=false",
                ),
            },
        ),
    )
