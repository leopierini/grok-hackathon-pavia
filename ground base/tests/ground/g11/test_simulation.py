"""Task 01 harness runs the owned provider. The v1 loader does not admit this slot."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.ground.extensions.g11.implementation import create
from patrol.ground.extensions.g11.scenarios import cases
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.testing.builders import build_test_services


def test_harness_cases_pass_with_empty_adapter_traces(tmp_path: Path) -> None:
    async def body() -> None:
        selected = cases(seed=0)
        assert len(selected) == 6
        for case in selected:
            built = build_test_services(
                clock_mode="manual",
                seed=0,
                output_dir=tmp_path / case.case_id,
            )
            report = await built.kernel.simulator.run(
                case,
                providers={"feature": create(built), "services": built},
                clock_mode="manual",
            )
            assert report.failures == (), case.case_id
            assert report.live_call_count == 0
            devices = getattr(built.adapters, "devices", None)
            assert getattr(devices, "calls", []) == []

    asyncio.run(body())


def test_services_argument_matches_the_harness_contract(tmp_path: Path) -> None:
    built = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
    assert isinstance(built, BaseServices)
    assert hasattr(create(built), "execute")
