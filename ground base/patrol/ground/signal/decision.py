"""Map one model reading onto a Task 16 ``vision.decision``.

Stage rules for this rehearsal:

- ``drone_search`` may leave ``track_id`` null. ``suggested_action`` is
  ``reposition`` and ``image_direction`` is ``left`` so the allowlisted
  left track step can continue the demo.
- ``dog_acquire`` uses track ``target-001`` and ``switch_to_dog_vision``.

The reason is plain language. Motor and SDK wording is replaced before
Ground's checker sees it. ``simulated`` stays true for fixture JPEGs.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from patrol.ground.signal.errors import SignalError

_STATES = frozenset({"person_visible", "not_visible", "uncertain"})
_TELLO_EXACT = frozenset(
    {
        "command",
        "takeoff",
        "land",
        "streamon",
        "streamoff",
        "emergency",
        "stop",
        "speed",
        "battery?",
        "speed?",
        "time?",
        "sdk",
        "sdk_command",
    }
)
_TELLO_PREFIXES = (
    "rc ",
    "go ",
    "curve ",
    "cw ",
    "ccw ",
    "forward ",
    "back ",
    "left ",
    "right ",
    "up ",
    "down ",
    "flip ",
    "motor ",
)
_DISTANCE = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s*(?:m|cm|mm|meters?|metres?)|(?:five|ten|twenty|fifty)\s+met(?:er|re)s?)\b",
    re.IGNORECASE,
)
_STAGES = frozenset({"drone_search", "drone_track", "dog_acquire", "dog_approach"})
_FALLBACK = {
    "person_visible": "A person is visible in the staged demo frame.",
    "not_visible": "No person is clearly visible in the staged demo frame.",
    "uncertain": "The staged demo frame is uncertain.",
}


@dataclass(frozen=True)
class Reading:
    """Fields taken from the model. Track identity and the action are not."""

    target_state: str
    confidence: float | None
    box: tuple[float, float, float, float] | None
    reason: str


def reading_from_model(payload: Mapping[str, object]) -> Reading:
    state = payload.get("target_state")
    if not isinstance(state, str) or state not in _STATES:
        raise SignalError("invalid_input", "model target_state is not a vision state")
    reason = payload.get("reason")
    if not isinstance(reason, str):
        reason = ""
    if state != "person_visible":
        return Reading(state, None, None, _plain_reason(reason, state))
    confidence = _confidence(payload.get("confidence"))
    box = _box(payload.get("box_xyxy_norm"))
    return Reading(state, confidence, box, _plain_reason(reason, state))


def decision_from_reading(
    request: Mapping[str, object],
    reading: Reading,
    *,
    model_id: str,
) -> dict[str, object]:
    """Build the envelope Ground's Task 16 checker accepts."""

    if request.get("kind") != "vision.request":
        raise SignalError("invalid_input", "request kind must be vision.request")
    if request.get("source") != "ground" or request.get("destination") != "vision":
        raise SignalError("invalid_input", "request route must be ground to vision")
    if request.get("simulated") is not True:
        raise SignalError("unsafe_state", "rehearsal image evidence must stay simulated")
    payload = _object(request.get("payload"), "request payload")
    frame = _object(payload.get("frame"), "request frame")
    if frame.get("simulated") is not True:
        raise SignalError("unsafe_state", "rehearsal image evidence must stay simulated")
    stage = payload.get("stage")
    if not isinstance(stage, str) or not stage:
        raise SignalError("invalid_input", "request stage is missing")
    request_id = _text(payload.get("request_id"), "request_id")
    frame_id = _text(frame.get("frame_id"), "frame_id")
    captured = _text(frame.get("captured_at"), "frame_captured_at")
    message_id = _text(request.get("message_id"), "message_id")
    prompt = _text(payload.get("prompt_version"), "prompt_version")
    active = payload.get("active_track_id")
    active_track = active if isinstance(active, str) and active else None
    track_id, action, direction = _stage_policy(stage, active_track, reading)
    detections: list[dict[str, object]] = []
    if reading.target_state == "person_visible":
        if reading.box is None or reading.confidence is None:
            raise SignalError("invalid_input", "a visible person needs a box and a confidence")
        detections.append(
            {
                "label": "person",
                "track_id": track_id,
                "confidence": reading.confidence,
                "box_xyxy_norm": [reading.box[0], reading.box[1], reading.box[2], reading.box[3]],
            }
        )
    sent_at = request.get("sent_at")
    if not isinstance(sent_at, str) or not sent_at:
        sent_at = captured
    seq = request.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        seq = 1
    epoch = request.get("epoch")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        raise SignalError("invalid_input", "request epoch must be a whole number")
    return {
        "protocol_version": "2.0-draft",
        "message_id": f"msg-decision-{request_id}",
        "mission_id": _text(request.get("mission_id"), "mission_id"),
        "epoch": epoch,
        "seq": seq,
        "sent_at": sent_at,
        "source": "vision",
        "destination": "ground",
        "kind": "vision.decision",
        "correlation_id": message_id,
        "expires_at": None,
        "simulated": True,
        "payload": {
            "request_id": request_id,
            "frame_id": frame_id,
            "frame_captured_at": captured,
            "provider": "xai",
            "model_id": model_id,
            "prompt_version": prompt,
            "target_state": reading.target_state,
            "detections": detections,
            "suggested_action": action,
            "image_direction": direction,
            "reason": reading.reason,
        },
    }


