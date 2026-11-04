"""Capture-time boundaries and phone provenance."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from pathlib import Path

from patrol.contract import Frame
from patrol.ground.extensions.g06.clock import ManualClock
from patrol.ground.extensions.g06.images import write_jpeg
from patrol.ground.extensions.g06.implementation import create
from patrol.ground.extensions.g06.io import RealIO
from patrol.ground.extensions.g06.model import (
    CaptureInterval,
    EvidenceLimits,
    KernelContext,
    ServicePorts,
)
from tests.ground.g06.support import NOW, live_frame, validate


def test_unknown_phone_time_is_not_replaced_by_copy_or_mtime(tmp_path: Path) -> None:
    original = tmp_path / "original.jpg"
    copied = tmp_path / "artifacts" / "copy.jpg"
    data = write_jpeg(original)
    copied.parent.mkdir()
    copied.write_bytes(data)
    os.utime(copied, (1_700_000_000, 1_700_000_000))
    frame = Frame(str(copied), "phone", "entrance", None, False)

    result = asyncio.run(validate(frame, root=tmp_path / "unused", interval=None))

    assert result.status == "accepted"
    assert result.frame is frame
    assert frame.captured_at is None
    assert result.provenance is not None
    assert result.provenance["time_origin"] == "unknown_phone"
    assert result.provenance["captured_at"] is None
    assert result.provenance["file_mtime_used"] is False
    assert result.identity is not None
    assert int(result.identity["mtime_ns"]) != 0


def test_naive_malformed_null_and_future_timestamps(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    path = root / "frame.jpg"
    write_jpeg(path)
    interval = CaptureInterval((NOW - timedelta(seconds=5)).isoformat(), NOW.isoformat())
    cases = {
        None: "null_timestamp",
        "2026-11-04T12:00:00": "naive_timestamp",
        "not-a-timestamp": "malformed_timestamp",
        " 2026-11-04T12:00:00Z": "malformed_timestamp",
        (NOW + timedelta(minutes=5)).isoformat(): "future_timestamp",
    }
    for stamp, expected in cases.items():
        frame = Frame(str(path), "dog", "room_2", stamp, False)
        result = asyncio.run(validate(frame, root=root, interval=interval))
        assert result.reason == expected
        assert frame.captured_at == stamp


def test_interval_edges_and_pre_request_buffer(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    start = NOW - timedelta(seconds=10)
    end = NOW
    interval = CaptureInterval(start.isoformat(), end.isoformat())
    accepted = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "now": NOW.isoformat(),
    }
    for name, stamp in accepted.items():
        frame, _ignored = live_frame(root, captured_at=stamp, name=f"{name}.jpg")
        result = asyncio.run(validate(frame, root=root, interval=interval))
        assert result.status == "accepted", name

    before = (start - timedelta(microseconds=1)).isoformat()
    stale, _ignored = live_frame(root, captured_at=before, name="stale.jpg")
    original = stale.captured_at
    rejected = asyncio.run(validate(stale, root=root, interval=interval))

    assert rejected.reason == "pre_request"
    assert stale.captured_at == original
    assert rejected.frame is None


def test_landing_delay_is_accepted_and_five_second_rule_is_not_applied(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    capture = NOW - timedelta(seconds=12)
    interval = CaptureInterval((NOW - timedelta(seconds=13)).isoformat(), NOW.isoformat())
    aerial, _ignored = live_frame(root, source="drone", captured_at=capture.isoformat())
    dog_capture = NOW - timedelta(seconds=6)
    dog_interval = CaptureInterval((NOW - timedelta(seconds=10)).isoformat(), NOW.isoformat())
    dog, _ignored = live_frame(root, captured_at=dog_capture.isoformat(), name="dog.jpg")

    aerial_result = asyncio.run(validate(aerial, root=root, interval=interval))
    dog_result = asyncio.run(validate(dog, root=root, interval=dog_interval))

    assert aerial_result.status == "accepted"
    assert aerial_result.provenance is not None
    assert aerial_result.provenance["age_s"] == 12.0
    assert dog_result.status == "accepted"
    assert dog_result.provenance is not None
    assert dog_result.provenance["age_s"] == 6.0
    assert dog_result.provenance["five_second_return_rule_applied"] is False
    assert dog_result.provenance["stream_selection_freshness"] == "not_claimed"


def test_zulu_phone_time_is_preserved_and_operation_interval_is_ignored(tmp_path: Path) -> None:
    phone = tmp_path / "phone.jpg"
    write_jpeg(phone)
    stamp = "2026-11-04T11:00:00Z"
    frame = Frame(str(phone), "phone", "display", stamp, False)
    # This interval does not contain 11:00Z. It must not reject a phone image.
    interval = CaptureInterval(NOW.isoformat(), (NOW + timedelta(seconds=1)).isoformat())

    result = asyncio.run(validate(frame, root=tmp_path / "adapter", interval=interval))

    assert result.status == "accepted"
    assert frame.captured_at == stamp
    assert result.provenance is not None
    assert result.provenance["phone_interval_ignored"] is True


def test_missing_inverted_and_naive_intervals_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    frame, _interval = live_frame(root)
    missing = asyncio.run(validate(frame, root=root, interval=None))
    inverted = asyncio.run(
        validate(
            frame,
            root=root,
            interval=CaptureInterval(NOW.isoformat(), (NOW - timedelta(seconds=5)).isoformat()),
        )
    )
    naive = asyncio.run(
        validate(
            frame,
            root=root,
            interval=CaptureInterval("2026-11-04T11:00:00", "2026-11-04T12:00:00"),
        )
    )

    assert missing.reason == "missing_interval"
    assert inverted.reason == "invalid_interval"
    assert naive.reason == "invalid_interval"


def test_a_backward_clock_jump_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    capture = NOW.isoformat()
    frame, interval = live_frame(root, captured_at=capture)
    clock = ManualClock(utc=NOW - timedelta(hours=3))
    kernel = KernelContext(clock=clock, io=RealIO(), limits=EvidenceLimits())
    port = create(kernel, ServicePorts())

    result = asyncio.run(
        port.validate(
            frame,
            expected_source="dog",
            zone="room_2",
            mode="real",
            output_root=root,
            interval=interval,
        )
    )

    assert result.reason == "future_timestamp"
    assert frame.captured_at == capture
