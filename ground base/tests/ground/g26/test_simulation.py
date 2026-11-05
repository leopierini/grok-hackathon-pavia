"""Run every proximity case through Task 01's simulator."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g26.implementation import create
from patrol.ground.extensions.g26.scenarios import cases
from patrol.ground.testing.builders import build_test_services
from tests.ground.g26.conftest import run


def test_harness_runs_every_owned_case(tmp_path: Path) -> None:
    async def body() -> None:
        for case in cases(seed=0):
            services = build_test_services(output_dir=tmp_path / case.case_id, seed=0)
            feature = create(services)
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            assert report.failures == (), case.case_id
            assert report.live_call_count == 0
            assert report.cases[0]["passed"] is True

    run(body)
