"""Decide one drone primitive. This module does not import an SDK or open a socket."""

from __future__ import annotations

import math
import random
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

_PROPOSAL_ACTIONS = {
    "hold": "hover",
    "search": "search_step",
    "reposition": "track_step",
    "land_on_dog": "land_on_dog",
}
_DOG_COMMANDS = frozenset({"play_warning", "follow", "stop", "return_home"})
_USE_CONTEXT = object()
_OPERATOR_ACTIONS = {
    "hold": "hover",
    "hover": "hover",
    "search": "search_step",
    "search_step": "search_step",
    "reposition": "track_step",
    "track_step": "track_step",
    "takeoff": "takeoff",
    "land": "land",
}
_PROPOSAL_FIELDS = frozenset(
    {
        "proposal_id",
        "target_component",
        "action",
        "direction_hint",
        "track_id",
        "evidence_frame_id",
        "candidate_id",
        "beacon_epoch",
        "warning_id",
        "text",
        "standoff_m",
        "reason",
    }
)
_OPERATOR_FIELDS = frozenset(
    {
        "request_id",
        "action",
        "direction_hint",
        "track_id",
        "evidence_frame_id",
        "camera_id",
        "beacon_epoch",
        "supervised",
        "mission_id",
        "epoch",
        "simulated",
        "reason",
        "expires_at",
    }
)
_DIRECTIONS = frozenset({"left", "center", "right", "unknown"})
_MOTION = frozenset({"search_step", "track_step"})
_SAFE = frozenset({"hover", "land"})
_SDK_FIELDS = frozenset({"sdk", "raw_command", "sdk_command", "rc", "command_string"})
_DISTANCE_FIELDS = frozenset({"displacement_m", "distance_m", "meters"})
_SDK_TEXT = re.compile(
    r"send_rc_control|move_forward|move_back|move_left|move_right|move_up|move_down|"
    r"rotate_clockwise|rotate_counter_clockwise|djitellopy|curve_to|"
    r"\bflip\s*\(|\bgo\s*\(|\btakeoff\s*\(|\bland\s*\(",
    re.IGNORECASE,
)
_DISTANCE_TEXT = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)"
    r"[\s-]*(?:meters?|m)\b",
    re.IGNORECASE,
)


class _DogCommand(Exception):
    def __init__(self, command: dict[str, object]) -> None:
        self.command = command
        super().__init__("dog command")


class _Refuse(Exception):
    def __init__(self, status: str, code: str, reason: str, recovery: bool) -> None:
        self.status = status
        self.code = code
        self.reason = reason
        self.recovery = recovery
        super().__init__(reason)


@dataclass(frozen=True)
class CommandDraft:
    action: str
    primitive_id: str
    lease_ms: int
    deadline_ms: int
    requested_height_m: float | None
    height_reference: str
    evidence_frame_id: str | None
    track_id: str | None
    camera_id: str
    beacon_epoch: int | None
    reason: str
    proposal_id: str | None
    idempotency_key: str
    mission_id: str
    epoch: int
    simulated: bool
    correlation_id: str | None
    evaluated_at: str
    supervised: bool
    camera_epoch: int | None


@dataclass(frozen=True)
class Decision:
    ok: bool
    status: str
    code: str
    reason: str
    recovery_required: bool
    draft: CommandDraft | None
    dog_command: Mapping[str, object] | None = None


def peek_key(context: Mapping[str, object]) -> str | None:
    """Return the id that makes a later approval idempotent, when one is present."""
    proposal = context.get("proposal")
    operator = context.get("operator_request")
    if proposal is not None and operator is not None:
        return None
    if isinstance(proposal, Mapping):
        body = _body(proposal)
        if isinstance(body, Mapping):
            ident = body.get("proposal_id")
            if isinstance(ident, str) and ident.strip():
                return ident.strip()
    if isinstance(operator, Mapping):
        ident = operator.get("request_id")
        if isinstance(ident, str) and ident.strip():
            return ident.strip()
    return None


