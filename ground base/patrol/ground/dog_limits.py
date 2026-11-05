"""Speed ceiling for commands Ground sends to the dog.

The dog folder's hand-control recommendations are below the adapter's hard
caps: 0.3 m/s forward and back, 0.2 m/s sideways, 0.6 rad/s turn, and a one
second step. A raw command at those values can still run away on a museum
floor, so the unattended demo starts at one fifth of each of them. A slider can move
back up, and it cannot pass the dog-folder recommendation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

RECOMMENDED = {
    "forward_m_s": 0.3,
    "side_m_s": 0.2,
    "yaw_rad_s": 0.6,
    "step_s": 1.0,
}
DEMO_SCALE = 0.2
_FLOOR = {
    "forward_m_s": 0.05,
    "side_m_s": 0.05,
    "yaw_rad_s": 0.05,
    "step_s": 0.3,
}


def default_limits() -> dict[str, float]:
    return {key: round(RECOMMENDED[key] * DEMO_SCALE, 3) for key in RECOMMENDED}


def clamp_limits(raw: object) -> dict[str, float]:
    """Keep every axis inside the dog-folder recommendation."""
    source = raw if isinstance(raw, Mapping) else {}
    limits = default_limits()
    for key, ceiling in RECOMMENDED.items():
        if key not in source:
            continue
        try:
            value = float(source[key])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        limits[key] = round(min(ceiling, max(_FLOOR[key], value)), 3)
    return limits


def apply_limits(segment: Mapping[str, Any], limits: Mapping[str, float]) -> dict[str, float | str]:
    """Clip one body-frame step. Positive side speed is left, matching the dog joystick."""
    caps = clamp_limits(limits)

    def clip(name: str, cap_key: str) -> float:
        try:
            value = float(segment[name])
        except (KeyError, TypeError, ValueError):
            return 0.0
        if not math.isfinite(value):
            return 0.0
        return max(-caps[cap_key], min(caps[cap_key], value))

    try:
        duration = float(segment["duration_s"])
    except (KeyError, TypeError, ValueError):
        duration = caps["step_s"]
    if not math.isfinite(duration):
        duration = caps["step_s"]
    return {
        "vx": clip("vx", "forward_m_s"),
        "vy": clip("vy", "side_m_s"),
        "vyaw": clip("vyaw", "yaw_rad_s"),
        "duration_s": round(min(caps["step_s"], max(0.3, duration)), 3),
        "command_id": str(segment.get("command_id") or "ground"),
    }


def direction_steps(limits: Mapping[str, float]) -> list[dict[str, float | str]]:
    """One stopped step forward, back, right, then left."""
    caps = clamp_limits(limits)
    forward = caps["forward_m_s"]
    side = caps["side_m_s"]
    duration = caps["step_s"]
    signed = (
        ("forward", forward, 0.0),
        ("back", -forward, 0.0),
        ("right", 0.0, -side),
        ("left", 0.0, side),
    )
    return [
        {
            "vx": vx,
            "vy": vy,
            "vyaw": 0.0,
            "duration_s": duration,
            "command_id": f"dog-test-{name}",
        }
        for name, vx, vy in signed
    ]
