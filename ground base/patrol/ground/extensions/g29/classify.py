"""Pure classification and redaction for the proposed v2 journal.

The team has not sent the final log list. ``log_schema`` ``proposed-1`` is a
revision point for a later field. It is not a claim that the list arrived.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import cast

LOG_SCHEMA = "proposed-1"
LOGS_STATUS = "proposed_pending_team"
SLOT = "feature.v2_logs"
TASK_SCHEMA = "ground-task-v2"

CATEGORIES = frozenset(
    {
        "session",
        "observation",
        "vision",
        "approval",
        "command",
        "acknowledgement",
        "safety",
        "completion",
        "persistence",
    }
)

KIND_CATEGORY: dict[str, str] = {
    "capabilities.report": "session",
    "heartbeat": "session",
    "drone.observation": "observation",
    "dog.observation": "observation",
    "rssi.window": "observation",
    "navigation.candidates": "observation",
    "vision.request": "vision",
    "vision.decision": "vision",
    "motion.proposal": "approval",
    "dog.command": "command",
    "drone.command": "command",
    "command.ack": "acknowledgement",
    "proximity.evidence": "completion",
}

MISSION_CATEGORY: dict[str, str] = {
    "drone_target_acquired": "observation",
    "dog_dispatched": "command",
    "demo_goal_reached": "completion",
    "landing_unverified": "safety",
}

JOURNAL_EVENT: dict[str, str] = {
    "session": "incident_accepted",
    "observation": "frame_validated",
    "vision": "decision_received",
    "approval": "permission_granted",
    "command": "operation_started",
    "acknowledgement": "operation_completed",
    "safety": "recovery_required",
    "completion": "mission_finished",
    "persistence": "report_saved",
}

COMMAND_KINDS = frozenset({"dog.command", "drone.command", "command.ack"})
VISION_KINDS = frozenset({"vision.request", "vision.decision"})
SOURCES = frozenset({"ground", "drone", "dog", "pi", "vision", "operator"})
DESTINATIONS = frozenset({"ground", "drone", "dog", "pi", "vision", "all"})
KINDS = frozenset(KIND_CATEGORY) | {"mission.event"}

_CREDENTIALS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "authorisation",
        "password",
        "aes_key",
        "credential",
        "secret",
    }
)
_BYTE_KEYS = frozenset(
    {
        "image_bytes",
        "image_data",
        "jpeg_bytes",
        "png_bytes",
        "raw_image",
        "pixels",
        "frame_bytes",
        "content_bytes",
        "bytes",
    }
)
_MEASUREMENT_NAMES = frozenset(
    {
        "confidence",
        "battery_percent",
        "median_rssi_dbm",
        "spread_db",
        "rssi_dbm",
        "height_estimate_m",
        "range_m",
        "horizontal_offset_m",
        "clock_error_ms",
    }
)
_SUFFIXES = (
    "_dbm",
    "_percent",
    "_rad_s",
    "_m_s",
    "_ms",
    "_px",
    "_db",
    "_rad",
    "_m",
)
_ARTIFACT_REFS = frozenset({"image_ref", "acceptance_evidence_ref", "artifact_ref"})


def category_for(kind: str, payload: Mapping[str, object]) -> tuple[str, str]:
    """Return the journal category and the distinct event name."""
    if kind == "mission.event":
        event = payload.get("event")
        if not isinstance(event, str) or not event.strip():
            return "observation", "mission.event"
        name = event.strip()
        return MISSION_CATEGORY.get(name, "observation"), name
    category = KIND_CATEGORY.get(kind, "")
    if kind == "command.ack" and payload.get("reason_code") == "landing_not_verified":
        return category, "landing_not_verified"
    return category, kind


def missing_correlation(kind: str, payload: Mapping[str, object]) -> str | None:
    """Return a rejection detail when a required id for this kind is absent."""
    if kind in COMMAND_KINDS and _text_at(payload, "command_id") is None:
        return "command record is missing command_id"
    if kind not in VISION_KINDS:
        return None
    missing: list[str] = []
    if _text_at(payload, "request_id") is None:
        missing.append("request_id")
    if vision_frame_id(payload) is None:
        missing.append("frame_id")
    if not missing:
        return None
    return "vision record is missing " + " and ".join(missing)


def correlation(payload: Mapping[str, object]) -> dict[str, object]:
    """Copy optional ids. Absent ids are omitted. Invalid numbers are not zero."""
    found: dict[str, object] = {}
    for key in ("command_id", "request_id", "proposal_id", "track_id"):
        value = _first_text(payload, key, skip_under=frozenset())
        if value is not None:
            found[key] = value
    frame = vision_frame_id(payload)
    if frame is None:
        frame = _first_text(payload, "frame_id", skip_under=frozenset({"pose"}))
    if frame is None:
        frame = _first_text(payload, "frame_id", skip_under=frozenset())
    if frame is not None:
        found["frame_id"] = frame
    for key in ("beacon_epoch", "map_epoch", "camera_epoch"):
        epoch = _first_int(payload, key)
        if epoch is not None:
            found[key] = epoch
    return found


def vision_frame_id(payload: Mapping[str, object]) -> str | None:
    """Camera frame on a vision message. A pose frame is not a substitute."""
    direct = _text_at(payload, "frame_id")
    if direct is not None:
        return direct
    frame = payload.get("frame")
    nested = _as_dict(frame)
    if nested is None:
        return None
    return _text_at(nested, "frame_id")


def sanitize(
    payload: Mapping[str, object],
    denylist: set[str],
) -> tuple[dict[str, object], list[str], dict[str, str], dict[str, str], list[str]]:
    """Return summary, redacted paths, measurement reasons, artifacts, omitted paths."""
    redacted: list[str] = []
    reasons: dict[str, str] = {}
    artifacts: dict[str, str] = {}
    omitted: list[str] = []
    summary = _clean(dict(payload), denylist, redacted, reasons, artifacts, omitted, "")
    if not isinstance(summary, dict):
        summary = {}
    return summary, redacted, reasons, artifacts, omitted


def normalize_name(value: str) -> str:
    return value.casefold().replace("-", "_")


def _is_secret(key: str, denylist: set[str]) -> bool:
    folded = normalize_name(key)
    return folded in denylist or folded in _CREDENTIALS


def _is_measurement(key: str) -> bool:
    return key in _MEASUREMENT_NAMES or key.endswith(_SUFFIXES)


def _clean(
    value: object,
    denylist: set[str],
    redacted: list[str],
    reasons: dict[str, str],
    artifacts: dict[str, str],
    omitted: list[str],
    path: str,
) -> object:
    mapping = _as_dict(value)
    if mapping is not None:
        cleaned: dict[str, object] = {}
        for key, item in mapping.items():
            child = key if not path else f"{path}.{key}"
            if _is_secret(key, denylist):
                redacted.append(child)
                continue
            if _drops_bytes(key, item):
                omitted.append(child)
                continue
            if key in _ARTIFACT_REFS and isinstance(item, str) and item:
                artifacts.setdefault("artifact_ref", item)
            if key == "sha256" and isinstance(item, str) and item:
                artifacts.setdefault("artifact_sha256", item)
            if _is_measurement(key):
                number, reason = _measurement(item)
                if reason is not None:
                    reasons[child] = reason
                    cleaned[key] = None
                    continue
                cleaned[key] = number
                continue
            cleaned[key] = _clean(item, denylist, redacted, reasons, artifacts, omitted, child)
        return cleaned
    if isinstance(value, (list, tuple)):
        items: list[object] = []
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            items.append(_clean(item, denylist, redacted, reasons, artifacts, omitted, child))
        return items
    if isinstance(value, (bytes, bytearray)):
        omitted.append(path or "bytes")
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def _drops_bytes(key: str, item: object) -> bool:
    if key in _BYTE_KEYS or isinstance(item, (bytes, bytearray)):
        return True
    if key == "image" and isinstance(item, str) and not item.startswith("artifact:"):
        return len(item) > 256
    return False


def _measurement(value: object) -> tuple[object, str | None]:
    if value is None:
        return None, "unknown"
    if isinstance(value, str):
        if value.strip().casefold() in {"", "unknown", "null", "none"}:
            return None, "unknown"
        return None, "not_a_number"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "not_a_number"
    if not math.isfinite(float(value)):
        return None, "not_finite"
    return value, None


def _text_at(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _first_text(
    node: object,
    key: str,
    *,
    skip_under: frozenset[str],
) -> str | None:
    found: list[object] = []
    _walk(node, key, skip_under, False, found)
    for item in found:
        if isinstance(item, str) and item.strip():
            return item
    return None


def _first_int(node: object, key: str) -> int | None:
    found: list[object] = []
    _walk(node, key, frozenset(), False, found)
    for item in found:
        if isinstance(item, bool) or not isinstance(item, int):
            continue
        if item < 0:
            continue
        return item
    return None


def _walk(
    node: object,
    key: str,
    skip_under: frozenset[str],
    skipped: bool,
    found: list[object],
) -> None:
    mapping = _as_dict(node)
    if mapping is not None:
        if not skipped and key in mapping:
            found.append(mapping[key])
        for child_key, child in mapping.items():
            child_skipped = skipped or child_key in skip_under
            _walk(child, key, skip_under, child_skipped, found)
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, key, skip_under, skipped, found)


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        return None
    copied: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        copied[key] = item
    return copied
