"""Browser joystick for the Go2, served on 127.0.0.1 only.

    .venv/bin/python -m patrol.dog.joystick --fake                 # simulated dog, no robot
    .venv/bin/python -m patrol.dog.joystick --config config/dog.local.json   # real dog

Open the printed URL yourself (nothing opens automatically). One process owns the
single RealDog (the Go2 allows one WebRTC client). Connecting never moves the dog.

STOP = lie down softly. The STOP button, Space, Q, the REST button, and in this
terminal Q / Enter / Ctrl+C all call RealDog.rest(): StopMove, then StandDown
(api 1005), never Damp (1001). Ctrl+C rests and then exits.
Releasing the sticks, the 300 ms dead-man, closing the page or switching tab only
send StopMove (the dog stays standing).

The staff controller is always the primary stop. This page is a backup.

Safety thresholds (RealDog's envelope: fence around home, sustained speed and tilt,
route overshoot) are ON at every start and for every new adapter. A trip lies the dog
down softly (rest) and is logged as `safety_trip`. The page checkbox can turn them off
for this server run only (controller, stationary dog; logged, loud banner). Home is
kept across Re-arm; "Set home here" moves it to the current spot (stationary only).
"Take control" on a view-only tab moves control to it (StopMove first).
Speeds are capped here (0.3 m/s fwd/back, 0.2 m/s sideways, 0.6 rad/s yaw), below
RealDog's own caps. Every motion command goes through RealDog.

Logs JSON lines to <out>/joystick.jsonl (stop latency, dead-man, connection,
photos, brightness). --fake writes to evidence/dog/fake/ by default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any, Callable

from aiohttp import WSMsgType, web

from patrol.contract import AdapterError, DogStatus, RunContext

JOY_MAX_VX = 0.3        # m/s forward/back (RealDog cap is 0.5)
JOY_MAX_VY = 0.2        # m/s sideways (RealDog cap is 0.3)
JOY_MAX_VYAW = 0.6      # rad/s (RealDog cap is 0.8)
DEFAULT_SPEED = 0.5     # fraction of the caps
DEADMAN_S = 0.3         # no drive message for this long while moving => StopMove
TICK_S = 0.025          # control loop period
MOVE_MIN_INTERVAL_S = 0.05   # Move rate cap: <= 20 Hz
STATUS_PERIOD_S = 0.25  # 4 Hz status push
VIDEO_FPS = 10
VIDEO_WIDTH = 640
JPEG_QUALITY = 60
STOP_MEASURE_S = 3.0
ZONES = ("entrance", "room_2", "display")
HTML_PATH = Path(__file__).with_name("joystick.html")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v: Any, lo: float, hi: float, default: float = 0.0) -> float:
    """Finite float clamped to [lo, hi]; anything else (NaN, inf, junk) => default."""
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(f):
        return default
    return max(lo, min(hi, f))


def _encode_jpeg(img) -> bytes | None:
    import cv2

    h, w = img.shape[:2]
    if w > VIDEO_WIDTH:
        img = cv2.resize(img, (VIDEO_WIDTH, int(h * VIDEO_WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    return buf.tobytes() if ok else None


class JsonlLog:
    def __init__(self, path: Path, *, fake: bool) -> None:
        self.path = Path(path)
        self.fake = fake

    def write(self, event: str, **fields) -> dict:
        rec = {"utc": _utc(), "event": event, **fields}
        if self.fake:
            rec["fake"] = True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
        except OSError as e:
            print(f"[joystick] log write failed: {e}", flush=True)
        return rec


class Controller:
    """Owns the single RealDog. All motion goes through it."""

    def __init__(self, dog_factory: Callable[[], Any], *, log_path: Path, fake: bool = False,
                 deadman_s: float = DEADMAN_S, verbose: bool = True) -> None:
        self._factory = dog_factory
        self.dog: Any = None
        self.fake = fake
        self.log = JsonlLog(log_path, fake=fake)
        self.deadman_s = deadman_s
        self.verbose = verbose
        self.caps = {"vx": JOY_MAX_VX, "vy": JOY_MAX_VY, "vyaw": JOY_MAX_VYAW}

        self.target = (0.0, 0.0, 0.0)       # m/s, m/s, rad/s (already capped)
        self.target_t = 0.0                 # monotonic time of the last drive message
        self.moving = False                 # a Move was sent since the last stop
        self.refused: str | None = None     # drive refused; cleared when the sticks go to zero
        self.last_move_t = 0.0
        self.last_cmd_t: float | None = None
        self.busy: str | None = None        # "connecting" | "stand"
        self.brightness: int | None = None
        self.last_stop: dict | None = None
        self.last_photo: str | None = None
        self.deadman_count = 0
        self.connect_error: str | None = None
        self.home: list | None = None       # kept across re-arms (odometry frame survives reconnects)
        self.envelope_enabled = True        # safety thresholds; ON at every server start
        self._seen_trip: Any = None
        self._outside_noted = False

        self._old_dog: Any = None           # adapter being closed during re-arm (still usable for STOP)
        self.clients: set[web.WebSocketResponse] = set()
        self.controller_ws: web.WebSocketResponse | None = None
        self.closing = False
        self._rest_pending = False
        self._rest_task: asyncio.Task | None = None
        self._drive_task: asyncio.Task | None = None
        self._busy_task: asyncio.Task | None = None
        self._measure_task: asyncio.Task | None = None
        self._loops: list[asyncio.Task] = []
        self._tasks: set[asyncio.Task] = set()
        self._jpeg_cache: tuple[float | None, bytes | None] = (None, None)
        self._jpeg_lock = asyncio.Lock()

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._loops = [asyncio.create_task(self._control_loop()),
                       asyncio.create_task(self._status_loop())]
        self.busy = "connecting"
        self._busy_task = self._spawn(self._connect_new("startup"))

    async def wait_connected(self, timeout: float = 10.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.busy is None and self.dog is not None:
                return (await self.dog.get_status()).connected
            await asyncio.sleep(0.02)
        return False

    async def shutdown(self) -> None:
        self.closing = True
        for t in self._loops:
            t.cancel()
        if self._rest_task is not None and not self._rest_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._rest_task), 5.0)
            except Exception:
                pass
        if self.dog is not None:
            try:
                await self.dog.close()
            except Exception:
                pass
            self.log.write("connection", action="closed")
        for t in list(self._tasks):
            t.cancel()

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    def _say(self, msg: str, level: str = "info") -> None:
        if self.verbose:
            print(f"[joystick] {msg}", flush=True)
        for ws in list(self.clients):
            self._spawn(self._send(ws, {"t": "event", "level": level, "msg": msg}))

    @staticmethod
    async def _send(ws, data: dict) -> None:
        try:
            await ws.send_json(data)
        except Exception:
            pass

    async def _connect_new(self, reason: str) -> None:
        self.busy = "connecting"
        try:
            dog = self._factory()
            self._apply_safety_settings(dog)
            t0 = time.monotonic()
            try:
                st = await dog.connect()
            except AdapterError as e:
                self.connect_error = str(e)
                self.dog = dog
                self.log.write("connection", action="connect_failed", reason=reason, error=str(e))
                self._say(f"connect failed: {e} (press Re-arm to retry)", "error")
                return
            self.connect_error = None
            self.dog = dog
            try:
                self.brightness = await dog.get_brightness()
            except AdapterError:
                self.brightness = None
            safety = self._safety_of(dog)
            if safety and safety.get("home") is not None:
                self.home = safety["home"]
            self.log.write("connection", action="connected", reason=reason,
                           connect_s=round(time.monotonic() - t0, 2), status=st.__dict__,
                           brightness=self.brightness,
                           home=self.home, home_source=(safety or {}).get("home_source"),
                           safety_enabled=(safety or {}).get("enabled"))
            self._say(f"connected ({reason}) in {time.monotonic() - t0:.1f} s: {st}")
        finally:
            self.busy = None
            if self._rest_pending:          # Q/STOP arrived while (re)connecting
                self._rest_task = self._spawn(self._do_rest("pending"))

    def _apply_safety_settings(self, dog) -> None:
        """New adapter: keep the previous home and this run's envelope setting (before connect)."""
        if self.home is not None and hasattr(dog, "adopt_home"):
            try:
                dog.adopt_home(self.home)
            except AdapterError as e:
                self._say(f"could not keep home {self.home}: {e}", "error")
        # Thresholds are NOT carried over: every new adapter starts with them ON.
        if not self.envelope_enabled:
            self._say("safety thresholds back ON for the new connection (turn off again if needed)", "warn")
            self.log.write("safety_envelope_on", reason="new adapter (re-arm/startup)")
        self.envelope_enabled = True

    @staticmethod
    def _safety_of(dog) -> dict | None:
        fn = getattr(dog, "safety_status", None)
        if fn is None:
            return None
        try:
            return fn()
        except Exception:
            return None

    # ------------------------------------------------------------ commands

    def set_target(self, x: Any, y: Any, yaw: Any, speed: Any) -> tuple[float, float, float]:
        """Stick vector in [-1, 1] times speed fraction [0, 1] times the joystick caps."""
        sp = _num(speed, 0.0, 1.0, DEFAULT_SPEED)
        vx = _num(_num(x, -1, 1) * sp * JOY_MAX_VX, -JOY_MAX_VX, JOY_MAX_VX)
        vy = _num(_num(y, -1, 1) * sp * JOY_MAX_VY, -JOY_MAX_VY, JOY_MAX_VY)
        vyaw = _num(_num(yaw, -1, 1) * sp * JOY_MAX_VYAW, -JOY_MAX_VYAW, JOY_MAX_VYAW)
        now = time.monotonic()
        self.target = (vx, vy, vyaw)
        self.target_t = now
        self.last_cmd_t = now
        if not any(self.target):
            self.refused = None
        return self.target

    def request_rest(self, source: str) -> None:
        """STOP: lie down softly (RealDog.rest). Top priority, overrides everything."""
        self.target = (0.0, 0.0, 0.0)
        self.refused = None
        self.last_cmd_t = time.monotonic()
        if self._drive_task is not None and not self._drive_task.done():
            self._drive_task.cancel()
        if self.busy == "stand" and self._busy_task is not None:
            self._busy_task.cancel()
        self.log.write("stop_pressed", source=source)
        if self._rest_task is not None and not self._rest_task.done():
            return                          # a rest is already running
        self._rest_pending = True           # cleared by _do_rest once it reaches a connected adapter
        self._say(f"STOP ({source}): lying down softly", "warn")
        self._rest_task = self._spawn(self._do_rest(source))

    async def _do_rest(self, source: str) -> None:
        # Deliver on ANY adapter that is still connected: the current one, or the old one
        # while a re-arm is closing it. Never wait for a reconnect if we can stop now.
        dog = None
        for cand in (self.dog, self._old_dog):
            if cand is not None and getattr(cand, "_connected", False):
                dog = cand
                break
        if dog is None:
            if self.busy == "connecting":
                self._say("STOP queued: reconnecting. If the dog moves, USE THE STAFF CONTROLLER", "error")
                return                      # _connect_new applies the rest once connected
            self._rest_pending = False
            self.log.write("rest", source=source, report={"standdown_sent": False, "error": "not connected"})
            self._say("STOP NOT DELIVERED: dog not connected. USE THE STAFF CONTROLLER", "error")
            return
        self._rest_pending = False
        snap = self._snapshot(dog)
        self.moving = False
        self._start_measure("rest", dog, snap, {"source": source})
        report = await dog.rest()
        self.log.write("rest", source=source, report=report)
        if report.get("standdown_sent") is True:
            self._say(f"rest sent: {report}")
        else:
            self._say(f"STOP MAY NOT HAVE ARRIVED ({report}). USE THE STAFF CONTROLLER", "error")

    def request_stand(self) -> None:
        self._spawn(self._do_stand())

    async def _do_stand(self) -> None:
        dog = self.dog
        if dog is None or self.busy is not None:
            return self._say("stand refused: busy or not connected", "warn")
        st = await dog.get_status()
        lock = dog.motion_lock()
        if lock:
            return self._say(f"stand refused: motion locked ({lock}); press Re-arm first", "warn")
        if self.moving or any(self.target) or st.stationary is not True:
            return self._say(f"stand refused: not stationary ({st})", "warn")
        block = dog.safety_block() if hasattr(dog, "safety_block") else None
        if block:
            return self._say(f"stand refused: {block}", "warn")
        self.busy = "stand"
        self._busy_task = asyncio.current_task()
        try:
            ctx = RunContext(mission_id="joystick", deadline_monotonic=time.monotonic() + 15, cancel=Event())
            st = await dog.prepare(ctx)
            self.log.write("stand", status=st.__dict__)
            self._say(f"stand done: {st}")
        except AdapterError as e:
            self._say(f"stand failed: {e}", "error")
        except asyncio.CancelledError:
            self._say("stand cancelled", "warn")
        finally:
            self.busy = None

    def request_rearm(self) -> None:
        self._spawn(self._do_rearm())

    async def _do_rearm(self) -> None:
        if self.busy is not None or (self._rest_task is not None and not self._rest_task.done()):
            return self._say("re-arm refused: busy", "warn")
        if self.moving or any(self.target):
            return self._say("re-arm refused: release the sticks first", "warn")
        old = self.dog
        trip_rest = getattr(old, "_safety_rest_task", None) if old is not None else None
        if trip_rest is not None and not trip_rest.done():
            return self._say("re-arm refused: the automatic lie-down after a safety trip is still running", "warn")
        if old is not None:
            self._check_safety_events(old)      # log a trip that happened just now
            st = await old.get_status()
            if st.connected and st.stationary is not True:
                return self._say(f"re-arm refused: dog not stationary ({st})", "warn")
            safety = self._safety_of(old)
            if safety and safety.get("home") is not None:
                self.home = safety["home"]      # the new adapter keeps this fence centre
        self.busy = "connecting"
        self._say("re-arm: closing the adapter and connecting a new one (no motion on connect)")
        self.log.write("connection", action="rearm")
        self.dog = None
        self._old_dog = old
        try:
            if old is not None:
                try:
                    await old.close()
                except Exception:
                    pass
        finally:
            self._old_dog = None
        await self._connect_new("rearm")

    def request_set_home(self) -> None:
        dog = self.dog
        if dog is None or not hasattr(dog, "set_home"):
            return self._say("set home refused: not connected", "warn")
        if self.busy or self.moving or any(self.target) or (
                self._rest_task is not None and not self._rest_task.done()):
            return self._say("set home refused: release the sticks / wait (must be stationary)", "warn")
        try:
            rec = dog.set_home()
        except AdapterError as e:
            return self._say(f"set home refused: {e}", "warn")
        self.home = rec["new"]
        self.log.write("set_home", old=rec["old"], new=rec["new"], source="browser")
        self._say(f"home set here: {rec['new']} (was {rec['old']}); fence is now centred on this spot", "warn")

    def request_safety(self, enabled: Any) -> None:
        if not isinstance(enabled, bool):
            return
        dog = self.dog
        if dog is None or self.busy == "connecting" or not getattr(dog, "_connected", False):
            return self._say("safety setting unchanged: not connected yet (try again once connected)", "warn")
        if enabled == bool(getattr(dog, "safety_envelope_enabled", True)):
            return
        if not enabled and (self.busy or self.moving or any(self.target)):
            return self._say("safety thresholds stay ON: only while stationary (release the sticks)", "warn")
        res: dict = {}
        if dog is not None and hasattr(dog, "set_safety_envelope"):
            try:
                res = dog.set_safety_envelope(enabled)
            except AdapterError as e:
                return self._say(f"safety thresholds stay ON: {e}", "warn")
        self.envelope_enabled = enabled
        safety = self._safety_of(dog) or {}
        if enabled:
            self.log.write("safety_envelope_on", outside_fence=res.get("outside_fence"),
                           distance_from_home_m=safety.get("distance_from_home_m"))
            msg = "safety thresholds ON again"
            if res.get("outside_fence"):
                msg += ("; the dog is OUTSIDE the fence: driving is refused until you press "
                        "'Set home here' (no automatic lie-down for this)")
            self._say(msg, "warn")
        else:
            self.log.write("safety_envelope_off", distance_from_home_m=safety.get("distance_from_home_m"))
            if self.verbose:
                print("[joystick] *** SAFETY THRESHOLDS OFF (fence / speed / tilt / overshoot): "
                      "no automatic stops. STOP / Q and the staff controller still work. ***", flush=True)
            self._say("SAFETY THRESHOLDS OFF: no automatic fence/speed/tilt/overshoot stops", "trip")

    def take_control(self, ws) -> None:
        """A view-only tab takes control: stop the dog first (StopMove, stays standing),
        demote the old controller, then promote the new one."""
        old = self.controller_ws
        if old is ws:
            return
        self.target = (0.0, 0.0, 0.0)
        self.refused = None
        if self._drive_task is not None and not self._drive_task.done():
            self._drive_task.cancel()
        self._stop("control_taken")         # StopMove even if we think we're idle
        self.controller_ws = None
        if old is not None:
            self._spawn(self._send(old, {"t": "role", "role": "view"}))
            self._spawn(self._send(old, {"t": "event", "level": "warn",
                                         "msg": "control taken by another tab (dog sent StopMove)"}))
        self.log.write("control_taken", had_controller=old is not None)
        self.controller_ws = ws
        self._spawn(self._send(ws, {"t": "role", "role": "control"}))
        self._say("control taken by another tab: dog sent StopMove, new tab has control", "warn")

    def request_light(self, level: Any) -> None:
        self._spawn(self._do_light(level))

    async def _do_light(self, level: Any) -> None:
        dog = self.dog
        if dog is None:
            return
        try:
            sent = await dog.set_brightness(_num(level, 0, 10, 0))
        except AdapterError as e:
            return self._say(f"light failed: {e}", "error")
        old, self.brightness = self.brightness, sent
        self.log.write("brightness", old=old, new=sent)
        self._say(f"head light {sent}/10")

    def request_photo(self, zone: Any) -> None:
        self._spawn(self._do_photo(zone if zone in ZONES else "room_2"))

    async def _do_photo(self, zone: str) -> None:
        dog = self.dog
        if dog is None:
            return
        try:
            ctx = RunContext(mission_id="joystick", deadline_monotonic=time.monotonic() + 5, cancel=Event())
            frame = await dog.capture_frame(zone, ctx)
        except AdapterError as e:
            return self._say(f"photo failed: {e}", "error")
        self.last_photo = frame.path
        self.log.write("photo", path=frame.path, zone=zone, captured_at=frame.captured_at)
        self._say(f"photo saved: {frame.path}")

    def on_controller_lost(self, reason: str) -> None:
        self.target = (0.0, 0.0, 0.0)
        self.refused = None
        if self.moving:
            self._stop(reason)
        self.log.write("client", action="controller_lost", reason=reason)

    # ------------------------------------------------------------ control loop

    def _drive_block(self, st: DogStatus | None = None) -> str | None:
        """Why the sticks do nothing right now (None = drive allowed by this layer)."""
        dog = self.dog
        if dog is None:
            return "not connected"
        lock = dog.motion_lock()
        if lock:
            return f"motion locked ({lock}): press Re-arm"
        if self.busy:
            return f"busy: {self.busy}"
        if self._rest_task is not None and not self._rest_task.done():
            return "resting"
        if self.refused:
            return f"refused: {self.refused} (release the sticks)"
        if st is not None and not st.connected:
            return "not connected"
        block_fn = getattr(dog, "safety_block", None)
        block = block_fn() if block_fn is not None else None
        if block:                           # before "Stand up": standing is refused outside the fence
            return block
        if st is not None:
            if st.standing is not True:
                return "not standing (press Stand up)" if st.standing is False else "standing unknown"
            if st.avoidance_enabled is not True:
                return "avoidance not confirmed on"
        return None

    async def _control_loop(self) -> None:
        while not self.closing:
            try:
                self._tick()
            except Exception as e:  # never let the dead-man loop die
                print(f"[joystick] control loop error: {type(e).__name__}: {e}", flush=True)
            await asyncio.sleep(TICK_S)

    def _check_safety_events(self, dog) -> None:
        trip = getattr(dog, "last_safety_trip", None)
        if trip is not None and trip is not self._seen_trip:
            self._seen_trip = trip
            snap = self._snapshot(dog)
            self.target = (0.0, 0.0, 0.0)
            self.refused = None
            if self._drive_task is not None and not self._drive_task.done():
                self._drive_task.cancel()
            self.moving = False
            self.log.write("safety_trip", kind=trip.get("kind"), reason=trip.get("reason"),
                           values=trip.get("values"), rest_scheduled=trip.get("rest_scheduled"), home=self.home)
            self._say(f"SAFETY TRIP: {trip.get('reason')}. Lying down softly (automatic).", "trip")
            self._start_measure("safety_trip", dog, snap, {"reason": trip.get("reason")})
        block_fn = getattr(dog, "safety_block", None)
        block = block_fn() if block_fn is not None else None
        outside = bool(block and "outside fence" in block)
        if outside and not self._outside_noted:
            self._outside_noted = True
            self.log.write("safety_outside_fence", block=block)
            self._say(f"{block}", "warn")
        elif not outside:
            self._outside_noted = False

    def _tick(self) -> None:
        now = time.monotonic()
        if self.dog is not None:
            self._check_safety_events(self.dog)
        v = self.target
        nonzero = any(v)
        fresh = now - self.target_t <= self.deadman_s
        dog = self.dog
        active = (nonzero and fresh and self.controller_ws is not None and self._drive_block() is None)
        if active:
            idle = self._drive_task is None or self._drive_task.done()
            if idle and now - self.last_move_t >= MOVE_MIN_INTERVAL_S:
                if self._measure_task is not None and not self._measure_task.done():
                    self._measure_task.cancel()          # a new command interrupts the stop measurement
                self.moving = True
                self.last_move_t = now
                self._drive_task = self._spawn(self._drive_once(dog, v))
        elif self.moving:
            if nonzero and not fresh:
                self.deadman_count += 1
                self.log.write("deadman", silence_s=round(now - self.target_t, 3))
                self._say(f"dead-man: no stick input for {now - self.target_t:.2f} s, StopMove", "warn")
                self._stop("deadman")
                self.target = (0.0, 0.0, 0.0)
            else:
                self._stop("release")

    async def _drive_once(self, dog, v) -> None:
        try:
            await dog.drive(*v)
        except asyncio.CancelledError:
            pass
        except AdapterError as e:
            self.refused = str(e)
            self.target = (0.0, 0.0, 0.0)
            self._say(f"drive refused: {e}", "warn")
            if self.moving:
                self._stop("refused")

    def _stop(self, kind: str, extra: dict | None = None) -> None:
        dog = self.dog
        snap = self._snapshot(dog)
        self.moving = False
        if dog is None:
            return
        self._spawn(dog.stop_move())
        self._start_measure(kind, dog, snap, extra)

    def _snapshot(self, dog) -> dict:
        now = time.monotonic()
        snap: dict = {"since_last_move_s": round(now - self.last_move_t, 3) if self.last_move_t else None,
                      "commanded": list(self.target)}
        sport = (dog.raw_state().get("sport") if dog is not None else None) or {}
        try:
            snap["speed_at_stop"] = round(math.hypot(float(sport["velocity"][0]), float(sport["velocity"][1])), 3)
            snap["yaw_speed_at_stop"] = round(float(sport["yaw_speed"]), 3)
        except (KeyError, TypeError, ValueError, IndexError):
            snap["speed_at_stop"] = None
        return snap

    def _start_measure(self, kind: str, dog, snap: dict, extra: dict | None) -> None:
        if self._measure_task is not None and not self._measure_task.done():
            self._measure_task.cancel()
        self._measure_task = self._spawn(self._measure_stop(kind, dog, snap, extra or {}))

    async def _measure_stop(self, kind: str, dog, snap: dict, extra: dict) -> None:
        """Time from the stop command until RealDog reports stationary (passive metric)."""
        t0 = time.monotonic()
        latency = None
        interrupted = False
        try:
            while time.monotonic() - t0 < STOP_MEASURE_S:
                st = await dog.get_status()
                if st.stationary is True:
                    latency = round(time.monotonic() - t0, 3)
                    break
                await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            interrupted = True
        rec = {"kind": kind, "stop_latency_s": latency, **snap, **extra}
        if interrupted:
            rec["interrupted_by_new_command"] = True
        self.last_stop = self.log.write("stop", **rec)
        if latency is not None and self.verbose:
            print(f"[joystick] stop ({kind}): stationary after {latency:.3f} s "
                  f"(speed at stop {snap.get('speed_at_stop')})", flush=True)

    # ------------------------------------------------------------ status + video

    async def status(self) -> dict:
        dog = self.dog
        st = await dog.get_status() if dog is not None else DogStatus(False, None, None, None)
        raw = dog.raw_state() if dog is not None else {}
        sport = raw.get("sport") or {}
        low = raw.get("low") or {}
        now = time.monotonic()

        def g(fn):
            try:
                return fn()
            except Exception:
                return None

        _, frame_t = dog.latest_frame() if dog is not None else (None, None)
        return {
            "t": "status", "fake": self.fake,
            "connected": st.connected, "standing": st.standing, "stationary": st.stationary,
            "avoidance": st.avoidance_enabled,
            "battery": g(lambda: (low.get("bms_state") or {}).get("soc")),
            "body_height": g(lambda: round(float(sport["body_height"]), 3)),
            "mode": sport.get("mode"),
            "position": g(lambda: [round(float(p), 3) for p in sport["position"][:2]]),
            "speed": g(lambda: round(math.hypot(float(sport["velocity"][0]), float(sport["velocity"][1])), 3)),
            "yaw_speed": g(lambda: round(float(sport["yaw_speed"]), 3)),
            "state_age_s": raw.get("sport_age_s"),
            "commanded": [round(v, 3) for v in self.target], "moving": self.moving,
            "last_cmd_age_s": round(now - self.last_cmd_t, 2) if self.last_cmd_t else None,
            "lock": dog.motion_lock() if dog is not None else None,
            "drive_block": self._drive_block(st),
            "busy": self.busy, "connect_error": self.connect_error,
            "resting": self._rest_task is not None and not self._rest_task.done(),
            "brightness": self.brightness, "last_stop": self.last_stop, "last_photo": self.last_photo,
            "deadman_count": self.deadman_count,
            "frame_age_s": round(now - frame_t, 2) if frame_t else None,
            "controller_present": self.controller_ws is not None, "caps": self.caps,
            "safety": self._safety_of(dog) if dog is not None else None,
            "safety_enabled": (bool(getattr(dog, "safety_envelope_enabled"))
                               if dog is not None and hasattr(dog, "safety_envelope_enabled") else None),
            "home": self.home,
        }

    async def _status_loop(self) -> None:
        while not self.closing:
            if self.clients:
                try:
                    s = await self.status()
                    for ws in list(self.clients):
                        role = "control" if ws is self.controller_ws else "view"
                        self._spawn(self._send(ws, {**s, "role": role}))
                except Exception as e:
                    print(f"[joystick] status error: {type(e).__name__}: {e}", flush=True)
            await asyncio.sleep(STATUS_PERIOD_S)

    async def jpeg(self) -> tuple[bytes | None, float | None]:
        dog = self.dog
        if dog is None:
            return None, None
        img, t = dog.latest_frame()
        if img is None:
            return None, None
        async with self._jpeg_lock:
            if self._jpeg_cache[0] != t:
                self._jpeg_cache = (t, await asyncio.to_thread(_encode_jpeg, img))
            return self._jpeg_cache[1], t

    # ------------------------------------------------------------ websocket messages

    def handle(self, ws, msg: Any) -> None:
        if not isinstance(msg, dict):
            return
        t = msg.get("t")
        if t in ("stop", "rest"):              # anyone may stop, even view-only clients
            self.request_rest(f"browser:{t}")
            return
        if t == "claim":
            if self.controller_ws is None:
                self.controller_ws = ws
                self.log.write("client", action="control_claimed")
                self._spawn(self._send(ws, {"t": "role", "role": "control"}))
                self._say("a browser took control")
            elif ws is not self.controller_ws:
                self.take_control(ws)
            return
        if ws is not self.controller_ws:
            self._spawn(self._send(ws, {"t": "event", "level": "warn", "msg": "view-only: command ignored"}))
            return
        if t == "drive":
            self.set_target(msg.get("x"), msg.get("y"), msg.get("yaw"), msg.get("speed"))
        elif t == "stand":
            self.request_stand()
        elif t == "rearm":
            self.request_rearm()
        elif t == "light":
            self.request_light(msg.get("level"))
        elif t == "photo":
            self.request_photo(msg.get("zone"))
        elif t == "set_home":
            self.request_set_home()
        elif t == "safety":
            self.request_safety(msg.get("enabled"))


