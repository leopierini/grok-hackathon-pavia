"""Real vision transport. The published Ground route is /ws/robot/v2."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def published_endpoint() -> dict[str, object]:
    """Host, port, and auth for the operator's /ws/robot/v2 listener."""
    path = _config_path()
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("robot_v2.json must be an object")
    host = parsed.get("host")
    port = parsed.get("port")
    header = parsed.get("auth_header")
    auth_env = parsed.get("auth_env")
    route = parsed.get("route")
    if (
        not isinstance(host, str)
        or not host
        or isinstance(port, bool)
        or not isinstance(port, int)
        or not isinstance(header, str)
        or not header
        or not isinstance(auth_env, str)
        or not auth_env
        or route != "/ws/robot/v2"
    ):
        raise ValueError("robot_v2.json is missing host, port, or auth")
    return {
        "route": route,
        "host": host,
        "port": port,
        "auth_header": header,
        "auth_env": auth_env,
        "url": f"ws://{host}:{port}{route}",
    }


def main() -> int:
    try:
        endpoint = published_endpoint()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.stderr.write(
            "patrol.vision_v2: real mode exits 2; "
            f"/ws/robot/v2 host, port, and auth are unset ({exc})\n"
        )
        return 2
    sys.stdout.write(json.dumps(endpoint) + "\n")
    return 0


def _config_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "ground base" / "config" / "robot_v2.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("ground base/config/robot_v2.json")


if __name__ == "__main__":
    raise SystemExit(main())
