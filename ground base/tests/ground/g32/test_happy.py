"""Happy-path order, correlation, and the operator script."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.extensions.g32.rehearsal import HAPPY_TRACE
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.kernel.paths import repo_root
from tests.ground.g32.conftest import calls_of, report_at, run


def test_happy_path_order_and_labels(services: BaseServices) -> None:
    _feature, result = run(services, "happy_path")
    assert result.status == "ok"
    assert result.data["detail"] == "happy_path"
    assert result.data["trace"] == HAPPY_TRACE
    assert result.data["slot"] == "feature.v2_rehearsal"
    assert result.data["schema_version"] == "ground-task-v2"
    assert result.data["simulated"] is True
    assert result.data["authorized"] is False
    assert result.error is None
    assert calls_of(services) == []
    saved = report_at(services, "happy_path")
    assert saved["label"] == "software simulation"
    assert saved["evidence"] == "simulated"
    assert saved["physical_acceptance"] is False
    assert saved["goal_status"] == "reached"
    assert saved["landing_status"] == "verified"
    assert saved["passed"] is True
    assert "random_search" not in saved["trace"]


def test_happy_journal_keeps_correlation_ids(services: BaseServices) -> None:
    run(services, "happy_path")
    devices = getattr(services.adapters, "devices", None)
    output = Path(str(getattr(devices, "output_dir", "")))
    lines = (output / "rehearsal-happy_path-seed0" / "events.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in lines.splitlines() if line.strip()]
    drone = next(
        row
        for row in rows
        if row["kind"] == "drone.command" and row["command_id"] == "cmd-drone-001"
    )
    dog = next(row for row in rows if row["kind"] == "dog.command")
    vision = next(row for row in rows if row["kind"] == "vision.request")
    for row in (drone, dog, vision):
        assert row["message_id"]
        assert row["mission_id"] == "demo-20261104-001"
        assert row["epoch"] == 1
        assert row["simulated"] is True
    assert drone["beacon_epoch"] == 4
    assert drone["track_id"] == "target-001"
    assert drone["frame_id"] == "drone-downward-001"
    assert dog["command_id"] == "cmd-dog-001"
    assert dog["map_epoch"] == 1
    assert dog["beacon_epoch"] == 4
    assert vision["request_id"]
    assert vision["frame_id"]
    assert vision["camera_epoch"] == 1
    copied = (output / "rehearsal-happy_path-seed0" / "script.md").read_text(encoding="utf-8")
    assert "artifacts/<mission_id>/events.jsonl" in copied


def test_script_names_teammate_files_halt_height_and_limits() -> None:
    text = (repo_root() / "demo" / "script.md").read_text(encoding="utf-8")
    required = (
        "Site check",
        "4 m",
        "## Arm",
        "halt",
        "goal",
        "landing",
        "software simulation",
        "physical acceptance",
        "artifacts/<mission_id>/events.jsonl",
        "contracts/drone-to-ai.md",
        "contracts/ai-to-drone.md",
        "contracts/dog-to-ai.md",
        "contracts/ai-to-dog.md",
        "contracts/vision.md",
        "contracts/rssi-and-navigation.md",
        "contracts/events-and-logs.md",
        "drone-capabilities.json",
        "ground-to-drone-command.json",
        "dog-capabilities.json",
        "ground-to-dog-command.json",
        "ai-to-dog-proposal.json",
        "drone-vision-request.json",
        "pi-rssi-window.json",
        "example-events.jsonl",
        "event-demo_goal_reached.json",
        "event-landing_unverified.json",
        "ground-to-dog-halt.json",
        "verified",
    )
    for phrase in required:
        assert phrase in text
