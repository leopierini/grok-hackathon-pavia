"""Validate one vision.decision. A detection never becomes a motor command."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

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
_DECISION_PAYLOAD = frozenset(
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
_REQUEST_PAYLOAD = frozenset(
    {
        "request_id",
        "provider",
        "model_id",
        "prompt_version",
        "stage",
        "frame",
        "target_description",
        "active_track_id",
        "scene_context",
        "max_evidence_age_ms",
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
_TARGET_STATES = frozenset({"person_visible", "not_visible", "uncertain"})
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
_STAGES = frozenset({"drone_search", "drone_track", "dog_acquire", "dog_approach"})
_DOG_STAGES = frozenset({"dog_acquire", "dog_approach"})
_BODY_MOVES = frozenset(
    {"reposition", "approach", "dispatch_dog", "continue_search", "continue_homing"}
)
_PROPOSAL_ACTION = {
    "hold": "hold",
    "reposition": "reposition",
    "continue_search": "search",
    "approach": "approach",
    "stop": "stop",
    "dispatch_dog": "dispatch",
    "play_warning": "play_warning",
    "follow": "follow",
    "return_home": "return_home",
    "land_on_dog": "land_on_dog",
}
_DRONE_PROPOSALS = frozenset({"hold", "search", "reposition", "land_on_dog"})
_PRESENCE_PROPOSALS = frozenset(
    {"approach", "stop", "play_warning", "follow", "return_home", "land_on_dog"}
)
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
_ID_LIMIT = 160


@dataclass(frozen=True)
class Assessment:
    """One decision outcome. A stored proposal may be approved later.

    motion_authorized is true only when this assessment stored a proposal.
    The assessment still does not call a device or grant a motor command.
    """

    status: str
    error_code: str | None
    error_detail: str | None
    outcome: str
    detail: str
    trace: tuple[str, ...]
    track_id: str | None
    track_changed: bool
    proposal: Mapping[str, object] | None
    image_direction: str | None
    image_direction_space: str
    motion_authorized: bool
    halt_latched: bool
    model_id: str | None
    model_score: float | None
    journal: Mapping[str, object]


@dataclass(frozen=True)
class _Detection:
    label: str
    track_id: str | None
    confidence: float
    box: tuple[float, float, float, float]


@dataclass(frozen=True)
class _Request:
    request_id: str
    frame_id: str
    camera_epoch: int
    expires_at: datetime
    stage: str
    active_track_id: str | None
    calibration_id: str | None
    mission_id: str
    epoch: int


@dataclass(frozen=True)
class _Decision:
    message_id: str
    mission_id: str
    epoch: int
    seq: int
    sent_at: datetime
    sent_at_text: str
    request_id: str
    frame_id: str
    model_id: str
    target_state: str
    detections: tuple[_Detection, ...]
    suggested_action: str
    image_direction: str
    reason: str
    simulated: bool


class _Stop(Exception):
    def __init__(self, assessment: Assessment) -> None:
        self.assessment = assessment


def assess(
    decision: Mapping[str, object],
    request: Mapping[str, object],
    *,
    current_track_id: str | None = None,
    current_camera_epoch: int | None = None,
    halt_latched: bool = False,
    staged_association: bool = False,
) -> Assessment:
    """Accept a correlated decision, or a review/rejection that does not move."""
    try:
        return _assess(
            decision,
            request,
            current_track_id=current_track_id,
            current_camera_epoch=current_camera_epoch,
            halt_latched=halt_latched,
            staged_association=staged_association,
        )
    except _Stop as stopped:
        return stopped.assessment


def _assess(
    decision_raw: Mapping[str, object],
    request_raw: Mapping[str, object],
    *,
    current_track_id: str | None,
    current_camera_epoch: int | None,
    halt_latched: bool,
    staged_association: bool,
) -> Assessment:
    if current_track_id is not None:
        _identifier(current_track_id, "current track id", current_track_id, halt_latched)
    if current_camera_epoch is not None:
        _whole(current_camera_epoch, "current camera epoch", current_track_id, halt_latched)
    request = _parse_request(request_raw, current_track_id, halt_latched)
    decision = _parse_decision(decision_raw, current_track_id, halt_latched)
    journal = _journal(decision, request, current_track_id)
    if decision.request_id != request.request_id:
        _stop(
            status="failed",
            code="rejected",
            detail="request_mismatch",
            token="request_mismatch",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            journal=journal,
            model_id=decision.model_id,
        )
    if decision.frame_id != request.frame_id:
        _stop(
            status="failed",
            code="rejected",
            detail="frame_mismatch",
            token="frame_mismatch",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            journal=journal,
            model_id=decision.model_id,
        )
    if decision.mission_id != request.mission_id or decision.epoch != request.epoch:
        _stop(
            status="failed",
            code="rejected",
            detail="mission_mismatch",
            token="mission_mismatch",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            journal=journal,
            model_id=decision.model_id,
        )
    if decision.sent_at > request.expires_at:
        _stop(
            status="blocked",
            code="expired_deadline",
            detail="request_expired",
            token="expired",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            journal=journal,
            model_id=decision.model_id,
        )
    if current_camera_epoch is not None and request.camera_epoch < current_camera_epoch:
        _stop(
            status="blocked",
            code="epoch_mismatch",
            detail="stale_camera_epoch",
            token="camera_epoch",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            journal=journal,
            model_id=decision.model_id,
        )
    motor = _motor_text(decision.reason)
    if motor is not None:
        _stop(
            status="failed",
            code="rejected",
            detail=motor,
            token=motor,
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            journal=journal,
            model_id=decision.model_id,
        )
    if decision.target_state != "person_visible":
        presence = _presence_outcome(
            decision,
            request,
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
        if presence is not None:
            return presence
        return _withheld(
            decision,
            request,
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            head="review" if decision.target_state == "uncertain" else "hold",
            token=decision.target_state,
            detail="review" if decision.target_state == "uncertain" else "hold",
            outcome="review" if decision.target_state == "uncertain" else "hold",
        )
    chosen = _select_person(
        decision.detections,
        staged_association=staged_association,
        active_track_id=request.active_track_id,
        current_track_id=current_track_id,
        halt_latched=halt_latched,
        journal=journal,
        model_id=decision.model_id,
    )
    if chosen is None:
        return _withheld(
            decision,
            request,
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            head="review",
            token="multiple_people",
            detail="review",
            outcome="review",
        )
    mode, track_id = _bind_track(
        chosen,
        stage=request.stage,
        current_track_id=current_track_id,
        active_track_id=request.active_track_id,
    )
    if mode == "mismatch":
        _stop(
            status="failed",
            code="rejected",
            detail="track_mismatch",
            token="track_mismatch",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            journal=journal,
            model_id=decision.model_id,
        )
    if mode == "review" or track_id is None:
        return _withheld(
            decision,
            request,
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            head="review",
            token="track_unassigned",
            detail="review",
            outcome="review",
            model_score=chosen.confidence,
        )
    action, forced = _action(decision.suggested_action, request.calibration_id)
    proposal = _proposal(
        decision,
        request,
        track_id=track_id,
        action=action,
        forced=forced,
        halt_latched=halt_latched,
    )
    detail = "hold" if forced else ("track_opened" if mode == "opened" else "track_updated")
    outcome = detail
    trace_list = ["accepted"]
    if forced:
        trace_list.extend(("forced_hold", "uncalibrated"))
    trace_list.append(f"{'track_opened' if mode == 'opened' else 'track_updated'}:{track_id}")
    if proposal is None:
        trace_list.append("no_proposal")
    else:
        payload = proposal["payload"]
        proposal_action = payload["action"] if isinstance(payload, Mapping) else ""
        trace_list.append(f"proposal:{proposal_action}")
    if forced:
        trace_list.append("no_body_proposal")
    trace_list.append(f"direction:{decision.image_direction}:image")
    if halt_latched:
        trace_list.append("halt_preserved")
    trace_list.extend(("motion:empty", "devices:untouched"))
    return Assessment(
        status="ok",
        error_code=None,
        error_detail=None,
        outcome=outcome,
        detail=detail,
        trace=tuple(trace_list),
        track_id=track_id,
        track_changed=True,
        proposal=proposal,
        image_direction=decision.image_direction,
        image_direction_space="image",
        motion_authorized=proposal is not None,
        halt_latched=halt_latched,
        model_id=decision.model_id,
        model_score=chosen.confidence,
        journal=_journal(decision, request, track_id),
    )


def _withheld(
    decision: _Decision,
    request: _Request,
    *,
    current_track_id: str | None,
    halt_latched: bool,
    head: str,
    token: str,
    detail: str,
    outcome: str,
    model_score: float | None = None,
) -> Assessment:
    unchanged = (
        f"track_unchanged:{current_track_id}" if current_track_id else "track_unchanged"
    )
    trace = [head, token, "no_proposal", unchanged]
    if halt_latched:
        trace.append("halt_preserved")
    trace.extend(("motion:empty", "devices:untouched"))
    return Assessment(
        status="ok",
        error_code=None,
        error_detail=None,
        outcome=outcome,
        detail=detail,
        trace=tuple(trace),
        track_id=current_track_id,
        track_changed=False,
        proposal=None,
        image_direction=decision.image_direction,
        image_direction_space="image",
        motion_authorized=False,
        halt_latched=halt_latched,
        model_id=decision.model_id,
        model_score=model_score,
        journal=_journal(decision, request, current_track_id),
    )


def _bind_track(
    detection: _Detection,
    *,
    stage: str,
    current_track_id: str | None,
    active_track_id: str | None,
) -> tuple[str, str | None]:
    carried = detection.track_id
    if stage in _DOG_STAGES:
        expected = current_track_id or active_track_id
        if carried is None or expected is None or carried != expected:
            return "mismatch", None
        return "updated", expected
    if carried is not None:
        if current_track_id is not None and carried != current_track_id:
            return "mismatch", None
        if current_track_id == carried:
            return "updated", carried
        return "opened", carried
    if current_track_id is not None:
        return "updated", current_track_id
    if stage == "drone_search":
        return "opened", "target-001"
    return "review", None


def _action(suggested: str, calibration_id: str | None) -> tuple[str, bool]:
    if calibration_id is None and suggested in _BODY_MOVES:
        return "hold", True
    return suggested, False


def _presence_outcome(
    decision: _Decision,
    request: _Request,
    *,
    current_track_id: str | None,
    halt_latched: bool,
) -> Assessment | None:
    """Honor a gone or uncertain presence action instead of dropping it."""
    mapped = _PROPOSAL_ACTION.get(decision.suggested_action)
    if mapped not in _PRESENCE_PROPOSALS or halt_latched or not current_track_id:
        return None
    proposal = _proposal(
        decision,
        request,
        track_id=current_track_id,
        action=decision.suggested_action,
        forced=False,
        halt_latched=False,
    )
    if proposal is None:
        return None
    payload = proposal["payload"]
    proposal_action = payload["action"] if isinstance(payload, Mapping) else ""
    trace = (
        "accepted",
        decision.target_state,
        f"proposal:{proposal_action}",
        f"direction:{decision.image_direction}:image",
        "motion:empty",
        "devices:untouched",
    )
    return Assessment(
        status="ok",
        error_code=None,
        error_detail=None,
        outcome=str(proposal_action),
        detail=str(proposal_action),
        trace=trace,
        track_id=current_track_id,
        track_changed=False,
        proposal=proposal,
        image_direction=decision.image_direction,
        image_direction_space="image",
        motion_authorized=True,
        halt_latched=False,
        model_id=decision.model_id,
        model_score=None,
        journal=_journal(decision, request, current_track_id),
    )


def _proposal(
    decision: _Decision,
    request: _Request,
    *,
    track_id: str,
    action: str,
    forced: bool,
    halt_latched: bool,
) -> dict[str, object] | None:
    if halt_latched:
        return None
    if request.stage == "dog_acquire" and action == "switch_to_dog_vision":
        return None
    mapped = _PROPOSAL_ACTION.get(action)
    if mapped is None:
        return None
    if mapped in _DRONE_PROPOSALS or (action == "dispatch_dog" and forced):
        component = "drone"
    else:
        component = "dog"
    reason = (
        "Image-space hold. A body-frame move needs calibration."
        if forced
        else "Image-space proposal. Later tasks own any device action."
    )
    return {
        "protocol_version": "2.0-draft",
        "message_id": f"msg-proposal-{decision.request_id}",
        "mission_id": decision.mission_id,
        "epoch": decision.epoch,
        "seq": decision.seq,
        "sent_at": decision.sent_at_text,
        "source": "vision",
        "destination": "ground",
        "kind": "motion.proposal",
        "correlation_id": decision.message_id,
        "expires_at": request.expires_at.isoformat().replace("+00:00", "Z"),
        "simulated": decision.simulated,
        "payload": {
            "proposal_id": f"proposal-{decision.request_id}",
            "target_component": component,
            "action": mapped,
            "direction_hint": decision.image_direction,
            "track_id": track_id,
            "evidence_frame_id": decision.frame_id,
            "candidate_id": None,
            "beacon_epoch": None,
            "reason": reason,
        },
    }


def _select_person(
    detections: tuple[_Detection, ...],
    *,
    staged_association: bool,
    active_track_id: str | None,
    current_track_id: str | None,
    halt_latched: bool,
    journal: Mapping[str, object],
    model_id: str | None,
) -> _Detection | None:
    if len(detections) == 1:
        return detections[0]
    if len(detections) == 0:
        _stop(
            status="failed",
            code="rejected",
            detail="missing_detection",
            token="missing_detection",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
            journal=journal,
            model_id=model_id,
        )
    if not staged_association:
        return None
    expected = current_track_id or active_track_id
    matched = [
        item
        for item in detections
        if item.track_id is not None and item.track_id == expected
    ]
    if len(matched) == 1:
        return matched[0]
    return None


def _parse_request(
    raw: Mapping[str, object],
    current_track_id: str | None,
    halt_latched: bool,
) -> _Request:
    _exact(raw, _ENVELOPE, "request", current_track_id, halt_latched)
    _const(raw, "protocol_version", "2.0-draft", current_track_id, halt_latched)
    _const(raw, "source", "ground", current_track_id, halt_latched)
    _const(raw, "destination", "vision", current_track_id, halt_latched)
    _const(raw, "kind", "vision.request", current_track_id, halt_latched)
    payload = _mapping(raw.get("payload"), "request payload", current_track_id, halt_latched)
    _exact(payload, _REQUEST_PAYLOAD, "request payload", current_track_id, halt_latched)
    frame = _mapping(payload.get("frame"), "frame", current_track_id, halt_latched)
    _exact(frame, _FRAME, "frame", current_track_id, halt_latched)
    stage = _choice(payload.get("stage"), _STAGES, "stage", current_track_id, halt_latched)
    expires = raw.get("expires_at")
    if expires is None:
        _stop(
            status="failed",
            code="rejected",
            detail="request_missing_expiry",
            token="request_missing_expiry",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    return _Request(
        request_id=_identifier(
            payload.get("request_id"), "request_id", current_track_id, halt_latched
        ),
        frame_id=_identifier(frame.get("frame_id"), "frame_id", current_track_id, halt_latched),
        camera_epoch=_whole(
            frame.get("camera_epoch"), "camera_epoch", current_track_id, halt_latched
        ),
        expires_at=_time(expires, "expires_at", current_track_id, halt_latched),
        stage=stage,
        active_track_id=_optional_id(
            payload.get("active_track_id"), "active_track_id", current_track_id, halt_latched
        ),
        calibration_id=_optional_id(
            frame.get("camera_to_body_calibration_id"),
            "calibration_id",
            current_track_id,
            halt_latched,
        ),
        mission_id=_identifier(
            raw.get("mission_id"), "mission_id", current_track_id, halt_latched
        ),
        epoch=_whole(raw.get("epoch"), "epoch", current_track_id, halt_latched),
    )


def _parse_decision(
    raw: Mapping[str, object],
    current_track_id: str | None,
    halt_latched: bool,
) -> _Decision:
    _exact(raw, _ENVELOPE, "decision", current_track_id, halt_latched)
    _const(raw, "protocol_version", "2.0-draft", current_track_id, halt_latched)
    _const(raw, "source", "vision", current_track_id, halt_latched)
    _const(raw, "destination", "ground", current_track_id, halt_latched)
    _const(raw, "kind", "vision.decision", current_track_id, halt_latched)
    _bool(raw.get("simulated"), "simulated", current_track_id, halt_latched)
    payload = _mapping(raw.get("payload"), "decision payload", current_track_id, halt_latched)
    _exact(payload, _DECISION_PAYLOAD, "decision payload", current_track_id, halt_latched)
    _const(payload, "provider", "xai", current_track_id, halt_latched)
    detections_raw = payload.get("detections")
    if not isinstance(detections_raw, list):
        _stop(
            status="failed",
            code="rejected",
            detail="detections_not_a_list",
            token="detections_not_a_list",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    detections = tuple(
        _detection(item, index, current_track_id, halt_latched)
        for index, item in enumerate(detections_raw)
    )
    sent_text = raw.get("sent_at")
    return _Decision(
        message_id=_identifier(
            raw.get("message_id"), "message_id", current_track_id, halt_latched
        ),
        mission_id=_identifier(
            raw.get("mission_id"), "mission_id", current_track_id, halt_latched
        ),
        epoch=_whole(raw.get("epoch"), "epoch", current_track_id, halt_latched),
        seq=_whole(raw.get("seq"), "seq", current_track_id, halt_latched),
        sent_at=_time(sent_text, "sent_at", current_track_id, halt_latched),
        sent_at_text=sent_text if isinstance(sent_text, str) else "",
        request_id=_identifier(
            payload.get("request_id"), "request_id", current_track_id, halt_latched
        ),
        frame_id=_identifier(payload.get("frame_id"), "frame_id", current_track_id, halt_latched),
        model_id=_text(payload.get("model_id"), "model_id", current_track_id, halt_latched),
        target_state=_choice(
            payload.get("target_state"),
            _TARGET_STATES,
            "target_state",
            current_track_id,
            halt_latched,
        ),
        detections=detections,
        suggested_action=_choice(
            payload.get("suggested_action"),
            _ACTIONS,
            "suggested_action",
            current_track_id,
            halt_latched,
        ),
        image_direction=_choice(
            payload.get("image_direction"),
            _DIRECTIONS,
            "image_direction",
            current_track_id,
            halt_latched,
        ),
        reason=_text(payload.get("reason"), "reason", current_track_id, halt_latched),
        simulated=raw["simulated"] is True,
    )


def _detection(
    raw: object,
    index: int,
    current_track_id: str | None,
    halt_latched: bool,
) -> _Detection:
    body = _mapping(raw, f"detection {index}", current_track_id, halt_latched)
    _exact(body, _DETECTION, f"detection {index}", current_track_id, halt_latched)
    label = body.get("label")
    if label != "person":
        _stop(
            status="failed",
            code="rejected",
            detail="label_rejected",
            token="label_rejected",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    return _Detection(
        label="person",
        track_id=_optional_id(body.get("track_id"), "track_id", current_track_id, halt_latched),
        confidence=_score(body.get("confidence"), current_track_id, halt_latched),
        box=_box(body.get("box_xyxy_norm"), current_track_id, halt_latched),
    )


def _journal(decision: _Decision, request: _Request, track_id: str | None) -> dict[str, object]:
    return {
        "message_id": decision.message_id,
        "mission_id": decision.mission_id,
        "epoch": decision.epoch,
        "request_id": decision.request_id,
        "frame_id": decision.frame_id,
        "track_id": track_id,
        "command_id": None,
        "beacon_epoch": None,
        "map_epoch": None,
        "camera_epoch": request.camera_epoch,
    }


def _motor_text(reason: str) -> str | None:
    text = " ".join(reason.strip().lower().split())
    if text in _TELLO_EXACT or any(text.startswith(prefix) for prefix in _TELLO_PREFIXES):
        return "sdk_reason"
    if _DISTANCE.search(text):
        return "invented_distance"
    return None


def _exact(
    raw: Mapping[str, object],
    allowed: frozenset[str],
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> None:
    extra = sorted(set(raw) - allowed)
    if extra:
        _stop(
            status="failed",
            code="validation_failed",
            detail=f"unknown_field:{extra[0]}",
            token=f"unknown_field:{extra[0]}",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    missing = sorted(allowed - set(raw))
    if missing:
        _stop(
            status="failed",
            code="rejected",
            detail=f"missing_field:{missing[0]}",
            token=f"missing_field:{missing[0]}",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )


def _const(
    raw: Mapping[str, object],
    key: str,
    expected: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> None:
    if raw.get(key) != expected:
        _stop(
            status="failed",
            code="rejected",
            detail=f"bad_{key}",
            token=f"bad_{key}",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )


def _mapping(
    value: object,
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    _stop(
        status="failed",
        code="rejected",
        detail=f"{label}_not_object",
        token=f"{label}_not_object",
        current_track_id=current_track_id,
        halt_latched=halt_latched,
    )


def _text(
    value: object,
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> str:
    if isinstance(value, str) and value.strip():
        return value
    _stop(
        status="failed",
        code="rejected",
        detail=f"bad_{label}",
        token=f"bad_{label}",
        current_track_id=current_track_id,
        halt_latched=halt_latched,
    )


def _identifier(
    value: object,
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> str:
    text = _text(value, label, current_track_id, halt_latched)
    if len(text) > _ID_LIMIT:
        _stop(
            status="failed",
            code="rejected",
            detail=f"bad_{label}",
            token=f"bad_{label}",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    return text


def _optional_id(
    value: object,
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> str | None:
    if value is None:
        return None
    return _identifier(value, label, current_track_id, halt_latched)


def _choice(
    value: object,
    allowed: frozenset[str],
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    _stop(
        status="failed",
        code="rejected",
        detail=f"bad_{label}",
        token=f"bad_{label}",
        current_track_id=current_track_id,
        halt_latched=halt_latched,
    )


def _whole(
    value: object,
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _stop(
            status="failed",
            code="rejected",
            detail=f"bad_{label}",
            token=f"bad_{label}",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    return value


def _bool(
    value: object,
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> None:
    if not isinstance(value, bool):
        _stop(
            status="failed",
            code="rejected",
            detail="boolean_required",
            token="boolean_required",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )


def _score(value: object, current_track_id: str | None, halt_latched: bool) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        _stop(
            status="failed",
            code="rejected",
            detail="bad_confidence",
            token="bad_confidence",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    score = float(value)
    if score < 0 or score > 1:
        _stop(
            status="failed",
            code="rejected",
            detail="bad_confidence",
            token="bad_confidence",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    return score


def _box(
    value: object,
    current_track_id: str | None,
    halt_latched: bool,
) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        _stop(
            status="failed",
            code="rejected",
            detail="bad_box",
            token="bad_box",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    numbers: list[float] = []
    for item in value:
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
        ):
            _stop(
                status="failed",
                code="rejected",
                detail="bad_box",
                token="bad_box",
                current_track_id=current_track_id,
                halt_latched=halt_latched,
            )
        number = float(item)
        if number < 0 or number > 1:
            _stop(
                status="failed",
                code="rejected",
                detail="bad_box",
                token="bad_box",
                current_track_id=current_track_id,
                halt_latched=halt_latched,
            )
        numbers.append(number)
    xmin, ymin, xmax, ymax = numbers
    if not (xmin < xmax and ymin < ymax):
        _stop(
            status="failed",
            code="rejected",
            detail="unordered_box",
            token="unordered_box",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    return xmin, ymin, xmax, ymax


def _time(
    value: object,
    label: str,
    current_track_id: str | None,
    halt_latched: bool,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _stop(
            status="failed",
            code="rejected",
            detail=f"bad_{label}",
            token=f"bad_{label}",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _stop(
            status="failed",
            code="rejected",
            detail=f"bad_{label}",
            token=f"bad_{label}",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    if parsed.tzinfo is None:
        _stop(
            status="failed",
            code="rejected",
            detail=f"bad_{label}",
            token=f"bad_{label}",
            current_track_id=current_track_id,
            halt_latched=halt_latched,
        )
    return parsed.astimezone(UTC)


def _stop(
    *,
    status: str,
    code: str,
    detail: str,
    token: str,
    current_track_id: str | None,
    halt_latched: bool,
    journal: Mapping[str, object] | None = None,
    model_id: str | None = None,
) -> NoReturn:
    unchanged = (
        f"track_unchanged:{current_track_id}" if current_track_id else "track_unchanged"
    )
    head = "dropped" if status == "blocked" else "rejected"
    trace = [head, token, unchanged]
    if halt_latched:
        trace.append("halt_preserved")
    trace.append("devices:untouched")
    raise _Stop(
        Assessment(
            status=status,
            error_code=code,
            error_detail=detail,
            outcome="dropped" if status == "blocked" else "rejected",
            detail=detail,
            trace=tuple(trace),
            track_id=current_track_id,
            track_changed=False,
            proposal=None,
            image_direction=None,
            image_direction_space="image",
            motion_authorized=False,
            halt_latched=halt_latched,
            model_id=model_id,
            model_score=None,
            journal=journal or _blank_journal(),
        )
    )


def _blank_journal() -> dict[str, object]:
    return {
        "message_id": None,
        "mission_id": None,
        "epoch": None,
        "request_id": None,
        "frame_id": None,
        "track_id": None,
        "command_id": None,
        "beacon_epoch": None,
        "map_epoch": None,
        "camera_epoch": None,
    }
