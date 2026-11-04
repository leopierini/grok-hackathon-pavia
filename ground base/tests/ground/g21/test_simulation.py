"""Task 01 harness cases for the RSSI provider."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import cast

from patrol.ground.extensions.g21.implementation import create
from patrol.ground.extensions.g21.scenarios import cases
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


class _SocketGuard:
    def __init__(self) -> None:
        self.count = 0
        self._original_init = socket.socket.__init__

    def install(self) -> None:
        guard = self

        def guarded(sock: socket.socket, *args: object, **kwargs: object) -> None:
            frames = traceback.extract_stack()[:-1]
            caller = frames[-1].filename.replace("\\", "/") if frames else ""
            if "/patrol/" in caller and "/asyncio/" not in caller:
                guard.count += 1
                raise RuntimeError("simulation opened a socket")
            original = cast(Callable[..., None], guard._original_init)
            original(sock, *args, **kwargs)

        socket.socket.__init__ = guarded  # type: ignore[method-assign]

    def close(self) -> None:
        socket.socket.__init__ = self._original_init  # type: ignore[method-assign]


def test_harness_covers_every_scripted_case(tmp_path: Path) -> None:
    async def body() -> None:
        guard = _SocketGuard()
        guard.install()
        rows: list[dict[str, object]] = []
        assertions = 0
        try:
            for case in cases(0):
                services = build_test_services(
                    clock_mode="manual",
                    seed=0,
                    output_dir=tmp_path / case.case_id,
                )
                feature = create(services)
                report = await services.kernel.simulator.run(
                    case,
                    providers={"feature": feature, "services": services},
                    clock_mode="manual",
                )
                assert report.failures == (), report.cases
                assert report.live_call_count == 0
                assertions += report.assertion_count
                devices = getattr(services.adapters, "devices", None)
                assert getattr(devices, "calls", None) == []
                assert "state.apply" not in getattr(services.state, "trace", [])
                for row in report.cases:
                    rows.append(dict(row))
        finally:
            guard.close()
        assert guard.count == 0
        destination = repo_root() / "artifacts" / "task-21" / "simulation.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "task_id": "GROUND-21",
            "seed": 0,
            "clock_mode": "manual",
            "cases": rows,
            "failures": [],
            "assertion_count": assertions,
            "modes": {"dog": "fake", "drone": "fake", "grok": "fake"},
            "trace": [],
            "artifact_paths": [str(destination)],
            "live_call_count": 0,
            "skipped": 0,
            "evidence": "simulated",
        }
        destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        assert len(rows) == 10

    asyncio.run(body())


def test_gate_c_admits_owned_v2_manifest() -> None:

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="21")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-21"
    assert found[0].slot == "feature.v2_rssi"


def test_sim_command_runs_registered_rssi() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root())
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "patrol.ground.sim",
            "--task",
            "21",
            "--case",
            "all",
            "--seed",
            "0",
            "--report",
            "artifacts/task-21/cli-simulation.json",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root(),
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert "simulation passed" in completed.stdout
