"""Ticket, cancellation, and generation fences."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g08.helpers import open_gateway, permit, run


def test_cancelled_and_mismatched_context_do_not_call(tmp_path: Path) -> None:
    async def body() -> None:
        kernel, bundle, gateway = await open_gateway(tmp_path)
        ticket, context = permit(kernel, "guard")
        context.cancel.set()
        with pytest.raises(GroundFault) as cancelled:
            await gateway.invoke(
                "dog",
                "prepare",
                (context,),
                ticket=ticket,
                context=context,
            )
        assert cancelled.value.error.code == "cancelled"
        assert "dog.prepare" not in bundle.log
        other = context_for_stage(
            "guard",
            kernel.clock.monotonic() + 100,
            30,
            kernel.authority.cancel_event,
            kernel.clock,
            real_adapter=False,
        )
        fresh, fresh_context = permit(kernel, "guard-fresh")
        with pytest.raises(GroundFault) as mismatch:
            await gateway.invoke(
                "dog",
                "prepare",
                (other,),
                ticket=fresh,
                context=fresh_context,
            )
        assert mismatch.value.error.code == "invalid_input"
        assert "dog.prepare" not in bundle.log
        await gateway.close()

    run(body)


def test_stale_epoch_blocks_the_second_operation(tmp_path: Path) -> None:
    async def body() -> None:
        kernel, bundle, gateway = await open_gateway(tmp_path)
        bundle.dog.hold = "dog.run_route"
        kernel.barriers.arm("dog.run_route")
        ticket, context = permit(kernel, "stale")
        first = asyncio.create_task(
            gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        )
        for _ in range(30):
            await asyncio.sleep(0)
            if "dog.run_route" in bundle.log:
                break
        kernel.authority.latch_cancel("halt")
        with pytest.raises(GroundFault) as second:
            await gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        assert second.value.error.code == "cancelled"
        assert bundle.log.count("dog.run_route") == 1
        kernel.barriers.release("dog.run_route")
        await first
        await gateway.invoke("dog", "halt", (), ticket=ticket, context=context)
        assert bundle.log[-1] == "dog.halt"
        await gateway.close()

    run(body)


def test_late_generation_cannot_publish(tmp_path: Path) -> None:
    async def body() -> None:
        kernel, bundle, gateway = await open_gateway(tmp_path)
        bundle.dog.hold = "late-route"
        kernel.barriers.arm("late-route")
        ticket, context = permit(kernel, "late")
        first = asyncio.create_task(
            gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        )
        for _ in range(30):
            await asyncio.sleep(0)
            if "dog.run_route" in bundle.log:
                break
        with pytest.raises(GroundFault):
            await gateway.close()
        kernel.barriers.release("late-route")
        with pytest.raises(GroundFault) as late:
            await first
        assert late.value.error.code == "epoch_mismatch"
        assert gateway.last_invoke is None
        assert "route" not in gateway.published
        await gateway.close()

    run(body)
