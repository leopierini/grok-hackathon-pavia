"""Real and manual clocks. Manual waits advance only when tests move the clock."""

from __future__ import annotations

import asyncio
import math
import time
from datetime import UTC, datetime, timedelta

from patrol.ground.kernel.faults import fault


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def utc_now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        _require_delay(seconds)
        await asyncio.sleep(seconds)

    def is_manual(self) -> bool:
        return False


class ManualClock:
    def __init__(self) -> None:
        self._mono = 0.0
        self._utc = datetime(2026, 1, 1, tzinfo=UTC)
        self._waiters: list[tuple[float, asyncio.Future[None]]] = []

    def monotonic(self) -> float:
        return self._mono

    def utc_now(self) -> datetime:
        return self._utc

    def is_manual(self) -> bool:
        return True

    def advance(self, seconds: float) -> None:
        _require_delay(seconds)
        if seconds == 0:
            return
        self._mono += seconds
        self._utc += timedelta(seconds=seconds)
        ready: list[asyncio.Future[None]] = []
        waiting: list[tuple[float, asyncio.Future[None]]] = []
        for target, waiter in self._waiters:
            if target <= self._mono and not waiter.done():
                ready.append(waiter)
            else:
                waiting.append((target, waiter))
        self._waiters = waiting
        for waiter in ready:
            waiter.set_result(None)

    async def sleep(self, seconds: float) -> None:
        _require_delay(seconds)
        if seconds == 0:
            await asyncio.sleep(0)
            return
        target = self._mono + seconds
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[None] = loop.create_future()
        self._waiters.append((target, waiter))
        try:
            await waiter
        except asyncio.CancelledError:
            self._waiters = [
                item for item in self._waiters if item[1] is not waiter
            ]
            raise


def _require_delay(seconds: float) -> None:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise fault("invalid_input", "delay must be a real number")
    if not math.isfinite(float(seconds)) or float(seconds) < 0:
        raise fault("invalid_input", "delay must be finite and non-negative")
