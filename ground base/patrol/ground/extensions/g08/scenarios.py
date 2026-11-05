"""Scripted adapter-gateway cases. The harness runs the real provider."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_CREATE = (
    "dog.create:ethernet",
    "drone.create:none",
    "reasoner.create:none",
)
_CLOSE = ("dog.close", "drone.close", "reasoner.close")
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)
_MOTION = ("dog.run_route", "drone.inspect", "drone.takeoff")


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(
        case_id: str,
        expected: dict[str, object],
        forbidden: tuple[str, ...] = _MOTION,
    ) -> SimulationCase:
        return SimulationCase(
            task_id="GROUND-08",
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

    base = {
        "live_call_count": 0,
        "device_calls": 0,
        "simulated": True,
        "slot": "base.adapters",
        "schema_version": "ground-task-v1",
    }
    return (
        make(
            "keyword_factories",
            {
                **base,
                "status": "ok",
                "authorized": True,
                "detail": "keywords=mode,config,output_dir",
                "trace": _CREATE + ("dog.connect", "drone.connect", "reasoner.metadata"),
            },
        ),
        make(
            "fake_signatures",
            {
                **base,
                "status": "ok",
                "authorized": True,
                "detail": "contract-signatures",
                "trace": _CREATE
                + (
                    "dog.connect",
                    "drone.connect",
                    "reasoner.metadata",
                    "dog.prepare",
                    "dog.get_status",
                    "dog.run_route",
                    "dog.capture_frame",
                    "dog.halt",
                    "drone.get_status",
                    "drone.inspect",
                    "drone.land",
                    "reasoner.assess_incident",
                    "reasoner.assess_ground_view",
                    "reasoner.resolve_incident",
                    "reasoner.compose_alert",
                )
                + _CLOSE,
            },
        ),
        make(
            "missing_public_factory",
            {
                "status": "ok",
                "authorized": True,
                "device_calls": 0,
                "detail": "public-factories",
            },
        ),
        make(
            "stale_epoch_blocks_second",
            {
                **base,
                "status": "ok",
                "authorized": False,
                "detail": "second-operation-blocked",
                "trace": _CREATE + ("dog.run_route", "refused:dog.run_route"),
            },
        ),
        make(
            "optional_drone_ground_only",
            {
                **base,
                "status": "ok",
                "authorized": True,
                "detail": "optional_unavailable",
                "trace": _CREATE
                + (
                    "dog.connect",
                    "drone.connect",
                    "reasoner.metadata",
                    "dog.capture_frame",
                ),
            },
        ),
        make(
            "profile_switch_one_owner",
            {
                **base,
                "status": "ok",
                "authorized": True,
                "detail": "one-owner:wifi",
                "trace": _CREATE + _CLOSE + (
                    "dog.create:wifi",
                    "drone.create:none",
                    "reasoner.create:none",
                ),
            },
        ),
        make(
            "cleanup_aggregation",
            {
                "status": "failed",
                "error_code": "recovery_required",
                "device_calls": 0,
                "detail": (
                    "primary: dog.run_route: AdapterError: device_error: boom; "
                    "dog: RuntimeError: dog close failed; "
                    "drone: RuntimeError: drone close failed"
                ),
                "trace": _CREATE + ("dog.run_route",) + _CLOSE,
            },
        ),
        make(
            "pending_worker_blocks_recreate",
            {
                **base,
                "status": "ok",
                "authorized": False,
                "retained": True,
                "detail": "pending worker blocks recreation",
                "trace": _CREATE + ("dog.run_route", "recreation-blocked"),
            },
        ),
        make(
            "late_generation_discarded",
            {
                **base,
                "status": "ok",
                "authorized": False,
                "detail": "stale generation result discarded",
                "trace": _CREATE + ("dog.run_route",) + _CLOSE + ("discarded:dog.run_route",),
            },
        ),
        make(
            "active_link_loss",
            {
                **base,
                "status": "ok",
                "authorized": True,
                "detail": "active_link_loss",
                "trace": _CREATE + ("drone.connect", "drone.get_status"),
            },
        ),
        make(
            "unknown_status",
            {
                **base,
                "status": "ok",
                "authorized": True,
                "detail": "unknown",
                "trace": _CREATE + ("dog.connect",),
            },
        ),
        make(
            "wrong_boundary_type",
            {
                "status": "failed",
                "error_code": "contract_mismatch",
                "device_calls": 0,
                "detail": "dog status must be DogStatus",
            },
        ),
        make(
            "real_to_fake_substitution",
            {
                "status": "failed",
                "error_code": "rejected",
                "device_calls": 0,
                "detail": "real-to-fake substitution",
            },
        ),
        make(
            "duplicate_owner",
            {
                "status": "failed",
                "error_code": "rejected",
                "device_calls": 0,
                "detail": "duplicate dog connection",
            },
        ),
    )
