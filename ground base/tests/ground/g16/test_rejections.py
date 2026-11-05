"""Rejections and review outcomes. None of them authorize motion."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.extensions.g16.implementation import VisionDecisionFeature, create
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def _load(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g16" / name
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(name)
    return {str(key): value for key, value in parsed.items()}


def _feature(tmp_path: Path) -> VisionDecisionFeature:
    created = create(build_test_services(output_dir=tmp_path))
    assert isinstance(created, VisionDecisionFeature)
    return created


def _decision() -> dict[str, object]:
    return json.loads(json.dumps(_load("drone-vision-decision.json")))


def _request() -> dict[str, object]:
    return json.loads(json.dumps(_load("drone-vision-request.json")))


def _payload(message: dict[str, object]) -> dict[str, object]:
    raw = message["payload"]
    assert isinstance(raw, dict)
    payload = {str(key): value for key, value in raw.items()}
    message["payload"] = payload
    return payload


def _detection(message: dict[str, object]) -> dict[str, object]:
    raw = _payload(message)["detections"]
    assert isinstance(raw, list) and isinstance(raw[0], dict)
    first = {str(key): value for key, value in raw[0].items()}
    raw[0] = first
    return first


def test_uncertain_and_not_visible_do_not_propose_motion(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    request = _request()
    uncertain = _decision()
    _payload(uncertain)["target_state"] = "uncertain"
    reviewed = feature.assess(uncertain, request, current_track_id="target-001")
    assert reviewed.status == "ok"
    assert reviewed.detail == "review"
    assert reviewed.proposal is None
    assert reviewed.track_changed is False
    assert reviewed.track_id == "target-001"
    hidden = _decision()
    payload = _payload(hidden)
    payload["target_state"] = "not_visible"
    payload["detections"] = []
    held = feature.assess(hidden, request)
    assert held.detail == "hold"
    assert held.proposal is None
    assert held.motion_authorized is False


def test_unordered_box_and_foreign_frame_fail(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    request = _request()
    unordered = _decision()
    _detection(unordered)["box_xyxy_norm"] = [0.8, 0.2, 0.3, 0.9]
    rejected = feature.assess(unordered, request, current_track_id="target-001")
    assert rejected.status == "failed"
    assert rejected.error_code == "rejected"
    assert rejected.detail == "unordered_box"
    assert rejected.track_id == "target-001"
    assert rejected.proposal is None
    foreign = _decision()
    _payload(foreign)["frame_id"] = "other-frame"
    mismatched = feature.assess(foreign, request, current_track_id="target-001")
    assert mismatched.detail == "frame_mismatch"
    assert mismatched.track_changed is False
    assert mismatched.track_id == "target-001"


def test_late_decision_and_old_epoch_do_not_move_the_track(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    request = _request()
    late = _decision()
    late["sent_at"] = "2026-11-04T13:00:14.000Z"
    feature.services.kernel.authority.latch_cancel("operator halt")
    dropped = feature.assess(
        late,
        request,
        current_track_id="target-001",
        halt_latched=True,
    )
    assert dropped.status == "blocked"
    assert dropped.error_code == "expired_deadline"
    assert dropped.track_changed is False
    assert dropped.track_id == "target-001"
    assert dropped.proposal is None
    assert dropped.halt_latched is True
    assert feature.services.kernel.authority.cancelled is True
    stale = feature.assess(
        _decision(),
        request,
        current_track_id="target-001",
        current_camera_epoch=2,
        halt_latched=True,
    )
    assert stale.error_code == "epoch_mismatch"
    assert stale.track_changed is False
    assert stale.halt_latched is True
    assert feature.services.kernel.authority.cancelled is True


def test_two_people_need_review_unless_one_is_associated(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    request = _request()
    decision = _decision()
    payload = _payload(decision)
    found = payload["detections"]
    assert isinstance(found, list) and isinstance(found[0], dict)
    second = {str(key): value for key, value in found[0].items()}
    second["box_xyxy_norm"] = [0.6, 0.1, 0.9, 0.95]
    second["track_id"] = "target-001"
    found.append(second)
    reviewed = feature.assess(decision, request, current_track_id="target-001")
    assert reviewed.detail == "review"
    assert reviewed.proposal is None
    assert reviewed.track_changed is False
    associated = feature.assess(
        decision,
        request,
        current_track_id="target-001",
        staged_association=True,
    )
    assert associated.track_id == "target-001"
    assert associated.track_changed is True
    assert associated.proposal is not None


def test_sdk_text_labels_and_string_booleans_are_rejected(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    request = _request()
    sdk = _decision()
    _payload(sdk)["sdk_command"] = "takeoff"
    unknown = feature.assess(sdk, request)
    assert unknown.status == "failed"
    assert unknown.error_code == "validation_failed"
    assert unknown.detail == "unknown_field:sdk_command"
    assert unknown.proposal is None
    reason = _decision()
    _payload(reason)["reason"] = "takeoff"
    told = feature.assess(reason, request)
    assert told.detail == "sdk_reason"
    rc = _decision()
    _payload(rc)["reason"] = "rc 0 0 0 0"
    assert feature.assess(rc, request).detail == "sdk_reason"
    distance = _decision()
    _payload(distance)["reason"] = "move five meters"
    assert feature.assess(distance, request).detail == "invented_distance"
    weapon = _decision()
    _detection(weapon)["label"] = "weapon"
    assert feature.assess(weapon, request).detail == "label_rejected"
    intent = _decision()
    _detection(intent)["label"] = "intent"
    assert feature.assess(intent, request).detail == "label_rejected"
    name = _decision()
    _detection(name)["label"] = "name"
    assert feature.assess(name, request).detail == "label_rejected"
    flagged = _decision()
    flagged["simulated"] = "true"
    assert feature.assess(flagged, request).detail == "boolean_required"
    scored = _decision()
    _detection(scored)["confidence"] = "0.91"
    assert feature.assess(scored, request).detail == "bad_confidence"


def test_uncalibrated_reposition_becomes_a_hold(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    decision = _decision()
    payload = _payload(decision)
    payload["suggested_action"] = "reposition"
    payload["image_direction"] = "left"
    request = _request()
    frame = request["payload"]
    assert isinstance(frame, dict)
    inner = frame["frame"]
    assert isinstance(inner, dict)
    inner["camera_to_body_calibration_id"] = None
    assessed = feature.assess(decision, request)
    assert assessed.detail == "hold"
    assert assessed.track_id == "target-001"
    assert assessed.proposal is not None
    body = assessed.proposal["payload"]
    assert isinstance(body, dict)
    assert body["action"] == "hold"
    assert body["direction_hint"] == "left"
    assert "motion" not in body
    assert assessed.motion_authorized is True


def test_dog_track_mismatch_does_not_replace_the_drone_track(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    decision = json.loads(json.dumps(_load("dog-vision-decision.json")))
    assert isinstance(decision, dict)
    payload = decision["payload"]
    assert isinstance(payload, dict)
    detections = payload["detections"]
    assert isinstance(detections, list) and isinstance(detections[0], dict)
    detections[0]["track_id"] = "target-999"
    request = _load("dog-vision-request.json")
    assessed = feature.assess(decision, request, current_track_id="target-001")
    assert assessed.status == "failed"
    assert assessed.detail == "track_mismatch"
    assert assessed.track_id == "target-001"
    assert assessed.track_changed is False
    assert assessed.proposal is None
