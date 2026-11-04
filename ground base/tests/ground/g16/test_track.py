"""Track updates from a matching vision.decision stay free of motor commands."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g16.implementation import SLOT, VisionDecisionFeature, create
from patrol.ground.kernel.contracts import FeatureRequest
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def _load(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g16" / name
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"{name} is not an object")
    return {str(key): value for key, value in parsed.items()}


def _feature(tmp_path: Path) -> VisionDecisionFeature:
    created = create(build_test_services(output_dir=tmp_path))
    if not isinstance(created, VisionDecisionFeature):
        raise AssertionError("factory did not return the vision feature")
    return created


def _payload(message: Mapping[str, object]) -> Mapping[str, object]:
    raw = message["payload"]
    if not isinstance(raw, Mapping):
        raise AssertionError("payload is missing")
    return raw


def test_drone_example_opens_a_track_and_a_hold_proposal(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    services = feature.services
    calls = list(services.adapters.devices.calls)  # type: ignore[attr-defined]
    decision = _load("drone-vision-decision.json")
    request = _load("drone-vision-request.json")
    assessed = feature.assess(decision, request)
    proposal = assessed.proposal
    assert assessed.status == "ok"
    assert assessed.track_id == "target-001"
    assert assessed.track_changed is True
    assert assessed.motion_authorized is False
    assert assessed.model_id == "CONFIGURE_VERIFIED_IMAGE_MODEL"
    assert assessed.model_score == 0.91
    assert assessed.image_direction == "center"
    assert assessed.image_direction_space == "image"
    assert proposal is not None
    body = _payload(proposal)
    example = _payload(_load("ai-to-drone-proposal.json"))
    assert set(body) == set(example)
    assert body["action"] == "hold"
    assert body["direction_hint"] == "center"
    assert body["target_component"] == "drone"
    assert body["track_id"] == "target-001"
    assert body["evidence_frame_id"] == "drone-downward-001"
    assert "motion" not in body
    assert "sdk_command" not in body
    assert "command_id" not in body
    assert proposal["kind"] == "motion.proposal"
    assert proposal["destination"] == "ground"
    assert services.adapters.devices.calls == calls  # type: ignore[attr-defined]
    assert services.kernel.authority.cancelled is False


def test_execute_records_image_space_and_leaves_devices_idle(tmp_path: Path) -> None:
    feature = _feature(tmp_path)

    async def body() -> None:
        result = await feature.execute(
            FeatureRequest("diagnostic", "drone_example", None, {"seed": 0})
        )
        assert result.status == "ok"
        assert result.error is None
        assert result.data["slot"] == SLOT
        assert result.data["authorized"] is False
        assert result.data["device_calls"] == 0
        assert result.events[0].kind == "decision_received"
        payload = result.events[0].payload
        assert payload["image_direction_space"] == "image"
        assert payload["image_direction"] == "center"
        assert payload["motion_authorized"] is False
        assert payload["model_score_is_permission"] is False
        assert payload["device_commands"] == ()
        assert payload["motion_trace"] == ()
        assert payload["command_id"] is None
        assert payload["beacon_epoch"] is None
        assert payload["camera_epoch"] == 1
        calls = feature.services.adapters.devices.calls  # type: ignore[attr-defined]
        assert calls == []
        for name in ("execute", "takeoff", "move", "drone.command", "dog.command"):
            assert name not in calls

    asyncio.run(body())


def test_low_score_still_opens_a_track_without_permission(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    decision = _load("drone-vision-decision.json")
    payload = dict(_payload(decision))
    detections = payload["detections"]
    assert isinstance(detections, list)
    first = dict(detections[0])
    first["confidence"] = 0.01
    detections = [first]
    payload["detections"] = detections
    cloned = dict(decision)
    cloned["payload"] = payload
    assessed = feature.assess(cloned, _load("drone-vision-request.json"))
    assert assessed.track_id == "target-001"
    assert assessed.model_score == 0.01
    assert assessed.motion_authorized is False


def test_carried_track_id_is_reused_and_a_second_id_is_not_opened(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    decision = _load("drone-vision-decision.json")
    payload = dict(_payload(decision))
    detections = payload["detections"]
    assert isinstance(detections, list)
    first = dict(detections[0])
    first["track_id"] = "target-777"
    payload["detections"] = [first]
    cloned = dict(decision)
    cloned["payload"] = payload
    request = _load("drone-vision-request.json")
    opened = feature.assess(cloned, request)
    assert opened.track_id == "target-777"
    assert opened.outcome == "track_opened"
    updated = feature.assess(decision, request, current_track_id="target-001")
    assert updated.track_id == "target-001"
    assert updated.outcome == "track_updated"
    stolen = feature.assess(cloned, request, current_track_id="target-001")
    assert stolen.status == "failed"
    assert stolen.detail == "track_mismatch"
    assert stolen.track_id == "target-001"
    assert stolen.track_changed is False


def test_dog_frame_updates_the_same_track_and_does_not_command(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    assessed = feature.assess(
        _load("dog-vision-decision.json"),
        _load("dog-vision-request.json"),
        current_track_id="target-001",
    )
    assert assessed.status == "ok"
    assert assessed.track_id == "target-001"
    assert assessed.outcome == "track_updated"
    assert assessed.proposal is None
    assert assessed.motion_authorized is False
