"""Mission budgets stay fixed and manual time does not use the wall clock."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from patrol.contract import RunContext
from tests.ground.g05.helpers import finished, make_executor, manual


def test_later_stage_cannot_extend_the_mission_deadline(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        clock = manual(services)
        assert executor.bind_mission("mission", 10) == 10
        clock.advance(4)
        seen: dict[str, float] = {}
        ticket = services.kernel.authority.issue("mission", "prepare")

        async def factory(context: RunContext) -> str:
            seen["deadline"] = context.deadline_monotonic
            assert context.cancel is services.kernel.authority.cancel_event
            return "ok"

        result = await executor.run("dog.prepare", ticket, factory, limit_s=30)
        assert result.status == "completed"
        assert seen["deadline"] == 10
        assert executor.bind_mission("mission", 100) == 10
        assert executor.mission_deadline == 10

    asyncio.run(body())


def test_expired_mission_rejects_before_a_new_stage_limit(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        clock = manual(services)
        executor.bind_mission("mission", 5)
        clock.advance(5)
        ticket = services.kernel.authority.issue("mission", "route")
        result = await executor.run("dog.run_route", ticket, finished, limit_s=30)
        assert result.status == "timeout"
        assert result.error is not None
        assert result.error.code == "expired_deadline"
        assert executor.factory_calls == []

    asyncio.run(body())


def test_manual_deadline_does_not_sleep_on_the_wall_clock(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        clock = manual(services)
        entered = asyncio.Event()
        executor.bind_mission("mission", 30)
        ticket = services.kernel.authority.issue("mission", "route")

        async def factory(context: RunContext) -> str:
            entered.set()
            await clock.sleep(context.deadline_monotonic - clock.monotonic())
            return "late"

        started = time.monotonic()
        run_task = asyncio.create_task(executor.run("dog.run_route", ticket, factory, limit_s=30))
        await entered.wait()
        clock.advance(30)
        result = await run_task
        elapsed = time.monotonic() - started
        assert result.status == "timeout"
        assert elapsed < 0.5

    asyncio.run(body())
