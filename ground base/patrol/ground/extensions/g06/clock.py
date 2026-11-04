"""Logical clock for evidence checks.

``sleep`` moves this clock. It does not wait on the wall clock, and it is not
the kernel clock used for device deadlines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class ManualClock:
    monotonic_s: float = 0.0
    utc: datetime = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.monotonic_s

    def utc_now(self) -> datetime:
        return self.utc

    def advance(self, seconds: float) -> None:
        self.monotonic_s += seconds
        self.utc = self.utc + timedelta(seconds=seconds)

    async def sleep(self, seconds: float) -> None:
        self.advance(seconds)
