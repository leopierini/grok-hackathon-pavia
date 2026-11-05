"""The live museum mission: drone patrol, person detection, dog alert, Grok, voice.

Ground is the only process that talks to all three peers:

- drone: the drone teammate's flight server (state, frames, hover/land/takeoff,
  short yaw nudges). Its deadman and land-always stay in that server.
- dog:   the dog bridge process (stand, speak, frame, StopMove, soft lie-down).
- Grok:  presence readings on real JPEGs, and the alert text.

Sequence (``ground base/ground.md`` and ``plan-meeting.md``):

1. standby   peers connected, dog in its standby posture, drone monitored.
2. patrol    drone frames go to Grok, one request in flight, newest frame only.
3. detected  N consecutive drone readings see a person: one incident id,
             drone hover, dog stand (alert/ready), Grok alert, dog speaks.
4. tracking  drone yaws in small bounded nudges to keep the person centred
             (no translation, yaw budget); dog camera frames go to Grok.
5. stop      drone land, dog StopMove + soft lie-down. Halt does the same at once
             and never waits for Grok.

The dog never walks on its own here. Dog steps are operator buttons only.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from patrol.ground.live.grok import DEFAULT_SPOKEN

Json = dict[str, Any]

PHASES = ("idle", "standby", "patrol", "detected", "tracking", "stopping", "stopped", "halted")

DOG_STEPS: dict[str, dict[str, float]] = {
    "forward": {"vx": 0.3, "vy": 0.0, "vyaw": 0.0, "duration_s": 1.0},
    "back": {"vx": -0.25, "vy": 0.0, "vyaw": 0.0, "duration_s": 0.8},
    "left": {"vx": 0.0, "vy": 0.0, "vyaw": 0.6, "duration_s": 0.8},
    "right": {"vx": 0.0, "vy": 0.0, "vyaw": -0.6, "duration_s": 0.8},
}


class DogLinkLike(Protocol):
    async def connect(self) -> Json: ...
    async def request(self, op: str, timeout: float = 30, **fields: Any) -> Json: ...
    async def frame(self) -> Json: ...
    async def halt(self) -> Json: ...
    async def move_segment(self, segment: Any) -> Json: ...
    async def close(self) -> None: ...


class DroneLike(Protocol):
    async def state(self) -> Json: ...
    async def frame(self) -> bytes | None: ...
    async def cmd(self, action: str) -> Json: ...
    async def yaw_nudge(self, axis: float, seconds: float) -> None: ...


class GrokLike(Protocol):
    name: str

    def assess(self, jpeg: bytes, camera: str) -> Json: ...
    def alert(self, observations: list[Any]) -> dict[str, str]: ...


@dataclass
class Settings:
    drone_vision_period_s: float = 1.2
    dog_vision_period_s: float = 2.0
    confirm_frames: int = 2
    min_confidence: float = 0.5
    track: bool = True
    track_deadband: float = 0.12  # |box centre - 0.5| below this: no nudge
    track_axis: float = 0.35
    track_nudge_s: float = 0.4
    track_budget_deg: float = 90.0  # max yaw away from the heading at detection
    dog_stand_on_detect: bool = True
    speak_cooldown_s: float = 20.0
    drone_poll_s: float = 0.5
    drone_lost_after: int = 6  # failed polls (~3 s) before the drone link counts as lost
    allow_takeoff: bool = False


def _iso() -> str:
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class LiveMission:
    def __init__(
        self,
        *,
        drone: DroneLike,
        dog: DogLinkLike | None,
        grok: GrokLike,
        run_dir: Path,
        settings: Settings | None = None,
        dog_mode: str = "ethernet",
    ) -> None:
        self.drone = drone
        self.dog = dog
        self.grok = grok
        self.run_dir = run_dir
        self.settings = settings or Settings()
        self.dog_mode = dog_mode
        self.run_id = run_dir.name
        self.phase = "idle"
        self.incident: Json | None = None
        self.events: deque[Json] = deque(maxlen=400)
        self.seq = 0
        self.subscribers: set[asyncio.Queue[Json]] = set()
        self.drone_state: Json = {}
        self.drone_link = "unknown"
        self.drone_fail = 0
        self.dog_state: Json = {"link": "down" if dog is None else "connecting"}
        self.dog_frame: bytes | None = None
        self.dog_frame_at = 0.0
        self.grok_state: Json = {"name": grok.name, "calls": 0, "errors": 0, "in_flight": False}
        self.readings: dict[str, Json | None] = {"drone": None, "dog": None}
        self.hits = 0
        self.last_spoken = 0.0
        self.track_origin_yaw: float | None = None
        self.track_nudges = 0
        self._budget_noted = False
        self.frame_counter = 0
        self._tasks: list[asyncio.Task[Any]] = []
        self._loops: list[asyncio.Task[Any]] = []
        self._lock = asyncio.Lock()
        self._dog_io = asyncio.Lock()
        self.halt_latched = False
        (run_dir / "frames").mkdir(parents=True, exist_ok=True)
        self._journal = (run_dir / "events.jsonl").open("a", encoding="utf-8")

    # ---------------------------------------------------------------- events

    def emit(self, kind: str, component: str, detail: str, **data: Any) -> Json:
        self.seq += 1
        event = {
            "seq": self.seq,
            "ts": _iso(),
            "t_mono": round(time.monotonic(), 3),
            "run_id": self.run_id,
            "incident_id": self.incident["id"] if self.incident else None,
            "kind": kind,
            "component": component,
            "phase": self.phase,
            "detail": detail,
            "data": data,
        }
        self.events.append(event)
        try:
            self._journal.write(json.dumps(event, default=str) + "\n")
            self._journal.flush()
        except (OSError, ValueError):
            pass
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def snapshot(self) -> Json:
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "halt_latched": self.halt_latched,
            "incident": self.incident,
            "drone": {"link": self.drone_link, **self._drone_view()},
            "dog": {**self.dog_state, "mode": self.dog_mode, "frame_age_s": self._dog_frame_age()},
            "grok": self.grok_state,
            "readings": self.readings,
            "tracking": {
                "enabled": self.settings.track,
                "nudges": self.track_nudges,
                "origin_yaw": self.track_origin_yaw,
            },
            "settings": self.settings.__dict__,
            "events": list(self.events)[-60:],
        }

    def _drone_view(self) -> Json:
        s = self.drone_state
        keys = ("state", "battery", "battery_low", "h", "tof", "yaw", "video", "deadman", "last_reply")
        return {k: s.get(k) for k in keys}

    def _dog_frame_age(self) -> float | None:
        return None if self.dog_frame is None else round(time.monotonic() - self.dog_frame_at, 2)

    def _set_phase(self, phase: str, detail: str) -> None:
        if phase == self.phase:
            return
        old = self.phase
        self.phase = phase
        self.emit("phase", "ground", detail, old=old, new=phase)

    # ---------------------------------------------------------------- lifecycle

    async def connect(self) -> None:
        """Bring peers up. Nothing moves: the dog keeps its posture, the drone is only read."""
        self._set_phase("standby", "Connecting peers. Nothing moves in standby.")
        self._loops.append(asyncio.create_task(self._drone_poll_loop(), name="drone-poll"))
        if self.dog is not None:
            try:
                ready = await self.dog.connect()
                status = ready.get("status") or {}
                self.dog_state = {"link": "up", **status, "armed": ready.get("armed")}
                self.emit("dog_connected", "dog", "Dog bridge is connected. The dog stays in standby.", status=status)
                self._loops.append(asyncio.create_task(self._dog_frame_loop(), name="dog-frames"))
            except Exception as exc:  # noqa: BLE001 - shown to the operator
                self.dog_state = {"link": "down", "error": str(exc)[:300]}
                self.emit("dog_link_error", "dog", f"Dog bridge did not connect: {exc}")
        else:
            self.emit("dog_absent", "dog", "No dog link configured for this run.")

    async def start(self, takeoff: bool = False) -> Json:
        async with self._lock:
            if self.halt_latched:
                return {"ok": False, "detail": "Halt is latched. Restart the live service to start a new run."}
            if self.phase not in {"standby", "stopped"}:
                return {"ok": False, "detail": f"Cannot start patrol from phase {self.phase}."}
            self.incident = None
            self.hits = 0
            self.readings = {"drone": None, "dog": None}
            self._set_phase("patrol", "Patrol started. Drone frames go to Grok.")
            if takeoff:
                if not self.settings.allow_takeoff:
                    self.emit("takeoff_refused", "drone", "Takeoff from Ground is disabled; the pilot takes off.")
                elif self.drone_state.get("state") == "grounded":
                    result = await self._safe(self.drone.cmd("takeoff"), "drone", "takeoff")
                    self.emit("drone_command", "drone", "takeoff sent", action="takeoff", result=result)
            self._tasks.append(asyncio.create_task(self._drone_vision_loop(), name="drone-vision"))
            return {"ok": True, "detail": "Patrol started."}

    async def stop(self, reason: str = "Operator stopped the patrol.") -> Json:
        async with self._lock:
            if self.phase in {"idle", "stopped", "halted"}:
                return {"ok": False, "detail": f"Nothing to stop in phase {self.phase}."}
            self._set_phase("stopping", reason)
            self._cancel_tasks()
            land = await self._safe(self.drone.cmd("land"), "drone", "land")
            self.emit("drone_command", "drone", "land sent", action="land", result=land)
            await self._dog_rest("Patrol stopped: dog StopMove and soft lie-down.")
            await self._final_report()
            self._set_phase("stopped", "Patrol stopped. Drone landing, dog lying down.")
            return {"ok": True, "detail": "Stopped."}

    async def halt(self, reason: str = "Operator halt.") -> Json:
        """Immediate. Does not take the mission lock and never waits for Grok."""
        self.halt_latched = True
        self._cancel_tasks()
        self.emit("halt", "ground", reason)
        results = await asyncio.gather(
            self._safe(self.drone.cmd("land"), "drone", "land"),
            self._dog_halt_now(),
            return_exceptions=True,
        )
        self.emit("halt_sent", "ground", "Halt delivered: drone land, dog StopMove + soft lie-down.",
                  drone=results[0], dog=results[1])
        self._set_phase("halted", reason)
        return {"ok": True, "detail": "Halt sent."}

    async def close(self) -> None:
        self._cancel_tasks()
        for task in self._loops:
            task.cancel()
        if self.dog is not None:
            try:
                await self.dog.close()
            except Exception:  # noqa: BLE001
                pass
        self._journal.close()

    def _cancel_tasks(self) -> None:
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current:
                task.cancel()
        self._tasks = [t for t in self._tasks if t is current]

    async def _safe(self, awaitable: Awaitable[Json], component: str, what: str) -> Json:
        try:
            return await awaitable
        except Exception as exc:  # noqa: BLE001 - reported, never raised into the mission
            self.emit("peer_error", component, f"{what} failed: {exc}")
            return {"ok": False, "error": str(exc)[:300]}

    # ---------------------------------------------------------------- drone

    async def _drone_poll_loop(self) -> None:
        while True:
            try:
                self.drone_state = await self.drone.state()
                if self.drone_link != "up":
                    self.emit("drone_link", "drone", "Drone flight server is reachable.",
                              state=self._drone_view())
                self.drone_link = "up"
                self.drone_fail = 0
            except Exception as exc:  # noqa: BLE001
                self.drone_fail += 1
                if self.drone_fail >= self.settings.drone_lost_after and self.drone_link != "down":
                    self.drone_link = "down"
                    self.emit("drone_link_lost", "drone", f"Drone flight server lost: {exc}")
                    if self.phase in {"detected", "tracking"}:
                        await self._dog_stop("Drone link lost: dog StopMove.")
            await asyncio.sleep(self.settings.drone_poll_s)

    async def _drone_vision_loop(self) -> None:
        period = self.settings.drone_vision_period_s
        while self.phase in {"patrol", "detected", "tracking"}:
            started = time.monotonic()
            jpeg = await self._safe_frame()
            if jpeg is not None:
                reading = await self._assess(jpeg, "drone")
                if reading is not None:
                    await self._on_drone_reading(reading)
            await asyncio.sleep(max(0.05, period - (time.monotonic() - started)))

    async def _safe_frame(self) -> bytes | None:
        try:
            return await self.drone.frame()
        except Exception:  # noqa: BLE001
            return None

    async def _on_drone_reading(self, reading: Json) -> None:
        visible = reading.get("target_state") == "person_visible" and (
            reading.get("confidence") is None or float(reading["confidence"]) >= self.settings.min_confidence
        )
        if self.phase == "patrol":
            self.hits = self.hits + 1 if visible else 0
            if self.hits >= self.settings.confirm_frames:
                await self._on_detected(reading)
            return
        if self.phase in {"detected", "tracking"} and visible and self.settings.track:
            await self._track(reading)

    async def _on_detected(self, reading: Json) -> None:
        self.incident = {
            "id": f"incident-{uuid.uuid4().hex[:8]}",
            "detected_at": _iso(),
            "t_detect": time.monotonic(),
            "drone_reading": reading,
            "dog_reading": None,
            "alert": None,
            "spoken": [],
        }
        self._set_phase("detected", "Person detected by the drone camera.")
        self.emit("drone_target_acquired", "drone", "Grok confirmed a person in the drone frame.",
                  reading=reading)
        hover = await self._safe(self.drone.cmd("hover"), "drone", "hover")
        self.emit("drone_command", "drone", "hover sent: drone holds position", action="hover", result=hover)
        yaw = self.drone_state.get("yaw")
        self.track_origin_yaw = float(yaw) if isinstance(yaw, (int, float)) else None
        self._budget_noted = False
        self._tasks.append(asyncio.create_task(self._dog_alert(), name="dog-alert"))
        self._tasks.append(asyncio.create_task(self._dog_vision_loop(), name="dog-vision"))
        self._set_phase("tracking", "Drone tracks the person with bounded yaw. Dog camera checks with Grok.")

    async def _track(self, reading: Json) -> None:
        box = reading.get("box_xyxy_norm")
        if not isinstance(box, list) or len(box) != 4:
            return
        offset = (float(box[0]) + float(box[2])) / 2 - 0.5
        if abs(offset) < self.settings.track_deadband:
            return
        yaw = self.drone_state.get("yaw")
        if self.track_origin_yaw is not None and isinstance(yaw, (int, float)):
            turned = (float(yaw) - self.track_origin_yaw + 180) % 360 - 180
            if (offset > 0 and turned >= self.settings.track_budget_deg) or (
                offset < 0 and turned <= -self.settings.track_budget_deg
            ):
                if not self._budget_noted:
                    self._budget_noted = True
                    self.emit("track_budget", "drone", "Yaw budget reached; drone holds.", turned_deg=turned)
                return
        if self.drone_state.get("state") != "airborne":
            self.emit("track_skipped", "drone", "Person off-centre but the drone is not airborne; no nudge.",
                      offset=round(offset, 3))
            return
        axis = self.settings.track_axis if offset > 0 else -self.settings.track_axis
        try:
            await self.drone.yaw_nudge(axis, self.settings.track_nudge_s)
            self.track_nudges += 1
            self.emit("track_nudge", "drone", f"Yaw nudge {'right' if axis > 0 else 'left'} to centre the person.",
                      offset=round(offset, 3), axis=axis)
        except Exception as exc:  # noqa: BLE001
            self.emit("peer_error", "drone", f"yaw nudge failed: {exc}")

    # ---------------------------------------------------------------- dog

    async def _dog_call(self, op: str, timeout: float = 30, **fields: Any) -> Json:
        if self.dog is None or self.dog_state.get("link") != "up":
            return {"ok": False, "detail": "dog link is down"}
        async with self._dog_io:
            return await self.dog.request(op, timeout=timeout, **fields)

    async def _dog_alert(self) -> None:
        """Detection response: stand (alert/ready), Grok alert text, spoken warning."""
        if self.settings.dog_stand_on_detect:
            stand = await self._safe(self._dog_call("stand", timeout=20), "dog", "stand")
            ok = stand.get("ok") is True
            if ok and isinstance(stand.get("status"), dict):
                self.dog_state.update(stand["status"])
            self.emit("dog_alert", "dog",
                      "Dog stood up: alert/ready." if ok else f"Dog stand refused: {stand.get('detail')}",
                      result=stand)
        alert = await self._compose_alert()
        await self._speak(alert.get("spoken") or DEFAULT_SPOKEN, "warning")

    async def _compose_alert(self) -> dict[str, str]:
        obs = [r for r in (self.readings.get("drone"), self.readings.get("dog")) if r]
        try:
            self.grok_state["in_flight"] = True
            alert = await asyncio.to_thread(self.grok.alert, obs)
        except Exception as exc:  # noqa: BLE001
            self.grok_state["errors"] += 1
            self.emit("grok_error", "grok", f"Alert composition failed, using the fixed warning: {exc}")
            alert = {"alert": "Person detected in the closed gallery.", "spoken": DEFAULT_SPOKEN}
        finally:
            self.grok_state["in_flight"] = False
        if self.incident is not None:
            self.incident["alert"] = alert.get("alert")
        self.emit("alert", "grok", alert.get("alert", ""), spoken=alert.get("spoken"))
        return alert

    async def _speak(self, text: str, why: str, force: bool = False) -> None:
        if not force and time.monotonic() - self.last_spoken < self.settings.speak_cooldown_s:
            return
        self.last_spoken = time.monotonic()
        said = await self._safe(self._dog_call("say", timeout=20, text=text), "dog", "say")
        if self.incident is not None and said.get("ok") is True:
            self.incident["spoken"].append(text)
        self.emit("dog_voice", "dog", f"Dog speaker: \"{text}\"" if said.get("ok") else
                  f"Dog speaker failed: {said.get('detail')}", why=why, result=said)

    async def _dog_frame_loop(self) -> None:
        while True:
            try:
                if self.dog is not None and self.dog_state.get("link") == "up":
                    async with self._dog_io:
                        got = await self.dog.frame()
                    if got.get("ok") is True and isinstance(got.get("jpeg"), bytes):
                        self.dog_frame = got["jpeg"]
                        self.dog_frame_at = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                self.dog_state["frame_error"] = str(exc)[:200]
            await asyncio.sleep(0.4)

    async def _dog_vision_loop(self) -> None:
        seen_once = False
        while self.phase in {"detected", "tracking"}:
            started = time.monotonic()
            jpeg = self.dog_frame if self._dog_frame_age() is not None and self._dog_frame_age() < 2.0 else None
            if jpeg is not None:
                reading = await self._assess(jpeg, "dog")
                if reading is not None and reading.get("target_state") == "person_visible":
                    if self.incident is not None:
                        self.incident["dog_reading"] = reading
                    if not seen_once:
                        seen_once = True
                        self.emit("dog_target_acquired", "dog", "Grok sees the person in the dog camera.",
                                  reading=reading)
                        await self._speak(
                            "I can see you. This gallery is closed. Please leave the area.", "dog_sees_person",
                            force=True,
                        )
            await asyncio.sleep(max(0.05, self.settings.dog_vision_period_s - (time.monotonic() - started)))

    async def dog_step(self, direction: str) -> Json:
        """Operator-supervised step. Never called by the mission itself."""
        if self.halt_latched:
            return {"ok": False, "detail": "Halt is latched."}
        segment = DOG_STEPS.get(direction)
        if segment is None:
            return {"ok": False, "detail": f"unknown direction {direction!r}"}
        if self.dog is None or self.dog_state.get("link") != "up":
            return {"ok": False, "detail": "dog link is down"}
        async with self._dog_io:
            if self.halt_latched:  # halt may have landed while this step waited
                return {"ok": False, "detail": "Halt is latched."}
            result = await self._safe(self.dog.move_segment(dict(segment)), "dog", f"step {direction}")
        self.emit("dog_step", "dog", f"Operator step {direction}: {result.get('detail')}", segment=segment,
                  result={k: v for k, v in result.items() if k != "status"})
        return result

    async def dog_stand(self) -> Json:
        result = await self._safe(self._dog_call("stand", timeout=20), "dog", "stand")
        self.emit("dog_stand", "dog", "Operator stand." if result.get("ok") else f"Stand refused: {result.get('detail')}",
                  result=result)
        return result

    async def dog_say(self, text: str) -> Json:
        self.last_spoken = 0.0
        await self._speak(text, "operator")
        return {"ok": True}

    async def _dog_stop(self, why: str) -> None:
        result = await self._safe(self._dog_call("stop", timeout=10), "dog", "stop")
        self.emit("dog_stop", "dog", why, result=result)

    async def _dog_rest(self, why: str) -> None:
        if self.dog is None or self.dog_state.get("link") != "up":
            return
        async with self._dog_io:
            result = await self._safe(self.dog.halt(), "dog", "halt")
        self.emit("dog_rest", "dog", why, result=result)

    async def _dog_halt_now(self) -> Json:
        if self.dog is None:
            return {"ok": False, "detail": "no dog link"}
        # No mission lock: the link writes halt at once and the bridge cancels any running op.
        return await self.dog.halt()

    # ---------------------------------------------------------------- grok

    async def _assess(self, jpeg: bytes, camera: str) -> Json | None:
        self.frame_counter += 1
        path = self.run_dir / "frames" / f"{self.frame_counter:05d}-{camera}.jpg"
        try:
            path.write_bytes(jpeg)
        except OSError:
            pass
        self.grok_state["in_flight"] = True
        self.grok_state["calls"] += 1
        try:
            reading = await asyncio.to_thread(self.grok.assess, jpeg, camera)
        except Exception as exc:  # noqa: BLE001
            self.grok_state["errors"] += 1
            self.grok_state["last_error"] = str(exc)[:200]
            self.emit("grok_error", "grok", f"{camera} frame: {exc}", frame=path.name)
            return None
        finally:
            self.grok_state["in_flight"] = False
        reading = {**reading, "frame": path.name, "at": _iso()}
        self.readings[camera] = reading
        self.grok_state["last_latency_ms"] = reading.get("latency_ms")
        self.emit("vision", "grok", f"{camera}: {reading.get('target_state')} — {reading.get('reason')}",
                  camera=camera, reading=reading)
        return reading

    async def _final_report(self) -> None:
        inc = self.incident
        if inc is None:
            self.emit("report", "ground", "Patrol ended with no person detected.")
            return
        summary = {
            "incident_id": inc["id"],
            "detected_at": inc["detected_at"],
            "drone_reason": (inc.get("drone_reading") or {}).get("reason"),
            "dog_confirmed": inc.get("dog_reading") is not None,
            "alert": inc.get("alert"),
            "spoken": inc.get("spoken"),
            "track_nudges": self.track_nudges,
            "grok_calls": self.grok_state["calls"],
            "grok_errors": self.grok_state["errors"],
        }
        try:
            (self.run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        except OSError:
            pass
        self.emit("report", "ground", "Incident summary written.", summary=summary)


async def run_until(mission: LiveMission, predicate: Callable[[], bool], timeout_s: float) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()
