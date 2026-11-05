"""Ethernet probes and real vision calls must not freeze the operator loop."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

from patrol.ground.demo import Demo
from patrol.ground.operator.host import Host


def test_stalled_probe_leaves_the_event_loop_free(tmp_path: Path) -> None:
    async def body() -> float:
        host = Host(tmp_path)

        async def heartbeat() -> float:
            start = time.perf_counter()
            await asyncio.sleep(0.01)
            return time.perf_counter() - start

        pulse = asyncio.create_task(heartbeat())
        await asyncio.sleep(0)

        def slow_probe() -> dict[str, bool]:
            time.sleep(0.2)
            return {"reachable": False}

        with patch("patrol.ground.operator.host.probe_dog_ethernet", slow_probe):
            await host.act("probe", {}, None)
        return await pulse

    elapsed = asyncio.run(body())
    assert elapsed < 0.1


def test_real_vision_call_yields_to_the_loop() -> None:
    async def body() -> float:
        demo = Demo.__new__(Demo)
        demo.live_calls = 0
        demo._vision_busy = False
        demo.should_halt = None
        demo.reason = ""

        async def heartbeat() -> float:
            start = time.perf_counter()
            await asyncio.sleep(0.01)
            return time.perf_counter() - start

        pulse = asyncio.create_task(heartbeat())
        await asyncio.sleep(0)

        def slow_model(request: object) -> dict[str, str]:
            del request
            time.sleep(0.2)
            return {"kind": "vision.decision"}

        with patch("patrol.ground.signal.assess_frame", slow_model):
            decision = await demo._real_decision_async({"kind": "vision.request"})
        assert decision["kind"] == "vision.decision"
        return await pulse

    elapsed = asyncio.run(body())
    assert elapsed < 0.1