def decide(context: Mapping[str, object]) -> Decision:
    try:
        draft = _decide(context)
    except _DogCommand as ready:
        return Decision(True, "ok", "", "approved", False, None, ready.command)
    except _Refuse as refused:
        return Decision(
            False,
            refused.status,
            refused.code,
            refused.reason,
            refused.recovery,
            None,
        )
    reason = "operator-supervised" if draft.supervised else "approved"
    return Decision(True, "ok", "", reason, False, draft)


def _decide(context: Mapping[str, object]) -> CommandDraft:
    proposal = context.get("proposal")
    operator = context.get("operator_request")
    if proposal is not None and operator is not None:
        _bad("one request at a time")
    if proposal is None and operator is None:
        _bad("a proposal or operator request is required")
    if proposal is not None:
        return _from_proposal(context, proposal)
    return _from_operator(context, operator)


def _from_proposal(context: Mapping[str, object], proposal: object) -> CommandDraft:
    if not isinstance(proposal, Mapping):
        _bad("proposal must be an object")
    _reject_motor_text(proposal)
    if "kind" not in proposal or "payload" not in proposal:
        _bad("proposal must be a v2 envelope")
    if proposal.get("kind") != "motion.proposal":
        _bad("proposal kind must be motion.proposal")
    body = proposal.get("payload")
    if not isinstance(body, Mapping):
        _bad("proposal payload must be an object")
    _known_fields(body, _PROPOSAL_FIELDS, "proposal")
    _reject_motor_text(body)
    target = body.get("target_component")
    action_name = body.get("action")
    direction = body.get("direction_hint")
    if direction not in _DIRECTIONS:
        _bad("direction_hint is not an image direction")
    _expired(proposal.get("expires_at"), _evaluated(context), required=True)
    if target == "dog":
        if action_name in _DOG_COMMANDS:
            raise _DogCommand(_dog_command(proposal, body, context))
        if action_name == "approach":
            _block("dog_policy", code="deferred")
        _block("wrong_component")
    if target != "drone":
        _bad("target_component must be drone or dog")
    if action_name == "stop":
        _block("stop_is_not_land")
    if not isinstance(action_name, str) or action_name not in _PROPOSAL_ACTIONS:
        _block("unsupported_action")
    return _issue(
        context,
        action=_PROPOSAL_ACTIONS[action_name],
        direction=direction if isinstance(direction, str) else None,
        supervised=False,
        evidence=_optional_text(body.get("evidence_frame_id"), "evidence_frame_id"),
        track=_optional_text(body.get("track_id"), "track_id"),
        proposal_id=_required_text(body, "proposal_id"),
        mission_id=_required_text(proposal, "mission_id"),
        epoch=_nonnegative(proposal.get("epoch"), "epoch"),
        simulated=_flag(proposal.get("simulated"), "simulated"),
        correlation=_optional_text(proposal.get("message_id"), "message_id"),
        key=_required_text(body, "proposal_id"),
        beacon=_proposal_beacon(body, action_name),
    )


def _from_operator(context: Mapping[str, object], operator: object) -> CommandDraft:
    if not isinstance(operator, Mapping):
        _bad("operator_request must be an object")
    _known_fields(operator, _OPERATOR_FIELDS, "operator request")
    _reject_motor_text(operator)
    action_name = operator.get("action")
    if not isinstance(action_name, str) or action_name not in _OPERATOR_ACTIONS:
        _block("unsupported_action")
    supervised = operator.get("supervised", False)
    if not isinstance(supervised, bool):
        _bad("supervised must be a boolean")
    direction = operator.get("direction_hint")
    if direction is not None and direction not in _DIRECTIONS:
        _bad("direction_hint is not an image direction")
    expires = operator.get("expires_at")
    if expires is not None:
        _expired(expires, _evaluated(context), required=True)
    return _issue(
        context,
        action=_OPERATOR_ACTIONS[action_name],
        direction=direction if isinstance(direction, str) else None,
        supervised=supervised,
        evidence=_optional_text(operator.get("evidence_frame_id"), "evidence_frame_id"),
        track=_optional_text(operator.get("track_id"), "track_id"),
        proposal_id=None,
        mission_id=_required_text(operator, "mission_id"),
        epoch=_nonnegative(operator.get("epoch"), "epoch"),
        simulated=_flag(operator.get("simulated"), "simulated"),
        correlation=None,
        key=_required_text(operator, "request_id"),
        beacon=_USE_CONTEXT,
    )


