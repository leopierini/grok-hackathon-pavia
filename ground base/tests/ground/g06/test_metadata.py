"""Source, zone, mode, and simulation-flag checks."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from patrol.contract import Frame
from patrol.ground.extensions.g06.images import write_jpeg
from patrol.ground.extensions.g06.model import CaptureInterval, ServicePorts
from tests.ground.g06.support import NOW, validate

_SOURCES = ("phone", "dog", "drone")
_MODES = ("fake", "real")
_ZONES = ("entrance", "room_2", "display")


@pytest.mark.parametrize("source", _SOURCES)
@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("zone", _ZONES)
def test_every_source_mode_and_zone_combination(
    tmp_path: Path, source: str, mode: str, zone: str
) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    simulated = mode == "fake"
    if source == "phone":
        path = tmp_path / "phone.jpg"
        captured_at = None
        interval = None
    else:
        path = root / "live.jpg"
        captured_at = (NOW - timedelta(seconds=1)).isoformat()
        interval = CaptureInterval((NOW - timedelta(seconds=5)).isoformat(), NOW.isoformat())
    write_jpeg(path)
    frame = Frame(str(path), source, zone, captured_at, simulated)  # type: ignore[arg-type]

    result = asyncio.run(
        validate(frame, source=source, zone=zone, mode=mode, root=root, interval=interval)
    )

    assert result.status == "accepted"
    assert result.frame is frame
    assert result.provenance is not None
    assert result.provenance["source"] == source
    assert result.provenance["zone"] == zone
    assert result.provenance["mode"] == mode
    assert result.provenance["simulated"] is simulated


def test_wrong_zone_and_source_are_distinct(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    path = root / "frame.jpg"
    write_jpeg(path)
    interval = CaptureInterval((NOW - timedelta(seconds=5)).isoformat(), NOW.isoformat())
    stamp = (NOW - timedelta(seconds=1)).isoformat()
    wrong_zone = Frame(str(path), "dog", "display", stamp, False)
    wrong_source = Frame(str(path), "drone", "room_2", stamp, False)

    zone_result = asyncio.run(
        validate(wrong_zone, source="dog", zone="room_2", root=root, interval=interval)
    )
    source_result = asyncio.run(
        validate(wrong_source, source="dog", zone="room_2", root=root, interval=interval)
    )

    assert zone_result.reason == "zone_mismatch"
    assert source_result.reason == "source_mismatch"
    assert zone_result.frame is None and source_result.frame is None


def test_simulation_flag_must_match_mode_and_stay_a_boolean(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    path = root / "frame.jpg"
    write_jpeg(path)
    interval = CaptureInterval((NOW - timedelta(seconds=5)).isoformat(), NOW.isoformat())
    stamp = (NOW - timedelta(seconds=1)).isoformat()
    simulated_real = Frame(str(path), "drone", "room_2", stamp, True)
    live_fake = Frame(str(path), "dog", "room_2", stamp, False)
    text_false = Frame(str(path), "dog", "room_2", stamp, "false")  # type: ignore[arg-type]

    real_result = asyncio.run(validate(simulated_real, root=root, interval=interval, mode="real"))
    fake_result = asyncio.run(validate(live_fake, root=root, interval=interval, mode="fake"))
    flag_result = asyncio.run(validate(text_false, root=root, interval=interval, mode="real"))

    assert real_result.reason == "simulation_mismatch"
    assert "simulated" in real_result.detail
    assert fake_result.reason == "simulation_mismatch"
    assert flag_result.reason == "invalid_simulation_flag"
    assert bool("false") is True
    assert flag_result.status == "rejected"


def test_phone_image_outside_the_adapter_directory_keeps_its_provenance(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    phone = tmp_path / "camera" / "shot.jpg"
    write_jpeg(phone)
    supplied = "2026-11-04T09:30:00+00:00"
    frame = Frame(str(phone), "phone", "room_2", supplied, False)
    peers = ServicePorts()

    result = asyncio.run(validate(frame, root=root, interval=None, peers=peers))

    assert result.status == "accepted"
    assert result.frame is frame
    assert frame.captured_at == supplied
    assert result.provenance is not None
    assert result.provenance["time_origin"] == "supplied_phone"
    assert result.provenance["file_mtime_used"] is False
