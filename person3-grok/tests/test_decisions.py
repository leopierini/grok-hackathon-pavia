"""vision.decision echoes the request and never mints a track id."""

import subprocess
import sys

import pytest

from patrol.grok import create_reasoner
from patrol.vision_v2.decision import PLACEHOLDER_MODEL, build_decision, build_request, refuse_placeholder_model


def test_decision_echo_and_null_expiry() -> None:
    request = build_request(
        stage="dog_approach",
        message_id="msg-req-1",
        request_id="vision-1",
        frame_id="frame-1",
    )
    decision = build_decision(request, state="person_visible", message_id="msg-dec-1", seq=3)
    assert decision["kind"] == "vision.decision"
    assert decision["source"] == "vision"
    assert decision["destination"] == "ground"
    assert decision["expires_at"] is None
    assert decision["correlation_id"] == "msg-req-1"
    payload = decision["payload"]
    assert payload["request_id"] == "vision-1"
    assert payload["frame_id"] == "frame-1"
    assert payload["frame_captured_at"] == request["payload"]["frame"]["captured_at"]
    assert payload["suggested_action"] == "approach"
    assert payload["detections"][0]["track_id"] == "target-001"
    assert payload["prompt_version"] == "patrol-presence-v1"
    assert request["payload"]["frame"]["camera_id"] == "front"


def test_not_visible_has_no_box() -> None:
    request = build_request(
        stage="drone_track",
        message_id="msg-req-2",
        request_id="vision-2",
        frame_id="frame-2",
    )
    decision = build_decision(request, state="not_visible", message_id="msg-dec-2", seq=4)
    payload = decision["payload"]
    assert payload["suggested_action"] == "stop"
    assert payload["detections"] == []
    assert payload["image_direction"] == "unknown"
    assert request["payload"]["frame"]["camera_id"] == "downward"


def test_placeholder_model_is_refused() -> None:
    with pytest.raises(ValueError, match="CONFIGURE_VERIFIED_IMAGE_MODEL"):
        refuse_placeholder_model(PLACEHOLDER_MODEL)


def test_real_reasoner_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from patrol.contract import AdapterError

    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(AdapterError) as caught:
        create_reasoner("real", {}, "/tmp")
    assert caught.value.code == "unsupported"
    assert "XAI_API_KEY is unset" in str(caught.value)
    assert "no model request was sent" in str(caught.value)

    monkeypatch.setenv("XAI_API_KEY", "present-but-not-sent")
    with pytest.raises(AdapterError) as present:
        create_reasoner("real", {}, "/tmp")
    assert present.value.code == "unsupported"
    assert "vision.decision" in str(present.value)
    assert "No model request was sent" in str(present.value)
    assert "present-but-not-sent" not in str(present.value)


def test_vision_module_exits_2() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "patrol.vision_v2"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "exits 2" in completed.stderr
