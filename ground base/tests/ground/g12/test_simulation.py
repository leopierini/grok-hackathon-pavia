"""Harness cases for capability admission, plus the frozen v1 loader boundary."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g12.implementation import create
from patrol.ground.extensions.g12.scenarios import cases
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def test_gate_c_admits_owned_v2_manifest() -> None:

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="12")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-12"
    assert found[0].slot == "feature.v2_capabilities"


def test_manifest_registers_only_the_v2_slot() -> None:
    path = (
        repo_root()
        / "patrol"
        / "ground"
        / "extensions"
        / "g12"
        / "manifest.json"
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": "ground-task-v2",
        "task_id": "GROUND-12",
        "slot": "feature.v2_capabilities",
        "factory": "patrol.ground.extensions.g12.implementation:create",
        "scenario_factory": "patrol.ground.extensions.g12.scenarios:cases",
    }


def test_harness_cases(tmp_path: Path) -> None:
    async def body() -> None:
        for case in cases(seed=0):
            services = build_test_services(output_dir=tmp_path / case.case_id, seed=0)
            feature = create(services)
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            assert report.failures == (), report
            assert report.live_call_count == 0
            devices = getattr(services.adapters, "devices", None)
            calls = getattr(devices, "calls", None)
            assert calls == []

    asyncio.run(body())