def _issue(
    context: Mapping[str, object],
    *,
    action: str,
    direction: str | None,
    supervised: bool,
    evidence: str | None,
    track: str | None,
    proposal_id: str | None,
    mission_id: str,
    epoch: int,
    simulated: bool,
    correlation: str | None,
    key: str,
    beacon: object,
) -> CommandDraft:
    if context.get("halt_latched") is True and action not in _SAFE:
        _block("cancelled", code="cancelled", recovery=True)
    _require_armed(context)
    capabilities = _section(context, "capabilities")
    observation = _section(context, "observation")
    allowlist = _section(context, "allowlist")
    controlled = _controlled(capabilities)
    flight = observation.get("flight_state")
    if flight not in {"airborne", "grounded", "unknown"}:
        _bad("flight_state must be airborne, grounded, or unknown")
    active = observation.get("active_command_id")
    if isinstance(active, str) and active.strip():
        _block("command_in_flight")
    if supervised and controlled and action in _MOTION:
        _block("supervised_conflicts_with_control")
    if action in _MOTION and not controlled and not (supervised and action == "search_step"):
        _block("controlled_motion_disabled")
    if action in {"takeoff", "land_on_dog"} and not controlled:
        _block("controlled_motion_disabled")
    if flight == "unknown" and action not in _SAFE:
        _block("aircraft_state_unknown")
    if action == "takeoff" and flight != "grounded":
        _block("already_airborne")
    if action in _MOTION and flight != "airborne":
        _block("aircraft_not_airborne")
    primitive = _primitive(
        allowlist,
        action=action,
        direction=direction,
        supervised=supervised and action == "search_step" and not controlled,
        seed=_seed(context),
        steps=_steps(context),
    )
    if action == "track_step":
        _require_calibration(context, observation)
        frame = _frame(observation)
        frame_id = frame.get("frame_id")
        if evidence is None or evidence != frame_id:
            _block("frame_mismatch")
        camera = frame.get("camera_id")
        if camera != primitive["camera_id"]:
            _block("frame_mismatch")
    if track is None:
        _block("track_missing")
    lease = _lease(context, primitive, action)
    deadline = _deadline(allowlist, action, lease)
    height, reference = _height(context, observation, allowlist)
    camera_id = primitive["camera_id"]
    if not isinstance(camera_id, str):
        _bad("primitive camera_id must be a string")
    _supported(capabilities, action, camera_id)
    return CommandDraft(
        action=action,
        primitive_id=_required_text(primitive, "primitive_id"),
        lease_ms=lease,
        deadline_ms=deadline,
        requested_height_m=height,
        height_reference=reference,
        evidence_frame_id=evidence,
        track_id=track,
        camera_id=camera_id,
        beacon_epoch=_resolve_beacon(beacon, context, observation),
        reason=_required_text(primitive, "reason"),
        proposal_id=proposal_id,
        idempotency_key=key,
        mission_id=mission_id,
        epoch=epoch,
        simulated=simulated,
        correlation_id=correlation,
        evaluated_at=_evaluated(context),
        supervised=supervised and action == "search_step" and not controlled,
        camera_epoch=_camera_epoch(observation),
    )


def _primitive(
    allowlist: Mapping[str, object],
    *,
    action: str,
    direction: str | None,
    supervised: bool,
    seed: int,
    steps: int,
) -> Mapping[str, object]:
    rows = allowlist.get("primitives")
    if not isinstance(rows, list) or not rows:
        _bad("allowlist primitives must be a list")
    chosen: Mapping[str, object] | None = None
    if action == "search_step" and supervised:
        _require_search_budget(allowlist, steps)
        for row in rows:
            if _is_row(row, "search_step") and row.get("supervised") is True:
                chosen = row
                break
    elif action == "search_step":
        search = _require_search_budget(allowlist, steps)
        pool = search.get("primitive_ids")
        identifiers = pool if isinstance(pool, list) else None
        if (
            not identifiers
            or not all(isinstance(item, str) for item in identifiers)
        ):
            _bad("search primitive_ids must be a list of strings")
        ident = _pick(identifiers, seed, steps)
        for row in rows:
            if (
                _is_row(row, "search_step")
                and row.get("primitive_id") == ident
                and row.get("supervised") is not True
            ):
                chosen = row
                break
    elif action == "track_step":
        for row in rows:
            if (
                _is_row(row, "track_step")
                and row.get("direction_hint") == direction
                and row.get("supervised") is not True
            ):
                chosen = row
                break
    else:
        for row in rows:
            if _is_row(row, action) and row.get("supervised") is not True:
                chosen = row
                break
    if chosen is None:
        _block("primitive_missing")
    return chosen


