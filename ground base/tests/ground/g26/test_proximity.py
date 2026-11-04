"""Direct checks for dog range and drone horizontal offset."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g26.implementation import ProximityFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, GroundEvent
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services
from tests.ground.g26.conftest import request, run

_FIXTURES = repo_root() / "fixtures" / "ground" / "g26"


def test_gate_c_admits_owned_v2_manifest() -> None:

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="26")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-26"
    assert found[0].slot == "feature.v2_proximity"


def test_example_emits_one_goal_and_no_landing(
    opened: tuple[BaseServices, ProximityFeature],
) -> None:
    services, feature = opened

    async def body() -> None:
        result = await feature.execute(request("example_accepted"))
        assert result.status == "ok"
        assert result.data["detail"] == "goal_reached"
        assert result.data["authorized"] is True
        assert result.data["trace"][0] == "thresholds:1.5,1.5"
        assert "demo_goal_reached" in result.data["trace"]
        assert "no_land" in result.data["trace"]
        assert "flight_state_untouched" in result.data["trace"]
        assert "recovery_untouched" in result.data["trace"]
        assert len(result.events) == 1
        event = result.events[0]
        assert isinstance(event, GroundEvent)
        assert event.kind == "decision_received"
        envelope = event.payload
        assert envelope["kind"] == "mission.event"
        mission = envelope["payload"]
        assert isinstance(mission, Mapping)
        assert mission["event"] == "demo_goal_reached"
        assert mission["phase"] == "proximity_verify"
        assert mission["outcome"] == "completed"
        assert mission["device_recovery_required"] is False
        assert mission["reason"].startswith("Both separately defined proximity checks")
        details = mission["details"]
        assert isinstance(details, Mapping)
        assert details["track_id"] == "target-001"
        assert details["logs_requirements_status"] == "proposed_pending_team"
        assert details["mission_id"] == "demo-20261104-001"
        assert details["dog_range_max_m"] == 1.5
        assert details["drone_horizontal_max_m"] == 1.5
        assert "flight_state" not in _keys(envelope)
        assert "command_id" not in details
        assert _calls(services) == []
        assert services.state.trace == []
        assert services.journal.records == []

    run(body)


def test_fixture_json_is_accepted_when_the_profile_is_open(tmp_path: Path) -> None:
    services = build_test_services(output_dir=tmp_path)
    feature = create(services)
    message = json.loads((_FIXTURES / "proximity-evidence.json").read_text(encoding="utf-8"))
    profile = json.loads((_FIXTURES / "profile-open.json").read_text(encoding="utf-8"))
    payload = {
        "message": message,
        "track_id": "target-001",
        "dog_stopped": True,
        "hold_state": "stable",
        "evaluated_at": "2026-11-04T13:00:11.000Z",
        "profile": profile,
    }

    async def body() -> None:
        result = await feature.execute(FeatureRequest("stage", "evaluate", None, payload))
        assert result.data["detail"] == "goal_reached"
        assert result.events[0].payload["kind"] == "mission.event"
        checked = services.kernel.result_validation.feature_result("kernel.foundation", result)
        assert checked.data["slot"] == "feature.v2_proximity"

    run(body)


def test_missing_offset_stays_unresolved(
    opened: tuple[BaseServices, ProximityFeature],
) -> None:
    _feature = opened[1]

    async def body() -> None:
        result = await _feature.execute(request("null_drone_offset"))
        assert result.status == "ok"
        assert result.data["detail"] == "unresolved"
        assert result.data["authorized"] is False
        assert result.events == ()
        assert "unresolved:missing_drone_offset" in result.data["trace"]
        assert "demo_goal_reached" not in result.data["trace"]

    run(body)


def test_four_meter_3d_claim_is_rejected(
    opened: tuple[BaseServices, ProximityFeature],
) -> None:
    feature = opened[1]

    async def body() -> None:
        result = await feature.execute(request("full_3d_at_4m"))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.recovery_required is False
        assert result.events == ()
        assert "rejected:full_3d_at_4m" in result.data["trace"]
        assert "no_land" in result.data["trace"]

    run(body)


def test_clearance_motion_operator_and_stale(
    opened: tuple[BaseServices, ProximityFeature],
) -> None:
    feature = opened[1]

    async def body() -> None:
        clearance = await feature.execute(request("clearance_not_range"))
        moving = await feature.execute(request("moving_dog"))
        beacon = await feature.execute(request("moving_beacon"))
        enabled = await feature.execute(request("operator_enabled"))
        disabled = await feature.execute(request("operator_disabled"))
        stale = await feature.execute(request("stale_timestamp"))
        fresh_edge = await feature.execute(request("age_boundary"))
        assert clearance.status == "failed"
        assert "rejected:clearance" in clearance.data["trace"]
        assert moving.data["detail"] == "unresolved"
        assert "unresolved:dog_moving" in moving.data["trace"]
        assert "unresolved:beacon_moving" in beacon.data["trace"]
        assert enabled.data["detail"] == "goal_reached"
        assert enabled.events[0].payload["payload"]["event"] == "demo_goal_reached"
        assert disabled.data["detail"] == "unresolved"
        assert "unresolved:operator_disabled" in disabled.data["trace"]
        assert "unresolved:stale" in stale.data["trace"]
        assert fresh_edge.data["detail"] == "goal_reached"
        assert _calls(opened[0]) == []

    run(body)


def test_profile_threshold_beats_the_example_numbers(
    opened: tuple[BaseServices, ProximityFeature],
) -> None:
    feature = opened[1]

    async def body() -> None:
        tight = await feature.execute(request("profile_threshold"))
        unset = await feature.execute(request("thresholds_unset"))
        equal = await feature.execute(request("threshold_equal"))
        height = await feature.execute(request("height_without_3d_claim"))
        assert tight.data["trace"][0] == "thresholds:1,1.5"
        assert "unresolved:outside_threshold" in tight.data["trace"]
        assert "thresholds:unset" in unset.data["trace"]
        assert equal.data["detail"] == "goal_reached"
        assert height.data["detail"] == "goal_reached"
        assert "demo_goal_reached" in height.data["trace"]

    run(body)


def test_string_boolean_is_not_coerced(
    opened: tuple[BaseServices, ProximityFeature],
) -> None:
    feature = opened[1]

    async def body() -> None:
        result = await feature.execute(request("string_bool"))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert result.events == ()

    run(body)


def _calls(services: object) -> list[str]:
    devices = getattr(getattr(services, "adapters", None), "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        found.update(str(key) for key in value)
        for item in value.values():
            found.update(_keys(item))
    elif isinstance(value, list | tuple):
        for item in value:
            found.update(_keys(item))
    return found


def _package() -> Path:
    return repo_root() / "patrol" / "ground" / "extensions" / "g26"
