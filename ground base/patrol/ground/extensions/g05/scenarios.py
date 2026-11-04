"""Scripted executor cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "dog.prepare",
    "dog.run_route",
    "dog.capture_frame",
    "drone.inspect",
    "reasoner.assess_incident",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(
        case_id: str,
        expected: dict[str, object],
    ) -> SimulationCase:
        return SimulationCase(
            task_id="GROUND-05",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=_FORBIDDEN,
            teardown=(
                "release_barriers",
                "collect_tasks",
                "remove_owned_temp",
                "assert_no_socket",
            ),
        )

    common = {
        "status": "ok",
        "simulated": True,
        "device_calls": 0,
        "live_call_count": 0,
        "slot": "base.executor",
        "schema_version": "ground-task-v1",
    }
    return (
        make(
            "completed_operation",
            {
                **common,
                "authorized": True,
                "retained": False,
                "trace": ("started", "completed", "authorizes"),
            },
        ),
        make(
            "barrier_console_pulse",
            {
                **common,
                "authorized": True,
                "retained": False,
                "trace": ("pulse", "completed"),
            },
        ),
        make(
            "deadline_before_start",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("rejected", "factory:0"),
                "detail": "expired before factory",
            },
        ),
        make(
            "deadline_during_execution",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("factory", "timeout", "invocations:1"),
            },
        ),
        make(
            "release_before_halt",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("completed", "next-rejected", "factory-next:0"),
            },
        ),
        make(
            "release_after_halt",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("cancelled", "late-value", "not-authorized"),
            },
        ),
        make(
            "same_turn_halt",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("same-turn", "not-authorized"),
            },
        ),
        make(
            "cancellation_resistant",
            {
                **common,
                "authorized": False,
                "retained": True,
                "trace": ("pending", "replacement-blocked", "factory-next:0"),
            },
        ),
        make(
            "recovery_budget",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("recovery-completed", "separate-context", "ordinary-blocked"),
            },
        ),
        make(
            "no_retry_timeout",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("timeout", "invocations:1", "no-retry"),
            },
        ),
        make(
            "cleanup_preserves_primary",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("timeout", "primary-kept", "cleanup-separate"),
                "detail": "primary timeout kept",
            },
        ),
        make(
            "cancelled_error_distinct",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("cancelled-error", "not-completed"),
            },
        ),
        make(
            "exact_deadline",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("exact-deadline", "timeout"),
                "detail": "deadline equality is timeout",
            },
        ),
        make(
            "mission_deadline_frozen",
            {
                **common,
                "authorized": True,
                "retained": False,
                "trace": ("deadline-frozen", "not-extended"),
                "detail": "10",
            },
        ),
        make(
            "zero_budget",
            {
                **common,
                "authorized": False,
                "retained": False,
                "trace": ("rejected", "factory:0", "zero-budget"),
            },
        ),
        make(
            "responsiveness",
            {
                **common,
                "authorized": False,
                "retained": False,
                "within_limit": True,
                "measurement_clock": "real",
                "trace": ("halt", "responsive"),
            },
        ),
    )
