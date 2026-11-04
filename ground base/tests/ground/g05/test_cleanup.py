"""Cleanup diagnostics stay separate from the primary timeout."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.contract import RunContext
from tests.ground.g05.helpers import make_executor


def test_cleanup_failure_preserves_the_primary_timeout(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        barriers = services.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        executor.bind_mission("mission", 5)
        ticket = services.kernel.authority.issue("mission", "inspect")

        async def factory(_context: RunContext) -> str:
            entered.set()
            await barriers.wait("hold")
            return "flew"

        run_task = asyncio.create_task(executor.run("drone.inspect", ticket, factory, limit_s=5))
        await entered.wait()
        services.kernel.clock.advance(5)  # type: ignore[attr-defined]
        primary = await run_task
        assert primary.status == "timeout"
        assert primary.error is not None
        assert primary.pending is False
        assert executor.factory_calls == ["drone.inspect"]

        async def cleanup(_context: RunContext) -> str:
            raise RuntimeError("disk full")

        returned = await executor.run_cleanup(primary, "journal.flush", cleanup, limit_s=2)
        assert returned is primary
        assert returned.error is primary.error
        assert returned.status == "timeout"
        assert executor.cleanup_errors[0].detail == "disk full"
        assert executor.cleanup_errors[0] is not primary.error
        assert executor.factory_calls == ["drone.inspect", "journal.flush"]
        assert services.safety.trace == []  # type: ignore[attr-defined]

    asyncio.run(body())


def test_recovery_uses_a_fresh_event_and_does_not_extend_the_mission(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        executor.bind_mission("mission", 30)
        frozen = executor.mission_deadline
        ticket = services.kernel.authority.issue("mission", "route")

        async def ordinary(context: RunContext) -> str:
            assert context.cancel is services.kernel.authority.cancel_event
            return "done"

        first = await executor.run("dog.run_route", ticket, ordinary, limit_s=5)
        assert first.status == "completed"
        services.kernel.authority.latch_cancel("halt")

        async def recovery(context: RunContext) -> str:
            assert context.cancel is not services.kernel.authority.cancel_event
            assert context.cancel.is_set() is False
            return "stopped"

        outcome = await executor.run_recovery("dog.halt", ticket, recovery, limit_s=3)
        assert outcome.status == "completed"
        assert outcome.value == "stopped"
        assert executor.mission_deadline == frozen

        async def again(_context: RunContext) -> str:
            return "walk"

        follow = await executor.run("dog.run_route", ticket, again, limit_s=5)
        assert follow.status == "cancelled"
        assert executor.factory_calls == ["dog.run_route", "dog.halt"]

    asyncio.run(body())
