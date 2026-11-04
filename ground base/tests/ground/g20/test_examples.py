"""The contract examples produce the documented safe candidate."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g20.policy import SCHEMA, SLOT
from patrol.ground.kernel.paths import repo_root
from tests.ground.g20.support import (
    CANDIDATE,
    calls_of,
    feature,
    forbid_target_range,
    ids_of,
    payload,
    readiness_of,
    request,
    run,
)


def test_manifest_names_the_v2_slot() -> None:
    path = repo_root() / "patrol" / "ground" / "extensions" / "g20" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == SCHEMA
    assert manifest["task_id"] == "GROUND-20"
    assert manifest["slot"] == SLOT
    assert manifest["factory"].endswith(":create")
    assert manifest["scenario_factory"].endswith(":cases")


def test_gate_c_admits_owned_v2_manifest() -> None:
    from patrol.ground.kernel.loader import discover

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="20")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-20"
    assert found[0].slot == "feature.v2_dog_navigation"


def test_example_pair_returns_the_documented_candidate(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        result = await port.execute(request(payload()))
        assert result.status == "ok"
        assert result.error is None
        assert ids_of(result) == (CANDIDATE,)
        readiness = readiness_of(result)
        assert readiness["standing"] is True
        assert readiness["stationary"] is True
        assert readiness["avoidance"] is True
        assert readiness["navigation_mode"] == "slam_local_planner"
        assert readiness["slam_state"] == "localized"
        assert readiness["minimum_clearance_m"] == 0.8
        assert result.data["ready"] is True
        assert result.data["ready_to_wait"] is False
        assert result.data["map_id"] == "museum-map-demo"
        assert result.data["map_epoch"] == 1
        assert result.data["pose_map_epoch"] == 1
        frame = result.data["frame"]
        assert isinstance(frame, Mapping)
        assert frame["frame_id"] == "dog-front-001"
        assert frame["image_ref"] == "artifact://demo-20261104-001/dog/front-001.jpg"
        assert result.data["commands"] == ()
        assert result.data["motion_proposed"] is False
        assert calls_of(built) == []
        forbid_target_range(result.data)
        assert result.events[0].kind == "decision_received"
        assert result.events[0].payload["candidate_ids"] == (CANDIDATE,)
        assert "move_local" not in result.events[0].payload

    run(body)
