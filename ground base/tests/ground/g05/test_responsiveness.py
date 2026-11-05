"""Wall-clock halt recognition stays separate from virtual deadlines."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from patrol.contract import RunContext
from tests.ground.g05.helpers import make_executor


def test_halt_is_observed_within_half_a_second(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path, clock_mode="real")
        assert services.kernel.clock.is_manual() is False
        entered = asyncio.Event()
        executor.bind_mission("mission", 30)
        ticket = services.kernel.authority.issue("mission", "model")

        async def factory(context: RunContext) -> str:
            entered.set()
            while not context.cancel.is_set():
                await asyncio.sleep(0.01)
            return "late"

        run_task = asyncio.create_task(
            executor.run("reasoner.assess_incident", ticket, factory, limit_s=10)
        )
        await entered.wait()
        await asyncio.sleep(0.02)
        started = time.monotonic()
        services.kernel.authority.latch_cancel("halt")
        result = await asyncio.wait_for(run_task, timeout=0.5)
        elapsed = time.monotonic() - started
        assert elapsed < 0.5
        assert result.status == "cancelled"
        assert executor.authorizes_next(result) is False

    asyncio.run(body())


def test_console_pulse_runs_while_a_route_is_held(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        barriers = services.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        pulses = 0
        stop = asyncio.Event()
        executor.bind_mission("mission", 30)
        ticket = services.kernel.authority.issue("mission", "route")

        async def pulse() -> None:
            nonlocal pulses
            while not stop.is_set():
                pulses += 1
                await asyncio.sleep(0)

        async def factory(_context: RunContext) -> str:
            entered.set()
            await barriers.wait("hold")
            return "moved"

        pulse_task = asyncio.create_task(pulse(), name="console-pulse")
        try:
            run_task = asyncio.create_task(
                executor.run("dog.run_route", ticket, factory, limit_s=10)
            )
            await entered.wait()
            await asyncio.sleep(0)
            assert pulses >= 1
            barriers.release("hold")
            result = await run_task
        finally:
            stop.set()
            await pulse_task
        assert result.status == "completed"
        assert executor.authorizes_next(result) is True

    asyncio.run(body())
