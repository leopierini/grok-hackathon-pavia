"""Front and downward cameras are accepted. Rear, back, and empty are not."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from tests.ground.g14.helpers import load_frame, run


def test_front_and_downward_identities(tmp_path: Path) -> None:
    async def body() -> None:
        downward, built = await run(tmp_path, load_frame("downward"), source="drone")
        assert downward.status == "ok"
        assert downward.data["camera_id"] == "downward"
        assert downward.data["uncalibrated"] is False
        handle = downward.data["handle"]
        assert isinstance(handle, Mapping)
        assert handle["camera_to_body_calibration_id"] == "synthetic-calibration-v1"
        assert built.adapters.devices.calls == []

        front, again = await run(tmp_path, load_frame("front"), source="dog")
        assert front.status == "ok"
        assert front.data["camera_id"] == "front"
        assert front.data["width_px"] == 1280
        assert front.data["height_px"] == 720
        assert again.adapters.devices.calls == []

    asyncio.run(body())


def test_rear_back_and_empty_cameras_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        rear = load_frame("downward")
        rear["camera_id"] = "rear"
        rejected, built = await run(tmp_path, rear)
        assert rejected.error is not None
        assert rejected.error.code == "rejected"
        assert rejected.error.detail == "rear_camera"
        assert rejected.events[0].kind == "frame_rejected"
        assert built.evidence.trace == []

        back = load_frame("front")
        back["camera_id"] = "back"
        again, _built = await run(tmp_path, back)
        assert again.error is not None
        assert again.error.detail == "rear_camera"

        empty = load_frame("front")
        empty["camera_id"] = ""
        blank, _built = await run(tmp_path, empty)
        assert blank.error is not None
        assert blank.error.detail == "camera_id"

        other = load_frame("front")
        other["camera_id"] = "side"
        unknown, _built = await run(tmp_path, other)
        assert unknown.error is not None
        assert unknown.error.detail == "camera_id"

    asyncio.run(body())


def test_null_calibration_is_preserved_and_flagged(tmp_path: Path) -> None:
    frame = load_frame("downward")
    frame["camera_to_body_calibration_id"] = None

    async def body() -> None:
        result, _built = await run(tmp_path, frame)
        assert result.status == "ok"
        assert result.data["camera_to_body_calibration_id"] is None
        assert result.data["uncalibrated"] is True
        handle = result.data["handle"]
        assert isinstance(handle, Mapping)
        assert handle["camera_to_body_calibration_id"] is None
        assert result.events[0].payload["uncalibrated"] is True
        assert result.events[0].payload["camera_epoch"] == 1

    asyncio.run(body())


def test_unknown_frame_field_is_rejected(tmp_path: Path) -> None:
    frame = load_frame("downward")
    frame["sdk_command"] = "takeoff"

    async def body() -> None:
        result, built = await run(tmp_path, frame)
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert built.adapters.devices.calls == []

    asyncio.run(body())
