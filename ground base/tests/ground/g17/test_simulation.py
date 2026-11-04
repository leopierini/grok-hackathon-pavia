"""Task 01's simulator runs the owned provider. The v1 loader cannot admit the slot."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g17.implementation import create
from patrol.ground.extensions.g17.scenarios import cases
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def test_harness_runs_every_case(tmp_path: Path) -> None:
    async def body() -> None:
        for case in cases(seed=0):
            services = build_test_services(output_dir=tmp_path / case.case_id)
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": create(services), "services": services},
                clock_mode="manual",
            )
            assert report.failures == ()
            assert report.live_call_count == 0
            assert report.cases[0]["passed"] is True

    asyncio.run(body())


def test_gate_c_admits_owned_v2_manifest() -> None:

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="17")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-17"
    assert found[0].slot == "feature.v2_drone_command"


def test_contract_examples_are_copied_into_the_task_fixtures() -> None:
    directory = repo_root() / "fixtures" / "ground" / "g17"
    for name in (
        "ai-to-drone-proposal.json",
        "ground-to-drone-command.json",
        "ground-to-drone-hover.json",
        "ground-to-drone-land.json",
        "drone-capabilities.json",
        "drone-observation.json",
    ):
        copied = json.loads((directory / name).read_text(encoding="utf-8"))
        source = repo_root() / "contracts" / "examples" / name
        assert source.is_file()
        assert copied == json.loads(source.read_text(encoding="utf-8"))
