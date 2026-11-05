"""Presence frames for the museum story.

Fake mode builds the decision locally and does not read ``XAI_API_KEY``.
Real mode calls Ground's ``assess_frame``. The prompt is ``patrol-presence-v1``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping
from types import ModuleType

from patrol.ground.kernel.paths import repo_root
from patrol.ground.museum.safety import decision_motor_phrase

PROMPT = "patrol-presence-v1"
MODEL = "grok-4.20-non-reasoning"
MISSION = "demo-20261104-001"
_BOX = [0.3, 0.2, 0.55, 0.8]
Json = dict[str, object]


def _presence() -> ModuleType:
    name = "museum_grok_presence"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = repo_root().parent / "person3-grok" / "patrol" / "grok" / "presence.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("presence module is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def frame_document(name: str) -> Json:
    path = repo_root() / "fixtures" / "ground" / "g14" / "accepted" / name
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{name} is not a frame")
    return {str(key): value for key, value in parsed.items()}


def build_request(
    *,
    stage: str,
    sent_at: str,
    expires_at: str,
    track_id: str,
    seq: int,
) -> Json:
    """Ground to vision. The JPEG is a rehearsal fixture, ``simulated`` true."""

    frame_name = "front.json" if stage == "dog_approach" else "downward.json"
    frame = frame_document(frame_name)
    return {
        "protocol_version": "2.0-draft",
        "message_id": f"msg-presence-request-{seq}",
        "mission_id": MISSION,
        "epoch": 1,
        "seq": seq,
        "sent_at": sent_at,
        "source": "ground",
        "destination": "vision",
        "kind": "vision.request",
        "correlation_id": None,
        "expires_at": expires_at,
        "simulated": True,
        "payload": {
            "request_id": f"vision-presence-{seq}",
            "provider": "xai",
            "model_id": MODEL,
            "prompt_version": PROMPT,
            "stage": stage,
            "frame": frame,
            "target_description": "A person in the operator-marked closed demo area.",
            "active_track_id": track_id,
            "scene_context": {"staged_demo": True, "area_closed_by_operator": True},
            "max_evidence_age_ms": 3000,
        },
    }


def scripted_decision(request: Mapping[str, object], state: str, sent_at: str) -> Json:
    """One fake presence reply. Timeout is not a decision."""

    if state == "timeout":
        raise ValueError("timeout does not produce a vision.decision")
    presence = _presence()
    if presence.PRESENCE_PROMPT_VERSION != PROMPT:
        raise RuntimeError("presence prompt version drifted")
    payload_in = request["payload"]
    if not isinstance(payload_in, Mapping):
        raise RuntimeError("request payload")
    frame = payload_in["frame"]
    if not isinstance(frame, Mapping):
        raise RuntimeError("request frame")
    stage = str(payload_in["stage"])
    action = str(presence.suggested_action(stage, state))
    if state == "person_visible":
        direction = str(presence.image_direction(_BOX))
        detections: list[Json] = [
            {
                "label": "person",
                "track_id": payload_in.get("active_track_id"),
                "confidence": 0.91,
                "box_xyxy_norm": list(_BOX),
            }
        ]
        reason = "Person still in frame."
    elif state == "not_visible":
        direction = "unknown"
        detections = []
        reason = "No person in frame."
    elif state == "uncertain":
        direction = "unknown"
        detections = []
        reason = "Presence is uncertain."
    else:
        raise ValueError(f"unknown presence state: {state}")
    decision: Json = {
        "protocol_version": "2.0-draft",
        "message_id": f"msg-decision-{payload_in['request_id']}",
        "mission_id": request["mission_id"],
        "epoch": request["epoch"],
        "seq": request["seq"],
        "sent_at": sent_at,
        "source": "vision",
        "destination": "ground",
        "kind": "vision.decision",
        "correlation_id": request["message_id"],
        "expires_at": None,
        "simulated": True,
        "payload": {
            "request_id": payload_in["request_id"],
            "frame_id": frame["frame_id"],
            "frame_captured_at": frame["captured_at"],
            "provider": "xai",
            "model_id": MODEL,
            "prompt_version": PROMPT,
            "target_state": state,
            "detections": detections,
            "suggested_action": action,
            "image_direction": direction,
            "reason": reason,
        },
    }
    if decision_motor_phrase(decision) is not None:
        raise RuntimeError("scripted decision contained a motor phrase")
    return decision


class ScriptedGrok:
    """Default. No key and no network."""

    def __init__(self) -> None:
        self.calls = 0
        self.decisions: list[Json] = []

    def answer(self, request: Mapping[str, object], state: str, sent_at: str) -> Json | None:
        self.calls += 1
        if state == "timeout":
            return None
        decision = scripted_decision(request, state, sent_at)
        self.decisions.append(decision)
        return decision


class RealGrok:
    """Calls ``assess_frame``. The key stays inside the signal connector."""

    def __init__(self) -> None:
        self.calls = 0
        self.decisions: list[Json] = []

    def answer(self, request: Mapping[str, object], state: str, sent_at: str) -> Json | None:
        del state, sent_at
        from patrol.ground.signal import assess_frame

        self.calls += 1
        decision = assess_frame(request)
        if not isinstance(decision, dict):
            raise RuntimeError("assess_frame did not return an object")
        stored = {str(key): value for key, value in decision.items()}
        self.decisions.append(stored)
        return stored


def summarize_decision(decision: Mapping[str, object]) -> Json:
    payload = decision.get("payload")
    body = payload if isinstance(payload, Mapping) else {}
    return {
        "source": decision.get("source"),
        "kind": decision.get("kind"),
        "target_state": body.get("target_state"),
        "suggested_action": body.get("suggested_action"),
        "prompt_version": body.get("prompt_version"),
        "reason": body.get("reason"),
    }
