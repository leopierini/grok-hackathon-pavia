"""Scripted envelope cases. The harness runs EnvelopeGate against kernel doubles."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "dog.run_route",
    "drone.inspect",
    "drone.land",
    "dog.halt",
    "reasoner.assess_incident",
    "reasoner.assess_ground_view",
    "reasoner.resolve_incident",
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
        detail: str,
        trace: tuple[str, ...],
        *,
        authorized: bool,
    ) -> SimulationCase:
        return SimulationCase(
            task_id="GROUND-11",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(
                {
                    "status": "ok",
                    "simulated": True,
                    "live_call_count": 0,
                    "slot": "feature.v2_envelope",
                    "schema_version": "ground-task-v2",
                    "measurement_clock": "manual",
                    "within_limit": True,
                    "authorized": authorized,
                    "retained": False,
                    "device_calls": 0,
                    "detail": detail,
                    "trace": trace,
                }
            ),
            forbidden_calls=_FORBIDDEN,
            teardown=_TEARDOWN,
        )

    return (
        make(
            "accepted_examples",
            "accepted",
            ("drone.observation", "dog.command", "pose_null", "adapters_idle"),
            authorized=True,
        ),
        make(
            "duplicate_command",
            "one_stored",
            ("accepted", "replay", "stored:1"),
            authorized=True,
        ),
        make(
            "wrong_source",
            "direction",
            ("direction", "adapters_idle"),
            authorized=False,
        ),
        make(
            "expired_and_null",
            "rejected_before_invoke",
            ("expired", "expiry_required", "halt_schema_valid", "adapters_idle"),
            authorized=False,
        ),
        make(
            "late_epoch",
            "stale",
            ("held", "epoch_changed", "stale_epoch", "not_stored"),
            authorized=False,
        ),
        make(
            "journal_projection",
            "journal_projected",
            ("journal", "mission", "epoch", "kind", "message_id", "no_key_material"),
            authorized=True,
        ),
    )
