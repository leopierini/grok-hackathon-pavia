"""Halt recognition stays off the writer path."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from patrol.ground.extensions.g04.implementation import JournalLimits
from patrol.ground.extensions.g04.writer import FaultWriter
from patrol.ground.kernel.build import build_kernel
from tests.ground.g04.support import event, journal_for


class Authority:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.event = threading.Event()

    def latch_cancel(self, reason: str) -> None:
        self.calls.append(reason)
        self.event.set()

    def require_current(self, ticket: object) -> None:
        self.calls.append(f"require:{ticket}")


def test_halt_latch_is_independent_of_a_blocked_write(tmp_path: Path) -> None:
    asyncio.run(_halt(tmp_path))


async def _halt(tmp_path: Path) -> None:
    gate = threading.Event()
    gate.set()
    writer = FaultWriter(gate=gate)
    authority = Authority()
    journal, _clock, _peers = journal_for(
        writer=writer,
        limits=JournalLimits(max_queue=2, flush_timeout_s=5, close_timeout_s=0.2),
        authority=authority,
    )
    flush_task: asyncio.Task[object] | None = None
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        gate.clear()
        assert journal.emit(event("incident_accepted")).ok is True
        assert journal.emit(event("state_changed", state="ROUTE")).ok is True
        saturated = journal.emit(event("halt_requested", state="HALT"))
        assert saturated.fault_code == "queue_full"
        flush_task = asyncio.create_task(journal.flush())
        assert await asyncio.to_thread(writer.entered.wait, 2) is True
        started = time.perf_counter()
        authority.latch_cancel("operator_halt")
        latch_s = time.perf_counter() - started
        emit_started = time.perf_counter()
        while_blocked = journal.emit(event("mission_finished", state="HALT"))
        emit_s = time.perf_counter() - emit_started
        assert authority.event.is_set()
        assert authority.calls == ["operator_halt"]
        assert latch_s < 0.5
        assert emit_s < 0.5
        assert while_blocked.fault_code == "queue_full"
        assert flush_task.done() is False
    finally:
        writer.gate.set()
        if flush_task is not None:
            await flush_task
        await journal.close()
    assert authority.calls == ["operator_halt"]
    assert _kernel_accepts(authority)


def _kernel_accepts(authority: Authority) -> bool:
    kernel = build_kernel(clock_mode="manual", seed=0, mode="simulation")
    kernel.authority = authority  # type: ignore[assignment]
    return kernel.authority is authority
