"""Scripted state cases. The harness runs the real SessionStore against these."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

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
        forbidden: tuple[str, ...] = (
            "dog.run_route",
            "drone.inspect",
            "reasoner.assess_incident",
        ),
    ) -> SimulationCase:
        return SimulationCase(
            task_id="GROUND-03",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=forbidden,
            teardown=_TEARDOWN,
        )

    common = {
        "slot": "base.state",
        "schema_version": "ground-task-v1",
        "simulated": True,
        "device_calls": 0,
        "live_call_count": 0,
    }
    return (
        make(
            "normal_phases",
            {
                **common,
                "status": "ok",
                "authorized": True,
                "trace": (
                    "IDLE",
                    "ASSESS",
                    "PREPARE_DOG",
                    "MOVE_DOG",
                    "WAIT_ARRIVAL",
                    "GROUND_VIEW",
                    "PREFLIGHT",
                    "INSPECT",
                    "RESOLVE",
                    "REPORT",
                    "DONE",
                ),
                "detail": (
                    "outcome=alerted;arrival_confirmed=true;arrival_method=simulated;"
                    "flight_lock=true;recovery_required=false;zone=room_2"
                ),
            },
        ),
        make(
            "single_admission",
            {
                **common,
                "status": "ok",
                "authorized": True,
                "trace": (
                    "missions:1",
                    "publications:1",
                    "duplicate_start_rejected",
                    "duplicate_decision_ignored",
                    "duplicate_completion_rejected",
                ),
                "detail": "missions=1;publications=1",
            },
        ),
        make(
            "halt_fence",
            {
                **common,
                "status": "ok",
                "authorized": False,
                "trace": ("MOVE_DOG", "ABORTED", "late_result_rejected"),
                "detail": "phase=ABORTED;outcome=aborted;arrival_confirmed=none",
            },
        ),
        make(
            "reset_epoch",
            {
                **common,
                "status": "ok",
                "authorized": False,
                "trace": ("IDLE", "epoch_advanced", "old_confirmation_rejected"),
                "detail": "epoch=2;arrival_confirmed=none;flight_lock=false",
            },
        ),
        make(
            "unknown_landing",
            {
                **common,
                "status": "ok",
                "authorized": False,
                "trace": ("FAULT", "fault_held"),
                "detail": (
                    "outcome=failed;phase=FAULT;recovery_required=true;"
                    "flight_lock=true;frame_retained=true"
                ),
            },
        ),
        make(
            "illegal_edges",
            {
                **common,
                "status": "ok",
                "authorized": False,
                "trace": ("illegal_phase_rejected", "wrong_zone_rejected"),
                "detail": "phase=WAIT_ARRIVAL;arrival_confirmed=none",
            },
        ),
        make(
            "replay_match",
            {
                **common,
                "status": "ok",
                "authorized": True,
                "trace": ("replay_match",),
                "detail": "equal=true",
            },
        ),
        make(
            "pure_reduction",
            {
                **common,
                "status": "ok",
                "authorized": True,
                "retained": False,
                "trace": ("peer_calls:0",),
                "detail": "retained=false",
            },
        ),
        make(
            "tri_state",
            {
                **common,
                "status": "ok",
                "authorized": False,
                "trace": ("string_rejected", "unknown_faulted", "route_not_started"),
                "detail": "phase=FAULT;recovery_required=true;standing=unknown",
            },
        ),
        make(
            "early_confirmation",
            {
                **common,
                "status": "ok",
                "authorized": False,
                "trace": ("early_flight_ready_rejected", "readiness_still_clear"),
                "detail": "phase=PREFLIGHT;readiness_confirmed=none",
            },
        ),
    )
