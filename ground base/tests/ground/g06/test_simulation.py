"""The task harness runs the owned provider and writes the simulation report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_simulation_command_passes_every_case(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    assert _run(first) == 0
    assert _run(second) == 0
    first_report = json.loads(first.read_text(encoding="utf-8"))
    second_report = json.loads(second.read_text(encoding="utf-8"))

    assert first_report["task_id"] == "GROUND-06"
    assert first_report["seed"] == 0
    assert first_report["failures"] == []
    assert first_report["live_call_count"] == 0
    assert first_report["evidence"] == "simulated"
    assert first_report["clock_mode"] == "manual"
    assert first_report["cases"] == second_report["cases"]
    accepted = _case(first_report, "live_dog_accepted")
    rejected = _case(first_report, "pre_request_buffer")
    landing = _case(first_report, "aerial_landing_delay")
    assert accepted["passed"] is True
    assert rejected["passed"] is True
    assert landing["passed"] is True


def _run(report: Path) -> int:
    root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "patrol.ground.sim",
            "--task",
            "06",
            "--case",
            "all",
            "--seed",
            "0",
            "--report",
            str(report),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout + "\n" + completed.stderr)
    return completed.returncode


def _case(report: dict[str, object], case_id: str) -> dict[str, object]:
    cases = report["cases"]
    assert isinstance(cases, list)
    for item in cases:
        assert isinstance(item, dict)
        if item["case_id"] == case_id:
            return item
    raise AssertionError(case_id)
