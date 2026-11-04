"""Gate C with actual Ground services, actual policies, and synthetic wire peers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from patrol.ground.__main__ import main
from patrol.ground.demo import SCENARIOS, run_demo


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("transport", ["ethernet", "wifi"])
@pytest.mark.parametrize("seed", [0, 7, 29])
def test_full_composition_outcomes(
    tmp_path: Path,
    scenario: str,
    transport: str,
    seed: int,
) -> None:
    output = tmp_path / "mission"
    report = asyncio.run(run_demo(output, scenario=scenario, seed=seed, transport=transport))
    assert report["evidence"] == "simulated"
    assert report["live_call_count"] == 0
    assert report["provider_tasks"] == list(range(11, 33))
    assert report["cleanup_errors"] == []
    assert report["goal_reached"] is (scenario in {"happy_path", "unknown_landing"})
    assert report["landing_verified"] is (scenario == "happy_path")
    assert report["outcome"] == ("completed" if scenario == "happy_path" else "unresolved")
    assert json.loads((output / "report.json").read_text()) == report
    summary = json.loads((output / "mission/summary.json").read_text())
    assert summary["goal_reached"] == report["goal_reached"]
    rows = [json.loads(line) for line in (output / "mission/events.jsonl").read_text().splitlines()]
    assert [row["seq"] for row in rows] == list(range(1, len(rows) + 1))
    assert all(row["modes"] == {"dog": "fake", "drone": "fake", "grok": "fake"} for row in rows)
    commands = report["commands"]
    assert all(c["simulated"] is True and c["source"] == "ground" for c in commands)
    assert not any(c["payload"]["action"] == "takeoff" for c in commands)
    dog_commands = [c for c in commands if c["destination"] == "dog"]
    assert len(dog_commands) == (1 if scenario in {"happy_path", "unknown_landing"} else 0)
    if dog_commands:
        motion = dog_commands[0]["payload"]["motion"]
        assert motion["candidate_id"] == "candidate-forward-01"
        assert motion["frame_id"] == "dog/base_link"
        assert motion["duration_ms"] <= 500
        stages = [row["task"] for row in report["trace"]]
        assert stages.index(16) < stages.index(17) < stages.index(18) < stages.index(23)
        assert stages.index(24) < stages.index(25) < stages.index(26) < stages.index(27)
    if scenario == "unknown_landing":
        assert report["recovery_required"] is True
        metric = report["metrics"]["metrics"]["goal_to_verified_landing_s"]
        assert metric["seconds"] is None
    assert report["metrics"]["metrics"]["model_accuracy"]["accuracy"] is None


def test_public_cli_runs_all_fake_and_keeps_real_mode_disarmed(tmp_path: Path) -> None:
    flags = ["--dog", "fake", "--drone", "fake", "--grok", "fake"]
    assert main([*flags, "--output-dir", str(tmp_path / "run")]) == 0
    assert main([*flags, "--output-dir", str(tmp_path / "run")]) == 1
    assert main(["--dog", "real", "--drone", "fake", "--grok", "fake"]) == 2
    assert main([*flags, "--image", "untrusted.jpg"]) == 2


def test_invalid_rehearsal_input_and_run_overwrite_fail_before_motion(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="unknown rehearsal"):
        asyncio.run(run_demo(tmp_path / "bad", scenario="not-a-scenario"))
    assert not (tmp_path / "bad").exists()
    with pytest.raises(Exception, match="integer"):
        asyncio.run(run_demo(tmp_path / "bad", seed=True))
