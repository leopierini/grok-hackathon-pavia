"""Ground's client for the drone teammate's flight server (``patrol.drone.manual``).

The flight server owns the Tello link, the deadman (sticks go to zero 300 ms
after the last update) and land-always. Ground only asks it for state and
frames, and sends hover, land, takeoff and short yaw nudges. It never sends a
raw Tello SDK string.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

SID = "ground-live"


class DroneError(Exception):
    pass


class DroneHttp:
    def __init__(self, base: str = "http://127.0.0.1:8766", timeout_s: float = 2.0) -> None:
        self.base = base.rstrip("/")
        self.timeout_s = timeout_s
        self._seq = 0

    def _get(self, path: str) -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=self.timeout_s) as resp:
                return int(resp.status), resp.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), b""
        except (urllib.error.URLError, OSError) as exc:
            raise DroneError(f"drone server unreachable: {exc}") from exc

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                parsed = json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            raise DroneError(f"drone server refused {path}: HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise DroneError(f"drone server unreachable: {exc}") from exc
        return parsed if isinstance(parsed, dict) else {"ok": False, "error": "reply was not an object"}

    async def state(self) -> dict[str, Any]:
        status, body = await asyncio.to_thread(self._get, "/state.json")
        if status != 200:
            raise DroneError(f"drone state HTTP {status}")
        parsed = json.loads(body.decode())
        if not isinstance(parsed, dict):
            raise DroneError("drone state was not an object")
        return parsed

    async def frame(self) -> bytes | None:
        status, body = await asyncio.to_thread(self._get, "/frame.jpg")
        if status != 200 or not body.startswith(b"\xff\xd8"):
            return None
        return body

    async def cmd(self, action: str) -> dict[str, Any]:
        if action not in {"takeoff", "land", "hover"}:
            raise DroneError(f"Ground does not send drone action {action!r}")
        return await asyncio.to_thread(self._post, "/cmd", {"action": action})

    async def yaw_nudge(self, axis: float, seconds: float) -> None:
        """Yaw only, |axis| <= 0.5, at most 0.8 s, then explicit zero. The server deadman backs it up."""
        axis = max(-0.5, min(0.5, float(axis)))
        seconds = max(0.0, min(0.8, float(seconds)))
        loop = asyncio.get_running_loop()
        end = loop.time() + seconds
        try:
            while loop.time() < end:
                self._seq += 1
                await asyncio.to_thread(
                    self._post, "/sticks", {"lr": 0, "fb": 0, "ud": 0, "yaw": axis, "sid": SID, "seq": self._seq}
                )
                await asyncio.sleep(0.1)
        finally:
            self._seq += 1
            await asyncio.to_thread(
                self._post, "/sticks", {"lr": 0, "fb": 0, "ud": 0, "yaw": 0, "sid": SID, "seq": self._seq}
            )
