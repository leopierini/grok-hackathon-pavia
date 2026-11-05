"""Decide when the dog leaves RSSI guidance for its own camera.

The model may suggest a switch. This module counts fresh dog-camera hits
and never emits a motion command, a proximity goal, or an arrival.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TypeGuard

from patrol.ground.kernel.faults import fault

_ENVELOPE = frozenset(
    {
        "protocol_version",
        "message_id",
        "mission_id",
        "epoch",
        "seq",
        "sent_at",
        "source",
        "destination",
        "kind",
        "correlation_id",
        "expires_at",
        "simulated",
        "payload",
    }
)
_DECISION = frozenset(
    {
        "request_id",
        "frame_id",
        "frame_captured_at",
        "provider",
        "model_id",
        "prompt_version",
        "target_state",
        "detections",
        "suggested_action",
        "image_direction",
        "reason",
    }
)
_FRAME = frozenset(
    {
        "frame_id",
        "image_ref",
        "sha256",
        "captured_at",
        "camera_id",
        "camera_epoch",
        "width_px",
        "height_px",
        "camera_frame_id",
        "camera_to_body_calibration_id",
        "simulated",
    }
)
_DETECTION = frozenset({"label", "track_id", "confidence", "box_xyxy_norm"})
_STATES = frozenset({"person_visible", "not_visible", "uncertain"})
_ACTIONS = frozenset(
    {
        "continue_search",
        "hold",
        "reposition",
        "dispatch_dog",
        "continue_homing",
        "switch_to_dog_vision",
        "approach",
        "stop",
        "review",
        "play_warning",
        "follow",
        "return_home",
        "land_on_dog",
    }
)
_DIRECTIONS = frozenset({"left", "center", "right", "unknown"})
_DEFAULT_BUDGET_MS = 3000
_DEFAULT_THRESHOLD = 2
_HANDOFF_REASON = (
    "The same track was visible on enough fresh dog frames. "
    "RSSI remains supporting evidence."
)


@dataclass(frozen=True)
class Outcome:
    status: str
    mode: str
    phase: str
    rssi_role: str
    hit_count: int
    frame_ids: tuple[str, ...]
    track_id: str
    resets: tuple[str, ...]
    ignored: tuple[tuple[str, str], ...]
    reason_token: str
    error_code: str
    error_detail: str
    handoff: bool
    rssi_records: tuple[Mapping[str, object], ...]
    journal: Mapping[str, object] | None


def evaluate(payload: Mapping[str, object]) -> Outcome:
    """Classify one dog-acquire batch. RSSI records are copied, never deleted."""
    track_id = _text(payload.get("track_id"), "track_id")
    camera_epoch = _whole(payload.get("camera_epoch"), "camera_epoch")
    observed_at = _time(payload.get("observed_at"), "observed_at")
    budget_ms = _optional_whole(
        payload.get("evidence_budget_ms", _DEFAULT_BUDGET_MS),
        "evidence_budget_ms",
        default=_DEFAULT_BUDGET_MS,
    )
    if budget_ms < 1:
        return _failed("invalid_input", "evidence_budget_ms", "evidence budget must be positive")
    threshold = _optional_whole(
        payload.get("consecutive_hit_threshold", _DEFAULT_THRESHOLD),
        "consecutive_hit_threshold",
        default=_DEFAULT_THRESHOLD,
    )
    if threshold < 1:
        return _failed(
            "invalid_input",
            "consecutive_hit_threshold",
            "consecutive hit threshold must be at least 1",
        )
    homing = payload.get("homing_allowed", True)
    if not isinstance(homing, bool):
        return _failed("invalid_input", "homing_allowed", "homing_allowed must be a boolean")
    frames = _frame_index(payload.get("frames"))
    if isinstance(frames, Outcome):
        return frames
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        return _failed("invalid_input", "decisions", "decisions must be a list")
    requests = _request_index(payload.get("requests", []))
    if isinstance(requests, Outcome):
        return requests
    records = _rssi_records(payload.get("rssi_records", []))
    if isinstance(records, Outcome):
        return records

    hits: list[str] = []
    resets: list[str] = []
    ignored: list[tuple[str, str]] = []
    review = False
    saw_dog = False
    saw_drone = False
    last_problem = ""
    hit_decisions: list[Mapping[str, object]] = []

    for item in decisions:
        parsed = _decision(item)
        if isinstance(parsed, Outcome):
            return parsed
        decision, body, frame_id = parsed
        frame = frames.get(frame_id)
        if frame is None:
            return _failed(
                "validation_failed",
                "missing_frame",
                f"decision frame {frame_id} is not in the frame set",
            )
        if frame.get("captured_at") != body.get("frame_captured_at"):
            return _failed(
                "validation_failed",
                "capture_time",
                "frame capture time does not match the decision",
            )
        role = _camera_role(frame)
        if role == "drone":
            saw_drone = True
            ignored.append(("drone", frame_id))
            continue
        if role != "dog":
            return _failed(
                "rejected",
                "unknown_camera",
                "decision frame is not the dog front camera",
            )
        saw_dog = True
        request = requests.get(_text(body.get("request_id"), "request_id"))
        if requests and request is None:
            return _failed(
                "validation_failed",
                "request",
                "decision request_id does not match a vision request",
            )
        if request is not None:
            stage = _request_stage(request, frame_id, track_id)
            if isinstance(stage, Outcome):
                return stage
            if stage not in {"dog_acquire", "dog_approach"}:
                ignored.append(("wrong_stage", frame_id))
                last_problem = "wrong_stage"
                continue
        frame_epoch = frame.get("camera_epoch")
        if frame_epoch != camera_epoch:
            hits.clear()
            hit_decisions.clear()
            resets.append("camera_epoch")
            ignored.append(("camera_epoch", frame_id))
            last_problem = "camera_epoch"
            continue
        captured = _time(frame.get("captured_at"), "captured_at")
        age_ms = (observed_at - captured).total_seconds() * 1000
        if age_ms < 0 or age_ms > budget_ms:
            hits.clear()
            hit_decisions.clear()
            token = "stale" if age_ms >= 0 else "future"
            resets.append(token)
            ignored.append((token, frame_id))
            last_problem = token
            continue
        state = body.get("target_state")
        if state in {"not_visible", "uncertain"}:
            hits.clear()
            hit_decisions.clear()
            token = str(state)
            resets.append(token)
            ignored.append((token, frame_id))
            last_problem = token
            if not homing:
                review = True
            continue
        detections = body.get("detections")
        if not isinstance(detections, list):
            return _failed("validation_failed", "detections", "detections must be a list")
        if len(detections) == 0:
            hits.clear()
            hit_decisions.clear()
            resets.append("empty")
            ignored.append(("empty", frame_id))
            last_problem = "empty"
            continue
        if not _single_match(detections, track_id):
            hits.clear()
            hit_decisions.clear()
            review = True
            resets.append("review")
            ignored.append(("review", frame_id))
            last_problem = "review"
            continue
        if review:
            ignored.append(("review", frame_id))
            continue
        if frame_id in hits:
            ignored.append(("duplicate", frame_id))
            last_problem = "duplicate"
            continue
        hits.append(frame_id)
        hit_decisions.append(decision)
        last_problem = ""

    if review:
        return _ok(
            mode="review",
            phase="review",
            rssi_role="primary",
            hits=(),
            track_id=track_id,
            resets=tuple(resets),
            ignored=tuple(ignored),
            records=records,
            journal=None,
        )
    if len(hits) >= threshold:
        journal = _journal(
            decisions=tuple(hit_decisions),
            frame_ids=tuple(hits),
            track_id=track_id,
            camera_epoch=camera_epoch,
            observed_at=payload.get("observed_at"),
            records=records,
        )
        return _ok(
            mode="visual",
            phase="handed_off",
            rssi_role="supporting",
            hits=tuple(hits),
            track_id=track_id,
            resets=tuple(resets),
            ignored=tuple(ignored),
            records=records,
            journal=journal,
        )
    if not saw_dog and saw_drone:
        return _blocked(
            "drone_camera",
            track_id,
            resets=tuple(resets),
            ignored=tuple(ignored),
            records=records,
        )
    if last_problem == "camera_epoch":
        return _blocked(
            "camera_epoch",
            track_id,
            resets=tuple(resets),
            ignored=tuple(ignored),
            records=records,
        )
    if last_problem == "wrong_stage" and not hits:
        return _blocked(
            "wrong_stage",
            track_id,
            resets=tuple(resets),
            ignored=tuple(ignored),
            records=records,
        )
    phase = "acquiring" if hits else "rssi"
    mode = "rssi"
    return _ok(
        mode=mode,
        phase=phase,
        rssi_role="primary",
        hits=tuple(hits),
        track_id=track_id,
        resets=tuple(resets),
        ignored=tuple(ignored),
        records=records,
        journal=None,
    )


def detail_of(outcome: Outcome) -> str:
    if outcome.status != "ok":
        return outcome.error_detail
    if outcome.phase == "acquiring":
        return "acquiring"
    return outcome.mode


def trace_of(outcome: Outcome) -> tuple[str, ...]:
    if outcome.status != "ok":
        lines = ["rejected", outcome.reason_token]
    else:
        lines = [
            f"mode:{outcome.mode}",
            f"phase:{outcome.phase}",
            f"rssi_role:{outcome.rssi_role}",
            f"hits:{outcome.hit_count}",
        ]
    lines.extend(["command:none", "goal:none", "arrival:none", "selection:none"])
    lines.extend(f"reset:{item}" for item in outcome.resets)
    lines.extend(f"ignored:{reason}:{frame_id}" for reason, frame_id in outcome.ignored)
    lines.extend(f"frame:{item}" for item in outcome.frame_ids)
    if outcome.handoff:
        lines.append("event:decision_received")
    lines.append(f"rssi_records:{len(outcome.rssi_records)}")
    return tuple(lines)


def _ok(
    *,
    mode: str,
    phase: str,
    rssi_role: str,
    hits: tuple[str, ...],
    track_id: str,
    resets: tuple[str, ...],
    ignored: tuple[tuple[str, str], ...],
    records: tuple[Mapping[str, object], ...],
    journal: Mapping[str, object] | None,
) -> Outcome:
    return Outcome(
        status="ok",
        mode=mode,
        phase=phase,
        rssi_role=rssi_role,
        hit_count=len(hits),
        frame_ids=hits,
        track_id=track_id,
        resets=resets,
        ignored=ignored,
        reason_token="",
        error_code="",
        error_detail="",
        handoff=journal is not None,
        rssi_records=records,
        journal=journal,
    )


def _blocked(
    token: str,
    track_id: str,
    *,
    resets: tuple[str, ...],
    ignored: tuple[tuple[str, str], ...],
    records: tuple[Mapping[str, object], ...],
) -> Outcome:
    return Outcome(
        status="blocked",
        mode="rssi",
        phase="rssi",
        rssi_role="primary",
        hit_count=0,
        frame_ids=(),
        track_id=track_id,
        resets=resets,
        ignored=ignored,
        reason_token=token,
        error_code="rejected",
        error_detail=f"rejected:{token}",
        handoff=False,
        rssi_records=records,
        journal=None,
    )


def _failed(code: str, token: str, detail: str) -> Outcome:
    return Outcome(
        status="failed",
        mode="rssi",
        phase="rssi",
        rssi_role="primary",
        hit_count=0,
        frame_ids=(),
        track_id="",
        resets=(),
        ignored=(),
        reason_token=token,
        error_code=code,
        error_detail=detail,
        handoff=False,
        rssi_records=(),
        journal=None,
    )


def _journal(
    *,
    decisions: tuple[Mapping[str, object], ...],
    frame_ids: tuple[str, ...],
    track_id: str,
    camera_epoch: int,
    observed_at: object,
    records: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    last = decisions[-1]
    body = last["payload"]
    if not isinstance(body, Mapping):
        raise fault("validation_failed", "decision payload is not an object")
    beacon_epoch, map_epoch = _correlation(records)
    details: dict[str, object] = {
        "message_id": "msg-dog-vision-handoff",
        "mission_id": last.get("mission_id"),
        "epoch": last.get("epoch"),
        "request_id": body.get("request_id"),
        "frame_id": frame_ids[-1],
        "frame_ids": list(frame_ids),
        "track_id": track_id,
        "beacon_epoch": beacon_epoch,
        "map_epoch": map_epoch,
        "camera_epoch": camera_epoch,
        "rssi_role": "supporting",
        "mode": "visual",
        "command": None,
        "goal_reached": False,
    }
    return {
        "protocol_version": "2.0-draft",
        "message_id": "msg-dog-vision-handoff",
        "mission_id": last.get("mission_id"),
        "epoch": last.get("epoch"),
        "seq": last.get("seq"),
        "sent_at": observed_at,
        "source": "ground",
        "destination": "all",
        "kind": "mission.event",
        "correlation_id": last.get("message_id"),
        "expires_at": None,
        "simulated": all(item.get("simulated") is True for item in decisions),
        "payload": {
            "event": "dog_vision_handoff",
            "phase": "dog_acquire",
            "outcome": None,
            "device_recovery_required": False,
            "reason": _HANDOFF_REASON,
            "details": details,
        },
    }


def _correlation(
    records: tuple[Mapping[str, object], ...],
) -> tuple[int | None, int | None]:
    if not records:
        return None, None
    body = records[0].get("payload")
    if not isinstance(body, Mapping):
        return None, None
    beacon = body.get("beacon_epoch")
    beacon_epoch = beacon if _is_whole(beacon) else None
    map_epoch: int | None = None
    samples = body.get("samples")
    if isinstance(samples, list) and samples and isinstance(samples[0], Mapping):
        pose = samples[0].get("pose")
        if isinstance(pose, Mapping):
            raw_map = pose.get("map_epoch")
            if _is_whole(raw_map):
                map_epoch = raw_map
    return beacon_epoch, map_epoch


def _frame_index(value: object) -> dict[str, Mapping[str, object]] | Outcome:
    if not isinstance(value, list):
        return _failed("invalid_input", "frames", "frames must be a list")
    found: dict[str, Mapping[str, object]] = {}
    for item in value:
        frame = _frame(item)
        if isinstance(frame, Outcome):
            return frame
        frame_id = frame["frame_id"]
        if not isinstance(frame_id, str):
            return _failed("validation_failed", "frame_id", "frame_id must be a string")
        if frame_id in found:
            return _failed("invalid_input", "frame_id", f"duplicate frame_id {frame_id}")
        found[frame_id] = frame
    return found


def _request_index(value: object) -> dict[str, Mapping[str, object]] | Outcome:
    if value is None:
        return {}
    if not isinstance(value, list):
        return _failed("invalid_input", "requests", "requests must be a list")
    found: dict[str, Mapping[str, object]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            return _failed("validation_failed", "request", "vision request must be an object")
        _exact(item, _ENVELOPE, "vision request")
        if item.get("kind") != "vision.request":
            return _failed("validation_failed", "request", "request kind must be vision.request")
        body = item.get("payload")
        if not isinstance(body, Mapping):
            return _failed("validation_failed", "request", "request payload must be an object")
        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            return _failed("validation_failed", "request_id", "request_id must be a string")
        found[request_id] = item
    return found


def _request_stage(
    request: Mapping[str, object],
    frame_id: str,
    track_id: str,
) -> str | Outcome:
    body = request.get("payload")
    if not isinstance(body, Mapping):
        return _failed("validation_failed", "request", "request payload must be an object")
    stage = body.get("stage")
    if not isinstance(stage, str) or not stage:
        return _failed("validation_failed", "stage", "request stage must be a string")
    frame = body.get("frame")
    if not isinstance(frame, Mapping) or frame.get("frame_id") != frame_id:
        return _failed(
            "validation_failed",
            "request_frame",
            "request frame_id does not match the decision",
        )
    active = body.get("active_track_id")
    if active is not None and active != track_id:
        return _failed(
            "validation_failed",
            "request_track",
            "request active_track_id does not match the dog track",
        )
    return stage


def _decision(
    value: object,
) -> tuple[Mapping[str, object], Mapping[str, object], str] | Outcome:
    if not isinstance(value, Mapping):
        return _failed("validation_failed", "decision", "vision decision must be an object")
    _exact(value, _ENVELOPE, "vision decision")
    if value.get("protocol_version") != "2.0-draft":
        return _failed("validation_failed", "protocol", "protocol_version must be 2.0-draft")
    if value.get("kind") != "vision.decision":
        return _failed("validation_failed", "kind", "kind must be vision.decision")
    if value.get("source") != "vision" or value.get("destination") != "ground":
        return _failed("validation_failed", "route", "decision route must be vision to ground")
    if not isinstance(value.get("simulated"), bool):
        return _failed("validation_failed", "simulated", "simulated must be a boolean")
    _whole(value.get("epoch"), "epoch")
    _whole(value.get("seq"), "seq")
    _text(value.get("message_id"), "message_id")
    _text(value.get("mission_id"), "mission_id")
    _time(value.get("sent_at"), "sent_at")
    _optional_text(value.get("correlation_id"), "correlation_id")
    _optional_text(value.get("expires_at"), "expires_at")
    body = value.get("payload")
    if not isinstance(body, Mapping):
        return _failed("validation_failed", "payload", "decision payload must be an object")
    _exact(body, _DECISION, "decision payload")
    if body.get("provider") != "xai":
        return _failed("validation_failed", "provider", "provider must be xai")
    _text(body.get("model_id"), "model_id")
    _text(body.get("prompt_version"), "prompt_version")
    _text(body.get("request_id"), "request_id")
    _text(body.get("reason"), "reason")
    if body.get("target_state") not in _STATES:
        return _failed("validation_failed", "target_state", "target_state is not allowed")
    if body.get("suggested_action") not in _ACTIONS:
        return _failed("validation_failed", "suggested_action", "suggested_action is not allowed")
    if body.get("image_direction") not in _DIRECTIONS:
        return _failed("validation_failed", "image_direction", "image_direction is not allowed")
    frame_id = _text(body.get("frame_id"), "frame_id")
    _time(body.get("frame_captured_at"), "frame_captured_at")
    detections = body.get("detections")
    if not isinstance(detections, list) or len(detections) > 10:
        return _failed("validation_failed", "detections", "detections must be a list of at most 10")
    for detection in detections:
        checked = _detection(detection)
        if isinstance(checked, Outcome):
            return checked
    return value, body, frame_id


def _detection(value: object) -> Mapping[str, object] | Outcome:
    if not isinstance(value, Mapping):
        return _failed("validation_failed", "detection", "detection must be an object")
    _exact(value, _DETECTION, "detection")
    if value.get("label") != "person":
        return _failed("validation_failed", "label", "detection label must be person")
    track = value.get("track_id")
    if track is not None and (not isinstance(track, str) or not track):
        return _failed(
            "validation_failed",
            "track_id",
            "detection track_id must be a string or null",
        )
    confidence = value.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return _failed("validation_failed", "confidence", "confidence must be a number")
    if not 0 <= float(confidence) <= 1:
        return _failed("validation_failed", "confidence", "confidence must be from 0 to 1")
    box = value.get("box_xyxy_norm")
    if not isinstance(box, list) or len(box) != 4:
        return _failed("validation_failed", "box", "box_xyxy_norm must contain four numbers")
    numbers: list[float] = []
    for item in box:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return _failed("validation_failed", "box", "box coordinates must be numbers")
        if not 0 <= float(item) <= 1:
            return _failed("validation_failed", "box", "box coordinates must be from 0 to 1")
        numbers.append(float(item))
    if numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
        return _failed("validation_failed", "box", "box endpoints must be ordered")
    return value


def _frame(value: object) -> Mapping[str, object] | Outcome:
    if not isinstance(value, Mapping):
        return _failed("validation_failed", "frame", "frame must be an object")
    _exact(value, _FRAME, "frame")
    _text(value.get("frame_id"), "frame_id")
    _text(value.get("image_ref"), "image_ref")
    digest = value.get("sha256")
    hex_ok = isinstance(digest, str) and len(digest) == 64
    if hex_ok and isinstance(digest, str):
        hex_ok = all(ch in "0123456789abcdef" for ch in digest)
    if not hex_ok:
        return _failed("validation_failed", "sha256", "sha256 must be 64 lowercase hex characters")
    _time(value.get("captured_at"), "captured_at")
    if value.get("camera_id") not in {"front", "downward"}:
        return _failed("validation_failed", "camera_id", "camera_id must be front or downward")
    _whole(value.get("camera_epoch"), "camera_epoch")
    width = value.get("width_px")
    height = value.get("height_px")
    if not _is_whole(width) or width < 1 or not _is_whole(height) or height < 1:
        return _failed("validation_failed", "size", "frame width and height must be positive")
    _text(value.get("camera_frame_id"), "camera_frame_id")
    calibration = value.get("camera_to_body_calibration_id")
    if calibration is not None and (not isinstance(calibration, str) or not calibration):
        return _failed(
            "validation_failed",
            "calibration",
            "calibration id must be a string or null",
        )
    if not isinstance(value.get("simulated"), bool):
        return _failed("validation_failed", "simulated", "frame simulated must be a boolean")
    return value


def _rssi_records(value: object) -> tuple[Mapping[str, object], ...] | Outcome:
    if value is None:
        return ()
    if not isinstance(value, list):
        return _failed("invalid_input", "rssi_records", "rssi_records must be a list")
    kept: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return _failed("validation_failed", "rssi", "rssi record must be an object")
        if item.get("kind") != "rssi.window":
            return _failed("validation_failed", "rssi", "rssi record kind must be rssi.window")
        message_id = item.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            return _failed("validation_failed", "rssi", "rssi message_id is required")
        kept.append(dict(item))
    return tuple(kept)


def _single_match(detections: list[object], track_id: str) -> bool:
    if len(detections) != 1 or not isinstance(detections[0], Mapping):
        return False
    return detections[0].get("label") == "person" and detections[0].get("track_id") == track_id


def _camera_role(frame: Mapping[str, object]) -> str:
    camera_id = frame.get("camera_id")
    frame_id = frame.get("frame_id")
    camera_frame_id = frame.get("camera_frame_id")
    drone = (
        camera_id == "downward"
        or (isinstance(frame_id, str) and frame_id.startswith("drone"))
        or (isinstance(camera_frame_id, str) and camera_frame_id.startswith("drone/"))
    )
    if drone:
        return "drone"
    dog_frame = isinstance(camera_frame_id, str) and camera_frame_id.startswith("dog/")
    if camera_id == "front" and dog_frame:
        return "dog"
    return "unknown"


def _exact(value: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = [key for key in value if key not in allowed]
    missing = [key for key in allowed if key not in value]
    if unknown or missing:
        detail = f"{label} keys do not match the contract"
        raise fault("validation_failed", detail)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{label} must be a string")
    return value


def _optional_text(value: object, label: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise fault("invalid_input", f"{label} must be a string or null")


def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise fault("invalid_input", f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise fault("invalid_input", f"{label} is not a timestamp") from exc
    if parsed.tzinfo is None:
        raise fault("invalid_input", f"{label} must include a timezone")
    return parsed


def _whole(value: object, label: str) -> int:
    if not _is_whole(value):
        raise fault("invalid_input", f"{label} must be a non-negative integer")
    return value


def _optional_whole(value: object, label: str, *, default: int) -> int:
    if value == default:
        return default
    return _whole(value, label)


def _is_whole(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
