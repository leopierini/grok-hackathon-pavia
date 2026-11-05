"""Motor-text scan shared by the museum story.

The lists match Task 16. A scene label such as ``stop`` is legal in
``suggested_action``. The same word in free text is not.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

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
_SDK = re.compile(
    r"send_rc_control|move_forward|move_back|djitellopy|unitree|webrtc|StopMove",
    re.IGNORECASE,
)


def motor_phrase(text: str) -> str | None:
    """Return a rejection token when free text is a motor or SDK phrase."""

    folded = " ".join(text.strip().lower().split())
    if not folded:
        return None
    if folded in _TELLO_EXACT or any(folded.startswith(prefix) for prefix in _TELLO_PREFIXES):
        return "sdk_reason"
    if _DISTANCE.search(folded) or _SDK.search(folded):
        return "invented_distance" if _DISTANCE.search(folded) else "sdk_reason"
    return None


def decision_motor_phrase(decision: Mapping[str, object]) -> str | None:
    """Scan the reason. Enum fields are not free text."""

    payload = decision.get("payload")
    if not isinstance(payload, Mapping):
        return "payload"
    reason = payload.get("reason")
    if not isinstance(reason, str):
        return "reason"
    return motor_phrase(reason)
