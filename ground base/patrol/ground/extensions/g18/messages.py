"""Strict readers for drone command and acknowledgement envelopes."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.paths import repo_root

_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
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
_ACK_FIELDS = frozenset(
    {
        "command_id",
        "state",
        "reason_code",
        "observed_at",
        "verified",
        "observed_motion",
        "detail",
    }
)
_COMMAND_FIELDS = frozenset(
    {
        "command_id",
        "proposal_id",
        "action",
        "primitive_id",
        "lease_ms",
        "requested_height_m",
        "height_reference",
        "evidence_frame_id",
        "track_id",
        "camera_id",
        "beacon_epoch",
        "reason",
    }
)
_SOURCES = frozenset({"ground", "drone", "dog", "pi", "vision", "operator"})
_DESTINATIONS = frozenset({"ground", "drone", "dog", "pi", "vision", "all"})
_ACK_STATES = frozenset(
    {"accepted", "running", "completed", "rejected", "cancelled", "failed", "unknown"}
)
_MOTIONS = frozenset({"stationary", "moving", "airborne", "grounded", "unknown"})
_ACTIONS = frozenset({"takeoff", "search_step", "track_step", "hover", "land"})
_HEIGHTS = frozenset({"floor_agl", "takeoff_relative", "unknown"})
_CAMERAS = frozenset({"front", "downward"})


@dataclass(frozen=True)
class Envelope:
    message_id: str
    mission_id: str
    epoch: int
    seq: int
    sent_at: str
    source: str
    destination: str
    kind: str
    correlation_id: str | None
    expires_at: str | None
    simulated: bool
    payload: Mapping[str, object]


@dataclass(frozen=True)
class AckBody:
    command_id: str
    state: str
    reason_code: str
    observed_at: str
    verified: bool
    observed_motion: str
    detail: str | None


@dataclass(frozen=True)
class CommandBody:
    command_id: str
    action: str
    beacon_epoch: int
    track_id: str | None


@dataclass(frozen=True)
class ObservationView:
    epoch: int
    mission_id: str
    flight_state: str | None
    ignored_local_flag: bool


def load_fixture(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g18" / name
    if not path.is_file():
        raise fault("invalid_input", f"fixture {name} is missing")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise fault(
            "io_fault",
            f"fixture {name} could not be read",
            recovery_required=True,
        ) from exc
    try:
        loaded: object = json.loads(text)
    except ValueError as exc:
        raise fault("invalid_input", f"fixture {name} is not json") from exc
    return _object(loaded, name)


def parse_ack(value: Mapping[str, object]) -> tuple[Envelope, AckBody]:
    envelope = _envelope(value, kind="command.ack")
    payload = _exact(envelope.payload, _ACK_FIELDS, "ack payload")
    body = AckBody(
        command_id=_text(payload["command_id"], "command_id"),
        state=_choice(payload["state"], "state", _ACK_STATES),
        reason_code=_text(payload["reason_code"], "reason_code", max_len=160),
        observed_at=_time(payload["observed_at"], "observed_at"),
        verified=_flag(payload["verified"], "verified"),
        observed_motion=_choice(payload["observed_motion"], "observed_motion", _MOTIONS),
        detail=_optional_text(payload["detail"], "detail", max_len=1000),
    )
    return envelope, body


def parse_command(value: Mapping[str, object]) -> tuple[Envelope, CommandBody]:
    envelope = _envelope(value, kind="drone.command")
    payload = _exact(envelope.payload, _COMMAND_FIELDS, "command payload")
    height = payload["requested_height_m"]
    if height is not None and (isinstance(height, bool) or not isinstance(height, (int, float))):
        raise fault("invalid_input", "requested_height_m must be a number or null")
    if isinstance(height, (int, float)) and not isinstance(height, bool) and float(height) <= 0:
        raise fault("invalid_input", "requested_height_m must be positive")
    lease = _integer(payload["lease_ms"], "lease_ms", minimum=1)
    if lease > 500:
        raise fault("invalid_input", "lease_ms must be at most 500")
    body = CommandBody(
        command_id=_text(payload["command_id"], "command_id"),
        action=_choice(payload["action"], "action", _ACTIONS),
        beacon_epoch=_integer(payload["beacon_epoch"], "beacon_epoch"),
        track_id=_optional_text(payload["track_id"], "track_id"),
    )
    _text(payload["primitive_id"], "primitive_id")
    _optional_text(payload["proposal_id"], "proposal_id")
    _optional_text(payload["evidence_frame_id"], "evidence_frame_id")
    _choice(payload["height_reference"], "height_reference", _HEIGHTS)
    _choice(payload["camera_id"], "camera_id", _CAMERAS)
    _text(payload["reason"], "reason", max_len=1000)
    return envelope, body


def parse_observation(value: Mapping[str, object]) -> ObservationView:
    envelope = _envelope(value, kind="drone.observation")
    if not isinstance(envelope.payload, Mapping):
        raise fault("invalid_input", "observation payload must be an object")
    flight = envelope.payload.get("flight_state")
    flight_state = None if flight is None else _text(flight, "flight_state", max_len=80)
    return ObservationView(
        epoch=envelope.epoch,
        mission_id=envelope.mission_id,
        flight_state=flight_state,
        ignored_local_flag="is_flying" in envelope.payload,
    )


def _envelope(value: Mapping[str, object], *, kind: str) -> Envelope:
    raw = _object(value, "message")
    _exact(raw, _ENVELOPE, "message")
    found = _text(raw["kind"], "kind", max_len=80)
    if found != kind:
        raise fault("invalid_input", f"kind must be {kind}")
    protocol = _text(raw["protocol_version"], "protocol_version", max_len=40)
    if protocol != "2.0-draft":
        raise fault("invalid_input", "protocol_version is not 2.0-draft")
    payload = raw["payload"]
    if not isinstance(payload, Mapping) or isinstance(payload, (str, bytes)):
        raise fault("invalid_input", "payload must be an object")
    return Envelope(
        message_id=_text(raw["message_id"], "message_id"),
        mission_id=_text(raw["mission_id"], "mission_id"),
        epoch=_integer(raw["epoch"], "epoch"),
        seq=_integer(raw["seq"], "seq"),
        sent_at=_time(raw["sent_at"], "sent_at"),
        source=_choice(raw["source"], "source", _SOURCES),
        destination=_choice(raw["destination"], "destination", _DESTINATIONS),
        kind=found,
        correlation_id=_optional_text(raw["correlation_id"], "correlation_id"),
        expires_at=_optional_time(raw["expires_at"], "expires_at"),
        simulated=_flag(raw["simulated"], "simulated"),
        payload=_object(payload, "payload"),
    )


def _exact(value: Mapping[str, object], allowed: frozenset[str], label: str) -> dict[str, object]:
    raw = _object(value, label)
    extra = [key for key in raw if key not in allowed]
    missing = [key for key in allowed if key not in raw]
    if extra or missing:
        raise fault("invalid_input", f"{label} fields do not match the contract")
    return raw


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        raise fault("invalid_input", f"{label} must be an object")
    found: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise fault("invalid_input", f"{label} keys must be strings")
        found[key] = item
    return found


def _text(value: object, label: str, *, max_len: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{label} must be a non-empty string")
    if len(value) > max_len:
        raise fault("invalid_input", f"{label} is too long")
    return value


def _optional_text(value: object, label: str, *, max_len: int = 160) -> str | None:
    if value is None:
        return None
    return _text(value, label, max_len=max_len)


def _flag(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise fault("invalid_input", f"{label} must be a boolean")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise fault("invalid_input", f"{label} must be an integer")
    if value < minimum:
        raise fault("invalid_input", f"{label} is below {minimum}")
    return value


def _choice(value: object, label: str, allowed: frozenset[str]) -> str:
    text = _text(value, label, max_len=80)
    if text not in allowed:
        raise fault("invalid_input", f"{label} is not allowed")
    return text


def _time(value: object, label: str) -> str:
    text = _text(value, label, max_len=40)
    if _TIME.fullmatch(text) is None:
        raise fault("invalid_input", f"{label} must be a UTC timestamp")
    return text


def _optional_time(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _time(value, label)
