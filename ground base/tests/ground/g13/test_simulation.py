"""Run the owned provider through the foundation simulator."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.ground.extensions.g13.implementation import create
from patrol.ground.extensions.g13.scenarios import cases
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def test_harness_cases_pass(tmp_path: Path) -> None:
    async def body() -> None:
        for case in cases(seed=0):
            services = build_test_services(
                clock_mode="manual",
                seed=0,
                output_dir=tmp_path / case.case_id,
            )
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": create(services), "services": services},
                clock_mode="manual",
            )
            assert report.failures == (), report.cases
            assert report.live_call_count == 0
            assert report.cases[0]["passed"] is True

    asyncio.run(body())


def test_gate_c_admits_owned_v2_manifest() -> None:

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="13")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-13"
    assert found[0].slot == "feature.v2_drone_observation"
