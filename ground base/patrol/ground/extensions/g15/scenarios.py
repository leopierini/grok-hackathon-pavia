"""Scripted vision-sampling cases. The harness runs the real scheduler."""

from __future__ import annotations

from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_FORBIDDEN = (
    "dog.connect",
    "dog.prepare",
    "dog.run_route",
    "dog.capture_frame",
    "dog.halt",
    "drone.connect",
    "drone.inspect",
    "drone.land",
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
    def make(case_id: str, expected: dict[str, object]) -> SimulationCase:
        merged: dict[str, object] = {
            "status": "ok",
            "simulated": True,
            "live_call_count": 0,
            "slot": "feature.v2_vision_schedule",
            "schema_version": "ground-task-v2",
            "measurement_clock": "manual",
            "within_limit": True,
            "authorized": False,
            "retained": False,
            "device_calls": 0,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-15",
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

    return (
        make(
            "fresh_drone",
            {
                "detail": "one_drone_request",
                "trace": (
                    "emitted",
                    "drone_search",
                    "track:null",
                    "placeholder",
                    "vision.request",
                ),
            },
        ),
        make(
            "inflight_newest",
            {
                "detail": "newest_follow_up",
                "trace": (
                    "emitted:a",
                    "held:b",
                    "dropped:b",
                    "held:c",
                    "dropped:c",
                    "held:d",
                    "follow_up:d",
                    "dropped_frame_count:2",
                ),
            },
        ),
        make(
            "stale_drop",
            {
                "detail": "evidence_age",
                "trace": ("dropped:stale", "no_request"),
            },
        ),
        make(
            "dog_track",
            {
                "detail": "track_required",
                "trace": ("rejected:dog_acquire", "emitted:dog_acquire", "track:target-001"),
            },
        ),
        make(
            "timeout_id",
            {
                "detail": "timeout_new_id",
                "trace": (
                    "emitted:vision-001",
                    "expired:vision-001",
                    "no_resend",
                    "retry:vision-002",
                    "same_frame",
                ),
            },
        ),
        make(
            "drop_count",
            {
                "detail": "drop_count",
                "trace": ("emitted:newest", "dropped_frame_count:2"),
            },
        ),
        make(
            "no_calls",
            {
                "detail": "no_motion",
                "trace": ("dog:0", "drone:0", "reasoner:0", "decision:0"),
            },
        ),
        make(
            "example_keys",
            {
                "detail": "example_keys",
                "trace": ("envelope", "payload", "frame", "drone", "dog"),
            },
        ),
        make(
            "clock_uncertainty",
            {
                "detail": "clock_uncertainty",
                "trace": ("blocked", "no_request"),
            },
        ),
        make(
            "placeholder_model",
            {
                "detail": "placeholder_copied",
                "trace": ("model:CONFIGURE_VERIFIED_IMAGE_MODEL", "unresolved"),
            },
        ),
        make(
            "sample_interval",
            {
                "detail": "sample_interval",
                "trace": ("emitted:first", "held:second", "follow_up:second"),
            },
        ),
        make(
            "cancelled",
            {
                "detail": "cancellation",
                "trace": ("cancelled", "no_request", "dog:0"),
            },
        ),
    )
