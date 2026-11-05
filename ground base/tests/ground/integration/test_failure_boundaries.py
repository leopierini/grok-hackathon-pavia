"""Exercise public fault paths that a successful mission cannot reach."""

from __future__ import annotations

import asyncio
import errno
import importlib
from dataclasses import replace
from pathlib import Path

import pytest
from patrol.contract import Frame, Incident
from patrol.ground.extensions.g02.loading import redacted_view
from patrol.ground.extensions.g04.writer import DiskWriter, WriterFault
from patrol.ground.extensions.g06.clock import ManualClock as EvidenceClock
from patrol.ground.extensions.g06.images import materialize_fixtures
from patrol.ground.extensions.g06.io import CountingIO, RealIO
from patrol.ground.kernel.contracts import GroundEvent, Ticket
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.snapshots import idle_snapshot

reduce_event = importlib.import_module("patrol.ground.extensions.g03.reduce").reduce_event


@pytest.mark.parametrize(
    "event,payload,phase,expected",
    [
        ("frame_rejected", {}, "GROUND_VIEW", "REPORT"),
        ("stop_result", {"stopped": None}, "MOVE_DOG", "FAULT"),
        ("stop_result", {"stopped": False}, "MOVE_DOG", "FAULT"),
        ("stop_result", {"stopped": True}, "ABORTED", "ABORTED"),
        ("recovery_required", {}, "INSPECT", "FAULT"),
        ("persistence_fault", {}, "MOVE_DOG", "FAULT"),
        ("mission_finished", {}, "DONE", "DONE"),
    ],
)
def test_reducer_faults_preserve_latches_and_reject_ordinary_resume(
    event: str,
    payload: dict[str, object],
    phase: str,
    expected: str,
) -> None:
    incident = Incident(
        "fault-test", "display", "target", Frame("/synthetic.jpg", "phone", "display", None, True)
    )
    before = idle_snapshot(
        epoch=1,
        modes={"dog": "fake", "drone": "fake", "grok": "fake"},
        dog_transport="ethernet",
        incident=incident,
        phase=phase,
    )
    ticket = Ticket("fault-test", 1, "fault-path")
    after = reduce_event(before, GroundEvent(event, ticket, payload), ticket)
    assert after.phase == expected
    assert before.phase == phase
    if expected == "FAULT":
        assert after.recovery_required and after.halt_latched
        with pytest.raises(GroundFault):
            reduce_event(
                after,
                GroundEvent("operation_started", ticket, {"operation": "dog.run_route"}),
                ticket,
            )
    if event == "mission_finished":
        assert after.decisions["finished"] is True
        with pytest.raises(GroundFault):
            reduce_event(after, GroundEvent(event, ticket, payload), ticket)


def test_configuration_journal_view_redacts_and_detects_allowlisted_leaks() -> None:
    secret = "synthetic-secret-value-123"
    settings = make_settings(adapter_configs={"grok": {"api_key": secret}})
    assert secret not in str(redacted_view(settings))
    contaminated = replace(settings, output_root=secret)
    with pytest.raises(GroundFault):
        redacted_view(contaminated)


@pytest.mark.parametrize(
    "problem,expected",
    [
        (PermissionError(errno.EACCES, "denied"), "permission"),
        (OSError(errno.ENOSPC, "full"), "disk_full"),
        (OSError("closed stream"), "closed_stream"),
        (OSError(errno.EIO, "unavailable"), "io_error"),
    ],
)
def test_real_writer_translates_os_failures_without_exposing_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    problem: OSError,
    expected: str,
) -> None:
    path = tmp_path / "events.jsonl"

    def deny(*args: object, **kwargs: object) -> None:
        raise problem

    monkeypatch.setattr(Path, "open", deny)
    with pytest.raises(WriterFault) as error:
        DiskWriter().append_lines(path, "synthetic sensitive payload")
    assert error.value.code == expected
    assert error.value.wrote is False
    assert "sensitive" not in str(error.value)


def test_fixture_generation_counted_read_and_logical_clock(tmp_path: Path) -> None:
    async def run() -> None:
        materialize_fixtures(tmp_path)
        reader = CountingIO()
        image = await reader.read(tmp_path / "phone.jpg", max_bytes=4096)
        assert reader.reads == 1
        assert await RealIO().decode_jpeg(image, max_pixels=100) == (8, 8)
        assert (tmp_path / "empty.jpg").read_bytes() == b""
        clock = EvidenceClock()
        before = clock.utc_now()
        await clock.sleep(2)
        assert clock.monotonic() == 2
        assert (clock.utc_now() - before).total_seconds() == 2

    asyncio.run(run())
