"""Emitted JSON keeps the example's required keys and the configured deadline."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.extensions.g15.schedule import format_utc, parse_utc
from tests.ground.g15.support import call, example, manual, message_of, opened, payload_of, run


def test_drone_and_dog_messages_have_the_example_keys(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        drone = example("drone-vision-request.json")
        dog = example("dog-vision-request.json")
        drone_result = await call(port, _request(built, drone))
        manual(built).advance(1)
        dog_result = await call(port, _request(built, dog, settle=True))
        _assert_shape(drone_result, drone)
        _assert_shape(dog_result, dog)
        emitted = tmp_path / "emitted"
        emitted.mkdir()
        drone_path = emitted / "drone-vision-request.json"
        dog_path = emitted / "dog-vision-request.json"
        example_copy = emitted / "drone-vision-request.example.json"
        drone_body = json.dumps(message_of(drone_result), indent=2) + "\n"
        dog_body = json.dumps(message_of(dog_result), indent=2) + "\n"
        drone_path.write_text(drone_body, encoding="utf-8")
        dog_path.write_text(dog_body, encoding="utf-8")
        example_copy.write_text(json.dumps(drone, indent=2) + "\n", encoding="utf-8")
        saved = json.loads(drone_path.read_text(encoding="utf-8"))
        assert set(saved) == set(json.loads(example_copy.read_text(encoding="utf-8")))
        assert json.loads(dog_path.read_text(encoding="utf-8"))["kind"] == "vision.request"

    run(body)


def test_expires_at_is_the_manual_clock_plus_the_timeout(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        result = await call(port, _request(built, example("drone-vision-request.json")))
        message = message_of(result)
        sent = parse_utc(str(message["sent_at"]), "sent_at")
        expires = parse_utc(str(message["expires_at"]), "expires_at")
        assert sent == manual(built).utc_now()
        assert (expires - sent).total_seconds() == 5
        assert message["source"] == "ground"
        assert message["destination"] == "vision"
        assert message["kind"] == "vision.request"
        assert message["correlation_id"] is None
        assert payload_of(result)["max_evidence_age_ms"] == 3000
        assert "vision.decision" not in json.dumps(message)

    run(body)


def test_scene_context_and_artifact_reference_are_copied(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        result = await call(port, _request(built, example("drone-vision-request.json")))
        payload = payload_of(result)
        frame = payload["frame"]
        assert isinstance(frame, dict)
        assert frame["image_ref"] == "artifact://demo-20261104-001/drone/downward-001.jpg"
        assert payload["scene_context"] == {
            "staged_demo": True,
            "area_closed_by_operator": True,
        }
        assert payload["target_description"] == "A person in the operator-marked closed demo area."

    run(body)


def test_local_paths_http_urls_and_extra_frame_fields_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        body_json = _request(built, example("drone-vision-request.json"))
        frame = body_json["frame"]
        assert isinstance(frame, dict)
        local = dict(frame)
        local["image_ref"] = r"C:\photos\frame.jpg"
        remote = dict(frame)
        remote["image_ref"] = "https://example.test/frame.jpg"
        extra = dict(frame)
        extra["note"] = "ignore"
        for broken in (local, remote, extra):
            submitted = dict(body_json)
            submitted["frame"] = broken
            result = await call(port, submitted)
            assert result.data["message"] is None
            assert result.error is not None

    run(body)


def _request(
    built: object,
    example_message: dict[str, object],
    *,
    settle: bool = False,
) -> dict[str, object]:
    from patrol.ground.kernel.contracts import BaseServices

    if not isinstance(built, BaseServices):
        raise AssertionError("expected services")
    payload = example_message["payload"]
    if not isinstance(payload, dict):
        raise AssertionError("payload missing")
    frame = dict(payload["frame"]) if isinstance(payload["frame"], dict) else {}
    frame["captured_at"] = format_utc(built.kernel.clock.utc_now())
    scene = payload["scene_context"]
    if not isinstance(scene, dict):
        raise AssertionError("scene missing")
    body: dict[str, object] = {
        "stage": payload["stage"],
        "target_description": payload["target_description"],
        "frame": frame,
        "active_track_id": payload["active_track_id"],
        "settings": {
            "sample_ms": 1000,
            "timeout_ms": 5000,
            "evidence_age_ms": 3000,
            "max_in_flight": 1,
            "model_id": payload["model_id"],
            "prompt_version": payload["prompt_version"],
            "scene_context": {
                "staged_demo": scene["staged_demo"],
                "area_closed_by_operator": scene["area_closed_by_operator"],
            },
            "mission_id": example_message["mission_id"],
            "epoch": example_message["epoch"],
            "simulated": example_message["simulated"],
        },
    }
    if settle:
        body["settle"] = True
    return body


def _assert_shape(result: object, example_message: dict[str, object]) -> None:
    from patrol.ground.kernel.contracts import FeatureResult

    if not isinstance(result, FeatureResult):
        raise AssertionError("expected a feature result")
    message = message_of(result)
    payload = payload_of(result)
    example_payload = example_message["payload"]
    assert isinstance(example_payload, dict)
    assert set(message) == set(example_message)
    assert set(payload) == set(example_payload)
    frame = payload["frame"]
    example_frame = example_payload["frame"]
    assert isinstance(frame, dict)
    assert isinstance(example_frame, dict)
    assert set(frame) == set(example_frame)
    scene = payload["scene_context"]
    example_scene = example_payload["scene_context"]
    assert isinstance(scene, dict)
    assert isinstance(example_scene, dict)
    assert set(scene) == set(example_scene)
