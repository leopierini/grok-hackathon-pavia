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

Audio (never affects motion): volume 0..10, "say" (macOS TTS test, Italian or
English), test chime, stop audio, hold-to-talk (browser mic -> dog speaker, controller
only), listen (dog mic -> browser, any tab; the dog's mic channel is on only while
someone listens or records), record N s of the dog's mic to a WAV. A 10 Hz "meter"
message streams the mic and speaker levels and the dog's own volume readback.
Every STOP also cuts the speaker.

Workflow (real dog): the server connects on start; if the dog isn't reachable yet (cable
out, dog off) it checks port 8081 every 3 s and connects as soon as it answers. "Run test"
runs a no-motion real_selftest step (read / audio) on a fresh connection, appends it to
<out>/session.jsonl and re-arms automatically (STOP keeps working during the test; a STOP
during it leaves the new connection locked). "Shut down server" = Ctrl+C (lie down, exit).
Launcher: double-click scripts/dog_joystick.command.

LiDAR: a <= 5 Hz "lidar" message (top-down points in the dog's body frame) goes to every tab;
the page draws it forward = up. If connected but the dog has sent no LiDAR for 5 s, the controller
tab may press "Turn LiDAR on (ask staff first)" (logged as `lidar_switch`; never automatic). The dog
needs lidar_view / lidar_status / lidar_switch_on, else skipped. `--no-lidar` (config
`lidar_enabled: false`) turns the whole LiDAR path off: nothing is subscribed or pushed.
LiDAR brake (both drive modes, ON at every start; page checkbox, controller only, logged): while
the latest view is fresh (<= 1 s, not stale), forward speed becomes 0 when "nearest obstacle ahead"
< 0.5 m (lidar.brake_forward). Turning, sideways and backward are never braked. No fresh LiDAR =>
no brake (fails open) and status says "inactive (no fresh LiDAR)". Engage/release are logged once
each (`lidar_brake`). The brake only ever lowers a command; it never starts motion.

Drive mode ("move" at every start): "move" = sport Move (api 1008). "sticks" = simulated
remote-controller sticks on rt/wirelesscontroller (RealDog.send_sticks, |value| <= STICK_MAX),
the path the dog's own obstacle avoidance filters (plain Move walked into a person/box with
avoidance on, 2026-11-04 18:08). Switchable by the controller only while stationary (logged
`drive_mode`). Every stop zeroes the sticks too (RealDog's stop paths). Test first: the staff
controller stop must still win.

Follow signal (demo, docs/Lidar + SLAM.md §8b): the controller places a simulated signal point
(beacon_place, odom metres) and presses Start following (follow_start, refused unless standing,
stationary, no stick held, avoidance on, thresholds on and inside the fence, LiDAR brake on and fresh).
patrol.dog.follow.Follower turns the fake RSSI into (vx >= 0, vyaw) at ~10 Hz, written into the
drive target: same brake, drive mode, caps and RealDog checks as the sticks. Arrived = StopMove once,
stays standing. Ends on Stop following, 60 s limit, any page stick input (manual takeover), and every
existing stop (STOP, ws loss, blur, take control, trip, re-arm, disconnect). Follow dead-man: the
page sends follow_alive every 250 ms while following; > 1 s of silence ends it (StopMove).

Logs JSON lines to <out>/joystick.jsonl (stop latency, dead-man, connection,
photos, brightness, volume, audio). --fake writes to evidence/dog/fake/ by default.
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
from typing import Any, Awaitable, Callable

from aiohttp import WSMsgType, web

from patrol.contract import AdapterError, DogStatus, RunContext
from patrol.dog.follow import ARRIVE_DBM, RESUME_DBM, RUN_LIMIT_S, Follower, VirtualBeacon
from patrol.dog.lidar import BRAKE_DISTANCE_M, brake_forward
from patrol.dog.real import AVOID_REFUSED, LIDAR_LYING_MSG, STICK_MAX

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
METER_PERIOD_S = 0.1    # 10 Hz audio meter push
LIDAR_PERIOD_S = 0.2    # <= 5 Hz LiDAR top-down push
NO_LIDAR_WARN_S = 5.0   # page: connected but no LiDAR message for this long => offer the switch
LISTEN_RATE = 16000     # dog mic -> browser, mono s16
TALK_MAX_LAG_S = 0.4    # browser mic -> dog: never more than this behind
TALK_MAX_CHUNK = 64000  # bytes per binary message
SAY_VOICES = {"it": "Alice", "en": "Samantha"}
RECORD_MAX_S = 30.0
ZONES = ("entrance", "room_2", "display")
CHECK_STEPS = ("read", "audio")   # real_selftest steps the page may run: never the motion ones
CHECK_TIMEOUT_S = 60.0
AUTO_CONNECT_S = 3.0    # while the dog was never reached: probe this often, connect when it answers
SIGNALING_PORT = 8081   # the dog's legacy WebRTC /offer port (probe target)
DRIVE_MODES = ("move", "sticks")   # sport Move | remote-controller sticks (dog's own avoidance)
BRAKE_FRESH_S = 1.0     # LiDAR brake uses a view received at most this long ago (and not stale)
BRAKE_INACTIVE = "inactive (no fresh LiDAR)"
FOLLOW_TICK_S = 0.1     # follower step (~10 Hz); its command goes out through the normal drive path
FOLLOW_DEADMAN_S = 1.0  # following: no follow_alive from the controller page for this long => end (StopMove)
FOLLOW_SAMPLE_S = 1.0   # one follow_sample log line per second while following
BEACON_NOISE_DB = 2.0   # simulated signal noise (dB); was 3.0, lowered for the demo 2026-11-04
BEACON_MAX_M = 50.0     # a virtual point further than this from odom zero is junk
BEACON_FENCE_MARGIN_M = 1.5   # the point must lie within fence radius - this of home (room to arrive inside)
REFUSAL_SHOW_S = 20.0   # the page shows the last follow refusal this long
MOVE_MODE_WARN = "dog's own avoidance is off — our LiDAR dodge + brake only"
FOLLOW_STOP_REASONS = {"button": "Stop following button", "blur": "tab blur", "hidden": "tab hidden",
                       "pagehide": "page closed"}
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


def _check_summary(rec: dict) -> dict:
    """The few fields worth showing on the page after a test."""
    keys = ("error", "connect_s", "battery", "photo", "volume_before", "volume_set", "volume_restored",
            "loopback_heard", "loopback_tone_rise_db", "recording", "note")
    return {k: rec[k] for k in keys if rec.get(k) is not None}


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
                 deadman_s: float = DEADMAN_S, verbose: bool = True, out_dir: Path | None = None,
                 auto_connect_s: float | None = None,
                 reachable: Callable[[], Awaitable[bool]] | None = None) -> None:
        self._factory = dog_factory
        self.out_dir = Path(out_dir) if out_dir is not None else Path(log_path).parent
        self.auto_connect_s = auto_connect_s    # None or no probe = no auto-connect
        self._reachable = reachable
        self.dog: Any = None
        self.fake = fake
        self.log = JsonlLog(log_path, fake=fake)
        self.deadman_s = deadman_s
        self._safety_check_err: str | None = None   # last _tick check error (printed once, not per tick)
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
        self.volume: int | None = None      # last value read or set
        self.last_recording: dict | None = None
        self.recording = False
        self.talk_rate: int | None = None   # set while the controller holds Talk
        self._talk_t0 = 0.0
        self.listeners: set = set()         # websockets that asked for the dog's mic
        self._listen_task: asyncio.Task | None = None
        self.last_stop: dict | None = None
        self.last_photo: str | None = None
        self.deadman_count = 0
        self.connect_error: str | None = None
        self.home: list | None = None       # kept across re-arms (odometry frame survives reconnects)
        self.envelope_enabled = True        # safety thresholds; ON at every server start
        self.drive_mode = "move"            # "move" | "sticks"; "move" at every server start
        self.lidar_brake_enabled = True     # LiDAR forward brake; ON at every server start
        self._brake_view: dict | None = None    # latest LiDAR view built by _lidar_loop
        self._brake_view_t = 0.0                # monotonic time it was received
        self._sticks_seen = False           # sticks were sent this server run (new adapters zero them)
        self._braking = False               # the brake is holding forward motion right now
        self._brake_near: float | None = None
        self._seen_trip: Any = None
        self._outside_noted = False
        # follow a virtual signal point (demo mode): autonomous, but through the same drive path
        self.beacon: VirtualBeacon | None = None
        self.beacon_noise_db = BEACON_NOISE_DB
        self.beacon_rng = None              # tests: random.Random(seed)
        self.follow_limit_s = RUN_LIMIT_S
        self.follower = Follower()
        self._follow_on = False             # a run is active (following / probing / arrived)
        self._follow_dog: Any = None        # the adapter the run started on (a new adapter ends it)
        self._follow_t = 0.0
        self._follow_sample_t = 0.0
        self._follow_cmd = None             # last FollowCommand
        self._follow_rssi: float | None = None
        self._follow_wanted_fwd = False     # the follower asked for forward at least once this run
        self._follow_err: str | None = None
        self._follow_alive_t = 0.0          # last follow_alive from the controller page (follow dead-man)
        self._follow_refused: tuple[str, float] | None = None   # (reason, monotonic t): shown on the page

        self._old_dog: Any = None           # adapter being closed during re-arm (still usable for STOP)
        self._check_dog: Any = None         # adapter a page-run selftest step is using (usable for STOP)
        self._stop_during_check = False
        self.last_check: dict | None = None
        self.on_exit: Callable[[str], None] | None = None   # set by main: Shut down button
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
        self._lidar_err: str | None = None  # last LiDAR loop error printed (print each distinct one once)
        self._lidar_inflight: set = set()   # ws with a lidar send still pending (per-tab backpressure)

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._loops = [asyncio.create_task(self._control_loop()),
                       asyncio.create_task(self._status_loop()),
                       asyncio.create_task(self._meter_loop()),
                       asyncio.create_task(self._lidar_loop())]
        if self._reachable is not None and self.auto_connect_s:
            self._loops.append(asyncio.create_task(self._autoconnect_loop()))
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
    async def _send(ws, data: dict | str) -> None:
        try:
            if isinstance(data, str):
                await ws.send_str(data)          # already serialized (shared by all tabs)
            else:
                await ws.send_json(data)
        except Exception:
            pass

    async def _connect_new(self, reason: str, latch: str | None = None) -> None:
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
                retry = ("retrying automatically when the dog answers"
                         if self._reachable is not None and self.auto_connect_s else "press Re-arm to retry")
                self._say(f"connect failed: {e} ({retry})", "error")
                return
            self.connect_error = None
            if latch:
                dog.latch_lock(latch)       # before anyone can see the adapter: no unlocked window
            self.dog = dog
            await self._zero_sticks_on_new(dog, reason)
            try:
                self.brightness = await dog.get_brightness()
            except AdapterError:
                self.brightness = None
            try:
                self.volume = await dog.get_volume()
            except (AdapterError, AttributeError):
                self.volume = None
            safety = self._safety_of(dog)
            if safety and safety.get("home") is not None:
                self.home = safety["home"]
            self.log.write("connection", action="connected", reason=reason,
                           connect_s=round(time.monotonic() - t0, 2), status=st.__dict__,
                           brightness=self.brightness, volume=self.volume,
                           home=self.home, home_source=(safety or {}).get("home_source"),
                           safety_enabled=(safety or {}).get("enabled"),
                           lidar_enabled=getattr(dog, "lidar_enabled", None))
            self._say(f"connected ({reason}) in {time.monotonic() - t0:.1f} s: {st}")
        finally:
            self.busy = None
            if self._rest_pending:          # Q/STOP arrived while (re)connecting
                self._rest_task = self._spawn(self._do_rest("pending"))

    async def _zero_sticks_on_new(self, dog, reason: str) -> None:
        """A link lost mid-walk in sticks mode may have eaten the release zero, and the dog may
        still hold the last stick. A new adapter therefore marks sticks as used (its STOP paths
        zero them) and sends one zero burst right after connect. A zero stick is no motion."""
        if not (self.drive_mode == "sticks" or self._sticks_seen) or not hasattr(dog, "mark_sticks_used"):
            return
        try:
            dog.mark_sticks_used()
            res = await dog.zero_sticks()
            counts = res if isinstance(res, dict) else {}
            msg = ("zero_sticks dropped (data channel not open)" if counts.get("dropped")
                   else "zero_sticks failed (publish raised)" if counts.get("failed") else None)
            self.log.write("zero_sticks", reason=f"new adapter ({reason}) after sticks use",
                           drive_mode=self.drive_mode, counts=counts or None, **({"error": msg} if msg else {}))
            if msg and not counts.get("sent"):
                self._say(f"{msg}: if the dog moves, USE THE STAFF CONTROLLER", "error")
        except Exception as e:      # never block a connect; STOP still works
            self.log.write("zero_sticks", reason=f"new adapter ({reason})", error=f"{type(e).__name__}: {e}")

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
        self._end_follow(f"STOP ({source})", stop=False)    # rest() below does StopMove + StandDown
        self.target = (0.0, 0.0, 0.0)
        self.refused = None
        self.last_cmd_t = time.monotonic()
        if self._drive_task is not None and not self._drive_task.done():
            self._drive_task.cancel()
        if self.busy == "stand" and self._busy_task is not None:
            self._busy_task.cancel()
        self.log.write("stop_pressed", source=source)
        self.talk_rate = None               # STOP also cuts the speaker
        if self.busy == "check":
            self._stop_during_check = True  # the re-arm after the test keeps the lock latched
        for cand in (self.dog, self._old_dog, self._check_dog):
            try:
                if cand is not None:
                    cand.stop_audio()
            except Exception:
                pass
        if self._rest_task is not None and not self._rest_task.done():
            return                          # a rest is already running
        self._rest_pending = True           # cleared by _do_rest once it reaches a connected adapter
        self._say(f"STOP ({source}): lying down softly", "warn")
        self._rest_task = self._spawn(self._do_rest(source))

    async def _do_rest(self, source: str) -> None:
        # Deliver on ANY adapter that is still connected: the current one, the old one while
        # a re-arm is closing it, or the one a page-run test is using. Never wait if we can stop now.
        dog = None
        for cand in (self.dog, self._old_dog, self._check_dog):
            if cand is not None and getattr(cand, "_connected", False):
                dog = cand
                break
        if dog is None:
            if self.busy in ("connecting", "check"):
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
        if report.get("standdown_code") == 4201:    # accepted/busy; lying down checked via state
            self.log.write("standdown_code_4201", source=source, lying_confirmed=report.get("lying_confirmed"))
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
        if self._follow_on:
            return self._say("stand refused: following the signal (Stop following first)", "warn")
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
            if st.avoidance_enabled is not True:    # read-only: we never switch it on
                self.log.write("avoidance_not_confirmed", avoidance=st.avoidance_enabled)
                self._say(f"{AVOID_REFUSED} (avoidance reads {st.avoidance_enabled})", "warn")
        except AdapterError as e:
            self._say(f"stand failed: {e}", "error")
        except asyncio.CancelledError:
            self._say("stand cancelled", "warn")
        finally:
            self.busy = None

    def request_rearm(self) -> None:
        self._end_follow("re-arm")          # StopMove; the re-arm itself waits for stationary
        self._spawn(self._do_rearm())

    async def _do_rearm(self, reason: str = "rearm") -> None:
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
        self.log.write("connection", action="rearm", reason=reason)
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
        await self._connect_new(reason)

    # ------------------------------------------------------------ auto-connect

    def _should_autoconnect(self) -> bool:
        """Only while the dog was never reached on this adapter (cable not in yet, dog off).
        Never for a connected adapter, so a STOP lock is never cleared automatically."""
        dog = self.dog
        return (not self.closing and self.busy is None and dog is not None
                and self.connect_error is not None and not getattr(dog, "_connected", False)
                and (self._rest_task is None or self._rest_task.done())
                and not self.moving and not any(self.target))

    async def _autoconnect_loop(self) -> None:
        while not self.closing:
            await asyncio.sleep(self.auto_connect_s)
            if not self._should_autoconnect():
                continue
            try:
                ok = await asyncio.wait_for(self._reachable(), 2.0)
            except Exception:
                ok = False
            if ok and self._should_autoconnect():
                self._say("dog reachable: connecting automatically (no motion on connect)")
                await self._do_rearm("auto")

    # ------------------------------------------------------------ page-run selftest step

    def _check_refused(self, step: Any, why: str) -> None:
        self.log.write("check", action="refused", step=str(step)[:20], reason=why)
        self._say(f"test refused: {why}", "warn")

    def request_check(self, step: Any, volume: Any = None) -> None:
        """Run a no-motion real_selftest step ("read" or "audio") from the page: release this
        connection, run the step on a fresh adapter, then re-arm automatically."""
        if step not in CHECK_STEPS:
            return self._check_refused(step, f"only {' / '.join(CHECK_STEPS)} run from the page "
                                              "(motion steps: use the terminal with --arm)")
        if self.busy is not None:
            return self._check_refused(step, f"busy: {self.busy}")
        if self._rest_task is not None and not self._rest_task.done():
            return self._check_refused(step, "lying down (resting)")
        if self.moving or any(self.target):
            return self._check_refused(step, "release the sticks first")
        if self._follow_on:
            return self._check_refused(step, "following the signal: Stop following first")
        if self.recording or self.talk_rate:
            return self._check_refused(step, "recording or talking: stop that first")
        vol = None
        if step == "audio":
            vol = int(_num(volume, 0, 10, 5)) if volume is not None else 5
            if vol == 0:                    # a silent test proves nothing (real dog, 2026-11-04)
                vol = 5
                self._say("audio test: Set volume is 0, testing at 5 (the old volume is restored after)", "warn")
        self.busy = "check"                 # set now: a double click is refused
        self._stop_during_check = False
        self._spawn(self._do_check(step, vol))

    async def _do_check(self, step: str, volume: int | None) -> None:
        from patrol.dog import real_selftest

        released = False
        try:
            old = self.dog
            if old is not None:
                st = await old.get_status()
                if st.connected and st.stationary is not True:
                    self.busy = None
                    return self._check_refused(step, f"dog not stationary ({st})")
                safety = self._safety_of(old)
                if safety and safety.get("home") is not None:
                    self.home = safety["home"]
            self.log.write("check", action="start", step=step, volume=volume)
            self._say(f"test '{step}': releasing the connection, running real_selftest --step {step}"
                      + (f" --volume {volume}" if volume is not None else "") + " (no motion)")
            released = True
            self.dog = None
            self._old_dog = old
            try:
                if old is not None:
                    await old.close()
            except Exception:
                pass
            finally:
                self._old_dog = None
            dog = self._factory()
            if self.home is not None and hasattr(dog, "adopt_home"):
                dog.adopt_home(self.home)
            if (self.drive_mode == "sticks" or self._sticks_seen) and hasattr(dog, "mark_sticks_used"):
                dog.mark_sticks_used()      # a STOP during the test zeroes the sticks too
            self._check_dog = dog
            rec = await asyncio.wait_for(
                real_selftest._run(step, {}, self.out_dir, volume, dog=dog, keys=False), CHECK_TIMEOUT_S)
            rec["source"] = "joystick"
            if self._stop_during_check:
                rec["stop_during_check"] = True
            real_selftest.append_session(self.out_dir, rec)
            summary = _check_summary(rec)
            self.last_check = {"step": step, "ok": bool(rec.get("ok")), "utc": rec.get("utc"), **summary}
            self.log.write("check", action="done", step=step, ok=bool(rec.get("ok")), **summary)
            text = ", ".join(f"{k} {v}" for k, v in summary.items() if v is not None)
            self._say(f"test '{step}': {'PASS' if rec.get('ok') else 'FAIL'}: {text}",
                      "info" if rec.get("ok") else "error")
        except Exception as e:              # incl. timeout: report, never crash the server
            err = f"{type(e).__name__}: {e}"
            self.last_check = {"step": step, "ok": False, "error": err}
            self.log.write("check", action="done", step=step, ok=False, error=err)
            self._say(f"test '{step}' failed: {err}", "error")
        finally:
            self._check_dog = None
            if released and not self.closing:
                latch = "STOP during test: press Re-arm" if self._stop_during_check else None
                self._say("test finished: re-arming automatically (no motion on connect)")
                await self._connect_new("after_check", latch=latch)
            elif self.busy == "check":
                self.busy = None

    # ------------------------------------------------------------ shut down (page button)

    def request_exit(self, source: str) -> None:
        """Shut down button: same as Ctrl+C in the terminal (lie down softly, then exit)."""
        self.log.write("shutdown_requested", source=source)
        self._say("SHUT DOWN requested: lying down softly, then the server exits", "warn")
        if self.on_exit is not None:
            self.on_exit(source)

    def request_set_home(self) -> None:
        dog = self.dog
        if dog is None or not hasattr(dog, "set_home"):
            return self._say("set home refused: not connected", "warn")
        if self.busy or self.moving or any(self.target) or self._follow_on or (
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
        if not enabled and (self.busy or self.moving or any(self.target) or self._follow_on):
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

    def request_drive_mode(self, mode: Any, source: str = "browser") -> None:
        """Switch between sport Move and remote-controller sticks. Only while stationary and
        no motion is commanded; never changes anything on the dog itself."""
        if mode not in DRIVE_MODES:
            self.log.write("drive_mode", action="refused", requested=str(mode)[:20], reason="unknown mode")
            return self._say(f"drive mode unchanged ({self.drive_mode}): unknown mode", "warn")
        if mode == self.drive_mode:
            return
        self._spawn(self._do_drive_mode(mode, source))

    async def _do_drive_mode(self, mode: str, source: str) -> None:
        def busy_reason() -> str | None:
            if self.busy:
                return f"busy: {self.busy}"
            if self._follow_on:
                return "following the signal: Stop following first"
            if (self.moving or any(self.target)
                    or (self._drive_task is not None and not self._drive_task.done())):
                return "only while stationary: release the sticks first"
            return None

        dog = self.dog
        why = None
        if dog is None or not getattr(dog, "_connected", False):
            why = "dog not connected"
        elif mode == "sticks" and not callable(getattr(dog, "send_sticks", None)):
            why = "this dog adapter has no stick input"
        else:
            why = busy_reason()
            if why is None:
                st = await dog.get_status()
                if st.stationary is not True:
                    why = f"dog not stationary ({st})"
                else:
                    why = busy_reason()     # re-check after the await
        if why is not None:
            self.log.write("drive_mode", action="refused", requested=mode, reason=why, source=source)
            return self._say(f"drive mode unchanged ({self.drive_mode}): {why}", "warn")
        old, self.drive_mode = self.drive_mode, mode
        self.log.write("drive_mode", old=old, new=mode, source=source)
        if mode == "sticks":
            self._say("drive mode: STICKS (remote-controller path, dog's own obstacle avoidance). "
                      "Test first: the staff controller stop must still win", "warn")
        else:
            self._say("drive mode: Move (sport api 1008)")

    def request_lidar_brake(self, enabled: Any) -> None:
        if not isinstance(enabled, bool) or enabled == self.lidar_brake_enabled:
            return
        self.lidar_brake_enabled = enabled
        if enabled:
            self.log.write("lidar_brake_on")
            self._say(f"LiDAR brake ON ({BRAKE_DISTANCE_M:g} m)")
        else:
            self.log.write("lidar_brake_off", drive_mode=self.drive_mode)
            if self.verbose:
                print("[joystick] *** LiDAR BRAKE OFF: no automatic forward stop near obstacles ***", flush=True)
            self._say("LiDAR BRAKE OFF: no automatic forward stop near obstacles", "warn")

    def take_control(self, ws) -> None:
        """A view-only tab takes control: stop the dog first (StopMove, stays standing),
        demote the old controller, then promote the new one."""
        old = self.controller_ws
        if old is ws:
            return
        self._end_follow("control taken by another tab", stop=False)   # _stop below sends StopMove
        self.target = (0.0, 0.0, 0.0)
        self.refused = None
        if self._drive_task is not None and not self._drive_task.done():
            self._drive_task.cancel()
        self._stop("control_taken")         # StopMove even if we think we're idle
        self.talk_rate = None               # the old tab's hold-to-talk ends too
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

    # ------------------------------------------------------------ audio

    def _audio_dog(self):
        dog = self.dog
        if dog is None or not getattr(dog, "_connected", False):
            self._say("audio: dog not connected", "warn")
            return None
        return dog

    def request_volume(self, level: Any) -> None:
        self._spawn(self._do_volume(level))

    async def _do_volume(self, level: Any) -> None:
        dog = self._audio_dog()
        if dog is None:
            return
        try:
            sent = await dog.set_volume(_num(level, 0, 10, 0))
        except AdapterError as e:
            return self._say(f"volume failed: {e}", "error")
        old, self.volume = self.volume, sent
        self.log.write("volume", old=old, new=sent)
        self._say(f"volume {sent}/10")

    def request_say(self, text: Any, lang: Any) -> None:
        self._spawn(self._do_say(text, lang))

    async def _do_say(self, text: Any, lang: Any) -> None:
        dog = self._audio_dog()
        if dog is None:
            return
        text = text.strip() if isinstance(text, str) else ""
        voice = SAY_VOICES.get(lang if isinstance(lang, str) else "", SAY_VOICES["it"])
        try:
            secs = await dog.say(text, voice)
        except AdapterError as e:
            return self._say(f"say failed: {e}", "error")
        self.log.write("say", text=text, voice=voice, seconds=secs, volume=self.volume)
        self._say(f"saying ({secs:.1f} s): {text}" + (" (volume is 0!)" if self.volume == 0 else ""))

    def request_chime(self) -> None:
        dog = self._audio_dog()
        if dog is None:
            return
        try:
            secs = dog.play_chime()
        except AdapterError as e:
            return self._say(f"chime failed: {e}", "error")
        self.log.write("chime", seconds=secs, volume=self.volume)
        self._say("test chime" + (" (volume is 0!)" if self.volume == 0 else ""))

    def request_audio_stop(self) -> None:
        self.talk_rate = None
        if self.dog is not None:
            self.dog.stop_audio()
        self.log.write("audio_stop")

    def request_record(self, seconds: Any) -> None:
        if self.recording:
            return self._say("already recording", "warn")
        self._spawn(self._do_record(_num(seconds, 0.5, RECORD_MAX_S, 5.0)))

    async def _do_record(self, seconds: float) -> None:
        dog = self._audio_dog()
        if dog is None:
            return
        self.recording = True
        self._say(f"recording the dog's mic for {seconds:.0f} s…")
        try:
            rec = await dog.record_audio(seconds, name="joystick_mic")
        except AdapterError as e:
            return self._say(f"record failed: {e}", "error")
        finally:
            self.recording = False
        self.last_recording = {"path": rec["path"], "seconds": rec["seconds"], "peak_dbfs": rec["peak_dbfs"]}
        self.log.write("recording", **self.last_recording)
        self._say(f"recording saved ({rec['seconds']} s, peak {rec['peak_dbfs']} dBFS): {rec['path']}")

    def request_talk(self, on: Any, rate: Any) -> None:
        if on is True:
            r = int(_num(rate, 8000, 48000, 48000))
            if self._audio_dog() is None:
                return
            self.talk_rate = r
            self._talk_t0 = time.monotonic()
            self.log.write("talk", action="start", rate=r, volume=self.volume)
            if self.volume == 0:
                self._say("talking, but the dog's volume is 0", "warn")
        elif self.talk_rate is not None:
            self.talk_rate = None
            self.log.write("talk", action="stop", seconds=round(time.monotonic() - self._talk_t0, 1))

    def handle_binary(self, ws, data: bytes) -> None:
        """Hold-to-talk audio from the controller tab: mono s16 at talk_rate."""
        if ws is not self.controller_ws or self.talk_rate is None or len(data) > TALK_MAX_CHUNK:
            return
        dog = self.dog
        if dog is None:
            return
        try:
            dog.play_pcm(data, self.talk_rate, 1, max_lag_s=TALK_MAX_LAG_S)
        except AdapterError as e:
            self.talk_rate = None
            self._say(f"talk failed: {e}", "error")

    def set_listen(self, ws, on: Any) -> None:
        if on is True:
            if ws not in self.listeners:
                self.listeners.add(ws)
                self.log.write("listen", action="start", listeners=len(self.listeners))
            if self._listen_task is None or self._listen_task.done():
                self._listen_task = self._spawn(self._listen_pump())
        elif ws in self.listeners:
            self.listeners.discard(ws)
            self.log.write("listen", action="stop", listeners=len(self.listeners))

    async def _listen_pump(self) -> None:
        """While anyone listens: one mic subscription on the CURRENT adapter (follows re-arms),
        forwarded to the listening tabs as binary mono s16 at LISTEN_RATE."""
        dog = q = None
        try:
            while self.listeners and not self.closing:
                cur = self.dog
                if cur is not dog or (cur is not None and not getattr(cur, "_connected", False)):
                    if q is not None:
                        dog.mic_unsubscribe(q)
                    dog, q = cur, None
                if q is None and dog is not None and getattr(dog, "_connected", False):
                    try:
                        q = dog.mic_subscribe(LISTEN_RATE, max_chunks=50)
                    except AdapterError as e:
                        self._say(f"listen: {e}", "warn")
                        await asyncio.sleep(1.0)
                        continue
                if q is None:
                    await asyncio.sleep(0.2)
                    continue
                try:
                    chunk = await asyncio.wait_for(q.get(), 0.25)
                except asyncio.TimeoutError:
                    continue
                while not q.empty() and len(chunk) < 3200:   # batch to ~100 ms per message
                    chunk += q.get_nowait()
                for ws in list(self.listeners):
                    if ws.closed:
                        self.listeners.discard(ws)
                    else:
                        self._spawn(self._send_bytes(ws, chunk))
        finally:
            if q is not None and dog is not None:
                dog.mic_unsubscribe(q)

    @staticmethod
    async def _send_bytes(ws, data: bytes) -> None:
        try:
            await ws.send_bytes(data)
        except Exception:
            pass

    def audio_status(self) -> dict:
        dog = self.dog
        sp = dog.speaker_status() if dog is not None and hasattr(dog, "speaker_status") else {}
        mic = dog.mic_status() if dog is not None and hasattr(dog, "mic_status") else {}
        rb = dog.volume_readback() if dog is not None and hasattr(dog, "volume_readback") else None
        return {"volume": rb if rb is not None else self.volume, "volume_readback": rb,
                "volume_set": self.volume,
                "mic_on": mic.get("on"), "mic_dbfs": mic.get("level_dbfs"),
                "mic_frames": mic.get("frames"), "mic_age_s": mic.get("last_frame_age_s"),
                "mic_format": mic.get("format"),
                "spk_dbfs": sp.get("level_dbfs"), "playing": sp.get("playing"),
                "queued_s": sp.get("queued_s"), "spk_sent_s": sp.get("audio_sent_s"),
                "spk_direction": sp.get("direction"),
                "talking": self.talk_rate is not None, "recording": self.recording,
                "listeners": len(self.listeners), "last_recording": self.last_recording}

    async def _meter_loop(self) -> None:
        while not self.closing:
            if self.clients:
                try:
                    m = {"t": "meter", **self.audio_status()}
                    for ws in list(self.clients):
                        self._spawn(self._send(ws, {**m, "listening": ws in self.listeners}))
                except Exception as e:
                    print(f"[joystick] meter error: {type(e).__name__}: {e}", flush=True)
            await asyncio.sleep(METER_PERIOD_S)

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
        self._end_follow(f"controller lost ({reason})")
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
                return AVOID_REFUSED
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
            self._end_follow(f"safety trip: {trip.get('reason')}", stop=False)   # the trip lies it down
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
            try:                            # must never skip the dead-man / stop logic below
                self._check_safety_events(self.dog)
            except Exception as e:
                err = f"safety event check error: {type(e).__name__}: {e}"
                if err != self._safety_check_err:
                    self._safety_check_err = err
                    print(f"[joystick] {err}", flush=True)
        if self._follow_on:
            try:                            # its command lands in self.target: same path as the sticks
                self._follow_step(now)
            except Exception as e:          # never let following skip the stop logic below
                err = f"follow error: {type(e).__name__}: {e}"
                if err != self._follow_err:
                    self._follow_err = err
                    print(f"[joystick] {err}", flush=True)
                self._end_follow(err)
        v = self.target
        nonzero = any(v)
        fresh = now - self.target_t <= self.deadman_s
        dog = self.dog
        try:
            active = (nonzero and fresh and self.controller_ws is not None and self._drive_block() is None)
        except Exception as e:              # a broken check means "not active": fall through to the stop
            active = False
            err = f"drive block check error: {type(e).__name__}: {e}"
            if err != self._safety_check_err:
                self._safety_check_err = err
                print(f"[joystick] {err}", flush=True)
        if active:
            idle = self._drive_task is None or self._drive_task.done()
            if idle and now - self.last_move_t >= MOVE_MIN_INTERVAL_S:
                if self._measure_task is not None and not self._measure_task.done():
                    self._measure_task.cancel()          # a new command interrupts the stop measurement
                self.moving = True
                self.last_move_t = now
                v = self._apply_brake(v, now)
                if self.drive_mode == "sticks":
                    self._sticks_seen = True
                self._drive_task = self._spawn(self._drive_once(dog, v, self.drive_mode))
        elif self.moving:
            if nonzero and not fresh:
                self.deadman_count += 1
                self.log.write("deadman", silence_s=round(now - self.target_t, 3))
                self._say(f"dead-man: no stick input for {now - self.target_t:.2f} s, StopMove", "warn")
                self._end_follow("dead-man", stop=False)
                self._stop("deadman")
                self.target = (0.0, 0.0, 0.0)
            else:
                self._stop("follow_hold" if self._follow_on else "release")
        if not active and self._braking:
            self._set_braking(False, None, "drive stopped")

    # ------------------------------------------------------------ LiDAR forward brake

    def _brake_nearest(self, now: float) -> tuple[bool, float | None]:
        """(fresh, nearest_ahead_m) from the latest LiDAR view. Not fresh = received more than
        BRAKE_FRESH_S ago, scan itself older than BRAKE_FRESH_S (age_s), stale, or no usable
        scan/pose (the view says why)."""
        v = self._brake_view
        age = v.get("age_s") if isinstance(v, dict) else None
        if (not isinstance(v, dict) or now - self._brake_view_t > BRAKE_FRESH_S
                or v.get("stale") is not False or v.get("reason") is not None
                or isinstance(age, bool) or not isinstance(age, (int, float)) or not age <= BRAKE_FRESH_S):
            return False, None
        near = v.get("nearest_ahead_m")
        if isinstance(near, bool) or not isinstance(near, (int, float)) or not math.isfinite(near):
            near = None
        return True, near

    def _apply_brake(self, v: tuple[float, float, float], now: float) -> tuple[float, float, float]:
        """Forward component -> 0 near an obstacle (fresh LiDAR only; fails open)."""
        vx, vy, vyaw = v
        why = None
        fresh, near = self._brake_nearest(now)
        if self.lidar_brake_enabled and fresh:
            vx, why = brake_forward(vx, near)
        self._set_braking(why is not None, near, why)
        return (vx, vy, vyaw)

    def _set_braking(self, on: bool, near: float | None, why: str | None) -> None:
        """Log and announce only the transitions (no per-tick spam)."""
        if on:
            self._brake_near = near
        if on == self._braking:
            return
        self._braking = on
        if on:
            self.log.write("lidar_brake", action="engaged", nearest_ahead_m=near, reason=why,
                           drive_mode=self.drive_mode)
            self._say(f"LiDAR brake: {why}; forward stopped (turn, sideways, back still work)", "warn")
        else:
            self.log.write("lidar_brake", action="released", nearest_ahead_m=near, reason=why)
            self._say("LiDAR brake released")

    def _brake_status(self, now: float) -> str:
        if not self.lidar_brake_enabled:
            return "off"
        fresh, _ = self._brake_nearest(now)
        if not fresh:
            return BRAKE_INACTIVE
        if self._braking and self._brake_near is not None:
            return f"braking ({self._brake_near:.2f} m ahead)"
        return "ready"

    @staticmethod
    def _to_sticks(v: tuple[float, float, float]) -> tuple[float, float, float]:
        """Commanded velocity -> remote-controller sticks (lx, ly, rx). Fraction of the joystick
        cap per axis times STICK_MAX. ly + = forward, lx + = strafe right (our vy + = left, so
        lx = -vy fraction), rx + = turn RIGHT (our vyaw + = left, so rx = -vyaw fraction).
        The rx sign was measured on the real dog 2026-11-04 19:30 (rx + made the yaw decrease);
        the vendor example's "rx + = turn left" is wrong. lx/ly signs: vendor example, not measured."""
        vx, vy, vyaw = v
        return (-vy / JOY_MAX_VY * STICK_MAX + 0.0, vx / JOY_MAX_VX * STICK_MAX + 0.0,
                -vyaw / JOY_MAX_VYAW * STICK_MAX + 0.0)

    async def _drive_once(self, dog, v, mode: str = "move") -> None:
        try:
            if mode == "sticks":
                await dog.send_sticks(*self._to_sticks(v))
            else:
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

    # ------------------------------------------------------------ follow a virtual signal point (demo)
    # The follower only sees an RSSI number. Its (vx, 0, vyaw) is written into self.target and goes
    # out through _tick exactly like the page sticks: LiDAR brake, drive mode, joystick caps, RealDog
    # checks (lock, standing, avoidance, envelope). Start once; STOP (or any automatic stop) ends it.

    def _pose(self):
        fn = self._lidar_fn("lidar_pose")
        if fn is None:
            return None
        try:
            return fn()
        except Exception:
            return None

    @staticmethod
    def _xy3(pose) -> list | None:
        return [round(float(pose[0]), 3), round(float(pose[1]), 3), round(float(pose[2]), 3)] if pose else None

    def request_beacon_place(self, x: Any, y: Any) -> None:
        def coord(v):
            try:
                f = float(v)
            except (TypeError, ValueError, OverflowError):
                return None
            return f if math.isfinite(f) and abs(f) <= BEACON_MAX_M and not isinstance(v, bool) else None
        fx, fy = coord(x), coord(y)
        why = "invalid position" if fx is None or fy is None else self._beacon_fence_problem((fx, fy))
        if why is not None:
            self._follow_refused = (f"signal point not placed: {why}", time.monotonic())
            self.log.write("beacon_place", action="refused", reason=why, x=str(x)[:20], y=str(y)[:20])
            return self._say(f"signal point not placed: {why}", "warn")
        self._follow_refused = None
        if self.beacon is None:
            self.beacon = VirtualBeacon((fx, fy), self._pose, rng=self.beacon_rng, noise_db=self.beacon_noise_db)
            action = "placed"
        else:
            self.beacon.move_to((fx, fy))
            action = "moved"
        self.log.write("beacon_place", action=action, x=round(fx, 3), y=round(fy, 3), pose=self._xy3(self._pose()),
                       following=self._follow_on, noise_db=self.beacon.noise_db)
        self._say(f"simulated signal point {action} at ({fx:.2f}, {fy:.2f}) m (odom)")

    def _beacon_fence_problem(self, xy) -> str | None:
        """The point must be inside the fence with BEACON_FENCE_MARGIN_M to spare (home + radius from
        the dog's safety_status). Unknown home = refused."""
        sf = self._safety_of(self.dog) if self.dog is not None else None
        home = (sf or {}).get("home")
        r = (sf or {}).get("radius_m")
        if home is None or not isinstance(r, (int, float)) or isinstance(r, bool):
            return "home position unknown (fence centre): wait for odometry or press Set home here"
        limit = r - BEACON_FENCE_MARGIN_M
        d = math.hypot(float(xy[0]) - float(home[0]), float(xy[1]) - float(home[1]))
        if d > limit:
            return (f"point is {d:.2f} m from home, outside the fence margin (max {max(limit, 0):.1f} m = fence "
                    f"{r:g} m - {BEACON_FENCE_MARGIN_M:g} m): place it closer to home")
        return None

    def request_beacon_clear(self) -> None:
        if self.beacon is None:
            return
        self._end_follow("signal point cleared")
        self.beacon = None
        self.log.write("beacon_clear")
        self._say("simulated signal point cleared")

    def request_follow_stop(self, why: Any = None) -> None:
        reason = FOLLOW_STOP_REASONS.get(why if isinstance(why, str) else "button", FOLLOW_STOP_REASONS["button"])
        self._end_follow(reason)

    def request_follow_start(self, ws=None) -> None:
        self._spawn(self._do_follow_start(ws))

    def _follow_refusal(self, st: DogStatus | None = None, ws=None) -> str | None:
        dog = self.dog
        if self._follow_on:
            return "already following"
        if ws is not None and self.controller_ws is not ws:
            return "control moved to another tab"
        if self.beacon is None:
            return "no signal point: press Place signal point, then click the LiDAR panel"
        fence = self._beacon_fence_problem(self.beacon.point_xy)
        if fence:
            return f"signal point: {fence}"
        if dog is None or not getattr(dog, "_connected", False):
            return "dog not connected"
        if self.controller_ws is None:
            return "no controller tab"
        if (self.moving or any(self.target)
                or (self._drive_task is not None and not self._drive_task.done())):
            return "release the sticks first (must be stationary)"
        if not self.envelope_enabled or getattr(dog, "safety_envelope_enabled", True) is False:
            return "safety thresholds are off: turn them on first (the fence stays on while following)"
        if not self.lidar_brake_enabled:
            return "LiDAR brake is off: turn it on first"
        if not self._brake_nearest(time.monotonic())[0]:
            return f"LiDAR brake {BRAKE_INACTIVE}: following needs live LiDAR"
        if self._pose() is None:
            return "position unknown (no fresh odometry)"
        block = self._drive_block(st)
        if block:
            return block
        if st is not None and st.stationary is not True:
            return f"dog not stationary ({st})"
        return None

    async def _do_follow_start(self, ws=None) -> None:
        why = self._follow_refusal(ws=ws)
        if why is None:
            st = await self.dog.get_status()
            why = self._follow_refusal(st, ws)  # re-check after the await: still the controller, standing, ...
        if why is not None:
            self._follow_refused = (f"follow refused: {why}", time.monotonic())
            self.log.write("follow_start", action="refused", reason=why, drive_mode=self.drive_mode)
            return self._say(f"follow refused: {why}", "warn")
        self._follow_refused = None
        now = time.monotonic()
        self.follower.run_limit_s = self.follow_limit_s
        self.follower.start(now)
        self._follow_on, self._follow_dog = True, self.dog
        self._follow_t, self._follow_sample_t, self._follow_alive_t = 0.0, now, now
        self._follow_cmd, self._follow_rssi, self._follow_wanted_fwd = None, None, False
        self.log.write("follow_start", beacon_xy=list(self.beacon.point_xy), pose=self._xy3(self._pose()),
                       drive_mode=self.drive_mode, lidar_brake=self.lidar_brake_enabled, limit_s=self.follow_limit_s,
                       noise_db=self.beacon.noise_db)
        msg = f"following the simulated signal (max {self.follow_limit_s:g} s; STOP or Stop following ends it)"
        if self.drive_mode == "move":
            msg += f". Drive mode Move: {MOVE_MODE_WARN}"
        self._say(msg, "warn")

    def _end_follow(self, reason: str, *, stop: bool = True, keep_target: bool = False) -> bool:
        """End a run. stop=True: the existing StopMove path (zero sticks first in sticks mode), dog
        stays standing. stop=False when the caller's own stop follows (STOP/rest, trip, take control)."""
        if not self._follow_on:
            return False
        now = time.monotonic()
        before = self.follower.state
        self.follower.stop(reason, now)
        self._follow_on, self._follow_dog = False, None
        if not keep_target:
            self.target = (0.0, 0.0, 0.0)
            self.refused = None             # the follower's "sticks" are released
            if self._drive_task is not None and not self._drive_task.done():
                self._drive_task.cancel()
            if stop:
                self._stop("follow_stop", {"reason": reason})
        self.log.write("follow_stop", reason=self.follower.reason, state_before=before,
                       elapsed_s=round(self.follower.elapsed(now), 1), pose=self._xy3(self._pose()),
                       rssi_s=None if self.follower.rssi_smoothed is None else round(self.follower.rssi_smoothed, 1),
                       drive_mode=self.drive_mode)
        self._say(f"following ended: {self.follower.reason}"
                  + (" (dog stays standing)" if stop and not keep_target else ""), "warn")
        return True

    def _follow_step(self, now: float) -> None:
        dog = self.dog
        if dog is None or dog is not self._follow_dog or not getattr(dog, "_connected", False):
            return self._end_follow("dog disconnected or re-armed")
        if self.controller_ws is None:
            return self._end_follow("controller lost")
        if now - self._follow_alive_t > FOLLOW_DEADMAN_S:
            # The sticks' 300 ms dead-man can't see a frozen page while following (no stick messages),
            # so the page sends follow_alive every 250 ms; silence ends the run like the dead-man.
            self.deadman_count += 1
            self.log.write("deadman", silence_s=round(now - self._follow_alive_t, 3), following=True)
            return self._end_follow(f"dead-man: no message from the page for {now - self._follow_alive_t:.1f} s")
        block = self._drive_block()
        if block:
            return self._end_follow(f"blocked: {block}")
        if not self.lidar_brake_enabled:
            return self._end_follow("LiDAR brake turned off")
        if getattr(dog, "safety_envelope_enabled", True) is False:
            return self._end_follow("safety thresholds turned off")
        if self.beacon is None:
            return self._end_follow("no signal point")
        fresh, near = self._brake_nearest(now)
        if not fresh:
            return self._end_follow(f"LiDAR brake {BRAKE_INACTIVE}")
        if now - self._follow_t < FOLLOW_TICK_S:
            return
        self._follow_t = now
        pose = self._pose()
        rssi = self.beacon.read()
        prev, prev_side = self.follower.state, self.follower.dodge_side
        v = self._brake_view
        clear = v.get("clear") if isinstance(v, dict) else None   # fresh (checked above), same view as the brake
        cmd = self.follower.tick(now, pose, rssi, near, self._braking, clear=clear)
        if self.follower.dodge_side != prev_side:
            side = self.follower.dodge_side
            self.log.write("follow_dodge", action="end" if side is None else "start",
                           side=None if side is None else ("left" if side > 0 else "right"),
                           reason=cmd.reason, pose=self._xy3(pose), nearest_ahead_m=near,
                           near_m=clear.get("near_m") if isinstance(clear, dict) else None)
        self._follow_cmd, self._follow_rssi = cmd, rssi
        if cmd.state == "stopped":          # the follower's own stop: the time limit
            self.follower.state = prev      # so _end_follow logs the state it ended from
            return self._end_follow(cmd.reason or "stopped")
        if cmd.state != prev:
            self.log.write("follow_state", old=prev, new=cmd.state, reason=cmd.reason, pose=self._xy3(pose),
                           rssi_s=None if cmd.rssi_smoothed is None else round(cmd.rssi_smoothed, 1))
        if cmd.state == "arrived":
            if prev != "arrived":           # once on entry: the existing StopMove path, dog stays standing
                self.target = (0.0, 0.0, 0.0)
                if self._drive_task is not None and not self._drive_task.done():
                    self._drive_task.cancel()
                self._stop("follow_arrived", {"rssi_s": round(cmd.rssi_smoothed, 1)})
                self._say(f"arrived: signal {cmd.rssi_smoothed:.1f} dBm; holding (StopMove, standing). "
                          f"Resumes below {RESUME_DBM:g} dBm")
            self.target_t = now
            return
        if prev == "arrived":
            self._say(f"signal dropped: following again ({cmd.reason})")
        vx = _num(cmd.vx, 0.0, JOY_MAX_VX)  # never backward, never sideways; joystick caps
        vyaw = _num(cmd.vyaw, -JOY_MAX_VYAW, JOY_MAX_VYAW)
        if vx > 0:
            self._follow_wanted_fwd = True
        self.target = (vx, 0.0, vyaw)
        self.target_t = now
        self.last_cmd_t = now
        if now - self._follow_sample_t >= FOLLOW_SAMPLE_S:
            self._follow_sample_t = now
            self.log.write("follow_sample", pose=self._xy3(pose),
                           rssi=None if rssi is None else round(rssi, 1),
                           rssi_s=None if cmd.rssi_smoothed is None else round(cmd.rssi_smoothed, 1),
                           state=cmd.state, reason=cmd.reason, cmd=[round(vx, 3), round(vyaw, 3)],
                           est_dir_rad=None if cmd.est_dir_rad is None else round(cmd.est_dir_rad, 3),
                           nearest_ahead_m=near, braking=self._braking, drive_mode=self.drive_mode,
                           dodge=None if self.follower.dodge_side is None else
                           ("left" if self.follower.dodge_side > 0 else "right"),
                           near_m=clear.get("near_m") if isinstance(clear, dict) else None,
                           turn_room=clear.get("turn_room") if isinstance(clear, dict) else None,
                           bad_turn_room=self.follower.bad_turn_room)

    def _follow_status(self, now: float) -> dict:
        f, cmd, on = self.follower, self._follow_cmd, self._follow_on
        rssi = self._follow_rssi if on else None
        if not on and self.beacon is not None:
            try:
                rssi = self.beacon.read()   # live reading for the page while idle
            except Exception:
                rssi = None
        rs = f.rssi_smoothed if (on or f.state == "stopped") else None
        return {
            "state": f.state, "reason": f.reason if f.state == "stopped" else (cmd.reason if on and cmd else None),
            "rssi": None if rssi is None else round(rssi, 1),
            "rssi_smoothed": None if rs is None else round(rs, 1),
            "est_dir_rad": None if not (on and cmd and cmd.est_dir_rad is not None) else round(cmd.est_dir_rad, 3),
            "elapsed_s": round(f.elapsed(now), 1), "limit_s": f.run_limit_s if on else self.follow_limit_s,
            "beacon_xy": None if self.beacon is None else [round(c, 3) for c in self.beacon.point_xy],
            "drive_mode": self.drive_mode, "cmd": [round(v, 3) for v in (self.target[0], self.target[2])] if on else None,
            "arrive_dbm": ARRIVE_DBM, "resume_dbm": RESUME_DBM,
            "warning": MOVE_MODE_WARN if self.drive_mode == "move" else None,
            "last_refusal": ({"reason": self._follow_refused[0], "age_s": round(now - self._follow_refused[1], 1)}
                             if self._follow_refused and now - self._follow_refused[1] <= REFUSAL_SHOW_S else None),
            "point_area": self._point_area(),
        }

    def _point_area(self) -> dict | None:
        """Where a signal point may go (page draws it while placing): home + max distance."""
        sf = self._safety_of(self.dog) if self.dog is not None else None
        home, r = (sf or {}).get("home"), (sf or {}).get("radius_m")
        if home is None or not isinstance(r, (int, float)) or isinstance(r, bool):
            return None
        return {"home": [round(float(home[0]), 3), round(float(home[1]), 3)],
                "max_m": round(max(0.0, r - BEACON_FENCE_MARGIN_M), 2)}

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
            "brightness": self.brightness, "audio": self.audio_status(), "last_stop": self.last_stop, "last_photo": self.last_photo,
            "deadman_count": self.deadman_count,
            "frame_age_s": round(now - frame_t, 2) if frame_t else None,
            "controller_present": self.controller_ws is not None, "caps": self.caps,
            "safety": self._safety_of(dog) if dog is not None else None,
            "safety_enabled": (bool(getattr(dog, "safety_envelope_enabled"))
                               if dog is not None and hasattr(dog, "safety_envelope_enabled") else None),
            "home": self.home, "last_check": self.last_check,
            "auto_connect": self._reachable is not None and bool(self.auto_connect_s),
            "lidar": self._lidar_status(),
            "drive_mode": self.drive_mode,
            "lidar_brake": self._brake_status(now), "lidar_brake_enabled": self.lidar_brake_enabled,
            "pose": self._xy3(self._pose()), "follow": self._follow_status(now),
        }

    # ------------------------------------------------------------ LiDAR (view-only data, never motion)

    def _lidar_fn(self, name: str):
        """The dog's LiDAR method `name`, or None (no dog, missing, or not callable)."""
        fn = getattr(self.dog, name, None)
        return fn if callable(fn) else None

    def _lidar_status(self) -> dict | None:
        fn = self._lidar_fn("lidar_status")
        if fn is None:
            return None
        try:
            return fn()
        except Exception:
            return None

    async def _lidar_loop(self) -> None:
        """Push the top-down LiDAR view to every tab at <= 5 Hz. The view is built in a worker
        thread; nothing here touches the STOP path, and any error just skips the frame.
        A tab whose previous lidar frame is still being sent is skipped (a slow Wi-Fi link
        must not pile up frames or delay status/events behind them)."""
        while not self.closing:
            try:
                fn = self._lidar_fn("lidar_view") if self.clients else None
                st = self._lidar_status() if fn is not None else None
                if fn is not None and not (isinstance(st, dict) and st.get("enabled") is False):
                    view = await asyncio.to_thread(fn)
                    if isinstance(view, dict):
                        if "pose" not in view:      # page: odom<->body conversion (signal point clicks)
                            view = {**view, "pose": self._xy3(self._pose())}
                        self._brake_view, self._brake_view_t = view, time.monotonic()   # LiDAR brake input
                        text = json.dumps({**view, "t": "lidar"})      # once per frame, not once per tab
                        for ws in list(self.clients):
                            if ws not in self._lidar_inflight:
                                self._lidar_inflight.add(ws)
                                self._spawn(self._send_lidar(ws, text))
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                if err != self._lidar_err:
                    self._lidar_err = err
                    print(f"[joystick] lidar error: {err}", flush=True)
            await asyncio.sleep(LIDAR_PERIOD_S)

    async def _send_lidar(self, ws, text: str) -> None:
        try:
            await self._send(ws, text)
        finally:
            self._lidar_inflight.discard(ws)

    def request_lidar_on(self, source: str = "browser") -> None:
        """Controller asked to switch the dog's LiDAR on. Never automatic; not a motion command."""
        self._spawn(self._do_lidar_on(source))

    async def _do_lidar_on(self, source: str) -> None:
        dog = self.dog
        fn = self._lidar_fn("lidar_switch_on")
        if dog is None or not getattr(dog, "_connected", False) or fn is None:
            return self._say("LiDAR switch refused: dog not connected or LiDAR not supported", "warn")
        try:
            standing = (await dog.get_status()).standing
        except Exception:
            standing = None
        if standing is not True:            # lying down the LiDAR does not stream; never switch then
            self.log.write("lidar_switch", source=source, ok=False, error="not standing", standing=standing)
            return self._say(f"LiDAR switch refused: {LIDAR_LYING_MSG}", "warn")
        try:
            res = await fn()
        except Exception as e:
            self.log.write("lidar_switch", source=source, ok=False, error=f"{type(e).__name__}: {e}")
            return self._say(f"LiDAR switch failed: {e}", "error")
        self.log.write("lidar_switch", source=source, ok=True, **(res if isinstance(res, dict) else {}))
        self._say("LiDAR switch: sent 'on' to the dog (staff asked for it); data should start in a few seconds")

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
        if t == "listen":                      # passive, like the video: any tab
            self.set_listen(ws, msg.get("on"))
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
            if self._follow_on:
                if not any(_num(msg.get(k), -1, 1) for k in ("x", "y", "yaw")):
                    return                      # a zero (release) must not override the follower
                self._end_follow("manual takeover", stop=False, keep_target=True)   # the page drives now
            self.set_target(msg.get("x"), msg.get("y"), msg.get("yaw"), msg.get("speed"))
        elif t == "beacon_place":
            self.request_beacon_place(msg.get("x"), msg.get("y"))
        elif t == "beacon_clear":
            self.request_beacon_clear()
        elif t == "follow_start":
            self.request_follow_start(ws)
        elif t == "follow_stop":
            self.request_follow_stop(msg.get("reason"))
        elif t == "follow_alive":
            self._follow_alive_t = time.monotonic()
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
        elif t == "volume":
            self.request_volume(msg.get("level"))
        elif t == "say":
            self.request_say(msg.get("text"), msg.get("lang"))
        elif t == "chime":
            self.request_chime()
        elif t == "audio_stop":
            self.request_audio_stop()
        elif t == "record":
            self.request_record(msg.get("seconds"))
        elif t == "talk":
            self.request_talk(msg.get("on"), msg.get("rate"))
        elif t == "check":
            self.request_check(msg.get("step"), msg.get("volume"))
        elif t == "lidar_on":
            self.request_lidar_on("browser")
        elif t == "drive_mode":
            self.request_drive_mode(msg.get("mode"))
        elif t == "lidar_brake":
            self.request_lidar_brake(msg.get("enabled"))
        elif t == "shutdown":
            self.request_exit("browser:shutdown")


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
                             "default_speed": DEFAULT_SPEED, "deadman_s": ctl.deadman_s, "zones": ZONES,
                             "no_lidar_warn_s": NO_LIDAR_WARN_S, "drive_mode": ctl.drive_mode,
                             "lidar_brake_enabled": ctl.lidar_brake_enabled})
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except ValueError:
                        continue
                    ctl.handle(ws, data)
                elif msg.type == WSMsgType.BINARY:
                    ctl.handle_binary(ws, msg.data)
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            ctl.clients.discard(ws)
            ctl.listeners.discard(ws)
            ctl.log.write("client", action="ws_close", role="control" if ws is ctl.controller_ws else "view")
            if ws is ctl.controller_ws:
                ctl.controller_ws = None
                ctl.talk_rate = None
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

