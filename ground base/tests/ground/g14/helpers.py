"""Shared builders for the frame-provenance tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g14.implementation import FrameFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def services(tmp_path: Path) -> BaseServices:
    return build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)


def feature(tmp_path: Path) -> tuple[FrameFeature, BaseServices]:
    built = services(tmp_path)
    return create(built), built


def load_frame(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g14" / "accepted" / f"{name}.json"
    return dict(_object(path.read_text(encoding="utf-8")))


def load_json(relative: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g14" / relative
    return dict(_object(path.read_text(encoding="utf-8")))


def request(frame: Mapping[str, object], **extra: object) -> FeatureRequest:
    payload: dict[str, object] = {
        "frame": dict(frame),
        "zone": "display",
        "mission_id": "demo-20261104-001",
        "message_id": "msg-frame-check",
        "epoch": 1,
    }
    payload.update(extra)
    return FeatureRequest("stage", "feature.v2_frame", None, payload)


async def run(
    tmp_path: Path,
    frame: Mapping[str, object],
    **extra: object,
) -> tuple[FeatureResult, BaseServices]:
    checker, built = feature(tmp_path)
    result = await checker.execute(request(frame, **extra))
    return result, built


def _object(text: str) -> Mapping[str, object]:
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise AssertionError("fixture must be an object")
    return {str(key): value for key, value in loaded.items()}
