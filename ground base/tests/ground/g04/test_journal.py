"""Ordered JSONL, sequence assignment, and queue limits."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from patrol.ground.extensions.g04.implementation import QUEUE_POLICY, JournalLimits
from tests.ground.g04.support import event, journal_for, summary


def test_create_does_not_start_a_writer_or_touch_disk(tmp_path: Path) -> None:
    before = _journal_threads()
    journal, _clock, _peers = journal_for()
    assert _journal_threads() == before
    assert list(tmp_path.iterdir()) == []
    rejected = journal.emit(event("incident_accepted"))
    assert rejected.ok is False
    assert rejected.fault_code == "not_open"
    assert rejected.durability == "failed"


def test_ordered_jsonl_and_summary_null_arrival(tmp_path: Path) -> None:
    asyncio.run(_ordered(tmp_path))


def test_queue_rejects_new_events_without_dropping_old_ones(tmp_path: Path) -> None:
    asyncio.run(_queue(tmp_path))


def test_oversized_event_is_rejected(tmp_path: Path) -> None:
    asyncio.run(_oversized(tmp_path))


def test_sequence_is_assigned_or_retained(tmp_path: Path) -> None:
    asyncio.run(_sequence(tmp_path))


def test_concurrent_emits_keep_a_gap_free_sequence(tmp_path: Path) -> None:
    asyncio.run(_concurrent(tmp_path))


async def _ordered(tmp_path: Path) -> None:
    journal, clock, _peers = journal_for()
    try:
        opened = await journal.open("run-1", tmp_path)
        assert opened.ok is True
        assert opened.durability == "queued"
        assert (tmp_path / "run-1" / "dog").is_dir()
        first = journal.emit(event("incident_accepted"))
        clock.advance(1.5)
        second = journal.emit(event("state_changed", state="INSPECT"))
        assert first.seq == 1 and second.seq == 2
        assert first.durability == "queued"
        assert first.synced == 0
        flushed = await journal.flush()
        assert flushed.ok is True
        assert flushed.durability == "synced"
        assert flushed.flushed == 2
        assert flushed.synced == 2
        assert flushed.queued == 0
        published = await journal.publish(summary())
        assert published.ok is True
        assert published.durability == "published"
        assert published.published is True
        lines = _lines(tmp_path / "run-1" / "events.jsonl")
        assert [item["seq"] for item in lines] == [1, 2]
        assert [item["event"] for item in lines] == ["incident_accepted", "state_changed"]
        assert lines[1]["elapsed_s"] == 1.5
        assert str(lines[0]["timestamp_utc"]).endswith("Z")
        stored = json.loads((tmp_path / "run-1" / "summary.json").read_text(encoding="utf-8"))
        assert stored["time_to_arrival_s"] is None
        assert stored["arrival_confirmed"] is False
    finally:
        await journal.close()


async def _queue(tmp_path: Path) -> None:
    journal, _clock, _peers = journal_for(limits=JournalLimits(max_queue=2))
    try:
        assert await _open(journal, tmp_path)
        assert journal.emit(event("incident_accepted")).ok is True
        assert journal.emit(event("state_changed", state="ROUTE")).ok is True
        rejected = journal.emit(event("halt_requested", state="HALT"))
        assert rejected.ok is False
        assert rejected.fault_code == "queue_full"
        assert rejected.durability == "failed"
        assert QUEUE_POLICY == "reject-new"
        flushed = await journal.flush()
        assert flushed.synced == 2
        lines = _lines(tmp_path / "run-1" / "events.jsonl")
        assert [item["event"] for item in lines] == ["incident_accepted", "state_changed"]
    finally:
        await journal.close()


async def _oversized(tmp_path: Path) -> None:
    journal, _clock, _peers = journal_for(limits=JournalLimits(max_event_bytes=500))
    try:
        assert await _open(journal, tmp_path)
        huge = event("incident_accepted")
        huge["data"] = {"note": "x" * 400}
        rejected = journal.emit(huge)
        assert rejected.fault_code == "oversized"
        assert "xxxx" not in rejected.detail
        assert journal.emit(event("incident_accepted")).ok is True
        flushed = await journal.flush()
        assert flushed.synced == 1
    finally:
        await journal.close()


async def _sequence(tmp_path: Path) -> None:
    journal, _clock, _peers = journal_for()
    try:
        assert await _open(journal, tmp_path)
        kept = event("incident_accepted")
        kept["seq"] = 1
        assert journal.emit(kept).seq == 1
        skipped = event("state_changed", state="ROUTE")
        skipped["seq"] = 4
        assert journal.emit(skipped).fault_code == "sequence_conflict"
        assert journal.emit(event("state_changed", state="ROUTE")).seq == 2
        await journal.flush()
    finally:
        await journal.close()


async def _concurrent(tmp_path: Path) -> None:
    journal, _clock, _peers = journal_for()
    try:
        assert await _open(journal, tmp_path)
        errors: list[str] = []

        def send(index: int) -> None:
            result = journal.emit(event("incident_accepted", seed=index))
            if not result.ok:
                errors.append(result.fault_code or "failed")

        workers = [threading.Thread(target=send, args=(index,)) for index in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert errors == []
        flushed = await journal.flush()
        assert flushed.synced == 8
        lines = _lines(tmp_path / "run-1" / "events.jsonl")
        assert [item["seq"] for item in lines] == list(range(1, 9))
    finally:
        await journal.close()


async def _open(journal: object, root: Path) -> bool:
    opened = await journal.open("run-1", root)  # type: ignore[attr-defined]
    return bool(opened.ok)


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _journal_threads() -> list[str]:
    return [item.name for item in threading.enumerate() if item.name.startswith("ground-journal-")]
