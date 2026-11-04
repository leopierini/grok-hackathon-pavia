"""Run the owned scenarios through Task 01's simulator."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g29.implementation import create
from patrol.ground.extensions.g29.scenarios import cases
from patrol.ground.kernel.simulator import KernelSimulator
from patrol.ground.testing.builders import build_test_services
from tests.ground.g29.conftest import run


def test_simulation_cases(tmp_path: Path) -> None:
    async def body() -> None:
        simulator = KernelSimulator()
        for case in cases(seed=0):
            services = build_test_services(
                output_dir=tmp_path / case.case_id,
                clock_mode="manual",
                seed=0,
            )
            feature = create(services)
            report = await simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            assert report.failures == (), case.case_id
            assert report.live_call_count == 0
            assert report.cases[0]["passed"] is True

    run(body)
