"""Build a 2.0-draft vision.request / vision.decision pair for presence."""

from __future__ import annotations

from typing import Mapping

from patrol.grok.presence import (
    DOG_CAMERA,
    DOG_STAGE,
    DRONE_CAMERA,
    PRESENCE_PROMPT_VERSION,
    image_direction,
    suggested_action,
)

PLACEHOLDER_MODEL = "CONFIGURE_VERIFIED_IMAGE_MODEL"
_PERSON_BOX = [0.3, 0.2, 0.55, 0.8]


def camera_for(stage: str) -> str:
    if stage in {DOG_STAGE, "dog_acquire"}:
        return DOG_CAMERA
    return DRONE_CAMERA


def refuse_placeholder_model(model_id: str) -> str:
    if model_id == PLACEHOLDER_MODEL:
        raise ValueError("refuse placeholder model id CONFIGURE_VERIFIED_IMAGE_MODEL")
    if not model_id:
        raise ValueError("model_id is required")
    return model_id


def build_request(
    *,
    stage: str,
    message_id: str,
    request_id: str,
    frame_id: str,
    mission_id: str = "demo-20261104-001",
    epoch: int = 1,
    seq: int = 2,
    sent_at: str = "2026-11-04T13:00:10.100Z",
    expires_at: str = "2026-11-04T13:00:15.100Z",
    captured_at: str = "2026-11-04T13:00:10.000Z",
    active_track_id: str | None = "target-001",
    model_id: str = "grok-4.20-non-reasoning",
    prompt_version: str = PRESENCE_PROMPT_VERSION,
    simulated: bool = True,
) -> dict[str, object]:
    """Ground → vision request. Camera follows the stage. No socket is opened."""
    model_id = refuse_placeholder_model(model_id)
    return {
        "protocol_version": "2.0-draft",
        "message_id": message_id,
        "mission_id": mission_id,
        "epoch": epoch,
        "seq": seq,
        "sent_at": sent_at,
        "source": "ground",
        "destination": "vision",
        "kind": "vision.request",
        "correlation_id": None,
        "expires_at": expires_at,
        "simulated": simulated,
        "payload": {
            "request_id": request_id,
            "provider": "xai",
            "model_id": model_id,
            "prompt_version": prompt_version,
            "stage": stage,
            "frame": {
                "frame_id": frame_id,
                "image_ref": f"artifact://{mission_id}/{stage}/{frame_id}.jpg",
                "sha256": "6a3294c6b81ab68fc54d734be2436d1b317292a0367af713d65c0cd65c688537",
                "captured_at": captured_at,
                "camera_id": camera_for(stage),
                "camera_epoch": 1,
                "width_px": 1280,
                "height_px": 720,
                "camera_frame_id": f"{camera_for(stage)}/frame",
                "camera_to_body_calibration_id": "synthetic-calibration-v1",
                "simulated": simulated,
            },
            "target_description": "A person in the operator-marked closed demo area.",
            "active_track_id": active_track_id,
            "scene_context": {
                "staged_demo": True,
                "area_closed_by_operator": True,
            },
            "max_evidence_age_ms": 3000,
        },
    }


def build_decision(
    request: Mapping[str, object],
    *,
    state: str,
    message_id: str,
    seq: int,
    sent_at: str = "2026-11-04T13:00:10.200Z",
    box_xyxy_norm: list[float] | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Vision → ground decision. ``expires_at`` is always null. Track id is copied."""
    if state == "timeout":
        raise ValueError("timeout does not produce a vision.decision")
    payload_in = request["payload"]
    if not isinstance(payload_in, Mapping):
        raise ValueError("request payload")
    frame = payload_in["frame"]
    if not isinstance(frame, Mapping):
        raise ValueError("request frame")
    stage = str(payload_in["stage"])
    action = suggested_action(stage, state)
    active = payload_in.get("active_track_id")
    if state == "person_visible":
        box = list(box_xyxy_norm or _PERSON_BOX)
        direction = image_direction(box)
        detections: list[dict[str, object]] = [
            {
                "label": "person",
                "track_id": active,
                "confidence": 0.91,
                "box_xyxy_norm": box,
            }
        ]
        default_reason = "Person still in frame."
    else:
        direction = "unknown"
        detections = []
        default_reason = (
            "No person in frame." if state == "not_visible" else "Presence is uncertain."
        )
    return {
        "protocol_version": "2.0-draft",
        "message_id": message_id,
        "mission_id": request["mission_id"],
        "epoch": request["epoch"],
        "seq": seq,
        "sent_at": sent_at,
        "source": "vision",
        "destination": "ground",
        "kind": "vision.decision",
        "correlation_id": request["message_id"],
        "expires_at": None,
        "simulated": request["simulated"],
        "payload": {
            "request_id": payload_in["request_id"],
            "frame_id": frame["frame_id"],
            "frame_captured_at": frame["captured_at"],
            "provider": "xai",
            "model_id": payload_in["model_id"],
            "prompt_version": payload_in["prompt_version"],
            "target_state": state,
            "detections": detections,
            "suggested_action": action,
            "image_direction": direction,
            "reason": reason or default_reason,
        },
    }
