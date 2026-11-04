"""Exercise all owned providers through Gate C discovery and the official harness."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.v2_catalog import V2_SLOTS
from patrol.ground.sim import _run


def test_exactly_32_owned_contributions_are_loadable() -> None:
    manifests = discover(repo_root() / "patrol/ground/extensions")
    assert len(manifests) == 32
    assert [m.task_id for m in manifests] == [f"GROUND-{n:02}" for n in range(1, 33)]
    assert {m.slot: m.task_id[-2:] for m in manifests[10:]} == V2_SLOTS


@pytest.mark.parametrize("slot", ["feature.v2_unreviewed", "feature.v2_recovery"])
def test_v2_prefix_does_not_bypass_exact_ownership(tmp_path: Path, slot: str) -> None:
    root = tmp_path / "g11"
    root.mkdir()
    for name in ("implementation", "scenarios"):
        (root / f"{name}.py").write_text("def create(*args): return None\n")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "ground-task-v2",
                "task_id": "GROUND-11",
                "slot": slot,
                "factory": "patrol.ground.extensions.g11.implementation:create",
                "scenario_factory": "patrol.ground.extensions.g11.scenarios:cases",
            }
        )
    )
    with pytest.raises(GroundFault) as caught:
        discover(tmp_path)
    assert caught.value.error.code == (
        "unknown_slot" if slot.endswith("unreviewed") else "owner_mismatch"
    )


@pytest.mark.parametrize("task", range(1, 33))
def test_each_real_provider_passes_all_its_harness_cases(tmp_path: Path, task: int) -> None:
    report = asyncio.run(
        _run(
            task=str(task),
            case_name="all",
            seed=29,
            report_path=tmp_path / "simulation.json",
        )
    )
    assert report.task_id == f"GROUND-{task:02}"
    assert report.cases and all(row["passed"] is True for row in report.cases)
    assert report.failures == ()
    assert report.live_call_count == 0
    assert report.skipped == 0
    assert report.assertion_count >= len(report.cases)
