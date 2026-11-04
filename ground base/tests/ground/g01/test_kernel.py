"""Epoch fencing, cancellation, and retained-task collection."""

from __future__ import annotations

import asyncio

import pytest
from patrol.contract import RunContext
from patrol.ground.kernel import GroundFault, SessionAuthority
from patrol.ground.kernel.build import build_kernel
from patrol.ground.kernel.commands import parse_command
from patrol.ground.testing.builders import build_test_services


def test_cancel_is_monotonic_and_blocks_new_actions() -> None:
    authority = SessionAuthority()
    ticket = authority.issue("mission", "stage")
    epoch = authority.epoch
    authority.latch_cancel("halt")
    assert authority.epoch == epoch + 1
    authority.latch_cancel("halt again")
    assert authority.epoch == epoch + 1
    with pytest.raises(GroundFault) as current:
        authority.require_current(ticket)
    assert current.value.error.code == "cancelled"
    with pytest.raises(GroundFault):
        authority.issue("mission", "next")
    reset_epoch = authority.reset_generation("recovered")
    assert reset_epoch != ticket.epoch
    with pytest.raises(GroundFault) as stale:
        authority.require_current(ticket)
    assert stale.value.error.code == "stale_ticket"
    fresh = authority.issue("mission", "next")
    authority.require_current(fresh)


def test_expired_deadline_fails_the_action_check() -> None:
    kernel = build_kernel(clock_mode="manual")
    clock = kernel.clock
    ticket = kernel.authority.issue("mission", "stage")
    deadline = clock.monotonic() + 2
    kernel.authority.require_action(ticket, deadline_monotonic=deadline, clock=clock)
    assert hasattr(clock, "advance")
    clock.advance(2)  # type: ignore[attr-defined]
    with pytest.raises(GroundFault) as caught:
        kernel.authority.require_action(ticket, deadline_monotonic=deadline, clock=clock)
    assert caught.value.error.code == "expired_deadline"


def test_retained_tasks_can_be_collected() -> None:
    async def body() -> None:
        kernel = build_kernel()

        async def sleeper() -> None:
            await asyncio.sleep(30)

        task = asyncio.create_task(sleeper())
        kernel.tasks.retain("sleeper", task)
        assert kernel.tasks.pending() == ("sleeper",)
        kernel.tasks.cancel_pending()  # type: ignore[attr-defined]
        await kernel.tasks.collect(deadline=2)
        assert kernel.tasks.pending() == ()

    asyncio.run(body())


def test_executor_does_not_call_factory_after_cancel(tmp_path: object) -> None:
    async def body() -> None:
        services = build_test_services(output_dir=tmp_path)  # type: ignore[arg-type]
        called: list[RunContext] = []

        async def factory(context: RunContext) -> str:
            called.append(context)
            return "ran"

        ticket = services.kernel.authority.issue("mission", "route")
        services.kernel.authority.latch_cancel("halt")
        result = await services.executor.run("dog.run_route", ticket, factory, limit_s=5)
        assert result.status == "cancelled"
        assert called == []

    asyncio.run(body())


def test_recovery_string_is_rejected_and_commands_are_exact(tmp_path: object) -> None:
    async def body() -> None:
        services = build_test_services(output_dir=tmp_path)  # type: ignore[arg-type]
        with pytest.raises(GroundFault):
            await services.safety.reset({"verified": "true"})
        await services.safety.reset({"verified": True})

    asyncio.run(body())
    arrived = parse_command("arrived room_2")
    assert arrived.name == "arrived"
    assert arrived.args == ("room_2",)
    with pytest.raises(GroundFault):
        parse_command("arrived lobby")
    with pytest.raises(GroundFault):
        parse_command("fly now")