def _tcp_probe(host: str, port: int = SIGNALING_PORT, timeout: float = 1.0) -> Callable[[], Awaitable[bool]]:
    """True when the dog's signaling port accepts a TCP connection (cable in, dog on)."""
    async def probe() -> bool:
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        except (OSError, asyncio.TimeoutError):
            return False
        w.close()
        try:
            await w.wait_closed()
        except OSError:
            pass
        return True
    return probe


def _make_factory(args) -> tuple[Callable[[], Any], Path]:
    from patrol.dog.real import RealDog

    if args.fake:
        from patrol.dog.sim_conn import SimConn

        sim = SimConn()                        # one simulated body, reused across re-arms
        out = Path(args.out or "evidence/dog/fake")
        cfg = {"connection_mode": "LocalSTA", "interface": "simulated", "command_timeout_s": 1.0}
        if getattr(args, "no_lidar", False):
            cfg["lidar_enabled"] = False
        return (lambda: RealDog(config=cfg, output_dir=out, _conn_factory=lambda ip: sim)), out
    config = json.loads(Path(args.config).read_text())
    if getattr(args, "no_lidar", False):
        config = {**config, "lidar_enabled": False}
    out = Path(args.out or "evidence/dog")
    return (lambda: RealDog(config=config, output_dir=out)), out


