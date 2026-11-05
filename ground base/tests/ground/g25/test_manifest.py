"""The v2 manifest stays out of the frozen v1 slot table."""

from __future__ import annotations

import json

from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root


def test_manifest_file_names_the_v2_slot() -> None:
    path = repo_root() / "patrol" / "ground" / "extensions" / "g25" / "manifest.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "ground-task-v2"
    assert raw["task_id"] == "GROUND-25"
    assert raw["slot"] == "feature.v2_dog_acquire"
    assert raw["factory"] == "patrol.ground.extensions.g25.implementation:create"
    assert raw["scenario_factory"] == "patrol.ground.extensions.g25.scenarios:cases"


def test_gate_c_admits_owned_v2_manifest() -> None:
    from patrol.ground.kernel.loader import discover

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="25")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-25"
    assert found[0].slot == "feature.v2_dog_acquire"


def test_v1_discovery_still_names_the_safety_owner() -> None:
    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="10")
    assert found[0].slot == "base.safety"
    assert found[0].task_id == "GROUND-10"
    assert found[0].schema_version == "ground-task-v1"
