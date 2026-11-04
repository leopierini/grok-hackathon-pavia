"""Scripted safety cases for the frozen Task 01 simulator."""

from __future__ import annotations

from patrol.ground.extensions.g28.casespec import SCHEMA, SLOT, SPECS
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_MOTION = (
    "dog.run_route",
    "drone.inspect",
    "reasoner.assess_incident",
    "reasoner.assess_ground_view",
    "reasoner.resolve_incident",
    "reasoner.compose_alert",
)
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(spec_status: str, spec_id: str, expected: dict[str, object]) -> SimulationCase:
        merged: dict[str, object] = {
            "status": spec_status,
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
            "measurement_clock": "manual",
            "within_limit": True,
            "device_calls": 0,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-28",
            case_id=spec_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(merged),
            forbidden_calls=_MOTION,
            teardown=_TEARDOWN,
        )

    built: list[SimulationCase] = []
    for spec in SPECS:
        built.append(
            make(
                spec.status,
                spec.case_id,
                {
                    "authorized": spec.authorized,
                    "retained": spec.retained,
                    "detail": spec.detail,
                    "trace": spec.trace,
                    "error_code": spec.error_code,
                },
            )
        )
    return tuple(built)