def _stage_policy(
    stage: str,
    active_track: str | None,
    reading: Reading,
) -> tuple[str | None, str, str]:
    if stage not in _STAGES:
        raise SignalError("invalid_input", f"unknown vision stage: {stage}")
    if reading.target_state != "person_visible":
        return None, "review", "unknown"
    direction = _direction(reading.box)
    if stage == "drone_search":
        return None, "reposition", "left"
    if stage == "dog_acquire":
        if active_track not in {None, "target-001"}:
            raise SignalError("rejected", "dog_acquire track_id must be target-001")
        return "target-001", "switch_to_dog_vision", direction
    if stage == "dog_approach":
        if active_track is None:
            raise SignalError("rejected", "dog_approach requires an active track")
        return active_track, "approach", direction
    return active_track, "hold", direction


def _direction(box: tuple[float, float, float, float] | None) -> str:
    if box is None:
        return "unknown"
    centre = (box[0] + box[2]) / 2.0
    if centre < (1.0 / 3.0):
        return "left"
    if centre < (2.0 / 3.0):
        return "center"
    return "right"


def _plain_reason(reason: str, state: str) -> str:
    fallback = _FALLBACK[state]
    text = " ".join(reason.strip().lower().split())
    if not text:
        return fallback
    if text in _TELLO_EXACT or any(text.startswith(prefix) for prefix in _TELLO_PREFIXES):
        return fallback
    if _DISTANCE.search(text):
        return fallback
    return reason.strip()


def _confidence(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise SignalError("invalid_input", "model confidence must be a number from 0 to 1")
    score = float(value)
    if score < 0 or score > 1:
        raise SignalError("invalid_input", "model confidence must be a number from 0 to 1")
    return score


_BOX = "model box_xyxy_norm must be four numbers from 0 to 1"


def _box(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise SignalError("invalid_input", _BOX)
    numbers: list[float] = []
    for item in value:
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
        ):
            raise SignalError("invalid_input", _BOX)
        number = float(item)
        if number < 0 or number > 1:
            raise SignalError("invalid_input", _BOX)
        numbers.append(number)
    xmin, ymin, xmax, ymax = numbers
    if not (xmin < xmax and ymin < ymax):
        raise SignalError("invalid_input", "model box_xyxy_norm endpoints must be ordered")
    return xmin, ymin, xmax, ymax


def _object(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    raise SignalError("invalid_input", f"{label} must be an object")


def _text(value: object, label: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    raise SignalError("invalid_input", f"{label} is missing")