# ---------------------------------------------------------------- web app

LOCAL_HOSTS = ("127.0.0.1", "localhost")
CTL_KEY = web.AppKey("ctl", Controller)


def _hostname(value: str | None) -> str | None:
    if not value:
        return None
    from urllib.parse import urlsplit

    v = value if "://" in value else f"//{value}"
    try:
        return urlsplit(v).hostname
    except ValueError:
        return ""


@web.middleware
async def _local_only(request, handler):
    # Blocks DNS rebinding (Host must be loopback) and other websites in the operator's
    # browser (a browser always sends Origin on WebSocket/fetch; it must be our own page).
    if _hostname(request.headers.get("Host")) not in LOCAL_HOSTS:
        return web.Response(status=403, text="forbidden host")
    origin = request.headers.get("Origin")
    if origin is not None and _hostname(origin) not in LOCAL_HOSTS:
        ctl = request.app.get(CTL_KEY)
        if ctl is not None:
            ctl.log.write("client", action="rejected_origin", origin=origin)
        return web.Response(status=403, text="forbidden origin")
    return await handler(request)


def build_app(ctl: Controller) -> web.Application:
    app = web.Application(middlewares=[_local_only])
    app[CTL_KEY] = ctl

    async def index(request):
        return web.Response(text=HTML_PATH.read_text(), content_type="text/html",
                            headers={"Cache-Control": "no-store"})

    async def ws_handler(request):
        ws = web.WebSocketResponse(heartbeat=2.0)
        await ws.prepare(request)
        role = "view"
        if ctl.controller_ws is None and not ctl.closing:
            ctl.controller_ws = ws
            role = "control"
        ctl.clients.add(ws)
        ctl.log.write("client", action="ws_open", role=role, remote=request.remote)
        await ctl._send(ws, {"t": "hello", "role": role, "fake": ctl.fake, "caps": ctl.caps,
                             "safety_enabled": ctl.envelope_enabled,
                             "default_speed": DEFAULT_SPEED, "deadman_s": ctl.deadman_s, "zones": ZONES})
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except ValueError:
                        continue
                    ctl.handle(ws, data)
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            ctl.clients.discard(ws)
            ctl.log.write("client", action="ws_close", role="control" if ws is ctl.controller_ws else "view")
            if ws is ctl.controller_ws:
                ctl.controller_ws = None
                ctl.on_controller_lost("ws_close")
        return ws

    async def mjpeg(request):
        resp = web.StreamResponse(headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-store"})
        await resp.prepare(request)
        last_t = None
        try:
            while not ctl.closing:
                jpg, t = await ctl.jpeg()
                if jpg is not None and t != last_t:
                    last_t = t
                    await resp.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                await asyncio.sleep(1.0 / VIDEO_FPS)
        except (ConnectionResetError, ConnectionError):
            pass
        return resp

    async def on_startup(app):
        await ctl.start()

    async def on_shutdown(app):
        ctl.closing = True
        for ws in list(ctl.clients):
            await ws.close()

    async def on_cleanup(app):
        await ctl.shutdown()

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/video.mjpg", mjpeg)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    app.on_cleanup.append(on_cleanup)
    return app


# ---------------------------------------------------------------- terminal keys

class TerminalKeys:
    """Single-key stops in the server terminal (cbreak; restored on exit).

    Q or ENTER -> STOP: lie down softly (rest). Ctrl+C -> rest, then exit (signal handler).
    """

    def __init__(self, ctl: Controller) -> None:
        self.ctl = ctl
        self.active = False
        self._old = None

    def install(self) -> bool:
        if not sys.stdin.isatty():
            return False
        import termios
        import tty

        fd = sys.stdin.fileno()
        self._old = termios.tcgetattr(fd)
        tty.setcbreak(fd)                     # keys arrive immediately; Ctrl+C still raises SIGINT
        asyncio.get_running_loop().add_reader(fd, self._on_key)
        self.active = True
        return True

    def restore(self) -> None:
        if not self.active:
            return
        import termios

        fd = sys.stdin.fileno()
        try:
            asyncio.get_running_loop().remove_reader(fd)
        except Exception:
            pass
        termios.tcsetattr(fd, termios.TCSADRAIN, self._old)
        self.active = False

    def _on_key(self) -> None:
        self.handle(os.read(sys.stdin.fileno(), 1))

    def handle(self, ch: bytes) -> None:
        if ch in (b"q", b"Q"):
            self.ctl.request_rest("terminal:Q")
        elif ch in (b"\n", b"\r"):
            self.ctl.request_rest("terminal:Enter")


# ---------------------------------------------------------------- main

def _make_factory(args) -> tuple[Callable[[], Any], Path]:
    from patrol.dog.real import RealDog

    if args.fake:
        from patrol.dog.sim_conn import SimConn

        sim = SimConn()                        # one simulated body, reused across re-arms
        out = Path(args.out or "evidence/dog/fake")
        cfg = {"connection_mode": "LocalSTA", "interface": "simulated", "command_timeout_s": 1.0}
        return (lambda: RealDog(config=cfg, output_dir=out, _conn_factory=lambda ip: sim)), out
    config = json.loads(Path(args.config).read_text())
    out = Path(args.out or "evidence/dog")
    return (lambda: RealDog(config=config, output_dir=out)), out


async def _amain(args) -> int:
    factory, out = _make_factory(args)
    ctl = Controller(factory, log_path=out / "joystick.jsonl", fake=args.fake)
    app = build_app(ctl)
    runner = web.AppRunner(app, shutdown_timeout=2.0)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", args.port)
    try:
        await site.start()
    except OSError as e:
        print(f"Cannot listen on 127.0.0.1:{args.port}: {e}. Is another joystick running? Use --port.", flush=True)
        await runner.cleanup()                 # closes the dog adapter (no motion was sent)
        return 2

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    keys = TerminalKeys(ctl)
    try:
        keys_on = keys.install()
        mode = "FAKE (simulated dog)" if args.fake else "REAL dog (connecting, no motion on connect)"
        print(f"Go2 joystick: {mode}\n  open  http://127.0.0.1:{args.port}/   (not opened automatically)\n"
              f"  logs  {out / 'joystick.jsonl'}\n"
              f"  caps  {JOY_MAX_VX} m/s fwd/back, {JOY_MAX_VY} m/s sideways, {JOY_MAX_VYAW} rad/s yaw; "
              f"dead-man {DEADMAN_S * 1000:.0f} ms", flush=True)
        if keys_on:
            print("  terminal: Q or ENTER = STOP (lie down softly)   Ctrl+C = lie down + exit", flush=True)
        else:
            print("  WARNING: stdin is not a terminal, Q/ENTER stops here are OFF (Ctrl+C still rests + exits)",
                  flush=True)
        print("  Safety thresholds ON (fence / speed / tilt / route overshoot): a trip lies the dog down softly.",
              flush=True)
        print("  The staff controller is always the primary stop.", flush=True)
        await stop.wait()
        print("\n*** Ctrl+C: lying down softly, then exit ***", flush=True)
        ctl.request_rest("terminal:Ctrl+C")
        if ctl._rest_task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(ctl._rest_task), 8.0)
            except Exception:
                pass
    finally:
        keys.restore()
        await runner.cleanup()
    return 0


def main(argv: list[str] | None = None) -> int:
    import logging
    logging.getLogger("aiortc.codecs.h264").setLevel(logging.ERROR)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/dog.local.json")
    ap.add_argument("--fake", action="store_true", help="simulated dog; never touches the network")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--out", default=None, help="photos + joystick.jsonl (default evidence/dog, fake: evidence/dog/fake)")
    args = ap.parse_args(argv)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    sys.exit(main())