async def _amain(args) -> int:
    factory, out = _make_factory(args)
    probe = None
    if not args.fake and not args.no_auto_connect:
        host = json.loads(Path(args.config).read_text()).get("interface")
        if host:
            probe = _tcp_probe(host)
    ctl = Controller(factory, log_path=out / "joystick.jsonl", fake=args.fake, out_dir=out,
                     auto_connect_s=AUTO_CONNECT_S if probe else None, reachable=probe)
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
    exit_source = ["terminal:Ctrl+C"]

    def on_exit(source: str) -> None:       # Shut down button on the page
        exit_source[0] = source
        stop.set()
    ctl.on_exit = on_exit
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
        url = f"http://127.0.0.1:{args.port}/"
        print(f"Go2 joystick: {mode}\n  open  {url}" + ("" if args.open else "   (not opened automatically)") + "\n"
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
        print(f"  Drive mode: Move. LiDAR brake ON ({BRAKE_DISTANCE_M:g} m, needs fresh LiDAR).", flush=True)
        if probe is not None:
            print(f"  Auto-connect ON: until the dog first answers, checks port {SIGNALING_PORT} every "
                  f"{AUTO_CONNECT_S:.0f} s and connects (no motion on connect).", flush=True)
        if getattr(args, "no_lidar", False):
            print("  LiDAR OFF (--no-lidar): the LiDAR stream is not subscribed.", flush=True)
        print("  The staff controller is always the primary stop.", flush=True)
        if args.open:
            import webbrowser
            webbrowser.open(url)
        await stop.wait()
        why = "Shut down button" if exit_source[0] == "browser:shutdown" else "Ctrl+C"
        print(f"\n*** {why}: lying down softly, then exit ***", flush=True)
        ctl.request_rest(exit_source[0])
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
    ap.add_argument("--open", action="store_true", help="open the page in the default browser once the server is up")
    ap.add_argument("--no-auto-connect", action="store_true",
                    help="real dog: don't connect automatically when the dog becomes reachable")
    ap.add_argument("--no-lidar", action="store_true",
                    help="don't subscribe to the LiDAR stream at all (config lidar_enabled: false); "
                         "compare stop latency with/without it")
    args = ap.parse_args(argv)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    sys.exit(main())
