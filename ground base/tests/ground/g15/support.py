"""Direct scheduler helpers. They do not open sockets or call devices."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from patrol.ground.extensions.g15.implementation import VisionSchedule, create
from patrol.ground.extensions.g15.schedule import PLACEHOLDER_MODEL, format_utc
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services

SHA = "0f0479fff4658167e274ded2e2bdc58a9cc45ebdd667c955fb2a2f636906470f"
TARGET = "A person in the operator-marked closed demo area."


def run(test: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(test())


def services(tmp_path: Path) -> BaseServices:
    return build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)


def opened(tmp_path: Path) -> tuple[BaseServices, VisionSchedule]:
    built = services(tmp_path)
    return built, create(built)


def manual(built: BaseServices) -> ManualClock:
    clock = built.kernel.clock
    if not isinstance(clock, ManualClock):
        raise AssertionError("expected the manual clock")
    return clock


def calls_of(built: BaseServices) -> list[str]:
    devices = getattr(built.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found


def settings(**overrides: object) -> dict[str, object]:
    loaded = json.loads((repo_root() / "fixtures" / "ground" / "g15" / "schedule.json").read_text())
    if not isinstance(loaded, dict):
        raise AssertionError("schedule fixture must be an object")
    body = dict(loaded)
    body.update(overrides)
    return body


def frame(
    built: BaseServices,
    frame_id: str,
    *,
    camera: str = "downward",
    captured_at: str | None = None,
) -> dict[str, object]:
    prefix = "dog" if camera == "front" else "drone"
    return {
        "frame_id": frame_id,
        "image_ref": f"artifact://demo-20261104-001/{prefix}/{frame_id}.jpg",
        "sha256": SHA,
        "captured_at": captured_at or format_utc(built.kernel.clock.utc_now()),
        "camera_id": camera,
        "camera_epoch": 1,
        "width_px": 1280 if camera == "front" else 320,
        "height_px": 720 if camera == "front" else 240,
        "camera_frame_id": f"{prefix}/camera_{camera}",
        "camera_to_body_calibration_id": "synthetic-calibration-v1",
        "simulated": True,
    }


def payload(built: BaseServices, frame_id: str, **extra: object) -> dict[str, object]:
    camera = extra.pop("camera", "downward")
    if not isinstance(camera, str):
        raise AssertionError("camera must be a string")
    body: dict[str, object] = {
        "stage": "drone_search",
        "target_description": TARGET,
        "frame": frame(built, frame_id, camera=camera),
        "settings": settings(),
        "active_track_id": None,
    }
    body.update(extra)
    return body


async def call(port: VisionSchedule, body: Mapping[str, object]) -> FeatureResult:
    return await port.execute(FeatureRequest("stage", "schedule", None, dict(body)))


def message_of(result: FeatureResult) -> Mapping[str, object]:
    value = result.data.get("message")
    if not isinstance(value, Mapping):
        raise AssertionError("expected a vision.request message")
    return value


def payload_of(result: FeatureResult) -> Mapping[str, object]:
    value = message_of(result).get("payload")
    if not isinstance(value, Mapping):
        raise AssertionError("expected a vision.request payload")
    return value


def example(name: str) -> dict[str, object]:
    loaded = json.loads((repo_root() / "fixtures" / "ground" / "g15" / name).read_text())
    if not isinstance(loaded, dict):
        raise AssertionError("example must be an object")
    return loaded


def assert_placeholder(result: FeatureResult) -> None:
    assert result.data["model_id"] == PLACEHOLDER_MODEL
    assert result.data["model_unresolved"] is True
    assert payload_of(result)["model_id"] == PLACEHOLDER_MODEL
    assert payload_of(result)["provider"] == "xai"
