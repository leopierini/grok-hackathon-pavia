"""Signal connector: fixture bytes in, Task 16 decisions out. HTTP is mocked."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from patrol.ground.__main__ import main
from patrol.ground.demo import run_demo
from patrol.ground.extensions.g16.decide import assess
from patrol.ground.kernel.paths import repo_root
from patrol.ground.signal import SignalError, assess_frame
from patrol.ground.signal.client import API_URL, DEFAULT_IMAGE_MODEL


def _frame(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g14" / "accepted" / name
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _request(
    stage: str,
    frame_name: str,
    *,
    track: str | None,
    model_id: str = "CONFIGURE_VERIFIED_IMAGE_MODEL",
) -> dict[str, object]:
    return {
        "protocol_version": "2.0-draft",
        "message_id": f"msg-req-{stage}",
        "mission_id": "demo-20261104-001",
        "epoch": 1,
        "seq": 1,
        "sent_at": "2026-11-04T13:00:10.100Z",
        "source": "ground",
        "destination": "vision",
        "kind": "vision.request",
        "correlation_id": None,
        "expires_at": "2026-11-04T13:00:15.100Z",
        "simulated": True,
        "payload": {
            "request_id": f"vision-{stage}",
            "provider": "xai",
            "model_id": model_id,
            "prompt_version": "patrol-demo-v2.0",
            "stage": stage,
            "frame": _frame(frame_name),
            "target_description": "A person in the operator-marked closed demo area.",
            "active_track_id": track,
            "scene_context": {"staged_demo": True, "area_closed_by_operator": True},
            "max_evidence_age_ms": 3000,
        },
    }


def _http_reply(
    *,
    state: str = "person_visible",
    reason: str = "A person is visible in the closed demo area.",
    box: list[float] | None = None,
    confidence: float = 0.91,
) -> tuple[int, bytes]:
    body = {
        "target_state": state,
        "confidence": confidence,
        "box_xyxy_norm": [0.3, 0.2, 0.55, 0.8] if box is None else box,
        "reason": reason,
    }
    envelope = {"choices": [{"message": {"content": json.dumps(body)}}]}
    return 200, json.dumps(envelope).encode("utf-8")


def _transport(seen: dict[str, object]):
    def send(
        url: str,
        payload: bytes,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> tuple[int, bytes]:
        count = seen.get("count")
        seen["count"] = 1 if not isinstance(count, int) else count + 1
        seen["url"] = url
        seen["payload"] = payload
        seen["headers"] = dict(headers)
        seen["timeout_s"] = timeout_s
        reply = seen.get("reply")
        if isinstance(reply, tuple):
            return reply
        return _http_reply()

    return send


def test_dry_run_without_key_does_not_call_xai() -> None:
    seen: dict[str, object] = {}

    with pytest.raises(SignalError, match="XAI_API_KEY is unset") as caught:
        assess_frame(
            _request("drone_search", "downward.json", track=None),
            transport=_transport(seen),
            environ={},
        )

    assert caught.value.code == "unsupported"
    assert seen.get("count") is None
    assert "XAI_API_KEY" not in caught.value.detail or "unset" in caught.value.detail


def test_missing_artifact_and_hash_mismatch_fail_before_http() -> None:
    request = _request("drone_search", "downward.json", track=None)
    payload = request["payload"]
    assert isinstance(payload, dict)
    frame = payload["frame"]
    assert isinstance(frame, dict)
    frame["image_ref"] = "artifact://demo-20261104-001/drone/missing.jpg"
    seen: dict[str, object] = {}
    with pytest.raises(SignalError, match="artifact missing"):
        assess_frame(request, transport=_transport(seen), environ={"XAI_API_KEY": "test-key"})
    assert seen.get("count") is None

    frame["image_ref"] = "artifact://demo-20261104-001/drone/downward-001.jpg"
    frame["sha256"] = "a" * 64
    with pytest.raises(SignalError, match="sha256 mismatch"):
        assess_frame(request, transport=_transport(seen), environ={"XAI_API_KEY": "test-key"})
    assert seen.get("count") is None


def test_simulated_false_is_refused_before_http() -> None:
    request = _request("drone_search", "downward.json", track=None)
    request["simulated"] = False
    seen: dict[str, object] = {}
    with pytest.raises(SignalError, match="simulated") as caught:
        assess_frame(request, transport=_transport(seen), environ={"XAI_API_KEY": "test-key"})
    assert caught.value.code == "unsafe_state"
    assert seen.get("count") is None


def test_drone_search_decision_is_task16_valid() -> None:
    seen: dict[str, object] = {}
    request = _request("drone_search", "downward.json", track=None)
    decision = assess_frame(
        request,
        transport=_transport(seen),
        environ={"XAI_API_KEY": "test-key"},
    )
    assert seen["url"] == API_URL
    assert seen["timeout_s"] == 5.0
    headers = seen["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer test-key"
    raw = seen["payload"]
    assert isinstance(raw, bytes)
    assert b"test-key" not in raw
    posted = json.loads(raw)
    assert posted["model"] == DEFAULT_IMAGE_MODEL
    encoded = json.dumps(posted)
    assert "data:image/jpeg;base64," in encoded
    assert decision["source"] == "vision"
    assert decision["destination"] == "ground"
    assert decision["correlation_id"] == "msg-req-drone_search"
    assert decision["simulated"] is True
    payload = decision["payload"]
    assert isinstance(payload, dict)
    assert payload["request_id"] == "vision-drone_search"
    assert payload["frame_id"] == "drone-downward-001"
    frame = request["payload"]["frame"]
    assert isinstance(frame, dict)
    assert payload["frame_captured_at"] == frame["captured_at"]
    assert payload["model_id"] == DEFAULT_IMAGE_MODEL
    assert payload["model_id"] != "CONFIGURE_VERIFIED_IMAGE_MODEL"
    assert payload["target_state"] == "person_visible"
    assert payload["suggested_action"] == "reposition"
    assert payload["image_direction"] == "left"
    detection = payload["detections"][0]
    assert detection["label"] == "person"
    assert detection["track_id"] is None
    assert detection["box_xyxy_norm"] == [0.3, 0.2, 0.55, 0.8]
    assessed = assess(decision, request, current_camera_epoch=1)
    assert assessed.status == "ok"
    assert assessed.track_id == "target-001"
    assert assessed.proposal is not None
    proposal = assessed.proposal["payload"]
    assert isinstance(proposal, Mapping)
    assert proposal["action"] == "reposition"
    assert proposal["direction_hint"] == "left"


def test_dog_acquire_keeps_target_001_and_switches_vision() -> None:
    request = _request("dog_acquire", "front.json", track="target-001")
    decision = assess_frame(request, transport=_transport({}), environ={"XAI_API_KEY": "test-key"})
    payload = decision["payload"]
    assert isinstance(payload, dict)
    assert payload["suggested_action"] == "switch_to_dog_vision"
    assert payload["detections"][0]["track_id"] == "target-001"
    assert payload["image_direction"] == "center"
    assessed = assess(decision, request, current_track_id="target-001", current_camera_epoch=1)
    assert assessed.status == "ok"
    assert assessed.track_id == "target-001"
    assert "track_mismatch" not in assessed.trace


def test_rehearsal_prompt_does_not_use_the_presence_labels() -> None:
    request = _request("drone_search", "downward.json", track=None)
    decision = assess_frame(
        request,
        transport=_transport({"reply": _http_reply(state="not_visible", box=None)}),
        environ={"XAI_API_KEY": "test-key"},
    )
    payload = decision["payload"]
    assert isinstance(payload, dict)
    assert payload["prompt_version"] == "patrol-demo-v2.0"
    assert payload["suggested_action"] == "review"


def test_presence_prompt_maps_still_there_gone_and_unsure() -> None:
    gone_request = _request("dog_approach", "front.json", track="target-001")
    gone_payload = gone_request["payload"]
    assert isinstance(gone_payload, dict)
    gone_payload["prompt_version"] = "patrol-presence-v1"
    gone = assess_frame(
        gone_request,
        transport=_transport({"reply": _http_reply(state="not_visible", box=None)}),
        environ={"XAI_API_KEY": "test-key"},
    )
    gone_body = gone["payload"]
    assert isinstance(gone_body, dict)
    assert gone_body["target_state"] == "not_visible"
    assert gone_body["suggested_action"] == "stop"
    assert gone_body["image_direction"] == "unknown"
    assert gone_body["detections"] == []
    assessed = assess(gone, gone_request, current_track_id="target-001", current_camera_epoch=1)
    assert assessed.status == "ok"
    assert assessed.proposal is not None
    proposal = assessed.proposal["payload"]
    assert isinstance(proposal, Mapping)
    assert proposal["action"] == "stop"
    assert proposal["target_component"] == "dog"

    visible_request = _request("dog_approach", "front.json", track="target-001")
    visible_payload = visible_request["payload"]
    assert isinstance(visible_payload, dict)
    visible_payload["prompt_version"] = "patrol-presence-v1"
    visible = assess_frame(
        visible_request,
        transport=_transport({}),
        environ={"XAI_API_KEY": "test-key"},
    )
    visible_body = visible["payload"]
    assert isinstance(visible_body, dict)
    assert visible_body["suggested_action"] == "approach"
    assert visible_body["detections"][0]["track_id"] == "target-001"

    hold_request = _request("drone_track", "downward.json", track="target-001")
    hold_payload = hold_request["payload"]
    assert isinstance(hold_payload, dict)
    hold_payload["prompt_version"] = "patrol-presence-v1"
    holding = assess_frame(
        hold_request,
        transport=_transport({}),
        environ={"XAI_API_KEY": "test-key"},
    )
    holding_body = holding["payload"]
    assert isinstance(holding_body, dict)
    assert holding_body["suggested_action"] == "hold"

    unsure_request = _request("dog_approach", "front.json", track="target-001")
    unsure_payload = unsure_request["payload"]
    assert isinstance(unsure_payload, dict)
    unsure_payload["prompt_version"] = "patrol-presence-v1"
    unsure = assess_frame(
        unsure_request,
        transport=_transport({"reply": _http_reply(state="uncertain", box=None)}),
        environ={"XAI_API_KEY": "test-key"},
    )
    unsure_body = unsure["payload"]
    assert isinstance(unsure_body, dict)
    assert unsure_body["suggested_action"] == "review"
    withheld = assess(
        unsure, unsure_request, current_track_id="target-001", current_camera_epoch=1
    )
    assert withheld.proposal is None
    assert withheld.motion_authorized is False


def test_named_model_is_sent_and_motor_text_is_removed() -> None:
    seen: dict[str, object] = {"reply": _http_reply(reason="takeoff")}
    request = _request(
        "drone_search",
        "downward.json",
        track=None,
        model_id="grok-4.20-non-reasoning",
    )
    decision = assess_frame(
        request,
        transport=_transport(seen),
        environ={"XAI_API_KEY": "test-key"},
    )
    posted = json.loads(seen["payload"])  # type: ignore[arg-type]
    assert posted["model"] == "grok-4.20-non-reasoning"
    payload = decision["payload"]
    assert isinstance(payload, dict)
    assert payload["model_id"] == "grok-4.20-non-reasoning"
    assert "takeoff" not in payload["reason"].lower()
    assert assess(decision, request).status == "ok"

    seen["reply"] = _http_reply(reason="The person is 5 m away.")
    distance = assess_frame(
        request,
        transport=_transport(seen),
        environ={"XAI_API_KEY": "test-key"},
    )
    body = distance["payload"]
    assert isinstance(body, dict)
    assert "5 m" not in body["reason"]
    assert assess(distance, request).status == "ok"


def test_http_errors_fail_closed() -> None:
    request = _request("drone_search", "downward.json", track=None)
    denied: dict[str, object] = {"reply": (401, b"")}
    with pytest.raises(SignalError, match="HTTP 401") as http:
        assess_frame(request, transport=_transport(denied), environ={"XAI_API_KEY": "test-key"})
    assert http.value.code == "api_error"

    def explode(
        url: str,
        payload: bytes,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> tuple[int, bytes]:
        del url, payload, headers, timeout_s
        raise TimeoutError("timed out")

    with pytest.raises(SignalError, match="timed out") as timed:
        assess_frame(request, transport=explode, environ={"XAI_API_KEY": "test-key"})
    assert timed.value.code == "timeout"


def test_cli_refuses_real_grok_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert main(["--dog", "fake", "--drone", "fake", "--grok", "real"]) == 2
    assert "XAI_API_KEY is unset" in capsys.readouterr().err
    assert main(["--dog", "real", "--drone", "fake", "--grok", "fake"]) == 2


def test_stale_frame_does_not_call_the_connector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setattr("patrol.ground.signal.client.post_json", _transport(seen))
    report = asyncio.run(run_demo(tmp_path / "mission", scenario="stale_frame", grok="real"))
    assert seen.get("count") is None
    assert report["live_call_count"] == 0
    assert report["adapter_modes"] == {"dog": "fake", "drone": "fake", "grok": "real"}
    assert report["outcome"] == "unresolved"
    assert report["evidence"] == "simulated"


def test_happy_path_replaces_the_three_scripted_replies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setattr("patrol.ground.signal.client.post_json", _transport(seen))
    report = asyncio.run(run_demo(tmp_path / "mission", scenario="happy_path", seed=0, grok="real"))
    assert seen.get("count") == 3
    assert report["live_call_count"] == 3
    assert report["adapter_modes"] == {"dog": "fake", "drone": "fake", "grok": "real"}
    assert report["evidence"] == "simulated"
    assert report["goal_reached"] is True
    assert report["landing_verified"] is True
    assert report["outcome"] == "completed"
    assert report["cleanup_errors"] == []
    commands = report["commands"]
    assert all(item["simulated"] is True for item in commands)


@pytest.mark.parametrize(
    ("scenario", "calls"),
    [
        ("happy_path", 3),
        ("unknown_landing", 3),
        ("blocked_planner", 1),
        ("noisy_rssi", 1),
        ("halt", 1),
        ("link_loss", 1),
        ("lease_expiry", 1),
        ("stale_frame", 0),
        ("uncontrolled_motion", 0),
        ("missing_pi_path", 0),
    ],
)
def test_scenarios_hit_the_connector_only_after_a_vision_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    calls: int,
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setattr("patrol.ground.signal.client.post_json", _transport(seen))
    report = asyncio.run(run_demo(tmp_path / "mission", scenario=scenario, grok="real"))
    assert seen.get("count", 0) == calls
    assert report["live_call_count"] == calls
    assert report["evidence"] == "simulated"
    assert report["adapter_modes"]["dog"] == "fake"
    assert report["adapter_modes"]["drone"] == "fake"
    assert report["adapter_modes"]["grok"] == "real"
