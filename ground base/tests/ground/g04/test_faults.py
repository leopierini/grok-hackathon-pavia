"""Injected filesystem failures and secret handling."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g04.writer import FaultWriter
from tests.ground.g04.support import event, journal_for, summary


def test_disk_full_before_any_run_directory(tmp_path: Path) -> None:
    asyncio.run(_open_fault(tmp_path, "disk_full"))


def test_permission_failure_keeps_the_event_and_can_retry(tmp_path: Path) -> None:
    asyncio.run(_permission(tmp_path))


def test_closed_stream_is_a_visible_fault(tmp_path: Path) -> None:
    asyncio.run(_append_fault(tmp_path, "closed", "closed_stream"))


def test_sync_failure_is_not_claimed_as_durable(tmp_path: Path) -> None:
    asyncio.run(_sync(tmp_path))


def test_rename_failure_preserves_the_previous_summary(tmp_path: Path) -> None:
    asyncio.run(_rename(tmp_path))


def test_sanitizer_failure_does_not_echo_the_secret(tmp_path: Path) -> None:
    asyncio.run(_secret(tmp_path))


async def _open_fault(tmp_path: Path, fail: str) -> None:
    probe_calls: list[str] = []
    writer = FaultWriter(fail=fail)
    journal, _clock, peers = journal_for(writer=writer, peers=_peers(probe_calls))
    try:
        opened = await journal.open("run-1", tmp_path)
        assert opened.ok is False
        assert opened.fault_code == fail
        assert opened.durability == "failed"
        assert not (tmp_path / "run-1").exists()
        assert peers.dog is not None
        assert probe_calls == []
    finally:
        await journal.close()


async def _permission(tmp_path: Path) -> None:
    writer = FaultWriter()
    journal, _clock, _peers = journal_for(writer=writer)
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        writer.fail = "permission"
        assert journal.emit(event("incident_accepted")).ok is True
        failed = await journal.flush()
        assert failed.ok is False
        assert failed.fault_code == "permission"
        assert failed.synced == 0
        assert failed.flushed == 0
        assert (tmp_path / "run-1" / "events.jsonl").read_text(encoding="utf-8") == ""
        assert journal.emit(event("state_changed", state="ROUTE")).fault_code == "permission"
        writer.fail = None
        recovered = await journal.flush()
        assert recovered.ok is True
        assert recovered.durability == "synced"
        assert recovered.synced == 1
        lines = [
            json.loads(line)
            for line in (tmp_path / "run-1" / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        assert [item["event"] for item in lines] == ["incident_accepted"]
    finally:
        await journal.close()


async def _append_fault(tmp_path: Path, fail: str, code: str) -> None:
    writer = FaultWriter()
    journal, _clock, _peers = journal_for(writer=writer)
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        writer.fail = fail
        assert journal.emit(event("incident_accepted")).ok is True
        failed = await journal.flush()
        assert failed.fault_code == code
        assert failed.synced == 0
        assert (tmp_path / "run-1" / "events.jsonl").read_text(encoding="utf-8") == ""
    finally:
        await journal.close()


async def _sync(tmp_path: Path) -> None:
    writer = FaultWriter()
    journal, _clock, _peers = journal_for(writer=writer)
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        writer.fail = "sync"
        assert journal.emit(event("incident_accepted")).ok is True
        failed = await journal.flush()
        assert failed.fault_code == "sync"
        assert failed.flushed == 1
        assert failed.synced == 0
        assert failed.durability == "failed"
        text = (tmp_path / "run-1" / "events.jsonl").read_text(encoding="utf-8")
        assert text.count("incident_accepted") == 1
    finally:
        await journal.close()


async def _rename(tmp_path: Path) -> None:
    writer = FaultWriter()
    journal, _clock, _peers = journal_for(writer=writer)
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        first = await journal.publish(summary(error="route failed"))
        assert first.ok is True
        before = (tmp_path / "run-1" / "summary.json").read_bytes()
        writer.fail = "rename"
        second = await journal.publish(summary(error="cleanup failed"))
        assert second.ok is False
        assert second.fault_code == "rename"
        assert second.prior_preserved is True
        assert second.mission_error == "cleanup failed"
        assert second.writer_error == "rename"
        assert (tmp_path / "run-1" / "summary.json").read_bytes() == before
        stored = json.loads(before)
        assert stored["error"] == "route failed"
        assert stored["time_to_arrival_s"] is None
    finally:
        await journal.close()


async def _secret(tmp_path: Path) -> None:
    secret = "sk-live-secret"

    def explode(_record: Mapping[str, object]) -> Mapping[str, object]:
        raise RuntimeError(secret)

    def strip(record: Mapping[str, object]) -> Mapping[str, object]:
        data = dict(record["data"])  # type: ignore[arg-type]
        data.pop("api_key", None)
        updated = dict(record)
        updated["data"] = data
        return updated

    journal, _clock, _peers = journal_for(sanitizer=explode)
    try:
        assert (await journal.open("run-1", tmp_path)).ok is True
        body = event("incident_accepted")
        body["data"] = {"api_key": secret}
        failed = journal.emit(body)
        assert failed.fault_code == "sanitizer_failed"
        rendered = str(failed.as_dict())
        assert secret not in rendered
        assert secret not in failed.detail
    finally:
        await journal.close()

    cleaning, _clock, _peers = journal_for(sanitizer=strip)
    try:
        assert (await cleaning.open("run-2", tmp_path)).ok is True
        body = event("incident_accepted")
        body["data"] = {"api_key": secret, "seed": 1}
        assert cleaning.emit(body).ok is True
        assert (await cleaning.flush()).synced == 1
        text = (tmp_path / "run-2" / "events.jsonl").read_text(encoding="utf-8")
        assert secret not in text
        assert "api_key" not in text
    finally:
        await cleaning.close()


def _peers(calls: list[str]) -> object:
    from patrol.ground.extensions.g04.peers import ServicePorts
    from tests.ground.g04.support import Probe

    probe = Probe()
    probe.calls = calls
    return ServicePorts(dog=probe, drone=probe, reasoner=probe, safety=probe, workflow=probe)
