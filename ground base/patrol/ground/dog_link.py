"""Translate one approved Ground dog command into the dog's Ethernet session.

The dog package is a separate ``patrol`` tree, so it runs in its own process.
This module never imports it. Drone evidence is not sent here.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from patrol.ground.dog_limits import apply_limits, default_limits
from patrol.ground.kernel.paths import repo_root
from patrol.ground.radio import LinkError


def _dog_python(root: Path) -> str:
    """Prefer the dog checkout's own interpreter. It owns the Unitree library."""
    for parts in (
        (".venv", "Scripts", "python.exe"),
        (".venv", "bin", "python"),
    ):
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def dog_backend_root() -> Path:
    """The dog tree that sits next to ground base, or next to this checkout."""
    root = repo_root()
    candidates = (
        root.parent / "dog backend",
        root.parent / "grok-hackathon-pavia" / "dog backend",
    )
    for candidate in candidates:
        if (candidate / "patrol" / "dog" / "ground_bridge.py").is_file():
            return candidate
    raise LinkError("dog backend was not found beside ground base or this checkout")


def segment_from_command(command: Mapping[str, Any]) -> dict[str, float | str]:
    """The one motion Ground is allowed to put on the cable.

    ``move_local`` is a body-frame velocity for a few hundred milliseconds.
    Anything else, including a route replay, is refused.
    """
    payload = command.get("payload")
    if not isinstance(payload, Mapping) or payload.get("action") != "move_local":
        raise LinkError("only an approved move_local command can be sent to the dog")
    motion = payload.get("motion")
    if not isinstance(motion, Mapping):
        raise LinkError("dog command has no motion object")
    try:
        duration_s = float(motion["duration_ms"]) / 1000.0
        segment: dict[str, float | str] = {
            "vx": float(motion["linear_x_m_s"]),
            "vy": float(motion["linear_y_m_s"]),
            "vyaw": float(motion["angular_z_rad_s"]),
            "duration_s": duration_s,
            "command_id": str(payload["command_id"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise LinkError("dog motion is missing a finite velocity or duration") from exc
    if not 0 < duration_s <= 10:
        raise LinkError("dog motion duration must be between 0 and 10 seconds")
    return segment


CABLE_LIMIT_M = 0.5
CLEAR_MIN_M = 0.5


def direction_clearance_m(view: Mapping[str, Any], vx: float, vy: float) -> float | None:
    """Free space in metres along the commanded body direction. None if LiDAR did not say."""
    if view.get("stale") is True:
        return None
    clear = view.get("clear")
    bins = clear.get("m") if isinstance(clear, Mapping) else None
    if not isinstance(bins, list) or len(bins) < 24:
        return None
    if abs(vx) < 1e-4 and abs(vy) < 1e-4:
        return None
    index = int(round(math.atan2(vy, vx) / (2 * math.pi / 24))) % 24
    try:
        return float(bins[index])
    except (TypeError, ValueError):
        return None


class EthernetDogLink:
    """A running ``ground_bridge`` process. One WebRTC client, no camera, no drone."""

    def __init__(
        self,
        output: Path,
        *,
        armed: bool,
        fake: bool = False,
        ip: str = "192.168.123.161",
        limits: Mapping[str, float] | None = None,
    ) -> None:
        self.output = output
        self.armed = armed
        self.fake = fake
        self.ip = ip
        self.limits = default_limits() if limits is None else dict(limits)
        self.ready: dict[str, Any] | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._io = asyncio.Lock()
        self._stderr_text = ""
        self._stderr_task: asyncio.Task[None] | None = None

    async def connect(self) -> dict[str, Any]:
        if self._proc is not None:
            if self.ready is None:
                raise LinkError("dog bridge is already starting")
            return self.ready
        root = dog_backend_root()
        self.output.mkdir(parents=True, exist_ok=True)
        command = [
            _dog_python(root),
            "-m",
            "patrol.dog.ground_bridge",
            "--output",
            str(self.output),
            "--ip",
            self.ip,
        ]
        if self.fake:
            command.append("--fake")
        if self.armed:
            command.append("--arm")
        self._proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=4 * 1024 * 1024,
        )
        assert self._proc.stdout is not None
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        try:
            ready = await self._read_json(45)
        except LinkError as exc:
            if "closed its output" in str(exc):
                error = await self._stderr()
                raise LinkError(error or "dog bridge exited before it was ready") from exc
            raise
        if ready.get("ok") is not True:
            detail = "dog bridge ready line was not an object"
            if isinstance(ready, dict):
                detail = str(ready.get("detail") or "dog bridge did not connect")
            raise LinkError(detail)
        self.ready = ready
        return ready

    async def execute(self, command: Mapping[str, Any]) -> dict[str, Any]:
        segment = apply_limits(segment_from_command(command), self.limits)
        return await self.move_segment(segment)

    async def move_segment(self, segment: Mapping[str, Any]) -> dict[str, Any]:
        bounded = apply_limits(segment, self.limits)
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise LinkError("dog bridge is not connected")
        parsed = await self._roundtrip({"op": "move", "segment": bounded})
        parsed["segment"] = bounded
        return parsed

    async def halt(self) -> dict[str, Any]:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            return {
                "op": "halt",
                "ok": False,
                "sent": False,
                "detail": "dog bridge is not connected",
            }
        return await self._roundtrip({"op": "halt"})

    async def frame(self) -> dict[str, Any]:
        parsed = await self._roundtrip({"op": "frame"}, timeout=5)
        raw = parsed.pop("jpeg_b64", None)
        if parsed.get("ok") is True and isinstance(raw, str):
            parsed["jpeg"] = base64.b64decode(raw)
        return parsed

    async def lidar(self) -> dict[str, Any]:
        return await self._roundtrip({"op": "lidar"}, timeout=5)

    async def _roundtrip(self, message: Mapping[str, Any], timeout: float = 30) -> dict[str, Any]:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise LinkError("dog bridge is not connected")
        async with self._io:
            self._proc.stdin.write(json.dumps(message).encode() + b"\n")
            await self._proc.stdin.drain()
            return await self._read_json(timeout)

    async def _read_json(self, timeout: float) -> dict[str, Any]:
        """Read the next JSON object. The Unitree library also prints status lines."""
        if self._proc is None or self._proc.stdout is None:
            raise LinkError("dog bridge is not connected")
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise LinkError("dog bridge did not send a JSON reply in time")
            try:
                line = await asyncio.wait_for(self._proc.stdout.readline(), remaining)
            except TimeoutError as exc:
                raise LinkError("dog bridge did not send a JSON reply in time") from exc
            if not line:
                raise LinkError("dog bridge closed its output")
            text = line.decode(errors="replace").strip()
            if not text.startswith("{"):
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    async def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        if proc.stdin is not None and proc.returncode is None:
            try:
                proc.stdin.write(b'{"op":"close"}\n')
                proc.stdin.close()
            except OSError:
                pass
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        # Waiting on the process can stall the operator after the dog has already exited.
        asyncio.create_task(_reap(proc))

    async def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        parts: list[bytes] = []
        try:
            while True:
                block = await proc.stderr.read(4096)
                if not block:
                    break
                parts.append(block)
                if sum(len(item) for item in parts) > 65536:
                    parts = parts[-8:]
                self._stderr_text = b"".join(parts).decode(errors="replace")[-2000:]
        except Exception:
            return

    async def _stderr(self) -> str:
        task = self._stderr_task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), 0.5)
            except TimeoutError:
                pass
        return self._stderr_text


async def _reap(proc: asyncio.subprocess.Process) -> None:
    try:
        await proc.wait()
    except Exception:
        return
