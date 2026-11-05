"""Validate operator settings. Secrets are rejected and never echoed."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.settings import make_settings

Json = dict[str, Any]
_SECRET = ("secret", "password", "token", "api_key", "apikey", "credential", "private_key", "authorization")
_MODES = frozenset({"fake", "real"})
_CAMERAS = {"drone": frozenset({"front", "downward"}), "dog": frozenset({"front"})}
_PATHS = frozenset({None, "usb", "wire", "second_radio"})
_FIELDS = (
    "dog_transport",
    "connection_profiles",
    "modes",
    "pi_data_path",
    "vision",
    "cameras",
    "evidence_age_ms",
    "image_sample_ms",
    "vision_timeout_ms",
    "command_lease_ms",
    "flight_profile",
    "calibration_id",
    "dog_range_max_m",
    "drone_horizontal_max_m",
    "output_root",
    "pace_s",
)


class ConfigError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


def default_config() -> Json:
    return {
        "dog_transport": "ethernet",
        "connection_profiles": {
            "dog": "dog.ethernet",
            "drone": "tello-edu-ap",
            "pi": "pi-usb",
            "vision": "grok-laptop",
        },
        "modes": {"dog": "fake", "drone": "fake", "grok": "fake"},
        "pi_data_path": "usb",
        "vision": {
            "model_id": "CONFIGURE_VERIFIED_IMAGE_MODEL",
            "prompt_version": "patrol-demo-v2.0",
        },
        "cameras": {"drone": ["front", "downward"], "dog": ["front"]},
        "evidence_age_ms": 3000,
        "image_sample_ms": 1000,
        "vision_timeout_ms": 5000,
        "command_lease_ms": 500,
        "flight_profile": {"name": "proposed_4m_floor_agl", "enabled": False},
        "calibration_id": None,
        "dog_range_max_m": None,
        "drone_horizontal_max_m": None,
        "output_root": "artifacts/operator-runs",
        "pace_s": 0.12,
    }


def explain_unset(config: Mapping[str, Any]) -> list[Json]:
    notes: list[Json] = []
    if config.get("calibration_id") is None:
        notes.append(
            {
                "field": "calibration_id",
                "detail": "No operator calibration reference is set. A frame may still carry its own id.",
            }
        )
    if config.get("dog_range_max_m") is None:
        notes.append(
            {
                "field": "dog_range_max_m",
                "detail": "Dog-target range threshold is unset. It is not zero and cannot authorize a real goal.",
            }
        )
    if config.get("drone_horizontal_max_m") is None:
        notes.append(
            {
                "field": "drone_horizontal_max_m",
                "detail": "Drone horizontal offset threshold is unset. It is not zero and is not altitude.",
            }
        )
    if config.get("pi_data_path") is None:
        notes.append(
            {
                "field": "pi_data_path",
                "detail": "Pi telemetry path is unset. Live RSSI homing stays unavailable.",
            }
        )
    profile = config.get("flight_profile")
    if isinstance(profile, Mapping) and profile.get("enabled") is not True:
        notes.append(
            {
                "field": "flight_profile",
                "detail": "The 4 m floor-AGL profile is a proposal. It is not an enabled default.",
            }
        )
    return notes


def apply_timing() -> Json:
    return {field: "idle_or_new_session" for field in _FIELDS}


def validate_config(raw: object) -> Json:
    if not isinstance(raw, Mapping):
        raise ConfigError("invalid_input", "configuration must be an object")
    unknown = sorted(set(raw) - set(_FIELDS))
    if unknown:
        raise ConfigError("invalid_input", "unknown configuration fields")
    _reject_secrets(raw)
    current = default_config()
    current.update({key: raw[key] for key in raw})
    transport = _choice(current.get("dog_transport"), "dog_transport", frozenset({"ethernet", "wifi"}))
    profiles = _profiles(current.get("connection_profiles"))
    modes = _modes(current.get("modes"))
    path = current.get("pi_data_path")
    if path not in _PATHS:
        raise ConfigError("invalid_input", "pi_data_path must be usb, wire, second_radio, or null")
    vision = _vision(current.get("vision"))
    cameras = _cameras(current.get("cameras"))
    evidence_age = _millis("evidence_age_ms", current.get("evidence_age_ms"), 120_000)
    sample = _millis("image_sample_ms", current.get("image_sample_ms"), 60_000)
    timeout = _millis("vision_timeout_ms", current.get("vision_timeout_ms"), 120_000)
    lease = _millis("command_lease_ms", current.get("command_lease_ms"), 500)
    flight = _flight(current.get("flight_profile"))
    calibration = _optional_token(current.get("calibration_id"), "calibration_id")
    dog_range = _optional_meters(current.get("dog_range_max_m"), "dog_range_max_m")
    drone_offset = _optional_meters(current.get("drone_horizontal_max_m"), "drone_horizontal_max_m")
    output = _relative(current.get("output_root"))
    pace = _pace(current.get("pace_s"))
    try:
        make_settings(
            dog_transport=transport,
            profile_identity=profiles["dog"],
            modes=modes,
            output_root=output,
            scenario="blocked_resolved",
        )
    except GroundFault as exc:
        detail = exc.error.detail
        if any(part in detail.lower() for part in _SECRET):
            detail = "configuration was rejected"
        raise ConfigError(exc.error.code, detail) from exc
    return {
        "dog_transport": transport,
        "connection_profiles": profiles,
        "modes": modes,
        "pi_data_path": path,
        "vision": vision,
        "cameras": cameras,
        "evidence_age_ms": evidence_age,
        "image_sample_ms": sample,
        "vision_timeout_ms": timeout,
        "command_lease_ms": lease,
        "flight_profile": flight,
        "calibration_id": calibration,
        "dog_range_max_m": dog_range,
        "drone_horizontal_max_m": drone_offset,
        "output_root": output,
        "pace_s": pace,
    }


def redacted_config(config: Mapping[str, Any]) -> Json:
    return {
        "dog_transport": config.get("dog_transport"),
        "connection_profiles": dict(config.get("connection_profiles", {})),
        "modes": dict(config.get("modes", {})),
        "pi_data_path": config.get("pi_data_path"),
        "vision": {
            "model_id": (config.get("vision") or {}).get("model_id"),
            "prompt_version": (config.get("vision") or {}).get("prompt_version"),
        },
        "cameras": config.get("cameras"),
        "evidence_age_ms": config.get("evidence_age_ms"),
        "image_sample_ms": config.get("image_sample_ms"),
        "vision_timeout_ms": config.get("vision_timeout_ms"),
        "command_lease_ms": config.get("command_lease_ms"),
        "flight_profile": config.get("flight_profile"),
        "calibration_id": config.get("calibration_id"),
        "dog_range_max_m": config.get("dog_range_max_m"),
        "drone_horizontal_max_m": config.get("drone_horizontal_max_m"),
        "output_root": config.get("output_root"),
        "pace_s": config.get("pace_s"),
        "secrets": "not stored",
    }


def _reject_secrets(value: object, field: str = "") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key).lower()
            if any(part in name for part in _SECRET):
                label = f"{field}{key}"
                raise ConfigError("secret_rejected", f"secret field {label} is not accepted")
            _reject_secrets(item, f"{field}{key}.")
    elif isinstance(value, list):
        for item in value:
            _reject_secrets(item, field)


def _choice(value: object, name: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ConfigError("invalid_input", f"{name} is not an allowed value")
    return value


def _profiles(value: object) -> Json:
    if not isinstance(value, Mapping) or set(value) != {"dog", "drone", "pi", "vision"}:
        raise ConfigError("invalid_input", "connection profiles must name dog, drone, pi, and vision")
    cleaned: Json = {}
    for key, item in value.items():
        cleaned[str(key)] = _token(item, f"{key} profile")
    return cleaned


def _modes(value: object) -> Json:
    if not isinstance(value, Mapping) or set(value) != {"dog", "drone", "grok"}:
        raise ConfigError("invalid_input", "modes must name dog, drone, and grok")
    cleaned: Json = {}
    for key, item in value.items():
        if item not in _MODES:
            raise ConfigError("invalid_input", "adapter mode must be fake or real")
        cleaned[str(key)] = item
    return cleaned


def _vision(value: object) -> Json:
    if not isinstance(value, Mapping) or set(value) != {"model_id", "prompt_version"}:
        raise ConfigError("invalid_input", "vision needs model_id and prompt_version")
    return {
        "model_id": _token(value.get("model_id"), "model_id"),
        "prompt_version": _token(value.get("prompt_version"), "prompt_version"),
    }


def _cameras(value: object) -> Json:
    if not isinstance(value, Mapping) or set(value) != {"drone", "dog"}:
        raise ConfigError("invalid_input", "cameras must name drone and dog")
    cleaned: Json = {}
    for role, allowed in _CAMERAS.items():
        selected = value.get(role)
        if not isinstance(selected, list) or not selected:
            raise ConfigError("invalid_input", f"{role} cameras must be a nonempty list")
        if any(not isinstance(item, str) or item not in allowed for item in selected):
            raise ConfigError("invalid_input", f"{role} camera is unknown; rear is not a project camera")
        if len(set(selected)) != len(selected):
            raise ConfigError("invalid_input", f"{role} cameras must be unique")
        cleaned[role] = list(selected)
    return cleaned


def _flight(value: object) -> Json:
    if not isinstance(value, Mapping) or set(value) != {"name", "enabled"}:
        raise ConfigError("invalid_input", "flight_profile needs name and enabled")
    name = _token(value.get("name"), "flight profile")
    enabled = value.get("enabled")
    if enabled is not False:
        raise ConfigError(
            "rejected",
            "flight profile cannot be enabled; the 4 m proposal is not an accepted default",
        )
    return {"name": name, "enabled": False}


def _millis(name: str, value: object, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("invalid_input", f"{name} must be an integer")
    if not 1 <= value <= maximum:
        raise ConfigError("invalid_input", f"{name} must be from 1 to {maximum}")
    return value


def _optional_meters(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("invalid_input", f"{name} must be null or a number")
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= 100:
        raise ConfigError("invalid_input", f"{name} must be a positive finite number or null")
    return number


def _optional_token(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _token(value, name)


def _token(value: object, name: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 120:
        raise ConfigError("invalid_input", f"{name} must be 1 to 120 characters")
    if any(char.isspace() for char in value):
        raise ConfigError("invalid_input", f"{name} cannot contain whitespace")
    return value


def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")) or ".." in value:
        raise ConfigError("invalid_input", "output_root must be a relative path without ..")
    if ":" in value:
        raise ConfigError("invalid_input", "output_root must not be absolute")
    return value


def _pace(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("invalid_input", "pace_s must be a number")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ConfigError("invalid_input", "pace_s must be from 0 to 1")
    return number
