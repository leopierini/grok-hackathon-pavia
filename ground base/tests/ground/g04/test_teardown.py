"""Writer teardown reports pending work and joins the thread."""

from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path

from patrol.ground.extensions.g04.implementation import JournalLimits
from patrol.ground.extensions.g04.writer import FaultWriter
from tests.ground.g04.support import event, journal_for, summary


def test_normal_close_reports_saved_events(tmp_path: Path) -> None:
    asyncio.run(_normal(tmp_path))


def test_stalled_close_stays_pending_until_the_writer_joins(tmp_path: Path) -> None:
    asyncio.run(_stalled(tmp_path))


def test_writer_exception_does_not_leak_a_secret_or_a_thread(tmp_path: Path) -> None:
    asyncio.run(_boom(tmp_path))


def test_source_does_not_request_halt_or_devices() -> None:
    root = Path("patrol/ground/extensions/g04")
    owned = (root / "implementation.py", root / "writer.py")
    forbidden_calls = {"halt", "land", "latch_cancel", "assess_incident", "run_route"}
    forbidden_modules = {
        "socket",
        "urllib",
        "requests",
        "patrol.dog",
        "patrol.drone",
        "patrol.grok",
    }
    for path in owned:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                assert module not in forbidden_modules
                assert module.split(".", 1)[0] not in forbidden_modules


async def _normal(tmp_path: Path) -> None:
    journal, _clock, _peers = journal_for()
    assert (await journal.open("run-1", tmp_path)).ok is True
    assert journal.emit(event("incident_accepted")).ok is True
    assert (await journal.flush()).durability == "synced"
    assert (await journal.publish(summary())).published is True
    closed = await journal.close()
    assert closed.ok is True
    assert closed.saved is True
    assert closed.pending is False
    assert closed.published is True
    again = await journal.close()
    assert again.saved is True
    assert _journal_threads() == []


async def _stalled(tmp_path: Path) -> None:
    gate = threading.Event()
    gate.set()
    writer = FaultWriter(gate=gate)
    journal, _clock, _peers = journal_for(
        writer=writer,
        limits=JournalLimits(flush_timeout_s=5, close_timeout_s=0.2),
    )
    flush_task: asyncio.Task[object] | None = None
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        gate.clear()
        assert journal.emit(event("incident_accepted")).ok is True
        flush_task = asyncio.create_task(journal.flush())
        assert await asyncio.to_thread(writer.entered.wait, 2) is True
        pending = await journal.close()
        assert pending.pending is True
        assert pending.saved is False
        assert pending.durability == "pending"
        assert _journal_threads()
    finally:
        writer.gate.set()
        if flush_task is not None:
            await flush_task
        closed = await journal.close()
    assert closed.pending is False
    assert closed.saved is True
    assert _journal_threads() == []


async def _boom(tmp_path: Path) -> None:
    secret = "sk-live-secret"
    writer = FaultWriter()
    journal, _clock, _peers = journal_for(writer=writer)
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        writer.fail = "boom"
        assert journal.emit(event("incident_accepted")).ok is True
        failed = await journal.flush()
        rendered = str(failed.as_dict())
        assert failed.fault_code == "writer_error"
        assert secret not in rendered
        assert secret not in failed.detail
    finally:
        await journal.close()
    assert _journal_threads() == []


def _journal_threads() -> list[str]:
    return [item.name for item in threading.enumerate() if item.name.startswith("ground-journal-")]
