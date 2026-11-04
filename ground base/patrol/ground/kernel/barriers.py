"""Named barriers. Tests hold an operation until they release the name."""

from __future__ import annotations

import asyncio

from patrol.ground.kernel.faults import fault


class BarrierSet:
    def __init__(self) -> None:
        self._armed: set[str] = set()
        self._waiters: dict[str, list[asyncio.Future[None]]] = {}

    def arm(self, name: str) -> None:
        self._check_name(name)
        self._armed.add(name)

    def armed(self, name: str) -> bool:
        return name in self._armed

    def release(self, name: str) -> None:
        self._check_name(name)
        self._armed.discard(name)
        for waiter in self._waiters.pop(name, []):
            if not waiter.done():
                waiter.set_result(None)

    def release_all(self) -> None:
        for name in list(self._armed):
            self.release(name)
        for name in list(self._waiters):
            self.release(name)

    async def wait(self, name: str) -> None:
        self._check_name(name)
        if name not in self._armed:
            return
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[None] = loop.create_future()
        self._waiters.setdefault(name, []).append(waiter)
        try:
            await waiter
        except asyncio.CancelledError:
            waiting = self._waiters.get(name, [])
            self._waiters[name] = [item for item in waiting if item is not waiter]
            raise

    def _check_name(self, name: str) -> None:
        if not isinstance(name, str) or not name:
            raise fault("invalid_input", "barrier name is required")
