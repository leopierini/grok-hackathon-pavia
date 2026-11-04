"""Unique run directories."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from tests.ground.g04.support import event, journal_for


def test_two_run_ids_do_not_share_a_directory(tmp_path: Path) -> None:
    asyncio.run(_two_runs(tmp_path))


def test_existing_directory_is_not_reused(tmp_path: Path) -> None:
    asyncio.run(_reuse(tmp_path))


def test_second_process_cannot_create_the_same_run(tmp_path: Path) -> None:
    asyncio.run(_process(tmp_path))


def test_unsafe_run_ids_are_rejected(tmp_path: Path) -> None:
    asyncio.run(_unsafe(tmp_path))


async def _two_runs(tmp_path: Path) -> None:
    first, _clock, _peers = journal_for()
    second, _clock, _peers = journal_for()
    try:
        assert (await first.open("run-a", tmp_path)).ok is True
        assert (await second.open("run-b", tmp_path)).ok is True
        assert first.emit(event("incident_accepted", mission="run-a")).ok is True
        await first.flush()
        assert (tmp_path / "run-b" / "events.jsonl").read_text(encoding="utf-8") == ""
        assert "incident_accepted" in (tmp_path / "run-a" / "events.jsonl").read_text(
            encoding="utf-8"
        )
    finally:
        await first.close()
        await second.close()


async def _reuse(tmp_path: Path) -> None:
    first, _clock, _peers = journal_for()
    second, _clock, _peers = journal_for()
    try:
        assert (await first.open("run-1", tmp_path)).ok is True
        assert first.emit(event("incident_accepted")).ok is True
        await first.flush()
        before = (tmp_path / "run-1" / "events.jsonl").read_bytes()
        again = await second.open("run-1", tmp_path)
        assert again.ok is False
        assert again.fault_code == "run_exists"
        assert (tmp_path / "run-1" / "events.jsonl").read_bytes() == before
        repeat = await first.open("run-1", tmp_path)
        assert repeat.fault_code == "already_open"
    finally:
        await first.close()
        await second.close()


async def _process(tmp_path: Path) -> None:
    journal, _clock, _peers = journal_for()
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        completed = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).mkdir()",
                str(tmp_path / "run-1"),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode != 0
    finally:
        await journal.close()


async def _unsafe(tmp_path: Path) -> None:
    journal, _clock, _peers = journal_for()
    try:
        for run_id in ("../escape", "a/b", "..", "", "run id"):
            result = await journal.open(run_id, tmp_path)
            assert result.ok is False
            assert result.fault_code == "invalid_run_id"
        missing = tmp_path / "missing"
        assert (await journal.open("run-1", missing)).fault_code == "invalid_output_root"
        assert list(tmp_path.iterdir()) == []
    finally:
        await journal.close()
