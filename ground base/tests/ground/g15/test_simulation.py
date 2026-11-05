"""Task 01 harness over the owned provider. The v1 loader still rejects this slot."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g15.implementation import create
from patrol.ground.extensions.g15.scenarios import cases
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services
from tests.ground.g15.support import run


def test_kernel_simulator_runs_every_owned_case(tmp_path: Path) -> None:
    async def body() -> None:
        for case in cases(seed=0):
            stack = tmp_path / case.case_id
            stack.mkdir()
            built = build_test_services(clock_mode="manual", seed=0, output_dir=stack)
            feature = create(built)
            report = await built.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": built},
                clock_mode="manual",
            )
            assert report.failures == (), (case.case_id, report.cases)
            assert report.live_call_count == 0

    run(body)


def test_gate_c_admits_owned_v2_manifest() -> None:

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="15")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-15"
    assert found[0].slot == "feature.v2_vision_schedule"
