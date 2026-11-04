"""Read-only detection of incomplete artifacts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g04.peers import ServicePorts
from tests.ground.g04.support import FIXTURES, IdleIO, Probe, journal_for


def test_partial_tail_and_corrupt_summary_are_incomplete(tmp_path: Path) -> None:
    asyncio.run(_scan(tmp_path))


def test_valid_summary_does_not_repair_a_partial_tail(tmp_path: Path) -> None:
    asyncio.run(_partial_with_summary(tmp_path))


async def _scan(tmp_path: Path) -> None:
    probe = Probe()
    interrupted = tmp_path / "interrupted"
    interrupted.mkdir()
    (interrupted / "events.jsonl").write_bytes((FIXTURES / "truncated-events.jsonl").read_bytes())
    corrupt = tmp_path / "corrupt-summary"
    corrupt.mkdir()
    (corrupt / "events.jsonl").write_text(
        '{"event":"incident_accepted","seq":1}\n', encoding="utf-8", newline="\n"
    )
    (corrupt / "summary.json").write_bytes((FIXTURES / "corrupt-summary.json").read_bytes())
    journal, _clock, _peers = journal_for(
        peers=ServicePorts(dog=probe, drone=probe, reasoner=probe)
    )
    try:
        found = await journal.scan(tmp_path)
        mirrored = await journal.read(tmp_path)
        assert found.ok is True
        assert found.durability == "scanned"
        assert mirrored.scan == found.scan
        rows = {str(item["run_id"]): item for item in found.scan}
        partial = rows["interrupted"]
        assert partial["partial_tail"] is True
        assert partial["incomplete"] is True
        assert partial["complete_events"] == 1
        assert partial["summary_present"] is False
        assert "truncated final line" in partial["diagnostics"]
        broken = rows["corrupt-summary"]
        assert broken["summary_present"] is True
        assert broken["summary_valid"] is False
        assert broken["incomplete"] is True
        assert "corrupt summary" in broken["diagnostics"]
        assert probe.calls == []
    finally:
        await journal.close()


async def _partial_with_summary(tmp_path: Path) -> None:
    run = tmp_path / "run-1"
    run.mkdir()
    (run / "events.jsonl").write_bytes((FIXTURES / "truncated-events.jsonl").read_bytes())
    (run / "summary.json").write_text(
        json.dumps({"mission_id": "fixture", "time_to_arrival_s": None}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    journal, _clock, _peers = journal_for()
    try:
        found = await journal.scan(tmp_path)
        row = found.scan[0]
        assert row["summary_valid"] is True
        assert row["partial_tail"] is True
        assert row["incomplete"] is True
        assert row["complete_events"] == 1
        assert IdleIO is not None
    finally:
        await journal.close()
