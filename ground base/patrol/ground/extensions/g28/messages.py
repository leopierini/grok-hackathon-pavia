"""Accepted v2 safety commands. These are copies of the contract examples."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from patrol.ground.kernel.faults import fault

_ENVELOPE = (
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
)
_FORBIDDEN_ACTIONS = frozenset({"emergency", "motor_cut", "power_off", "cut_motors"})
_TOP_IDS = ("message_id", "mission_id", "epoch")
_BODY_IDS = (
    "command_id",
    "request_id",
    "proposal_id",
    "frame_id",
    "track_id",
    "beacon_epoch",
    "map_epoch",
    "camera_epoch",
)


@dataclass(frozen=True)
class Examples:
    dog_halt: Mapping[str, object]
    drone_hover: Mapping[str, object]
    drone_land: Mapping[str, object]
    dog_move: Mapping[str, object]
    drone_move: Mapping[str, object]
    recovery_token: str


def load_examples(root: Path) -> Examples:
    base = Path(root)
    dog_halt = _load(base / "ground-to-dog-halt.json")
    drone_hover = _load(base / "ground-to-drone-hover.json")
    drone_land = _load(base / "ground-to-drone-land.json")
    dog_move = _load(base / "ground-to-dog-command.json")
    drone_move = _load(base / "ground-to-drone-command.json")
    accept_command(dog_halt, kind="dog.command", action="halt")
    accept_command(drone_hover, kind="drone.command", action="hover")
    accept_command(drone_land, kind="drone.command", action="land")
    accept_command(dog_move, kind="dog.command", action="move_local")
    accept_command(drone_move, kind="drone.command", action="track_step")
    return Examples(
        dog_halt=dog_halt,
        drone_hover=drone_hover,
        drone_land=drone_land,
        dog_move=dog_move,
        drone_move=drone_move,
        recovery_token=_recovery_token(base / "recovery.json"),
    )


def accept_command(message: Mapping[str, object], *, kind: str, action: str) -> None:
    """Accept one copied contract command, or reject a motor cut."""
    for key in _ENVELOPE:
        if key not in message:
            raise fault("contract_mismatch", f"safety command is missing {key}")
    if message["protocol_version"] != "2.0-draft":
        raise fault("contract_mismatch", "safety command protocol is not 2.0-draft")
    if message["kind"] != kind:
        raise fault("contract_mismatch", "safety command kind does not match")
    if message["source"] != "ground":
        raise fault("contract_mismatch", "safety command must come from ground")
    if message["simulated"] is not True:
        raise fault("contract_mismatch", "safety command fixture must be simulated")
    payload = message["payload"]
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Mapping):
        raise fault("contract_mismatch", "safety command payload must be an object")
    found = payload.get("action")
    if found in _FORBIDDEN_ACTIONS:
        raise fault(
            "rejected",
            "motor cut is not a ground safety command",
            recovery_required=True,
        )
    if found != action:
        raise fault("contract_mismatch", "safety command action does not match")
    lease = payload.get("lease_ms")
    if isinstance(lease, bool) or not isinstance(lease, int) or not 1 <= lease <= 500:
        raise fault("contract_mismatch", "safety command lease_ms must be from 1 to 500")
    if not isinstance(payload.get("command_id"), str) or not payload.get("command_id"):
        raise fault("contract_mismatch", "safety command_id is required")


def command_id(message: Mapping[str, object]) -> str:
    payload = message.get("payload")
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Mapping):
        raise fault("invalid_input", "command payload must be an object")
    value = payload.get("command_id")
    if not isinstance(value, str) or not value:
        raise fault("invalid_input", "command_id is required")
    return value


def command_action(message: Mapping[str, object]) -> str:
    payload = message.get("payload")
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Mapping):
        raise fault("invalid_input", "command payload must be an object")
    value = payload.get("action")
    if not isinstance(value, str) or not value:
        raise fault("invalid_input", "command action is required")
    if value in _FORBIDDEN_ACTIONS:
        raise fault(
            "rejected",
            "motor cut is not a ground safety command",
            recovery_required=True,
        )
    return value


def destination(message: Mapping[str, object]) -> str:
    value = message.get("destination")
    if value == "dog":
        return "dog"
    if value == "drone":
        return "drone"
    kind = message.get("kind")
    if kind == "dog.command":
        return "dog"
    if kind == "drone.command":
        return "drone"
    raise fault("invalid_input", "command destination is unknown")


def correlation(message: Mapping[str, object]) -> dict[str, object]:
    """Copy the ids the journal is required to keep. Absent values stay absent."""
    found: dict[str, object] = {}
    for key in _TOP_IDS:
        value = message.get(key)
        if value is not None:
            found[key] = value
    payload = message.get("payload")
    if isinstance(payload, Mapping) and not isinstance(payload, (str, bytes)):
        for key in _BODY_IDS:
            value = payload.get(key)
            if value is not None:
                found[key] = value
    return found


def clone_message(message: Mapping[str, object]) -> dict[str, object]:
    cloned = _clone(dict(message))
    if not isinstance(cloned, dict):
        raise fault("internal", "command clone failed")
    return cloned


def _clone(value: object) -> object:
    if isinstance(value, dict):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise fault("invalid_input", "command keys must be strings")
            copied[key] = _clone(item)
        return copied
    if isinstance(value, list):
        return [_clone(item) for item in value]
    if isinstance(value, tuple):
        return [_clone(item) for item in value]
    return value


def _load(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise fault("missing_provider", f"{path.name} is missing")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise fault("contract_mismatch", f"{path.name} is not valid json") from exc
    return _object(raw, path.name)


def _recovery_token(path: Path) -> str:
    raw = _load(path)
    if set(raw) != {"operator_recovery_token"}:
        raise fault("contract_mismatch", "recovery fixture has an unsupported field")
    token = raw["operator_recovery_token"]
    if not isinstance(token, str) or not token.strip():
        raise fault("contract_mismatch", "operator recovery token is missing")
    return token


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise fault("contract_mismatch", f"{label} must be an object")
    found: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise fault("contract_mismatch", f"{label} has a non-string key")
        found[key] = item
    return found
