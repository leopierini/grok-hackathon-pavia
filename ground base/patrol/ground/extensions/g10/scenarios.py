"""Scripted safety cases. The harness runs SafetyService against kernel doubles."""

from __future__ import annotations

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
            "simulated": True,
            "live_call_count": 0,
            "slot": "base.safety",
            "schema_version": "ground-task-v1",
            "measurement_clock": "manual",
            "within_limit": True,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-10",
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

    return (
        make(
            "immediate_latch",
            {
                "authorized": False,
                "retained": True,
                "detail": "latched_before_device_await",
                "device_calls": 0,
                "trace": (
                    "latched",
                    "scheduled:dog.halt",
                    "scheduled:drone.land",
                    "devices_not_entered",
                    "journal_untouched",
                ),
            },
        ),
        make(
            "independent_stops",
            {
                "authorized": False,
                "retained": True,
                "detail": "independent_stop_requests",
                "device_calls": 4,
                "trace": (
                    "latched_before_await",
                    "started:dog.halt",
                    "started:drone.land",
                    "drone_done",
                    "dog_pending",
                ),
            },
        ),
        make(
            "coalesce",
            {
                "authorized": False,
                "retained": True,
                "detail": "one_supervisor",
                "device_calls": 4,
                "trace": ("same_handle", "dog.halt:1", "drone.land:1"),
            },
        ),
        make(
            "stop_errors",
            {
                "authorized": False,
                "retained": True,
                "detail": "both_stop_errors",
                "device_calls": 4,
                "trace": ("error:dog.halt", "error:drone.land", "both_attempted"),
            },
        ),
        make(
            "unknown_landing",
            {
                "authorized": False,
                "retained": True,
                "detail": "recovery_latched",
                "device_calls": 8,
                "trace": ("status:unknown", "late_grounded_ignored", "motion_locked"),
            },
        ),
        make(
            "resistant_worker",
            {
                "authorized": False,
                "retained": True,
                "detail": "reset_refused",
                "device_calls": 4,
                "trace": ("cancel_ignored", "reset_refused", "build:0"),
            },
        ),
        make(
            "fresh_reset",
            {
                "authorized": True,
                "retained": False,
                "detail": "disarmed",
                "device_calls": 14,
                "trace": (
                    "epoch_replaced",
                    "event_replaced",
                    "stale_ticket",
                    "confirmation_replaced",
                    "reconnected",
                    "disarmed",
                    "route_not_replayed",
                ),
            },
        ),
        make(
            "responsiveness",
            {
                "authorized": False,
                "retained": True,
                "detail": "recognition_only",
                "device_calls": 4,
                "measurement_clock": "real",
                "trace": ("recognized",),
            },
        ),
        make(
            "cleanup_fault",
            {
                "authorized": False,
                "retained": True,
                "detail": "original_preserved",
                "device_calls": 9,
                "trace": (
                    "original:route failed",
                    "cleanup:dog.close",
                    "cleanup:drone.close",
                    "cleanup:reasoner.close",
                    "generation_unchanged",
                ),
            },
        ),
        make(
            "expired_context",
            {
                "authorized": False,
                "retained": True,
                "detail": "recovery_after_expired_deadline",
                "device_calls": 4,
                "trace": (
                    "ordinary_deadline_expired",
                    "recovery_halt_started",
                    "recovery_land_started",
                ),
            },
        ),
        make(
            "link_loss",
            {
                "authorized": False,
                "retained": True,
                "detail": "delivery_not_assumed",
                "device_calls": 4,
                "trace": (
                    "delivery_not_assumed",
                    "started:dog.halt",
                    "started:drone.land",
                ),
            },
        ),
        make(
            "shutdown_once",
            {
                "authorized": False,
                "retained": True,
                "detail": "shutdown",
                "device_calls": 9,
                "trace": (
                    "one_supervisor",
                    "closed:dog.close",
                    "closed:drone.close",
                    "closed:reasoner.close",
                    "no_second_land",
                ),
            },
        ),
        make(
            "invalid_recovery",
            {
                "status": "failed",
                "error_code": "invalid_input",
                "error_detail": "recovery verified must be true",
                "authorized": True,
                "retained": False,
                "detail": "recovery verified must be true",
                "device_calls": 0,
                "trace": ("rejected_string_bool",),
            },
        ),
        make(
            "observe_timeout",
            {
                "authorized": False,
                "retained": True,
                "detail": "pending_after_deadline",
                "device_calls": 4,
                "trace": (
                    "pending_after_deadline",
                    "dog_attempt_alive",
                    "drone_attempt_alive",
                ),
            },
        ),
    )