def _require_search_budget(allowlist: Mapping[str, object], steps: int) -> Mapping[str, object]:
    search = allowlist.get("search")
    if not isinstance(search, Mapping):
        _bad("search profile is required")
    cap = search.get("step_cap")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        _bad("search step_cap must be a positive integer")
    if steps >= cap:
        _block("search_cap_exhausted")
    return search


def _pick(pool: list[object], seed: int, steps: int) -> str:
    identifiers = [item for item in pool if isinstance(item, str)]
    if not identifiers:
        _block("primitive_missing")
    rng = random.Random(seed)
    for _ in range(steps):
        rng.randrange(len(identifiers))
    return identifiers[rng.randrange(len(identifiers))]


def _lease(context: Mapping[str, object], primitive: Mapping[str, object], action: str) -> int:
    lease = primitive.get("lease_ms")
    if isinstance(lease, bool) or not isinstance(lease, int) or not 1 <= lease <= 500:
        _block("lease_exceeds_motion_cap")
    requested = context.get("lease_ms")
    if requested is None:
        return lease
    if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
        _bad("lease_ms must be a positive integer")
    if requested > 500:
        _block("lease_exceeds_motion_cap")
    if action in _MOTION and requested > 500:
        _block("lease_exceeds_motion_cap")
    if requested != lease:
        _block("lease_mismatch")
    return lease


def _deadline(allowlist: Mapping[str, object], action: str, lease: int) -> int:
    if action not in {"takeoff", "land", "land_on_dog"}:
        return lease
    label = "takeoff_deadline_ms" if action == "takeoff" else "land_deadline_ms"
    value = allowlist.get(label)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _bad(f"{label} must be a positive integer")
    if value <= 500:
        _block("deadline_reuses_motion_lease")
    return value


def _height(
    context: Mapping[str, object],
    observation: Mapping[str, object],
    allowlist: Mapping[str, object],
) -> tuple[float | None, str]:
    if "requested_height_m" not in context or context.get("requested_height_m") is None:
        return None, "unknown"
    height = context.get("requested_height_m")
    if (
        isinstance(height, bool)
        or not isinstance(height, (int, float))
        or not math.isfinite(float(height))
        or float(height) <= 0
    ):
        _bad("requested_height_m must be a positive number")
    reference = context.get("height_reference")
    if not isinstance(reference, str) or reference == "unknown":
        _block("height_reference_mismatch")
    if observation.get("height_reference") != reference:
        _block("height_reference_mismatch")
    profile = allowlist.get("height_profile")
    allowed = profile.get("allowed") if isinstance(profile, Mapping) else None
    if not isinstance(allowed, list):
        _block("height_not_in_profile")
    for entry in allowed:
        if not isinstance(entry, Mapping) or entry.get("height_reference") != reference:
            continue
        listed = entry.get("height_m")
        if (
            not isinstance(listed, bool)
            and isinstance(listed, (int, float))
            and abs(float(listed) - float(height)) < 1e-6
        ):
            return float(height), reference
    _block("height_not_in_profile")


def _require_calibration(
    context: Mapping[str, object],
    observation: Mapping[str, object],
) -> None:
    if "calibration" not in context:
        _block("calibration_missing")
    calibration = context.get("calibration")
    if calibration is not None and not isinstance(calibration, bool):
        _bad("calibration must be a boolean or null")
    frame = _frame(observation)
    ident = frame.get("camera_to_body_calibration_id")
    if calibration is not True or not isinstance(ident, str) or not ident.strip():
        _block("calibration_missing")


