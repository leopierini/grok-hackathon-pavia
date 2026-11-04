"""Strong references to stage tasks so teardown can see unfinished work."""

from __future__ import annotations

import asyncio

from patrol.ground.kernel.faults import fault


class RetainedTasks:
    def __init__(self) -> None:
        self._items: list[tuple[str, asyncio.Task[object]]] = []

    def retain(self, name: str, task: object) -> None:
        if not isinstance(name, str) or not name:
            raise fault("invalid_input", "task name is required")
        if not isinstance(task, asyncio.Task):
            raise fault("invalid_input", "retained work must be an asyncio.Task")
        self._items.append((name, task))

    def pending(self) -> tuple[str, ...]:
        return tuple(name for name, task in self._items if not task.done())

    def cancel_pending(self) -> None:
        for _name, task in self._items:
            if not task.done():
                task.cancel()

    async def collect(self, *, deadline: float) -> None:
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or deadline <= 0:
            raise fault("invalid_input", "collect deadline must be positive")
        pending = [task for _name, task in self._items if not task.done()]
        if not pending:
            return
        _done, not_done = await asyncio.wait(pending, timeout=float(deadline))
        if not_done:
            raise fault(
                "timeout",
                "retained task still pending",
                recovery_required=True,
            )
