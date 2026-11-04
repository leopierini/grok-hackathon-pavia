"""Scripted foundation cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(
        case_id: str,
        expected: dict[str, object],
        forbidden: tuple[str, ...] = (),
        teardown: tuple[str, ...] = (
            "release_barriers",
            "collect_tasks",
            "remove_owned_temp",
            "assert_no_socket",
        ),
    ) -> SimulationCase:
        return SimulationCase(
            task_id="GROUND-01",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=forbidden,
            teardown=teardown,
        )

    motion = ("dog.run_route", "drone.inspect", "reasoner.assess_incident")
    return (
        make(
            "synthetic_slot",
            {
                "status": "ok",
                "slot": "feature.status",
                "schema_version": "ground-task-v1",
                "device_calls": 0,
                "live_call_count": 0,
            },
            motion,
        ),
        make(
            "happy_devices",
            {
                "status": "ok",
                "live_call_count": 0,
                "simulated": True,
                "trace": (
                    "adapters.build",
                    "adapters.connect:dog",
                    "dog.connect",
                    "adapters.invoke:dog.capture_frame",
                    "dog.capture_frame",
                ),
            },
            ("dog.run_route", "drone.inspect"),
        ),
        make(
            "duplicate_slot",
            {"status": "failed", "error_code": "duplicate_slot", "device_calls": 0},
            motion,
        ),
        make(
            "missing_provider",
            {"status": "failed", "error_code": "missing_provider", "device_calls": 0},
            motion,
        ),
        make(
            "schema_mismatch",
            {"status": "failed", "error_code": "schema_mismatch", "device_calls": 0},
            motion,
        ),
        make(
            "path_escape",
            {"status": "failed", "error_code": "path_escape", "device_calls": 0},
            motion,
        ),
        make(
            "forbidden_command",
            {"status": "failed", "error_code": "forbidden_command", "device_calls": 0},
            motion,
        ),
        make(
            "cancel_barrier",
            {"status": "ok", "authorized": False, "device_calls": 0},
            ("dog.run_route",),
        ),
        make(
            "manual_deadline",
            {
                "status": "ok",
                "trace": ("issued", "before_deadline", "expired_deadline"),
                "device_calls": 0,
            },
            motion,
        ),
        make(
            "responsiveness",
            {
                "status": "ok",
                "within_limit": True,
                "measurement_clock": "real",
                "device_calls": 0,
            },
            motion,
        ),
        make(
            "fixture_io_fault",
            {
                "status": "failed",
                "error_code": "io_fault",
                "error_detail": "injected fixture read failure",
                "device_calls": 0,
            },
            motion,
        ),
        make(
            "teardown_release",
            {"status": "ok", "retained": True, "device_calls": 0},
            motion,
            (
                "release_barriers",
                "collect_tasks",
                "remove_owned_temp",
                "assert_no_socket",
                "assert_released",
            ),
        ),
    )