def _proposal_beacon(body: Mapping[str, object], action: str) -> object:
    """A land-on-dog proposal may name no beacon. Other actions keep the context epoch."""
    if action != "land_on_dog" or "beacon_epoch" not in body:
        return _USE_CONTEXT
    value = body.get("beacon_epoch")
    if value is None:
        return None
    return _nonnegative(value, "beacon_epoch")


def _resolve_beacon(
    beacon: object,
    context: Mapping[str, object],
    observation: Mapping[str, object],
) -> int | None:
    if beacon is _USE_CONTEXT:
        return _beacon(context, observation)
    if beacon is None:
        return None
    return _nonnegative(beacon, "beacon_epoch")


def _beacon(context: Mapping[str, object], observation: Mapping[str, object]) -> int:
    if "beacon_epoch" in context and context.get("beacon_epoch") is not None:
        return _nonnegative(context.get("beacon_epoch"), "beacon_epoch")
    beacon = observation.get("beacon")
    if isinstance(beacon, Mapping) and beacon.get("beacon_epoch") is not None:
        return _nonnegative(beacon.get("beacon_epoch"), "beacon_epoch")
    _block("beacon_missing")


def _camera_epoch(observation: Mapping[str, object]) -> int | None:
    frame = observation.get("frame")
    if not isinstance(frame, Mapping) or frame.get("camera_epoch") is None:
        return None
    return _nonnegative(frame.get("camera_epoch"), "camera_epoch")


def _supported(capabilities: Mapping[str, object], action: str, camera_id: str) -> None:
    commands = capabilities.get("supported_commands")
    cameras = capabilities.get("camera_ids")
    if not isinstance(commands, list) or action not in commands:
        _block("unsupported_command")
    if not isinstance(cameras, list) or camera_id not in cameras:
        _block("unsupported_command")


def _require_armed(context: Mapping[str, object]) -> None:
    armed = context.get("armed")
    if not isinstance(armed, bool):
        _bad("armed must be a boolean")
    if armed is not True:
        _block("not_armed")
    capabilities = _section(context, "capabilities")
    validated = capabilities.get("validated")
    if not isinstance(validated, bool):
        _bad("validated must be a boolean")
    if validated is not True:
        _block("capability_not_validated")


def _controlled(capabilities: Mapping[str, object]) -> bool:
    features = capabilities.get("features")
    if not isinstance(features, Mapping):
        _bad("features must be an object")
    if "controlled_motion" not in features:
        return False
    value = features.get("controlled_motion")
    if not isinstance(value, bool):
        _bad("controlled_motion must be a boolean")
    return value


