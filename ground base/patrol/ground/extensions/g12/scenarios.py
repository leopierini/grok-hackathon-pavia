"""Scripted capability cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "adapters.connect:dog",
    "adapters.connect:drone",
    "adapters.invoke:dog.run_route",
    "adapters.invoke:drone.inspect",
    "dog.connect",
    "dog.run_route",
    "drone.connect",
    "drone.inspect",
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
        expected: dict[str, object],
        *,
        status: str = "ok",
    ) -> SimulationCase:
        merged: dict[str, object] = {
            "status": status,
            "simulated": True,
            "live_call_count": 0,
            "slot": "feature.v2_capabilities",
            "schema_version": "ground-task-v2",
            "measurement_clock": "manual",
            "within_limit": True,
            "authorized": False,
            "retained": False,
            "device_calls": 0,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-12",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(merged),
            forbidden_calls=_FORBIDDEN,
            teardown=_TEARDOWN,
        )

    return (
        make(
            "admit_examples",
            {
                "detail": "three_peers_admitted",
                "trace": (
                    "peer:drone:admitted",
                    "peer:dog:admitted",
                    "peer:pi:admitted",
                    "controlled_motion:true",
                    "downward_video:true",
                    "rssi_receiver:true",
                    "lidar:true",
                    "slam:true",
                    "target_range:true",
                    "dog_controlled_motion:true",
                    "navigation_mode:slam_eligible",
                    "autonomous_search:armed",
                    "router:router-back",
                    "router_peer:false",
                    "motion_permission:false",
                    "armed_records:3",
                ),
            },
        ),
        make(
            "autonomous_search_blocked",
            {
                "detail": "controlled_motion_reported_false",
                "error_code": "rejected",
                "error_detail": "controlled_motion_reported_false",
                "trace": (
                    "controlled_motion:false",
                    "autonomous_search:blocked",
                    "motion_plan:none",
                    "motion_permission:false",
                ),
            },
            status="blocked",
        ),
        make(
            "pi_report_missing",
            {
                "detail": "pi_report_missing",
                "error_code": "unavailable",
                "error_detail": "pi_report_missing",
                "trace": (
                    "rssi_receiver:false",
                    "reason:pi_report_missing",
                    "vision_only_dog_approach:available",
                    "motion_permission:false",
                ),
            },
            status="blocked",
        ),
        make(
            "slam_unresolved",
            {
                "detail": "navigation_mode:unresolved",
                "trace": (
                    "lidar:true",
                    "slam:false",
                    "reactive_avoidance_eligible:true",
                    "navigation_mode:unresolved",
                ),
            },
        ),
        make(
            "unvalidated_dog",
            {
                "detail": "dog_motion_disarmed",
                "trace": (
                    "validated:false",
                    "dog_controlled_motion:false",
                    "reported_dog_controlled_motion:true",
                    "motion_armed:false",
                ),
            },
        ),
        make(
            "replay_one_report",
            {
                "detail": "single_armed_record",
                "trace": (
                    "replayed:msg-drone-capabilities",
                    "armed_records:3",
                    "motion_permission:false",
                ),
            },
        ),
        make(
            "downward_camera_missing",
            {
                "detail": "downward_video_disarmed",
                "trace": (
                    "downward_video:false",
                    "reported_downward_video:true",
                    "reason:downward_camera_id_missing",
                    "controlled_motion:true",
                ),
            },
        ),
        make(
            "honest_control_fault",
            {
                "detail": "controlled_motion_stays_false",
                "trace": (
                    "controlled_motion:false",
                    "reported_controlled_motion:false",
                    "downward_video:false",
                    "autonomous_search:not_requested",
                ),
            },
        ),
        make(
            "role_device_mismatch",
            {
                "detail": "role_device_mismatch",
                "error_code": "rejected",
                "error_detail": "role_device_mismatch",
                "trace": (
                    "rejected:role_device_mismatch",
                    "armed_records:0",
                    "motion_permission:false",
                ),
            },
            status="failed",
        ),
    )
