"""Manual waits stay on the manual clock. Real adapters use time.monotonic."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from patrol.ground.kernel import GroundFault, ManualClock, RealClock, context_for_stage
from patrol.ground.kernel.authority import SessionAuthority


def test_manual_sleep_waits_for_advance_not_wall_time() -> None:
    async def body() -> None:
        clock = ManualClock()
        started = time.monotonic()
        task = asyncio.create_task(clock.sleep(30))
        await asyncio.sleep(0)
        _done, pending = await asyncio.wait({task}, timeout=0.05)
        assert task in pending
        assert time.monotonic() - started < 1
        clock.advance(30)
        await task
        assert clock.monotonic() == 30
        assert time.monotonic() - started < 1

    asyncio.run(body())


def test_real_clock_sleep_uses_wall_time() -> None:
    async def body() -> None:
        clock = RealClock()
        started = time.monotonic()
        await clock.sleep(0.05)
        assert time.monotonic() - started >= 0.04
        assert clock.is_manual() is False

    asyncio.run(body())


def test_manual_clock_cannot_arm_a_real_adapter() -> None:
    manual = ManualClock()
    with pytest.raises(GroundFault) as caught:
        context_for_stage(
            "mission",
            100,
            1,
            threading.Event(),
            manual,
            real_adapter=True,
        )
    assert caught.value.error.code == "invalid_input"
    real = RealClock()
    context = context_for_stage(
        "mission",
        time.monotonic() + 30,
        5,
        threading.Event(),
        real,
        real_adapter=True,
    )
    assert context.deadline_monotonic <= time.monotonic() + 5.1


def test_manual_deadline_is_not_compared_with_time_monotonic() -> None:
    clock = ManualClock()
    authority = SessionAuthority()
    ticket = authority.issue("mission", "stage")
    deadline = clock.monotonic() + 5
    assert time.monotonic() > deadline
    authority.require_action(ticket, deadline_monotonic=deadline, clock=clock)
