"""JPEG bytes, capture time, artifact paths, and disappearance."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g14.store import fixture_store
from PIL import Image
from tests.ground.g14.helpers import feature, load_frame, request, run


def test_text_renamed_to_jpg_is_rejected(tmp_path: Path) -> None:
    store = tmp_path / "store"
    dest = store / "clip" / "frame.jpg"
    dest.parent.mkdir(parents=True)
    payload = b"not a jpeg\n"
    dest.write_bytes(payload)
    frame = load_frame("downward")
    frame["image_ref"] = "artifact://clip/frame.jpg"
    frame["sha256"] = hashlib.sha256(payload).hexdigest()

    async def body() -> None:
        result, built = await run(tmp_path, frame, store_root=str(store))
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.detail == "not_jpeg"
        assert built.evidence.trace == ["evidence.validate"]

    asyncio.run(body())


def test_capture_time_is_not_replaced_by_file_mtime(tmp_path: Path) -> None:
    store = tmp_path / "store"
    dest = store / "clip" / "frame.jpg"
    dest.parent.mkdir(parents=True)
    source = fixture_store() / "demo-20261104-001" / "drone" / "downward-001.jpg"
    shutil.copyfile(source, dest)
    os.utime(dest, (0, 0))
    frame = load_frame("downward")
    frame["image_ref"] = "artifact://clip/frame.jpg"
    assert os.path.getmtime(dest) == 0

    async def body() -> None:
        result, _built = await run(tmp_path, frame, store_root=str(store))
        assert result.status == "ok"
        assert result.data["captured_at"] == "2026-11-04T13:00:10.000Z"
        assert "1970" not in str(result.data["captured_at"])
        handle = result.data["handle"]
        assert isinstance(handle, Mapping)
        assert handle["captured_at"] == frame["captured_at"]

    asyncio.run(body())


def test_sender_path_and_traversal_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        windows = load_frame("downward")
        windows["image_ref"] = r"C:\Users\sender\Pictures\frame.jpg"
        rejected, built = await run(tmp_path, windows)
        assert rejected.error is not None
        assert rejected.error.detail == "not_artifact"
        assert "C:\\Users\\sender" not in str(rejected.data)
        assert built.evidence.trace == []

        escaped = load_frame("downward")
        escaped["image_ref"] = "artifact://demo-20261104-001/../../outside.jpg"
        again, _built = await run(tmp_path, escaped)
        assert again.error is not None
        assert again.error.code == "path_escape"

        slashed = load_frame("front")
        slashed["image_ref"] = "artifact://demo\\front.jpg"
        third, _built = await run(tmp_path, slashed)
        assert third.error is not None
        assert third.error.detail == "not_artifact"

    asyncio.run(body())


def test_file_disappears_and_changes_fail_closed(tmp_path: Path) -> None:
    async def body() -> None:
        checker, built = feature(tmp_path)
        store = tmp_path / "store"
        dest = store / "clip" / "frame.jpg"
        dest.parent.mkdir(parents=True)
        source = fixture_store() / "demo-20261104-001" / "drone" / "downward-001.jpg"
        shutil.copyfile(source, dest)
        frame = load_frame("downward")
        frame["image_ref"] = "artifact://clip/frame.jpg"
        built.kernel.barriers.arm("hold")

        async def call() -> object:
            return await checker.execute(
                request(frame, store_root=str(store), pause="hold")
            )

        task = asyncio.create_task(call())
        for _ in range(2000):
            if checker.phase == "paused":
                break
            await asyncio.sleep(0)
        else:
            raise AssertionError("validation did not pause")
        dest.unlink()
        built.kernel.barriers.release("hold")
        gone = await task
        assert gone.error is not None
        assert gone.error.code == "io_fault"
        assert gone.error.detail == "disappeared"
        assert gone.error.recovery_required is True
        assert gone.data["accepted"] is False

        shutil.copyfile(source, dest)
        other = fixture_store() / "placeholder.jpg"
        built.kernel.barriers.arm("hold")
        task = asyncio.create_task(call())
        for _ in range(2000):
            if checker.phase == "paused":
                break
            await asyncio.sleep(0)
        else:
            raise AssertionError("validation did not pause")
        dest.write_bytes(other.read_bytes())
        built.kernel.barriers.release("hold")
        changed = await task
        assert changed.error is not None
        assert changed.error.detail == "changed_during_validation"
        assert built.adapters.devices.calls == []

    asyncio.run(body())


def test_placeholder_cannot_be_labeled_real_but_other_bytes_can(tmp_path: Path) -> None:
    async def body() -> None:
        bundled = load_frame("downward")
        bundled["simulated"] = False
        rejected, _built = await run(tmp_path, bundled)
        assert rejected.error is not None
        assert rejected.error.detail == "synthetic_placeholder"

        store = tmp_path / "store"
        dest = store / "clip" / "live.jpg"
        dest.parent.mkdir(parents=True)
        Image.new("RGB", (8, 6), (9, 9, 9)).save(dest, format="JPEG")
        data = dest.read_bytes()
        frame = load_frame("front")
        frame["image_ref"] = "artifact://clip/live.jpg"
        frame["sha256"] = hashlib.sha256(data).hexdigest()
        frame["width_px"] = 8
        frame["height_px"] = 6
        frame["simulated"] = False
        frame["camera_epoch"] = 3
        accepted, built = await run(
            tmp_path,
            frame,
            source="dog",
            store_root=str(store),
            snapshot={
                "camera_id": "front",
                "camera_epoch": 1,
                "width_px": 1280,
                "height_px": 720,
                "camera_to_body_calibration_id": "synthetic-calibration-v1",
                "switched": False,
            },
        )
        assert accepted.status == "ok"
        assert accepted.data["simulated"] is False
        assert accepted.data["width_px"] == 8
        assert dest.is_file()
        assert built.adapters.devices.calls == []

    asyncio.run(body())


def test_string_simulation_flag_is_not_coerced(tmp_path: Path) -> None:
    frame = load_frame("downward")
    frame["simulated"] = "false"

    async def body() -> None:
        result, _built = await run(tmp_path, frame)
        assert result.error is not None
        assert result.error.code == "invalid_input"

    asyncio.run(body())


def test_zero_size_and_naive_time_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        blank = load_frame("downward")
        blank["width_px"] = 0
        rejected, _built = await run(tmp_path, blank)
        assert rejected.error is not None
        assert rejected.error.detail == "invalid_frame"
        naive = load_frame("front")
        naive["captured_at"] = "2026-11-04T13:00:10"
        again, _built = await run(tmp_path, naive)
        assert again.error is not None
        assert again.error.detail == "captured_at"

    asyncio.run(body())
