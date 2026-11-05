"""The v2 manifest stays out of the frozen v1 slot table."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.kernel.paths import repo_root


def test_manifest_names_the_v2_metrics_slot() -> None:
    path = repo_root() / "patrol" / "ground" / "extensions" / "g31" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ground-task-v2"
    assert manifest["task_id"] == "GROUND-31"
    assert manifest["slot"] == "feature.v2_metrics"


def test_gate_c_admits_owned_v2_manifest() -> None:
    from patrol.ground.kernel.loader import discover

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="31")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-31"
    assert found[0].slot == "feature.v2_metrics"


def test_examples_are_task_owned_copies() -> None:
    examples = repo_root() / "fixtures" / "ground" / "g31" / "examples"
    required = {
        "event-drone_target_acquired.json",
        "event-dog_dispatched.json",
        "event-demo_goal_reached.json",
        "event-landing_unverified.json",
        "drone-vision-request.json",
        "drone-vision-decision.json",
        "pi-rssi-window.json",
    }
    found = {path.name for path in examples.iterdir()}
    assert required <= found
    acquired = json.loads(
        (examples / "event-drone_target_acquired.json").read_text(encoding="utf-8")
    )
    assert acquired["payload"]["event"] == "drone_target_acquired"
    assert Path(examples / "event-landing_unverified.json").is_file()
