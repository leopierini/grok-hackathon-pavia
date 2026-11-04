"""Camera epoch must move when the camera, size, or calibration changes."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from patrol.ground.kernel.snapshots import idle_snapshot
from patrol.ground.kernel.validation import freeze_map
from tests.ground.g14.helpers import feature, load_frame, request


def _previous(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "camera_id": "downward",
        "camera_epoch": 1,
        "width_px": 320,
        "height_px": 240,
        "camera_to_body_calibration_id": "synthetic-calibration-v1",
        "switched": False,
    }
    base.update(overrides)
    return base


def test_same_epoch_continues_and_a_switch_must_increment(tmp_path: Path) -> None:
    async def body() -> None:
        checker, _built = feature(tmp_path)
        same = await checker.execute(
            request(load_frame("downward"), snapshot=_previous())
        )
        assert same.status == "ok"
        assert same.data["camera_epoch"] == 1

        switched = load_frame("front")
        rejected = await checker.execute(
            request(switched, source="dog", snapshot=_previous(switched=True))
        )
        assert rejected.error is not None
        assert rejected.error.code == "epoch_mismatch"
        assert rejected.error.detail == "epoch_mismatch"

        switched["camera_epoch"] = 2
        accepted = await checker.execute(
            request(switched, source="dog", snapshot=_previous(switched=True))
        )
        assert accepted.status == "ok"
        assert accepted.data["camera_epoch"] == 2

    asyncio.run(body())


def test_resolution_or_calibration_change_needs_a_new_epoch(tmp_path: Path) -> None:
    async def body() -> None:
        checker, _built = feature(tmp_path)
        resized = load_frame("downward")
        resized["width_px"] = 640
        resized["height_px"] = 480
        rejected = await checker.execute(request(resized, snapshot=_previous()))
        assert rejected.error is not None
        assert rejected.error.detail == "epoch_mismatch"

        resized["camera_epoch"] = 2
        # The bytes are still 320x240, so a new epoch is not enough when the
        # declared size does not match the file. This case only checks the epoch
        # rule against a matching file below.
        matching = load_frame("downward")
        matching["camera_to_body_calibration_id"] = None
        stale = await checker.execute(request(matching, snapshot=_previous()))
        assert stale.error is not None
        assert stale.error.detail == "epoch_mismatch"
        matching["camera_epoch"] = 2
        accepted = await checker.execute(request(matching, snapshot=_previous()))
        assert accepted.status == "ok"
        assert accepted.data["uncalibrated"] is True

    asyncio.run(body())


def test_older_epoch_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        checker, _built = feature(tmp_path)
        frame = load_frame("downward")
        result = await checker.execute(request(frame, snapshot=_previous(camera_epoch=4)))
        assert result.error is not None
        assert result.error.code == "epoch_mismatch"

    asyncio.run(body())


def test_session_snapshot_supplies_the_previous_epoch(tmp_path: Path) -> None:
    async def body() -> None:
        checker, _built = feature(tmp_path)
        snapshot = replace(
            idle_snapshot(
                epoch=1,
                modes={"dog": "fake", "drone": "fake", "grok": "fake"},
                dog_transport="ethernet",
            ),
            evidence=freeze_map(_previous(switched=True)),
        )
        result = await checker.execute(
            request(load_frame("front"), source="dog", snapshot=snapshot)
        )
        assert result.error is not None
        assert result.error.detail == "epoch_mismatch"

    asyncio.run(body())


def test_epoch_change_during_validation_is_stale(tmp_path: Path) -> None:
    async def body() -> None:
        checker, built = feature(tmp_path)
        snapshot = _previous()
        built.kernel.barriers.arm("hold")

        async def call() -> object:
            return await checker.execute(
                request(load_frame("downward"), snapshot=snapshot, pause="hold")
            )

        task = asyncio.create_task(call())
        for _ in range(2000):
            if checker.phase == "paused":
                break
            await asyncio.sleep(0)
        else:
            raise AssertionError("validation did not pause")
        snapshot["camera_epoch"] = 2
        built.kernel.barriers.release("hold")
        result = await task
        assert result.error is not None
        assert result.error.code == "epoch_mismatch"
        assert result.error.detail == "stale_epoch"
        assert result.data["accepted"] is False
        assert built.adapters.devices.calls == []

    asyncio.run(body())
