"""Pending work stays owned and blocks a replacement operation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from patrol.contract import RunContext
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g05.helpers import make_executor


def test_resistant_operation_blocks_replacement_and_reset(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        barriers = services.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        executor.bind_mission("mission", 5)
        ticket = services.kernel.authority.issue("mission", "inspect")

        async def factory(_context: RunContext) -> str:
            entered.set()
            while True:
                try:
                    await barriers.wait("hold")
                except asyncio.CancelledError:
                    continue
                return "finished"

        run_task = asyncio.create_task(executor.run("drone.inspect", ticket, factory, limit_s=5))
        await entered.wait()
        _advance(services, 5)
        result = await run_task
        assert result.status == "timeout"
        assert result.pending is True
        assert result.error is not None
        assert "does not prove the device stopped" in result.error.detail
        assert executor.pending() == ("drone.inspect",)
        assert "drone.inspect" in services.kernel.tasks.pending()

        async def replacement(_context: RunContext) -> str:
            return "replacement"

        blocked = await executor.run("drone.inspect", ticket, replacement, limit_s=5)
        assert blocked.status == "failed"
        assert blocked.error is not None
        assert blocked.error.code == "unsafe_state"
        assert executor.factory_calls == ["drone.inspect"]
        with pytest.raises(GroundFault) as caught:
            await services.safety.reset({"verified": True})
        assert caught.value.error.code == "unsafe_state"

        barriers.release("hold")
        late = await executor.inspect_late("drone.inspect")
        assert late == "finished"
        assert executor.history[0].status == "timeout"
        assert executor.pending() == ()
        await executor.collect(deadline=1)
        await services.safety.reset({"verified": True})

    asyncio.run(body())


def test_collect_consumes_a_finished_failure(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        ticket = services.kernel.authority.issue("mission", "model")

        async def factory(_context: RunContext) -> str:
            raise RuntimeError("boom")

        result = await executor.run("reasoner.assess_incident", ticket, factory, limit_s=2)
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "internal"
        assert result.error.detail == "boom"
        await executor.collect(deadline=1)
        assert executor.pending() == ()
        assert services.kernel.tasks.pending() == ()

    asyncio.run(body())


def _advance(services: BaseServices, seconds: float) -> None:
    services.kernel.clock.advance(seconds)  # type: ignore[attr-defined]
