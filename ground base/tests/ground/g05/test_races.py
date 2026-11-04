"""Same-turn halt and deadline races."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.contract import RunContext
from patrol.ground.kernel.contracts import Ticket
from tests.ground.g05.helpers import make_executor


def test_same_turn_halt_rejects_a_returned_value(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        barriers = services.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        executor.bind_mission("mission", 30)
        ticket = services.kernel.authority.issue("mission", "route")

        async def factory(_context: RunContext) -> str:
            entered.set()
            await barriers.wait("hold")
            return "value"

        run_task = asyncio.create_task(executor.run("dog.run_route", ticket, factory, limit_s=10))
        await entered.wait()

        def both() -> None:
            barriers.release("hold")
            services.kernel.authority.latch_cancel("halt")

        asyncio.get_running_loop().call_soon(both)
        result = await run_task
        assert result.status == "cancelled"
        assert result.error is not None
        assert executor.authorizes_next(result) is False
        assert services.kernel.tasks.pending() == ()

    asyncio.run(body())


def test_halt_after_completion_blocks_the_next_factory(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        barriers = services.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        executor.bind_mission("mission", 30)
        ticket = services.kernel.authority.issue("mission", "route")

        async def factory(_context: RunContext) -> str:
            entered.set()
            await barriers.wait("hold")
            return "arrived"

        run_task = asyncio.create_task(executor.run("dog.run_route", ticket, factory, limit_s=10))
        await entered.wait()
        barriers.release("hold")
        result = await run_task
        assert result.status == "completed"
        services.kernel.authority.latch_cancel("halt")

        async def again(_context: RunContext) -> str:
            return "again"

        follow = await executor.run("dog.run_route", ticket, again, limit_s=10)
        assert follow.status == "cancelled"
        assert executor.factory_calls == ["dog.run_route"]
        assert executor.authorizes_next(result) is False

    asyncio.run(body())


def test_halt_before_release_keeps_the_late_value(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        barriers = services.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        executor.bind_mission("mission", 30)
        ticket = services.kernel.authority.issue("mission", "route")

        async def factory(_context: RunContext) -> str:
            entered.set()
            try:
                await barriers.wait("hold")
            except asyncio.CancelledError:
                return "late"
            return "early"

        run_task = asyncio.create_task(executor.run("dog.run_route", ticket, factory, limit_s=10))
        await entered.wait()
        services.kernel.authority.latch_cancel("halt")
        result = await run_task
        assert result.status == "cancelled"
        assert result.value == "late"
        assert executor.authorizes_next(result) is False
        assert executor.history[0].status == "cancelled"

    asyncio.run(body())


def test_exact_deadline_is_timeout(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        clock = services.kernel.clock
        entered = asyncio.Event()
        executor.bind_mission("mission", 5)
        ticket = services.kernel.authority.issue("mission", "model")
        seen: dict[str, float] = {}

        async def factory(context: RunContext) -> str:
            entered.set()
            seen["deadline"] = context.deadline_monotonic
            await clock.sleep(context.deadline_monotonic - clock.monotonic())
            return "edge"

        run_task = asyncio.create_task(
            executor.run("reasoner.assess_incident", ticket, factory, limit_s=5)
        )
        await entered.wait()
        clock.advance(5)  # type: ignore[attr-defined]
        result = await run_task
        assert seen["deadline"] == 5
        assert result.status == "timeout"
        assert result.error is not None
        assert result.error.code == "timeout"
        assert executor.authorizes_next(result) is False

    asyncio.run(body())


def test_stale_ticket_after_reset_does_not_start(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        ticket: Ticket = services.kernel.authority.issue("mission", "route")
        services.kernel.authority.reset_generation("recovered")
        result = await executor.run("dog.run_route", ticket, _boom, limit_s=5)
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "stale_ticket"
        assert executor.factory_calls == []

    asyncio.run(body())


async def _boom(_context: RunContext) -> str:
    raise AssertionError("stale ticket invoked the factory")