def _section(context: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = context.get(name)
    if not isinstance(value, Mapping):
        _bad(f"{name} must be an object")
    return _body(value)


def _body(document: Mapping[str, object]) -> Mapping[str, object]:
    if "kind" in document and "payload" in document:
        body = document.get("payload")
        if not isinstance(body, Mapping):
            _bad("payload must be an object")
        return body
    return document


def _frame(observation: Mapping[str, object]) -> Mapping[str, object]:
    frame = observation.get("frame")
    if not isinstance(frame, Mapping):
        _block("frame_mismatch")
    return frame


def _known_fields(body: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    extra = [key for key in body if key not in allowed]
    if not extra:
        return
    if any(key in _DISTANCE_FIELDS for key in extra):
        _block("displacement_rejected")
    if any(key in _SDK_FIELDS for key in extra):
        _block("sdk_text_rejected")
    _bad(f"unknown {label} field")


def _reject_motor_text(value: object) -> None:
    for text in _strings(value):
        if _DISTANCE_TEXT.search(text):
            _block("displacement_rejected")
        if _SDK_TEXT.search(text):
            _block("sdk_text_rejected")


def _strings(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                found.append(key)
            found.extend(_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_strings(item))
    return found


def _expired(expires: object, evaluated: str, *, required: bool) -> None:
    if expires is None:
        if required:
            _block("expired_proposal")
        return
    if _stamp(evaluated, "evaluated_at") >= _stamp(expires, "expires_at"):
        _block("expired_proposal")


def _evaluated(context: Mapping[str, object]) -> str:
    value = context.get("evaluated_at")
    if not isinstance(value, str):
        _bad("evaluated_at must be a UTC timestamp")
    _stamp(value, "evaluated_at")
    return value


def _stamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _bad(f"{label} must be a UTC timestamp")
    body = value[:-1]
    try:
        parsed = (
            datetime.strptime(body, "%Y-%m-%dT%H:%M:%S.%f")
            if "." in body
            else datetime.strptime(body, "%Y-%m-%dT%H:%M:%S")
        )
    except ValueError:
        _bad(f"{label} must be a UTC timestamp")
    return parsed.replace(tzinfo=UTC)


def _seed(context: Mapping[str, object]) -> int:
    if "seed" not in context or context.get("seed") is None:
        return 0
    return _nonnegative(context.get("seed"), "seed")


def _steps(context: Mapping[str, object]) -> int:
    if "search_steps_taken" not in context or context.get("search_steps_taken") is None:
        return 0
    return _nonnegative(context.get("search_steps_taken"), "search_steps_taken")


def _is_row(row: object, action: str) -> bool:
    return isinstance(row, Mapping) and row.get("action") == action


def _required_text(body: Mapping[str, object], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        _bad(f"{name} must be a string")
    return value.strip()


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _bad(f"{label} must be a string or null")
    return value.strip()


def _flag(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _bad(f"{label} must be a boolean")
    return value


def _nonnegative(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _bad(f"{label} must be a non-negative integer")
    return value


def _dog_command(
    proposal: Mapping[str, object],
    body: Mapping[str, object],
    context: Mapping[str, object],
) -> dict[str, object]:
    action = body.get("action")
    if not isinstance(action, str) or action not in _DOG_COMMANDS:
        _bad("action is not a dog presence command")
    proposal_id = _required_text(body, "proposal_id")
    command_id = proposal_id if proposal_id.startswith("cmd-") else f"cmd-{proposal_id}"
    message_id = f"msg-{command_id}"
    if len(command_id) > 160 or len(message_id) > 160:
        _bad("proposal_id is too long for a command id")
    reason = body.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        _bad("reason must be a string")
    safety = context.get("safety_snapshot_id")
    if not isinstance(safety, str) or not safety.strip() or len(safety.strip()) > 160:
        _bad("safety_snapshot_id is required")
    payload: dict[str, object] = {
        "command_id": command_id,
        "proposal_id": proposal_id,
        "action": action,
        "lease_ms": 500,
        "motion": None,
        "track_id": _optional_text(body.get("track_id"), "track_id"),
        "beacon_epoch": _optional_beacon(body.get("beacon_epoch")),
        "safety_snapshot_id": safety.strip(),
        "reason": reason.strip(),
    }
    if action == "play_warning":
        payload["warning_id"] = _short_text(body.get("warning_id"), "warning_id")
        payload["text"] = _short_text(body.get("text"), "text")
    if action == "follow":
        payload["standoff_m"] = _standoff(body.get("standoff_m"))
    sent_at = proposal.get("sent_at")
    if not isinstance(sent_at, str) or not sent_at.strip():
        _bad("sent_at must be a string")
    return {
        "protocol_version": "2.0-draft",
        "message_id": message_id,
        "mission_id": _required_text(proposal, "mission_id"),
        "epoch": _nonnegative(proposal.get("epoch"), "epoch"),
        "seq": _nonnegative(proposal.get("seq"), "seq"),
        "sent_at": sent_at,
        "source": "ground",
        "destination": "dog",
        "kind": "dog.command",
        "correlation_id": _optional_text(proposal.get("message_id"), "message_id"),
        "expires_at": proposal.get("expires_at"),
        "simulated": _flag(proposal.get("simulated"), "simulated"),
        "payload": payload,
    }


def _optional_beacon(value: object) -> int | None:
    if value is None:
        return None
    return _nonnegative(value, "beacon_epoch")


def _short_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 160:
        _bad(f"{label} must be a short string")
    return value.strip()


def _standoff(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _bad("standoff_m must be a positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        _bad("standoff_m must be a positive number")
    return number


def _bad(reason: str) -> NoReturn:
    raise _Refuse("failed", "invalid_input", reason, False)


def _block(reason: str, *, code: str = "rejected", recovery: bool = False) -> NoReturn:
    raise _Refuse("blocked", code, reason, recovery)
