"""Scripted workflow cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

DISMISS_TRACE = (
    "startup",
    "load",
    "assess",
    "dispatch",
    "metrics",
    "report",
    "status",
    "terminal",
)
CLEAR_TRACE = (
    "startup",
    "load",
    "assess",
    "dispatch",
    "transport",
    "prepare",
    "route",
    "route_result",
    "arrival",
    "dog_frame",
    "ground_view",
    "resolve",
    "resolution",
    "metrics",
    "report",
    "status",
    "terminal",
)
BLOCKED_TRACE = (
    "startup",
    "load",
    "assess",
    "dispatch",
    "transport",
    "prepare",
    "route",
    "route_result",
    "arrival",
    "dog_frame",
    "ground_view",
    "transport",
    "preflight_initial",
    "flight_ready",
    "preflight_final",
    "inspect",
    "inspection_result",
    "resolve",
    "resolution",
    "metrics",
    "report",
    "status",
    "terminal",
)
HALT_TRACE = (
    "startup",
    "load",
    "assess",
    "dispatch",
    "transport",
    "prepare",
    "route",
    "terminal",
)
MISSING_DISPATCH_TRACE = (
    "startup",
    "load",
    "assess",
    "dispatch",
    "missing:feature.dispatch",
    "metrics",
    "report",
    "status",
    "terminal",
)
MISSING_PREFLIGHT_TRACE = (
    "startup",
    "load",
    "assess",
    "dispatch",
    "transport",
    "prepare",
    "route",
    "route_result",
    "arrival",
    "dog_frame",
    "ground_view",
    "transport",
    "preflight_initial",
    "missing:feature.preflight",
    "metrics",
    "report",
    "status",
    "terminal",
)
MOTION = (
    "dog.prepare",
    "dog.run_route",
    "dog.capture_frame",
    "drone.inspect",
    "reasoner.assess_ground_view",
    "reasoner.resolve_incident",
    "reasoner.compose_alert",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(
        case_id: str,
        expected: dict[str, object],
        forbidden: tuple[str, ...] = (),
    ) -> SimulationCase:
        return SimulationCase(
            task_id="GROUND-09",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=forbidden,
            teardown=(
                "release_barriers",
                "collect_tasks",
                "remove_owned_temp",
                "assert_no_socket",
            ),
        )

    common = {"live_call_count": 0, "simulated": True}
    return (
        make(
            "dispatch_dismiss",
            {
                **common,
                "status": "ok",
                "detail": "ignored",
                "authorized": True,
                "trace": DISMISS_TRACE,
            },
            MOTION,
        ),
        make(
            "ground_clear",
            {
                **common,
                "status": "ok",
                "detail": "cleared",
                "authorized": True,
                "trace": CLEAR_TRACE,
            },
            ("drone.inspect", "takeoff_attempt"),
        ),
        make(
            "ground_confirmed",
            {
                **common,
                "status": "ok",
                "detail": "alerted",
                "authorized": True,
                "trace": CLEAR_TRACE,
            },
            ("drone.inspect",),
        ),
        make(
            "blocked_resolved",
            {
                **common,
                "status": "ok",
                "detail": "alerted",
                "authorized": True,
                "trace": BLOCKED_TRACE,
            },
        ),
        make(
            "missing_dispatch",
            {
                **common,
                "status": "failed",
                "error_code": "missing_provider",
                "detail": "unresolved",
                "authorized": True,
                "trace": MISSING_DISPATCH_TRACE,
            },
            MOTION,
        ),
        make(
            "missing_preflight",
            {
                **common,
                "status": "failed",
                "error_code": "missing_provider",
                "detail": "unresolved",
                "authorized": True,
                "trace": MISSING_PREFLIGHT_TRACE,
            },
            ("drone.inspect", "reasoner.resolve_incident", "reasoner.compose_alert"),
        ),
        make(
            "halt_during_route",
            {
                **common,
                "status": "ok",
                "detail": "aborted",
                "authorized": False,
                "trace": HALT_TRACE,
            },
            (
                "dog.capture_frame",
                "drone.inspect",
                "reasoner.assess_ground_view",
                "reasoner.compose_alert",
            ),
        ),
        make(
            "malformed_dispatch",
            {
                **common,
                "status": "failed",
                "error_code": "validation_failed",
                "detail": "unresolved",
                "authorized": True,
                "trace": DISMISS_TRACE,
            },
            MOTION,
        ),
        make(
            "wrong_continuation",
            {
                **common,
                "status": "failed",
                "error_code": "validation_failed",
                "detail": "unresolved",
                "authorized": True,
                "trace": DISMISS_TRACE,
            },
            MOTION,
        ),
        make(
            "persistence_during_route",
            {
                **common,
                "status": "ok",
                "detail": "aborted",
                "authorized": False,
                "trace": HALT_TRACE[:7] + ("persistence_fault", "terminal"),
            },
            ("dog.capture_frame", "drone.inspect", "reasoner.compose_alert"),
        ),
        make(
            "link_loss_during_route",
            {
                **common,
                "status": "ok",
                "detail": "aborted",
                "authorized": False,
                "trace": HALT_TRACE[:7] + ("link_lost", "terminal"),
            },
            ("dog.capture_frame", "drone.inspect", "reasoner.compose_alert"),
        ),
        make(
            "synthetic_manifest",
            {
                **common,
                "status": "ok",
                "detail": "synthetic",
                "authorized": True,
                "trace": (),
                "slot": "feature.status",
                "schema_version": "ground-task-v1",
                "device_calls": 0,
            },
            MOTION,
        ),
    )
