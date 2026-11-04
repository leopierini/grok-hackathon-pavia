"""JPEG integrity, size limits, and output-directory containment."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from patrol.contract import Frame
from patrol.ground.extensions.g06.faults import FaultIO
from patrol.ground.extensions.g06.images import jpeg_bytes, write_jpeg
from patrol.ground.extensions.g06.io import FileSnapshot
from patrol.ground.extensions.g06.model import CaptureInterval, EvidenceLimits
from tests.ground.g06.support import NOW, live_frame, validate


def test_readable_jpeg_inside_output_is_accepted(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    frame, interval = live_frame(root)

    result = asyncio.run(validate(frame, root=root, interval=interval))

    assert result.status == "accepted"
    assert result.frame is frame
    assert result.identity is not None
    assert result.identity["sha256"]
    assert result.identity["width"] == 8
    frame.path and Path(frame.path).unlink()


def test_empty_truncated_text_and_png_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    valid = jpeg_bytes()
    samples = {
        "empty.jpg": b"",
        "truncated.jpg": valid[: max(2, len(valid) // 2)],
        "note.jpg": b"this is not a jpeg\n",
        "png.jpg": b"\x89PNG\r\n\x1a\nnot-really",
    }
    reasons = {
        "empty.jpg": "empty_file",
        "truncated.jpg": "truncated_jpeg",
        "note.jpg": "not_jpeg",
        "png.jpg": "not_jpeg",
    }
    for name, payload in samples.items():
        path = root / name
        path.write_bytes(payload)
        frame, interval = _frame(path)
        result = asyncio.run(validate(frame, root=root, interval=interval))
        assert result.status == "rejected"
        assert result.reason == reasons[name]
        assert result.frame is None


def test_size_and_pixel_bounds_reject_without_a_fallback(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    path = root / "frame.jpg"
    data = write_jpeg(path)
    frame, interval = _frame(path)

    too_big = asyncio.run(
        validate(
            frame,
            root=root,
            interval=interval,
            limits=EvidenceLimits(max_bytes=len(data) - 1),
        )
    )
    too_many_pixels = asyncio.run(
        validate(frame, root=root, interval=interval, limits=EvidenceLimits(max_pixels=1))
    )

    assert too_big.reason == "oversized"
    assert too_many_pixels.reason == "oversized"
    assert too_big.frame is None and too_many_pixels.frame is None


def test_relative_outside_and_dot_paths_cannot_escape(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    outside = tmp_path / "outside.jpg"
    write_jpeg(outside)
    outside_frame, interval = _frame(outside)
    traversal, _interval = _frame(root / ".." / "outside.jpg")
    relative = Frame("photo.jpg", "dog", "room_2", interval.started_at, False)
    io = FaultIO()

    outside_result = asyncio.run(validate(outside_frame, root=root, interval=interval, io=io))
    traversal_result = asyncio.run(validate(traversal, root=root, interval=interval, io=io))
    relative_result = asyncio.run(validate(relative, root=root, interval=interval, io=io))

    assert outside_result.reason == "containment_escape"
    assert traversal_result.reason == "containment_escape"
    assert relative_result.reason == "relative_path"
    assert io.reads == 0


def test_injected_symlink_escape_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    secret = tmp_path / "secret.jpg"
    write_jpeg(secret)
    link = root / "link.jpg"
    frame, interval = _frame(link)
    io = FaultIO(
        snapshot=FileSnapshot(
            size=10,
            is_symlink=True,
            is_regular=False,
            resolved=secret.resolve(),
            mtime_ns=0,
        )
    )

    result = asyncio.run(validate(frame, root=root, interval=interval, io=io))

    assert result.reason == "symlink_escape"
    assert io.reads == 0
    assert result.frame is None


def test_directory_is_not_a_regular_file(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    nested = root / "nested"
    nested.mkdir(parents=True)
    frame, interval = _frame(nested)

    result = asyncio.run(validate(frame, root=root, interval=interval))

    assert result.reason == "not_regular_file"


def _frame(path: Path) -> tuple[Frame, CaptureInterval]:
    interval = CaptureInterval((NOW - timedelta(seconds=5)).isoformat(), NOW.isoformat())
    stamp = (NOW - timedelta(seconds=1)).isoformat()
    return Frame(str(path), "dog", "room_2", stamp, False), interval
