"""Ground's one process on the dog: JSON lines on stdin, JSON lines on stdout.

    python -m patrol.dog.ground_bridge --output DIR [--ip 192.168.123.161] [--fake] [--arm]

Ground (``ground base/patrol/ground/dog_link.py``) spawns this with the dog
checkout's own interpreter, so Ground never imports the Unitree library.

The first JSON line is the ready line. Every request gets exactly one reply.
Lines that do not start with ``{`` are vendor noise; Ground skips them.

Requests (``op``):

- ``status``  posture, avoidance, speaker and LiDAR state. Never moves.
- ``stand``   StandUp + BalanceStand (``prepare``). Needs ``--arm``.
- ``move``    one bounded body-frame segment ``{vx, vy, vyaw, duration_s}``,
              re-sent at 10 Hz, then StopMove. Needs ``--arm`` and the dog's own
              checks (standing, avoidance confirmed, inside the fence).
- ``stop``    StopMove, the dog stays standing.
- ``halt``    STOP: StopMove, then a soft StandDown (``rest``). Never Damp.
- ``say``     speak ``text`` on the dog speaker (macOS TTS stand-in).
- ``frame``   newest camera frame as base64 JPEG.
- ``lidar``   the LiDAR panel view.
- ``close``   disconnect and exit.

Halt is always accepted, armed or not. Motion is refused unless ``--arm``.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from threading import Event
from typing import Any

from patrol.contract import AdapterError, RunContext

MAX_SEGMENT_S = 3.0
MOVE_PERIOD_S = 0.1
DEFAULT_VOLUME = 7
VOICE = "Samantha"  # English; "Alice" is the Italian voice


def emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()


def make_dog(args: argparse.Namespace) -> Any:
    from patrol.dog.real import RealDog

    out = Path(args.output)
    if args.fake:
        from patrol.dog.sim_conn import SimConn

        sim = SimConn()
        cfg: dict[str, Any] = {
            "connection_mode": "LocalSTA",
            "interface": "simulated",
            "command_timeout_s": 1.0,
        }
        return RealDog(config=cfg, output_dir=out, _conn_factory=lambda ip: sim)
    cfg = {"connection_mode": "LocalSTA", "interface": args.ip, "command_timeout_s": 3.0}
    if args.config:
        cfg = {**json.loads(Path(args.config).read_text()), "interface": args.ip}
    return RealDog(config=cfg, output_dir=out)


def status_of(dog: Any, st: Any) -> dict[str, Any]:
    body = dict(getattr(st, "__dict__", {}) or {})
    try:
        body["speaker"] = dog.speaker_status()
    except Exception:  # noqa: BLE001 - status must never raise
        pass
    try:
        body["motion_lock"] = dog.motion_lock()
    except Exception:  # noqa: BLE001
        pass
    return body


class Bridge:
    def __init__(self, dog: Any, armed: bool) -> None:
        self.dog = dog
        self.armed = armed
        self.halted = False
        self.volume_set = False

    async def handle(self, msg: dict[str, Any]) -> dict[str, Any]:
        op = msg.get("op")
        try:
            if op == "status":
                return {"op": op, "ok": True, "status": await self._status()}
            if op == "halt":
                return await self._halt()
            if op == "stop":
                await self.dog.stop_move()
                return {"op": op, "ok": True, "sent": True, "status": await self._status()}
            if op == "say":
                return await self._say(msg)
            if op == "frame":
                return await self._frame()
            if op == "lidar":
                return {"op": op, "ok": True, "view": self.dog.lidar_view()}
            if op == "stand":
                return await self._stand()
            if op == "move":
                return await self._move(msg.get("segment"))
            return {"op": op, "ok": False, "detail": f"unknown op {op!r}"}
        except AdapterError as exc:
            return {"op": op, "ok": False, "sent": False, "detail": f"{exc.code}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - one reply per request, always
            return {"op": op, "ok": False, "sent": False, "detail": f"{type(exc).__name__}: {exc}"}

    async def _status(self) -> dict[str, Any]:
        return status_of(self.dog, await self.dog.get_status())

    async def _halt(self) -> dict[str, Any]:
        self.halted = True
        report = await self.dog.rest()  # StopMove x3, then StandDown. Never Damp.
        return {
            "op": "halt",
            "ok": True,
            "sent": True,
            "detail": "StopMove sent, soft lie-down requested",
            "rest": report,
        }

    def _refuse_motion(self) -> str | None:
        if not self.armed:
            return "bridge is not armed; motion refused"
        if self.halted:
            return "halt is latched; motion refused until the bridge restarts"
        return None

    async def _stand(self) -> dict[str, Any]:
        refused = self._refuse_motion()
        if refused:
            return {"op": "stand", "ok": False, "sent": False, "detail": refused}
        try:
            self.dog.set_home()  # fence centred where Ground first stood the dog
        except AdapterError:
            pass
        ctx = RunContext(mission_id="ground", deadline_monotonic=time.monotonic() + 15, cancel=Event())
        st = await self.dog.prepare(ctx)
        return {"op": "stand", "ok": True, "sent": True, "status": status_of(self.dog, st)}

    async def _move(self, segment: Any) -> dict[str, Any]:
        refused = self._refuse_motion()
        if refused:
            return {"op": "move", "ok": False, "sent": False, "detail": refused}
        if not isinstance(segment, dict):
            return {"op": "move", "ok": False, "sent": False, "detail": "segment must be an object"}
        try:
            vx = float(segment.get("vx", 0.0))
            vy = float(segment.get("vy", 0.0))
            vyaw = float(segment.get("vyaw", 0.0))
            duration = float(segment.get("duration_s", 0.0))
        except (TypeError, ValueError):
            return {"op": "move", "ok": False, "sent": False, "detail": "segment values must be numbers"}
        if not 0 < duration <= MAX_SEGMENT_S:
            return {"op": "move", "ok": False, "sent": False, "detail": f"duration must be in (0, {MAX_SEGMENT_S}] s"}
        sent = 0
        started = time.monotonic()
        try:
            while time.monotonic() - started < duration and not self.halted:
                await self.dog.drive(vx, vy, vyaw)
                sent += 1
                await asyncio.sleep(MOVE_PERIOD_S)
        finally:
            await self.dog.stop_move()
        return {
            "op": "move",
            "ok": True,
            "sent": sent > 0,
            "moves": sent,
            "detail": f"{sent} Move packets over {time.monotonic() - started:.2f} s, then StopMove",
            "status": await self._status(),
        }

    async def _say(self, msg: dict[str, Any]) -> dict[str, Any]:
        text = msg.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 400:
            return {"op": "say", "ok": False, "sent": False, "detail": "text must be 1..400 characters"}
        if not self.volume_set:
            try:
                level = msg.get("volume", DEFAULT_VOLUME)
                await self.dog.set_volume(level)
            except AdapterError:
                pass  # speak anyway; the status says what the dog reported
            self.volume_set = True
        seconds = await self.dog.say(text.strip(), msg.get("voice") or VOICE)
        return {"op": "say", "ok": True, "sent": True, "seconds": round(float(seconds), 2), "text": text.strip()}

    async def _frame(self) -> dict[str, Any]:
        img, t = self.dog.latest_frame()
        if img is None or t is None:
            return {"op": "frame", "ok": False, "detail": "no camera frame yet"}
        import cv2

        ok, buf = await asyncio.to_thread(cv2.imencode, ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return {"op": "frame", "ok": False, "detail": "JPEG encode failed"}
        return {
            "op": "frame",
            "ok": True,
            "age_s": round(time.monotonic() - t, 3),
            "jpeg_b64": base64.b64encode(buf.tobytes()).decode(),
        }


async def _stdin_lines(queue: asyncio.Queue[str | None]) -> None:
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            await queue.put(None)
            return
        await queue.put(line)


async def run(args: argparse.Namespace) -> int:
    try:
        dog = make_dog(args)
        st = await dog.connect()
    except AdapterError as exc:
        emit({"op": "ready", "ok": False, "detail": f"{exc.code}: {exc}"})
        return 2
    except Exception as exc:  # noqa: BLE001
        emit({"op": "ready", "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return 2
    bridge = Bridge(dog, armed=args.arm)
    emit(
        {
            "op": "ready",
            "ok": True,
            "armed": args.arm,
            "fake": args.fake,
            "status": status_of(dog, st),
        }
    )
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    reader = asyncio.create_task(_stdin_lines(queue))
    try:
        while True:
            line = await queue.get()
            if line is None:
                break
            text = line.strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                emit({"ok": False, "detail": "request must be JSON"})
                continue
            if not isinstance(msg, dict):
                emit({"ok": False, "detail": "request must be an object"})
                continue
            if msg.get("op") == "close":
                break
            emit(await bridge.handle(msg))
    finally:
        reader.cancel()
        try:
            await dog.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m patrol.dog.ground_bridge")
    parser.add_argument("--output", required=True)
    parser.add_argument("--ip", default="192.168.123.161")
    parser.add_argument("--config", default=None)
    parser.add_argument("--fake", action="store_true", help="simulated body, no network")
    parser.add_argument("--arm", action="store_true", help="allow stand and move (halt is always allowed)")
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
