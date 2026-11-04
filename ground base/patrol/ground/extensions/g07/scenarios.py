"""Scripted console cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = ("dog.run_route", "drone.inspect")
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(case_id: str, expected: dict[str, object]) -> SimulationCase:
        payload = {
            "status": "ok",
            "live_call_count": 0,
            "device_calls": 0,
            "simulated": True,
            "slot": "base.console",
            "schema_version": "ground-task-v1",
            "authorized": False,
        }
        payload.update(expected)
        return SimulationCase(
            task_id="GROUND-07",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(payload),
            forbidden_calls=_FORBIDDEN,
            teardown=_TEARDOWN,
        )

    return (
        make(
            "command_stream",
            {
                "detail": "scripted stream accepted",
                "trace": (
                    "parsed:status",
                    "parsed:arm",
                    "parsed:start",
                    "parsed:reset",
                    "parsed:quit",
                    "event:reset_requested",
                    "event:shutdown_requested",
                ),
            },
        ),
        make(
            "arrival_confirmations",
            {
                "detail": "single arrival resolution",
                "trace": (
                    "confirmation:arrived:early",
                    "confirmation:arrived:wrong-zone",
                    "confirmation:arrived:accepted",
                    "confirmation:arrived:duplicate",
                ),
            },
        ),
        make(
            "pending_halt",
            {
                "detail": "commands progressed during pending work",
                "within_limit": True,
                "trace": (
                    "pending:reasoner.assess_incident",
                    "parsed:status",
                    "parsed:halt",
                    "pending:still-open",
                ),
            },
        ),
        make(
            "readiness_race",
            {
                "detail": "readiness invalidated",
                "trace": (
                    "same-turn:halt,flight-ready:rejected",
                    "same-turn:flight-ready,halt:rejected",
                ),
            },
        ),
        make(
            "lifecycle_faults",
            {
                "detail": "lifecycle events delivered",
                "trace": (
                    "event:halt_requested",
                    "renderer:isolated",
                    "event:shutdown_requested",
                    "input:error",
                ),
            },
        ),
        make(
            "scripted_parity",
            {
                "detail": "scripted and pipe input match",
                "trace": (
                    "scripted:status,arm,quit",
                    "prompt:status,arm,quit",
                    "parity:match",
                ),
            },
        ),
        make(
            "rejected_commands",
            {
                "detail": "trusted zone unchanged",
                "trace": (
                    "rejected:unknown command",
                    "rejected:command is empty",
                    "rejected:command does not take arguments",
                    "rejected:command contains control characters",
                    "zone:room_2",
                    "state.apply:absent",
                ),
            },
        ),
        make(
            "close_collect",
            {
                "detail": "input tasks collected",
                "retained": False,
                "trace": ("closed:once", "closed:idempotent", "tasks:0"),
            },
        ),
        make(
            "expired_confirmation",
            {
                "detail": "deadline rejected",
                "trace": ("confirmation:arrived:expired",),
            },
        ),
        make(
            "stale_epoch",
            {
                "detail": "epoch rejected",
                "trace": ("confirmation:flight-ready:stale",),
            },
        ),
    )
