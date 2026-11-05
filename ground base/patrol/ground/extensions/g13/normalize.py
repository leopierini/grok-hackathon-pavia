"""Pure checks for a drone.observation envelope. This module does not move hardware."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from patrol.ground.kernel.contracts import GroundError
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_drone_observation"
SCHEMA = "ground-task-v2"
_FLIGHT = frozenset({"grounded", "airborne", "unknown"})
_REFERENCES = frozenset({"floor_agl", "takeoff_relative", "unknown"})
_HOLD = frozenset({"stable", "moving", "unknown"})
_CONTROL = frozenset({"autonomous_verified", "operator_supervised", "unavailable"})
_CAMERAS = frozenset({"front", "downward"})
_BSSID = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)
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
_OBSERVATION = frozenset(
    {
        "device_id",
        "flight_state",
        "battery_percent",
        "pose",
        "height_estimate_m",
        "height_reference",
        "control_mode",
        "beacon",
        "frame",
        "active_command_id",
    }
)
_CAPABILITY = frozenset(
    {
        "device_id",
        "role",
        "model",
        "software_version",
        "supported_commands",
        "camera_ids",
        "pose_frames",
        "features",
        "validated",
        "acceptance_evidence_ref",
    }
)
_BEACON = frozenset(
    {
        "beacon_id",
        "bssid",
        "ssid",
        "beacon_epoch",
        "hold_state",
        "verified_at",
        "hold_valid_until",
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
_POSE = frozenset(
    {
        "frame_id",
        "map_id",
        "map_epoch",
        "x_m",
        "y_m",
        "z_m",
        "yaw_rad",
        "observed_at",
        "valid",
    }
)


@dataclass(frozen=True)
class ObservationRecord:
    device_id: str
    flight_state: str
    battery_percent: int | float | None
    pose: Mapping[str, object] | None
    height_estimate_m: float | None
    height_reference: str
    floor_agl_claim: bool
    beacon: Mapping[str, object]
    frame: Mapping[str, object] | None
    active_command_id: str | None
    command_completed: bool
    sent_at: str
    received_utc: str
    received_monotonic: float
    message_id: str
    mission_id: str
    epoch: int
    seq: int
    simulated: bool
    beacon_epoch: int
    frame_id: str | None
    camera_epoch: int | None
    map_epoch: int | None
    control_mode: str
    beacon_policy: str

    def to_mapping(self) -> Mapping[str, object]:
        return freeze_map(
            {
                "device_id": self.device_id,
                "flight_state": self.flight_state,
                "battery_percent": self.battery_percent,
                "pose": self.pose,
                "height_estimate_m": self.height_estimate_m,
                "height_reference": self.height_reference,
                "floor_agl_claim": self.floor_agl_claim,
                "beacon": self.beacon,
                "frame": self.frame,
                "active_command_id": self.active_command_id,
                "command_completed": self.command_completed,
                "sent_at": self.sent_at,
                "received_utc": self.received_utc,
                "received_monotonic": self.received_monotonic,
                "message_id": self.message_id,
                "mission_id": self.mission_id,
                "epoch": self.epoch,
                "seq": self.seq,
                "simulated": self.simulated,
                "beacon_epoch": self.beacon_epoch,
                "frame_id": self.frame_id,
                "camera_epoch": self.camera_epoch,
                "map_epoch": self.map_epoch,
                "control_mode": self.control_mode,
                "beacon_policy": self.beacon_policy,
            }
        )

    def journal(self) -> Mapping[str, object]:
        return freeze_map(
            {
                "kind": "drone.observation",
                "message_id": self.message_id,
                "mission_id": self.mission_id,
                "epoch": self.epoch,
                "command_id": self.active_command_id,
                "request_id": None,
                "frame_id": self.frame_id,
                "track_id": None,
                "beacon_epoch": self.beacon_epoch,
                "map_epoch": self.map_epoch,
                "camera_epoch": self.camera_epoch,
                "sent_at": self.sent_at,
                "received_utc": self.received_utc,
                "received_monotonic": self.received_monotonic,
                "height_estimate_m": self.height_estimate_m,
                "height_reference": self.height_reference,
                "floor_agl_claim": self.floor_agl_claim,
            }
        )


def normalize(
    envelope: object,
    capability: object,
    *,
    mission_epoch: object,
    received_utc: str,
    received_monotonic: float,
    height_label: object = None,
) -> ObservationRecord:
    message = _object(envelope, "envelope")
    _exact(message, _ENVELOPE, "envelope")
    if message["protocol_version"] != "2.0-draft":
        raise fault("invalid_input", "protocol_version must be 2.0-draft")
    if message["kind"] != "drone.observation":
        raise fault("invalid_input", "kind must be drone.observation")
    if message["source"] != "drone" or message["destination"] != "ground":
        raise fault("invalid_input", "observation direction must be drone to ground")
    _timestamp(message["sent_at"], "sent_at")
    _optional_timestamp(message["expires_at"], "expires_at")
    _optional_id(message["correlation_id"], "correlation_id")
    if not isinstance(message["simulated"], bool):
        raise fault("invalid_input", "simulated must be a boolean")
    payload = _object(message["payload"], "payload")
    _exact(payload, _OBSERVATION, "payload")
    armed = _armed_drone(capability)
    device_id = _ident(payload["device_id"], "device_id")
    if device_id != armed:
        raise fault("rejected", "observation device_id is not the armed drone")
    flight_state = _choice(payload["flight_state"], _FLIGHT, "flight_state")
    reference = _choice(payload["height_reference"], _REFERENCES, "height_reference")
    height = _height(payload["height_estimate_m"])
    _check_label(height_label, reference, height)
    if reference == "floor_agl" and height is None:
        raise fault("invalid_input", "floor_agl requires a reported height")
    epoch = _int(message["epoch"], "epoch")
    current = _int(mission_epoch, "mission_epoch")
    if epoch != current:
        raise fault(
            "stale_ticket",
            "observation epoch is not the current mission epoch",
            recovery_required=True,
        )
    pose = _pose(payload["pose"])
    frame = _frame(payload["frame"])
    beacon = _beacon(payload["beacon"])
    battery = _battery(payload["battery_percent"])
    control_mode = _choice(payload["control_mode"], _CONTROL, "control_mode")
    command_id = _optional_id(payload["active_command_id"], "active_command_id")
    beacon_epoch = beacon["beacon_epoch"]
    if not isinstance(beacon_epoch, int) or isinstance(beacon_epoch, bool):
        raise fault("invalid_input", "beacon_epoch must be an integer")
    frame_id = None if frame is None else _ident(frame["frame_id"], "frame_id")
    camera_epoch = None if frame is None else frame["camera_epoch"]
    if camera_epoch is not None and not isinstance(camera_epoch, int):
        raise fault("invalid_input", "camera_epoch must be an integer")
    map_epoch = None if pose is None else pose["map_epoch"]
    if map_epoch is not None and not isinstance(map_epoch, int):
        raise fault("invalid_input", "map_epoch must be an integer")
    sent_at = message["sent_at"]
    message_id = _ident(message["message_id"], "message_id")
    mission_id = _ident(message["mission_id"], "mission_id")
    if not isinstance(sent_at, str):
        raise fault("invalid_input", "sent_at must be a string")
    return ObservationRecord(
        device_id=device_id,
        flight_state=flight_state,
        battery_percent=battery,
        pose=pose,
        height_estimate_m=height,
        height_reference=reference,
        floor_agl_claim=reference == "floor_agl" and height is not None,
        beacon=beacon,
        frame=frame,
        active_command_id=command_id,
        command_completed=False,
        sent_at=sent_at,
        received_utc=received_utc,
        received_monotonic=received_monotonic,
        message_id=message_id,
        mission_id=mission_id,
        epoch=epoch,
        seq=_int(message["seq"], "seq"),
        simulated=bool(message["simulated"]),
        beacon_epoch=beacon_epoch,
        frame_id=frame_id,
        camera_epoch=camera_epoch if isinstance(camera_epoch, int) else None,
        map_epoch=map_epoch if isinstance(map_epoch, int) else None,
        control_mode=control_mode,
        beacon_policy="deferred",
    )


def rejection(error: GroundError) -> str:
    detail = error.detail.lower()
    if "bssid" in detail:
        return "bssid"
    if error.code == "stale_ticket":
        return "stale"
    return error.code


def _armed_drone(capability: object) -> str:
    message = _object(capability, "capability")
    _exact(message, _ENVELOPE, "capability")
    if message["kind"] != "capabilities.report":
        raise fault("invalid_input", "capability kind must be capabilities.report")
    payload = _object(message["payload"], "capability payload")
    _exact(payload, _CAPABILITY, "capability payload")
    if payload["role"] != "drone":
        raise fault("rejected", "capability is not the armed drone")
    if payload["validated"] is not True:
        raise fault("rejected", "drone capability is not armed")
    evidence = payload["acceptance_evidence_ref"]
    if not isinstance(evidence, str) or not evidence.strip():
        raise fault("rejected", "drone capability is not armed")
    features = payload["features"]
    if isinstance(features, (str, bytes)) or not isinstance(features, Mapping):
        raise fault("invalid_input", "capability features must be an object")
    return _ident(payload["device_id"], "capability device_id")


def _check_label(label: object, reference: str, height: float | None) -> None:
    if label is None:
        return
    if not isinstance(label, str) or label not in _REFERENCES:
        raise fault("invalid_input", "height_label must be a height reference")
    if label == reference:
        return
    if label == "floor_agl":
        shown = "null" if height is None else str(height)
        raise fault(
            "rejected",
            f"height {shown} labeled floor_agl cannot replace reference {reference}",
        )
    raise fault("rejected", "height reference cannot be relabeled")


def _beacon(value: object) -> Mapping[str, object]:
    body = _object(value, "beacon")
    _exact(body, _BEACON, "beacon")
    bssid = body["bssid"]
    if not isinstance(bssid, str) or _BSSID.fullmatch(bssid) is None:
        raise fault("invalid_input", "bssid must be six octets")
    hold = _choice(body["hold_state"], _HOLD, "hold_state")
    return freeze_map(
        {
            "beacon_id": _ident(body["beacon_id"], "beacon_id"),
            "bssid": bssid.lower(),
            "ssid": _ident(body["ssid"], "ssid"),
            "beacon_epoch": _int(body["beacon_epoch"], "beacon_epoch"),
            "hold_state": hold,
            "verified_at": _timestamp(body["verified_at"], "verified_at"),
            "hold_valid_until": _timestamp(body["hold_valid_until"], "hold_valid_until"),
        }
    )


def _pose(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    body = _object(value, "pose")
    _exact(body, _POSE, "pose")
    if not isinstance(body["valid"], bool):
        raise fault("invalid_input", "pose valid must be a boolean")
    map_id = body["map_id"]
    if map_id is not None:
        map_id = _ident(map_id, "map_id")
    return freeze_map(
        {
            "frame_id": _ident(body["frame_id"], "pose frame_id"),
            "map_id": map_id,
            "map_epoch": _int(body["map_epoch"], "map_epoch"),
            "x_m": _finite(body["x_m"], "x_m"),
            "y_m": _finite(body["y_m"], "y_m"),
            "z_m": _finite(body["z_m"], "z_m"),
            "yaw_rad": _finite(body["yaw_rad"], "yaw_rad"),
            "observed_at": _timestamp(body["observed_at"], "pose observed_at"),
            "valid": body["valid"],
        }
    )


def _frame(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    body = _object(value, "frame")
    _exact(body, _FRAME, "frame")
    digest = body["sha256"]
    if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
        raise fault("invalid_input", "frame sha256 must be 64 hex characters")
    calibration = body["camera_to_body_calibration_id"]
    if calibration is not None:
        calibration = _ident(calibration, "camera_to_body_calibration_id")
    if not isinstance(body["simulated"], bool):
        raise fault("invalid_input", "frame simulated must be a boolean")
    return freeze_map(
        {
            "frame_id": _ident(body["frame_id"], "frame_id"),
            "image_ref": _text(body["image_ref"], "image_ref", max_len=500),
            "sha256": digest,
            "captured_at": _timestamp(body["captured_at"], "captured_at"),
            "camera_id": _choice(body["camera_id"], _CAMERAS, "camera_id"),
            "camera_epoch": _int(body["camera_epoch"], "camera_epoch"),
            "width_px": _positive(body["width_px"], "width_px"),
            "height_px": _positive(body["height_px"], "height_px"),
            "camera_frame_id": _ident(body["camera_frame_id"], "camera_frame_id"),
            "camera_to_body_calibration_id": calibration,
            "simulated": body["simulated"],
        }
    )


def _height(value: object) -> float | None:
    if value is None:
        return None
    return _finite(value, "height_estimate_m")


def _battery(value: object) -> int | float | None:
    if value is None:
        return None
    number = _finite(value, "battery_percent")
    if number < 0 or number > 100:
        raise fault("invalid_input", "battery_percent must be from 0 to 100")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if float(number).is_integer():
        return int(number)
    return number


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        raise fault("invalid_input", f"{label} must be an object")
    found: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise fault("invalid_input", f"{label} keys must be strings")
        found[key] = item
    return found


def _exact(value: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    if set(value) != allowed:
        raise fault("invalid_input", f"{label} fields do not match the contract")


def _choice(value: object, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise fault("invalid_input", f"{label} is not an allowed value")
    return value


def _ident(value: object, label: str) -> str:
    return _text(value, label, max_len=160)


def _text(value: object, label: str, *, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise fault("invalid_input", f"{label} must be a non-empty string")
    return value


def _optional_id(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _ident(value, label)


def _int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise fault("invalid_input", f"{label} must be a non-negative integer")
    return value


def _positive(value: object, label: str) -> int:
    number = _int(value, label)
    if number <= 0:
        raise fault("invalid_input", f"{label} must be above zero")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", f"{label} must be a number")
    if not math.isfinite(float(value)):
        raise fault("invalid_input", f"{label} must be finite")
    return float(value)


def _timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or _TIME.fullmatch(value) is None:
        raise fault("invalid_input", f"{label} must be an RFC3339 timestamp")
    return value


def _optional_timestamp(value: object, label: str) -> None:
    if value is not None:
        _timestamp(value, label)
