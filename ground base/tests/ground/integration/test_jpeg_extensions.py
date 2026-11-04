"""JPG and JPEG are filename aliases for the same byte encoding."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path

import pytest
from patrol.ground.extensions.g14.store import fixture_store
from tests.ground.g06.support import live_frame, validate
from tests.ground.g14.helpers import load_frame, run


@pytest.mark.parametrize("extension", [".jpg", ".jpeg", ".JPG", ".JPEG"])
@pytest.mark.parametrize("source", ["dog", "drone"])
def test_actual_evidence_decoder_accepts_both_extensions(
    tmp_path: Path,
    extension: str,
    source: str,
) -> None:
    frame, interval = live_frame(tmp_path, source=source, name=f"capture{extension}")
    result = asyncio.run(validate(frame, root=tmp_path, interval=interval))
    assert result.status == "accepted"
    assert result.frame.path.endswith(extension)
    assert result.identity["sha256"] == hashlib.sha256(Path(frame.path).read_bytes()).hexdigest()


@pytest.mark.parametrize("extension", [".jpg", ".jpeg", ".JPG", ".JPEG"])
@pytest.mark.parametrize("camera", ["front", "downward"])
def test_v2_artifact_pipeline_accepts_both_extensions(
    tmp_path: Path,
    extension: str,
    camera: str,
) -> None:
    frame = load_frame(camera)
    source = fixture_store() / str(frame["image_ref"]).removeprefix("artifact://")
    store = tmp_path / "store"
    target = store / "clip" / f"frame{extension}"
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    frame["image_ref"] = f"artifact://clip/frame{extension}"
    result, built = asyncio.run(run(tmp_path, frame, store_root=str(store)))
    assert result.status == "ok", result.error
    assert result.data["accepted"] is True
    assert built.adapters.devices.calls == []


@pytest.mark.parametrize("extension", [".jpg", ".jpeg", ".JPG", ".JPEG"])
@pytest.mark.parametrize("source", ["dog", "drone"])
def test_renamed_non_jpeg_is_rejected_for_either_extension(
    tmp_path: Path,
    extension: str,
    source: str,
) -> None:
    frame, interval = live_frame(tmp_path, source=source, name=f"capture{extension}")
    Path(frame.path).write_bytes(b"\x89PNG\r\n\x1a\nnot JPEG bytes")
    result = asyncio.run(validate(frame, root=tmp_path, interval=interval))
    assert result.status == "rejected"
    assert result.reason == "not_jpeg"
    assert result.frame is None
