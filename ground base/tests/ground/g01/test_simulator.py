"""Simulation harness, readable fixtures, and deterministic replay."""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
import sys
from pathlib import Path

from patrol.contract import Frame, Incident, RunContext
from patrol.ground.kernel import tiny_jpeg_bytes
from patrol.ground.kernel.authority import SessionAuthority
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services
from PIL import Image


def test_tiny_jpeg_is_readable() -> None:
    with Image.open(io.BytesIO(tiny_jpeg_bytes())) as image:
        image.load()
        assert image.size == (2, 2)


def test_scripted_devices_keep_simulation_flags(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(scenario="dismiss", output_dir=tmp_path)
        devices = services.adapters.devices  # type: ignore[attr-defined]
        authority = SessionAuthority()
        ticket = authority.issue("mission", "dispatch")
        context = RunContext("mission", 10_000, authority.cancel_event)
        frame = Frame(str(tmp_path / "phone.jpg"), "phone", "room_2", None, True)
        incident = Incident("mission", "room_2", "a left object", frame)
        decision = await devices.reasoner.assess_incident(incident, context)
        assert decision.action == "dismiss"
        assert "dog.run_route" not in devices.calls
        stale = build_test_services(scenario="stale_frame", output_dir=tmp_path / "stale")
        stale_devices = stale.adapters.devices  # type: ignore[attr-defined]
        captured = await stale_devices.dog.capture_frame("room_2", context)
        assert captured.simulated is True
        assert captured.captured_at == "2000-01-01T00:00:00Z"
        assert ticket.mission_id == "mission"

    asyncio.run(body())


def test_simulation_command_and_seed_replay(tmp_path: Path) -> None:
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    for destination in (first, second):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "patrol.ground.sim",
                "--task",
                "01",
                "--case",
                "all",
                "--seed",
                "0",
                "--report",
                str(destination),
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=repo_root(),
        )
        assert completed.returncode == 0, completed.stderr
    left = json.loads(first.read_text(encoding="utf-8"))
    right = json.loads(second.read_text(encoding="utf-8"))
    assert left["seed"] == 0
    assert left["skipped"] == 0
    assert left["live_call_count"] == 0
    assert left["failures"] == []
    assert len(left["cases"]) == 12
    comparable = [
        {
            "case_id": case["case_id"],
            "passed": case["passed"],
            "status": case["status"],
            "error_code": case["error_code"],
            "trace": case["trace"],
        }
        for case in left["cases"]
    ]
    other = [
        {
            "case_id": case["case_id"],
            "passed": case["passed"],
            "status": case["status"],
            "error_code": case["error_code"],
            "trace": case["trace"],
        }
        for case in right["cases"]
    ]
    assert comparable == other
    assert left["evidence"] == "simulated"
