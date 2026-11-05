"""Scripted drone-command cases. The harness runs the real provider."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_MOTION = ("dog.run_route", "drone.inspect", "drone.land", "reasoner.assess_incident")
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
        authorized: bool = True,
    ) -> SimulationCase:
        merged: dict[str, object] = {
            "status": status,
            "simulated": True,
            "live_call_count": 0,
            "slot": "feature.v2_drone_command",
            "schema_version": "ground-task-v2",
            "measurement_clock": "manual",
            "within_limit": True,
            "retained": False,
            "device_calls": 0,
            "authorized": authorized,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-17",
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

    def blocked(case_id: str, reason: str, trace: tuple[str, ...]) -> SimulationCase:
        return make(
            case_id,
            {"detail": reason, "error_code": "rejected", "trace": trace},
            status="blocked",
            authorized=False,
        )

    return (
        make(
            "approve_track",
            {
                "detail": "track_step",
                "trace": (
                    "action:track_step",
                    "primitive:verified-left-step-v1",
                    "lease_ms:300",
                    "beacon_epoch:4",
                    "no_drone_call",
                ),
            },
        ),
        blocked(
            "controlled_motion_off",
            "controlled_motion_disabled",
            ("rejected:controlled_motion_disabled", "no_drone_call"),
        ),
        make(
            "land_deadline",
            {
                "detail": "land",
                "trace": (
                    "action:land",
                    "primitive:verified-floor-land-v1",
                    "lease_ms:500",
                    "deadline_ms:8000",
                    "no_drone_call",
                ),
            },
        ),
        blocked(
            "five_meter",
            "displacement_rejected",
            ("rejected:displacement_rejected", "no_drone_call"),
        ),
        make(
            "replay",
            {
                "detail": "replayed",
                "trace": ("command_id:cmd-drone-001", "allocations:1", "no_drone_call"),
            },
        ),
        blocked(
            "calibration_null",
            "calibration_missing",
            ("rejected:calibration_missing", "no_drone_call"),
        ),
        make(
            "no_drone_port",
            {
                "detail": "land",
                "trace": ("drone.inspect:0", "drone.land:0", "no_drone_call"),
            },
        ),
        blocked(
            "supervised_rejection",
            "controlled_motion_disabled",
            ("rejected:controlled_motion_disabled", "supervised_label_absent", "no_drone_call"),
        ),
        blocked(
            "sdk_text",
            "sdk_text_rejected",
            ("rejected:sdk_text_rejected", "no_drone_call"),
        ),
        blocked(
            "height_unknown",
            "height_reference_mismatch",
            ("rejected:height_reference_mismatch", "no_drone_call"),
        ),
        blocked(
            "expired_proposal",
            "expired_proposal",
            ("rejected:expired_proposal", "no_drone_call"),
        ),
        make(
            "search_bounded",
            {
                "detail": "search_step",
                "trace": (
                    "action:search_step",
                    "primitive:verified-search-right-v1",
                    "allowlist_only",
                    "step:0",
                    "cap:2",
                    "no_drone_call",
                ),
            },
        ),
        blocked(
            "search_cap",
            "search_cap_exhausted",
            ("rejected:search_cap_exhausted", "no_drone_call"),
        ),
        make(
            "hover_when_blocked",
            {
                "detail": "hover",
                "trace": (
                    "action:hover",
                    "primitive:verified-hold-v1",
                    "controlled_motion:false",
                    "no_drone_call",
                ),
            },
        ),
        make(
            "supervised_step",
            {
                "detail": "operator-supervised",
                "trace": (
                    "action:search_step",
                    "primitive:operator-supervised-step-v1",
                    "labeled:operator-supervised",
                    "no_drone_call",
                ),
            },
        ),
        blocked(
            "dog_target",
            "wrong_component",
            ("rejected:wrong_component", "dog.run_route:0", "no_drone_call"),
        ),
        blocked(
            "lease_5000",
            "lease_exceeds_motion_cap",
            ("rejected:lease_exceeds_motion_cap", "no_drone_call"),
        ),
        make(
            "bool_string",
            {
                "detail": "controlled_motion must be a boolean",
                "error_code": "invalid_input",
                "trace": ("rejected:not_a_boolean", "no_drone_call"),
            },
            status="failed",
            authorized=False,
        ),
    )
