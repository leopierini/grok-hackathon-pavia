"""Task 01 simulator, pointed at the timing cases."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.ground.extensions.g31.implementation import create
from patrol.ground.extensions.g31.scenarios import cases
from patrol.ground.testing.builders import build_test_services


def test_simulator_runs_every_timing_case(tmp_path: Path) -> None:
    async def invoke() -> None:
        services = build_test_services(output_dir=tmp_path, seed=0)
        feature = create(services)
        for case in cases(seed=0):
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            assert report.failures == ()
            assert report.live_call_count == 0
            assert report.cases[0]["passed"] is True

    asyncio.run(invoke())
