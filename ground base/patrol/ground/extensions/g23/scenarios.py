"""Scripted dog-command cases. The harness runs the real provider."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "dog.run_route",
    "dog.halt",
    "dog.prepare",
    "dog.capture_frame",
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
_ENVELOPE = (
    "protocol_version,message_id,mission_id,epoch,seq,sent_at,source,destination,"
    "kind,correlation_id,expires_at,simulated,payload"
)
_PAYLOAD = (
    "command_id,proposal_id,action,lease_ms,motion,track_id,beacon_epoch,"
    "safety_snapshot_id,reason"
)
_MOTION = (
    "frame_id,linear_x_m_s,linear_y_m_s,angular_z_rad_s,duration_ms,"
    "candidate_id,snapshot_id,map_epoch"
)
_MOVE_TRACE = (
    "kind:dog.command",
    "action:move_local",
    "frame:dog/base_link",
    "candidate:candidate-forward-01",
    "snapshot:nav-001",
    "map_epoch:1",
    "track:target-001",
    "beacon:3",
    "lease:300",
    "duration:300",
    "linear_x:0.1",
    "linear_y:0.0",
    "angular_z:0.0",
    "proposal:proposal-dog-001",
    "correlation:msg-ai-to-dog-proposal",
    "source:ground",
    "destination:dog",
    "simulated:true",
    "envelope:" + _ENVELOPE,
    "payload:" + _PAYLOAD,
    "motion:" + _MOTION,
    "no_altitude",
    "proposal_not_command",
    "recheck_required",
    "dog_port_not_called",
    "command_id:cmd-dog-001",
)
_HALT_TRACE = (
    "kind:dog.command",
    "action:halt",
    "motion:null",
    "proposal:null",
    "correlation:null",
    "lease:500",
    "track:target-001",
    "beacon:3",
    "safety:safety-stop-001",
    "no_altitude",
    "posture_stop",
    "dog_port_not_called",
    "command_id:cmd-dog-halt-001",
    "envelope:" + _ENVELOPE,
    "payload:" + _PAYLOAD,
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(case_id: str, expected: dict[str, object]) -> SimulationCase:
        merged: dict[str, object] = {
            "status": "ok",
            "simulated": True,
            "live_call_count": 0,
            "slot": "feature.v2_dog_command",
            "schema_version": "ground-task-v2",
            "measurement_clock": "manual",
            "within_limit": True,
            "authorized": True,
            "retained": False,
            "device_calls": 0,
            "error_code": None,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-23",
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

    def rejected(detail: str) -> dict[str, object]:
        return {
            "status": "blocked",
            "authorized": False,
            "error_code": "rejected",
            "detail": detail,
            "trace": ("rejected", detail),
        }

    return (
        make("example_move", {"detail": "example_move", "trace": _MOVE_TRACE}),
        make("example_halt", {"detail": "example_halt", "trace": _HALT_TRACE}),
        make("unknown_candidate", rejected("candidate is not in the safe list")),
        make("tether_overrun", rejected("ethernet step exceeds tether budget")),
        make("halt_latched_move", rejected("ordinary motion is refused while halt is latched")),
        make(
            "replay_selection",
            {
                "detail": "replay",
                "trace": (
                    "command_id:cmd-dog-001",
                    "replay_command_id:cmd-dog-001",
                    "issued_count:1",
                    "dog_port_not_called",
                ),
            },
        ),
        make(
            "dog_port_quiet",
            {
                "detail": "dog_port_quiet",
                "trace": (
                    "dog_port_not_called",
                    "device_calls:0",
                    "kind:dog.command",
                    "command_id:cmd-dog-001",
                ),
            },
        ),
        make("duration_rejected", rejected("duration_ms exceeds 500")),
        make("avoidance_null", rejected("avoidance_enabled is not true")),
        make("altitude_rejected", rejected("altitude is not a dog command field")),
        make(
            "vision_step",
            {
                "detail": "vision_step",
                "trace": (
                    "kind:dog.command",
                    "action:move_local",
                    "beacon:null",
                    "guidance:vision",
                    "dog_port_not_called",
                    "command_id:cmd-dog-001",
                ),
            },
        ),
        make("rssi_missing_beacon", rejected("beacon_epoch is required for an RSSI step")),
        make("halt_despite_block", {"detail": "halt_despite_block", "trace": _HALT_TRACE}),
        make(
            "operator_up",
            {
                "detail": "operator_up",
                "trace": (
                    "axis:up",
                    "linear_x:0.1",
                    "linear_y:0.0",
                    "no_altitude",
                    "frame:dog/base_link",
                    "dog_port_not_called",
                    "command_id:cmd-dog-001",
                ),
            },
        ),
        make(
            "homing_selection",
            {
                "detail": "homing_selection",
                "trace": (
                    "kind:dog.command",
                    "action:move_local",
                    "correlation:null",
                    "proposal:proposal-dog-001",
                    "candidate:candidate-forward-01",
                    "dog_port_not_called",
                    "command_id:cmd-dog-001",
                ),
            },
        ),
        make(
            "wifi_no_cable",
            {
                "detail": "wifi_no_cable",
                "trace": (
                    "transport:wifi",
                    "kind:dog.command",
                    "dog_port_not_called",
                    "command_id:cmd-dog-001",
                ),
            },
        ),
    )
