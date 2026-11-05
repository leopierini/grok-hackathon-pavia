"""Scripted vision-decision cases. The harness runs the real provider."""

from __future__ import annotations

from patrol.ground.extensions.g16.implementation import SCHEMA, SLOT
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_MOTION = (
    "dog.run_route",
    "drone.inspect",
    "reasoner.assess_incident",
    "execute",
    "takeoff",
    "move",
    "drone.command",
    "dog.command",
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
        trace: tuple[str, ...],
        detail: str,
        *,
        status: str = "ok",
        error_code: str | None = None,
    ) -> SimulationCase:
        expected: dict[str, object] = {
            "status": status,
            "authorized": False,
            "retained": False,
            "detail": detail,
            "trace": trace,
            "device_calls": 0,
            "live_call_count": 0,
            "simulated": True,
            "within_limit": True,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
        if error_code is not None:
            expected["error_code"] = error_code
            expected["error_detail"] = detail
        return SimulationCase(
            task_id="GROUND-16",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(expected),
            forbidden_calls=_MOTION,
            teardown=_TEARDOWN,
        )

    return (
        make(
            "drone_example",
            (
                "accepted",
                "track_opened:target-001",
                "proposal:hold",
                "direction:center:image",
                "motion:empty",
                "devices:untouched",
            ),
            "track_opened",
        ),
        make(
            "uncertain_review",
            (
                "review",
                "uncertain",
                "no_proposal",
                "track_unchanged",
                "motion:empty",
                "devices:untouched",
            ),
            "review",
        ),
        make(
            "frame_mismatch",
            ("rejected", "frame_mismatch", "track_unchanged", "devices:untouched"),
            "frame_mismatch",
            status="failed",
            error_code="rejected",
        ),
        make(
            "request_expired",
            (
                "dropped",
                "expired",
                "track_unchanged:target-001",
                "halt_preserved",
                "devices:untouched",
            ),
            "request_expired",
            status="blocked",
            error_code="expired_deadline",
        ),
        make(
            "multiple_people",
            (
                "review",
                "multiple_people",
                "no_proposal",
                "track_unchanged",
                "motion:empty",
                "devices:untouched",
            ),
            "review",
        ),
        make(
            "unordered_box",
            ("rejected", "unordered_box", "track_unchanged", "devices:untouched"),
            "unordered_box",
            status="failed",
            error_code="rejected",
        ),
        make(
            "dog_track_mismatch",
            (
                "rejected",
                "track_mismatch",
                "track_unchanged:target-001",
                "devices:untouched",
            ),
            "track_mismatch",
            status="failed",
            error_code="rejected",
        ),
        make(
            "unknown_sdk_field",
            (
                "rejected",
                "unknown_field:sdk_command",
                "track_unchanged",
                "devices:untouched",
            ),
            "unknown_field:sdk_command",
            status="failed",
            error_code="validation_failed",
        ),
        make(
            "sdk_reason",
            ("rejected", "sdk_reason", "track_unchanged", "devices:untouched"),
            "sdk_reason",
            status="failed",
            error_code="rejected",
        ),
        make(
            "not_visible",
            (
                "hold",
                "not_visible",
                "no_proposal",
                "track_unchanged",
                "motion:empty",
                "devices:untouched",
            ),
            "hold",
        ),
        make(
            "uncalibrated_reposition",
            (
                "accepted",
                "forced_hold",
                "uncalibrated",
                "track_opened:target-001",
                "proposal:hold",
                "no_body_proposal",
                "direction:left:image",
                "motion:empty",
                "devices:untouched",
            ),
            "hold",
        ),
        make(
            "stale_camera_epoch",
            (
                "dropped",
                "camera_epoch",
                "track_unchanged:target-001",
                "halt_preserved",
                "devices:untouched",
            ),
            "stale_camera_epoch",
            status="blocked",
            error_code="epoch_mismatch",
        ),
        make(
            "halt_preserved",
            (
                "accepted",
                "track_opened:target-001",
                "no_proposal",
                "direction:center:image",
                "halt_preserved",
                "motion:empty",
                "devices:untouched",
            ),
            "track_opened",
        ),
        make(
            "invented_distance",
            ("rejected", "invented_distance", "track_unchanged", "devices:untouched"),
            "invented_distance",
            status="failed",
            error_code="rejected",
        ),
        make(
            "dog_track_update",
            (
                "accepted",
                "track_updated:target-001",
                "no_proposal",
                "direction:center:image",
                "motion:empty",
                "devices:untouched",
            ),
            "track_updated",
        ),
        make(
            "calibrated_reposition",
            (
                "accepted",
                "track_opened:target-001",
                "proposal:reposition",
                "direction:left:image",
                "motion:empty",
                "devices:untouched",
            ),
            "track_opened",
        ),
        make(
            "weapon_label",
            ("rejected", "label_rejected", "track_unchanged", "devices:untouched"),
            "label_rejected",
            status="failed",
            error_code="rejected",
        ),
        make(
            "request_mismatch",
            ("rejected", "request_mismatch", "track_unchanged", "devices:untouched"),
            "request_mismatch",
            status="failed",
            error_code="rejected",
        ),
    )
