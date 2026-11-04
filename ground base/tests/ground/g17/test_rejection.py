"""Refusals stay on the ground side and do not allocate a command."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.ground.extensions.g17.samples import (
    armed_context,
    features_of,
    operator_context,
    payload_of,
)
from tests.ground.g17.support import calls_of, feature, request, run


def _block(tmp_path: Path, context: dict[str, object], reason: str) -> None:
    services, port = feature(tmp_path)

    async def body() -> None:
        result = await port.execute(request(context))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.detail == reason
        assert result.error.recovery_required is False
        assert result.data["command"] is None
        assert result.events[0].kind == "decision_received"
        assert result.events[0].payload["reason"] == reason
        assert calls_of(services) == []

    run(body)


def test_uncontrolled_track_is_rejected(tmp_path: Path) -> None:
    context = armed_context()
    features_of(_dict(context["capabilities"]))["controlled_motion"] = False
    _block(tmp_path, context, "controlled_motion_disabled")


def test_missing_calibration_blocks_track(tmp_path: Path) -> None:
    context = armed_context()
    context["calibration"] = None
    _block(tmp_path, context, "calibration_missing")


def test_false_calibration_blocks_track(tmp_path: Path) -> None:
    context = armed_context()
    context["calibration"] = False
    _block(tmp_path, context, "calibration_missing")


@pytest.mark.parametrize(
    "text",
    ["move five meters left", "shift 5 meters", "go 5m left", "a five-meter move"],
)
def test_displacement_text_is_rejected(tmp_path: Path, text: str) -> None:
    context = armed_context()
    payload_of(_dict(context["proposal"]))["reason"] = text
    _block(tmp_path, context, "displacement_rejected")


@pytest.mark.parametrize(
    "text",
    ["send_rc_control 0 0 0 0", "move_forward(50)", "from djitellopy import Tello"],
)
def test_sdk_text_is_rejected(tmp_path: Path, text: str) -> None:
    context = armed_context()
    payload_of(_dict(context["proposal"]))["reason"] = text
    _block(tmp_path, context, "sdk_text_rejected")


def test_track_lease_above_500_is_rejected(tmp_path: Path) -> None:
    context = armed_context()
    context["lease_ms"] = 5000
    _block(tmp_path, context, "lease_exceeds_motion_cap")


def test_height_with_unknown_reference_is_rejected(tmp_path: Path) -> None:
    context = armed_context()
    context["requested_height_m"] = 4
    context["height_reference"] = "unknown"
    _block(tmp_path, context, "height_reference_mismatch")


def test_height_outside_the_profile_is_rejected(tmp_path: Path) -> None:
    context = operator_context("takeoff", "operator-takeoff-height")
    observation = _dict(context["observation"])
    payload_of(observation)["flight_state"] = "grounded"
    allowlist = _dict(context["allowlist"])
    allowlist["height_profile"] = {"profile_id": "none", "allowed": []}
    context["requested_height_m"] = 4
    context["height_reference"] = "floor_agl"
    _block(tmp_path, context, "height_not_in_profile")


def test_expired_proposal_is_rejected(tmp_path: Path) -> None:
    context = armed_context()
    context["evaluated_at"] = "2026-11-04T13:00:10.700Z"
    _block(tmp_path, context, "expired_proposal")


def test_dog_proposal_is_not_a_dog_command(tmp_path: Path) -> None:
    context = armed_context()
    payload_of(_dict(context["proposal"]))["target_component"] = "dog"
    _block(tmp_path, context, "wrong_component")


def test_search_cap_is_rejected(tmp_path: Path) -> None:
    context = armed_context()
    payload_of(_dict(context["proposal"]))["action"] = "search"
    payload_of(_dict(context["proposal"]))["proposal_id"] = "proposal-search-capped"
    context["search_steps_taken"] = 2
    _block(tmp_path, context, "search_cap_exhausted")


def test_unlabeled_track_is_rejected_when_motion_is_uncontrolled(tmp_path: Path) -> None:
    context = operator_context("track_step", "operator-track-open", direction_hint="left")
    features_of(_dict(context["capabilities"]))["controlled_motion"] = False
    _block(tmp_path, context, "controlled_motion_disabled")


def test_string_boolean_is_not_permission(tmp_path: Path) -> None:
    services, port = feature(tmp_path)
    context = armed_context()
    features_of(_dict(context["capabilities"]))["controlled_motion"] = "true"

    async def body() -> None:
        result = await port.execute(request(context))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert result.error.detail == "controlled_motion must be a boolean"
        assert result.data["command"] is None
        assert calls_of(services) == []

    run(body)


def test_right_hint_without_a_primitive_is_rejected(tmp_path: Path) -> None:
    context = armed_context()
    payload_of(_dict(context["proposal"]))["direction_hint"] = "right"
    _block(tmp_path, context, "primitive_missing")


def test_takeoff_while_airborne_is_rejected(tmp_path: Path) -> None:
    context = operator_context("takeoff", "operator-takeoff-air")
    _block(tmp_path, context, "already_airborne")


def test_unknown_flight_state_blocks_track_and_still_allows_land(tmp_path: Path) -> None:
    services, port = feature(tmp_path)
    blocked = armed_context()
    payload_of(_dict(blocked["observation"]))["flight_state"] = "unknown"
    landing = operator_context("land", "operator-land-unknown")
    payload_of(_dict(landing["observation"]))["flight_state"] = "unknown"

    async def body() -> None:
        refused = await port.execute(request(blocked))
        allowed = await port.execute(request(landing))
        assert refused.status == "blocked"
        assert refused.error is not None
        assert refused.error.detail == "aircraft_state_unknown"
        assert allowed.status == "ok"
        assert allowed.data["action"] == "land"
        assert calls_of(services) == []

    run(body)


def test_halt_blocks_track_and_still_allows_land(tmp_path: Path) -> None:
    services, port = feature(tmp_path)
    services.kernel.authority.latch_cancel("operator halt")
    landing = operator_context("land", "operator-land-halt")

    async def body() -> None:
        refused = await port.execute(request(armed_context()))
        allowed = await port.execute(request(landing))
        assert refused.status == "blocked"
        assert refused.error is not None
        assert refused.error.code == "cancelled"
        assert refused.error.recovery_required is True
        assert allowed.status == "ok"
        assert allowed.data["action"] == "land"
        assert calls_of(services) == []

    run(body)


def test_stale_ticket_is_rejected(tmp_path: Path) -> None:
    services, port = feature(tmp_path)
    ticket = services.kernel.authority.issue("demo-20261104-001", "drone-command")
    services.kernel.authority.latch_cancel("operator halt")

    async def body() -> None:
        result = await port.execute(
            request(operator_context("land", "operator-land-stale"), ticket)
        )
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "stale_ticket"

    run(body)


def test_active_command_blocks_a_new_primitive(tmp_path: Path) -> None:
    context = armed_context()
    payload_of(_dict(context["observation"]))["active_command_id"] = "cmd-already"
    _block(tmp_path, context, "command_in_flight")


def test_landing_deadline_of_500_is_rejected(tmp_path: Path) -> None:
    context = operator_context("land", "operator-land-short")
    allowlist = _dict(context["allowlist"])
    allowlist["land_deadline_ms"] = 500
    _block(tmp_path, context, "deadline_reuses_motion_lease")


def test_supervised_label_conflicts_with_armed_control(tmp_path: Path) -> None:
    context = operator_context("search", "operator-supervised-armed", supervised=True)
    _block(tmp_path, context, "supervised_conflicts_with_control")


def _dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value
