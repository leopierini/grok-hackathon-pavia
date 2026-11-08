"""Real-peer configuration for the museum story.

Hosts, ports, and the Grok key come from the environment or a config file.
This module does not invent them and does not open a socket.
"""

from __future__ import annotations

from collections.abc import Mapping

MOTION_FLAG = "--i-understand-this-moves-hardware"


class ConfigError(Exception):
    """Closed configuration failure. The text must not contain a secret."""

DOG_FENCE_M = 1.5
DOG_MAX_SPEED_MPS = 0.25
DOG_MAX_ROUTE_S = 8.0
DOG_COMMAND_TIMEOUT_S = 2.0
DOG_CONNECT_TIMEOUT_S = 8.0
DOG_MAX_TILT_DEG = 20.0

DRONE_MAX_FLIGHT_S = 8.0
DRONE_SETTLE_S = 1.0
DRONE_HOLD_S = 1.0
DRONE_BATTERY_MIN = 20
DRONE_COMMAND_TIMEOUT_S = 5.0
DRONE_LINK_TIMEOUT_S = 2.0

# action -> (owner, issue numbers, what Ground refused to invent)
KNOWN_GAPS: dict[str, tuple[str, tuple[str, ...], str]] = {
    "follow": (
        "Leo",
        ("28", "78"),
        "RealDog refuses follow. Museum did not invent a walk and did not start the RSSI follower.",
    ),
    "return_home": (
        "Leo",
        ("28", "78"),
        "No confirmed return path. Museum did not call robot/go2/goal.py.",
    ),
    "stop": (
        "Leo",
        ("28", "78"),
        "stop is not halt, and this adapter has no stop_move.",
    ),
    "land_on_dog": (
        "Federico",
        ("72", "53", "73"),
        "land_on_dog was not sent. floor land() was not called.",
    ),
    "play_warning": (
        "Leo",
        ("28",),
        "The dog adapter could not speak. No speaker call was made outside that adapter.",
    ),
}


def gap(action: str) -> dict[str, object]:
    owner, issues, detail = KNOWN_GAPS[action]
    return {
        "action": action,
        "owner": owner,
        "issues": list(issues),
        "detail": detail,
    }


def motion_required_message() -> str:
    return (
        "real mode refused: pass --i-understand-this-moves-hardware before any motion. "
        "No socket was opened."
    )


def _blank(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def require_endpoint(
    peer: str,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
) -> tuple[str, int]:
    """Return ``(host, port)`` or raise. The error names the missing variable and not the value."""

    host_env = f"PATROL_{peer.upper()}_HOST"
    port_env = f"PATROL_{peer.upper()}_PORT"
    file_host: object = None
    file_port: object = None
    if isinstance(file_config, Mapping):
        section = file_config.get(peer)
        if isinstance(section, Mapping):
            file_host = section.get("host")
            file_port = section.get("port")
    host = _blank(environ.get(host_env)) or _blank(file_host)
    port_text = _blank(environ.get(port_env)) or _blank(file_port)
    missing = [name for name, value in ((host_env, host), (port_env, port_text)) if value is None]
    if missing:
        joined = ", ".join(missing)
        raise ConfigError(
            f"{peer} real refused: {joined} unset. No socket was opened. "
            "Set the variables in the environment, or pass --config with those "
            "values filled in. The example file leaves them null on purpose."
        )
    assert host is not None and port_text is not None
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ConfigError(
            f"{peer} real refused: {port_env} is not a valid port. No socket was opened."
        ) from exc
    if not 1 <= port <= 65535:
        raise ConfigError(
            f"{peer} real refused: {port_env} is not a valid port. No socket was opened."
        )
    return host, port


def dog_real_config(host: str) -> dict[str, object]:
    """Conservative WebRTC session. The port is not a RealDog field, so it is not copied in."""

    return {
        "interface": host,
        "connection_mode": "LocalSTA",
        "command_timeout_s": DOG_COMMAND_TIMEOUT_S,
        "connect_timeout_s": DOG_CONNECT_TIMEOUT_S,
        "max_route_s": DOG_MAX_ROUTE_S,
        "fence_radius_m": DOG_FENCE_M,
        "max_speed_mps": DOG_MAX_SPEED_MPS,
        "max_tilt_deg": DOG_MAX_TILT_DEG,
        "lidar_enabled": False,
        "safety_envelope_enabled": True,
    }


def drone_real_config(
    host: str,
    port: int,
    *,
    motion_authorized: bool,
    timing: Mapping[str, float] | None = None,
) -> dict[str, object]:
    extra = dict(timing or {})
    return {
        "host": host,
        "port": port,
        "motion_authorized": motion_authorized,
        "max_flight_s": extra.get("max_flight_s", DRONE_MAX_FLIGHT_S),
        "settle_s": extra.get("settle_s", DRONE_SETTLE_S),
        "hold_s": extra.get("hold_s", DRONE_HOLD_S),
        "battery_min_percent": DRONE_BATTERY_MIN,
        "command_timeout_s": DRONE_COMMAND_TIMEOUT_S,
        "link_timeout_s": DRONE_LINK_TIMEOUT_S,
    }


def secret_values(
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
) -> list[str]:
    """Values that must not appear in printed errors or reports."""

    found: list[str] = []
    for name in ("XAI_API_KEY", "PATROL_DOG_HOST", "PATROL_DRONE_HOST"):
        value = environ.get(name, "")
        if isinstance(value, str) and len(value.strip()) >= 4:
            found.append(value.strip())
    if isinstance(file_config, Mapping):
        for peer in ("dog", "drone"):
            section = file_config.get(peer)
            if isinstance(section, Mapping):
                host = section.get("host")
                if isinstance(host, str) and len(host.strip()) >= 4:
                    found.append(host.strip())
    return found


def redact(text: str, secrets: list[str]) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned
