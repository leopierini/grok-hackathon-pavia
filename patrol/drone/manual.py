"""Fully manual flight controller for the Tello: the fallback when the autonomous flow misbehaves.

    .venv/bin/python -m patrol.drone.manual            # real drone
    .venv/bin/python -m patrol.drone.manual --fake     # simulated drone, no radio

Then open http://127.0.0.1:8766 yourself. Nothing opens automatically.

It owns the Tello link (local UDP 9000), so `patrol.drone.live` must be stopped first.
Starting it never moves the drone: it only says `command`, asks the battery and turns the
camera on. Takeoff is a deliberate action in the page. Land is always one click or key away
and is never gated by a confirmation, a lock or a state check.

The logic lives in `Controller`, which holds no socket and no thread until `start()`.
Tests drive `tick()` with a fake clock and a fake SDK.
"""

from __future__ import annotations

import argparse
import errno
import json
import math
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

from patrol.drone.recon import parse_height_cm

HOST = "127.0.0.1"
PORT = 8766
PAGE = Path(__file__).with_name("manual.html")

# Sticks: the page sends axes in -1..1; the server scales them by the speed setting.
DEFAULT_SPEED = 30
MIN_SPEED = 10
MAX_SPEED = 70
RC_LIMIT = 100  # the Tello's own range

# Timing.
RC_PERIOD_S = 0.05  # at most 20 rc packets per second, whatever the page sends
WATCHDOG_S = 0.3  # no stick update for this long: sticks go to zero
KEEPALIVE_S = 2.0  # idle hover: rc 0 0 0 0 at least this often (the Tello lands itself at ~15 s)
ZERO_BURST = 4  # after the sticks are released, repeat the zero so one lost packet cannot matter
STICK_LOCKOUT_S = 1.0  # sticks ignored right after takeoff completes
TELEMETRY_STALE_S = 1.5
FRAME_STALE_S = 2.0

# Battery.
LOW_BATTERY = 20  # warn
MIN_TAKEOFF_BATTERY = 10  # refuse takeoff below this

# Emergency needs two deliberate steps: arm, then confirm between the min gap and the window.
EMERGENCY_WINDOW_S = 4.0
EMERGENCY_MIN_GAP_S = 0.3

ADOPT_HEIGHT_CM = 30  # telemetry says it is already flying: take over as airborne
ADOPT_HOLDOFF_S = 5.0  # after a land or emergency, old telemetry must not read as flying

GROUNDED, TAKING_OFF, AIRBORNE, LANDING = "grounded", "taking_off", "airborne", "landing"

BIND_HELP = (
    "Cannot open the Tello link: local UDP port 9000 is already in use ({reason}).\n"
    "Another process owns the drone: stop `patrol.drone.live` (or another "
    "`patrol.drone.manual`) first, then start this again."
)


class LinkBusy(RuntimeError):
    """Local UDP port 9000 is taken, so another process owns the Tello."""


def open_sdk(factory):
    """Build the SDK; turn a bind failure into one clear message."""
    try:
        return factory()
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE or "in use" in str(exc).lower():
            raise LinkBusy(BIND_HELP.format(reason=exc)) from exc
        raise


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clean_axis(value) -> float:
    """One stick axis from the page: a finite number in -1..1, anything else is 0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return clamp(value, -1.0, 1.0)


def map_sticks(axes, speed: float) -> tuple[int, int, int, int]:
    """Axes (left/right, forward/back, up/down, yaw) in -1..1 to rc integers.

    Scaled by the speed setting, which is itself capped at MAX_SPEED, then clamped to the
    Tello's -100..100.
    """
    speed = clamp(float(speed), 0, MAX_SPEED)
    out = []
    for axis in tuple(axes)[:4]:
        value = int(round(clean_axis(axis) * speed))
        out.append(int(clamp(value, -RC_LIMIT, RC_LIMIT)))
    while len(out) < 4:
        out.append(0)
    return tuple(out)  # type: ignore[return-value]


ZERO = (0, 0, 0, 0)


class Controller:
    def __init__(
        self,
        sdk=None,
        grabber_factory=None,
        clock=time.monotonic,
        spawn=None,
    ) -> None:
        self.sdk = sdk
        self._grabber_factory = grabber_factory
        self._clock = clock
        self._spawn = spawn or self._spawn_thread
        self.lock = threading.RLock()  # state; never held across a blocking query
        self.cmd_lock = threading.Lock()  # one reply-bearing command at a time
        self.link = "down"  # down | connecting | up
        self.state = GROUNDED
        self.speed = DEFAULT_SPEED
        self.axes = (0.0, 0.0, 0.0, 0.0)
        self.stick_at = -1e9
        self.last_rc = ZERO
        self.last_rc_at = -1e9
        self.zero_burst = 0
        self.airborne_since = -1e9
        self.adopt_block_until = -1e9
        self.watchdog_tripped = False
        self.stick_sid: str | None = None
        self.stick_seq = -1
        self.armed_at = -1e9
        self.armed_until = -1e9
        self.landing_inflight = False
        self.battery: int | None = None
        self.battery_at = -1e9
        self.last_command = ""
        self.last_reply = ""
        self.errors: deque[tuple[float, str]] = deque(maxlen=8)
        self.events: deque[str] = deque(maxlen=40)
        self.grabber = None
        self.video = "off"  # off | starting | ok | down
        self.video_error = ""
        self._jpeg: tuple[float, bytes] | None = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._connecting = False

    # ---- plumbing -------------------------------------------------------------------

    @staticmethod
    def _spawn_thread(fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def note(self, text: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {text}"
        self.events.append(line)
        print(line, flush=True)

    def error(self, text: str) -> None:
        with self.lock:
            self.errors.append((self._clock(), text))
        self.note(f"ERROR {text}")

    def start(self) -> None:
        """Run the rc sender and the connection loop on daemon threads."""
        for target in (self._send_loop, self._connect_loop):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

    def shutdown(self) -> None:
        """Server exiting. A controller that is gone cannot fly the drone: bring it down."""
        self._stop.set()
        sdk = self.sdk
        if sdk is not None and self.state != GROUNDED:
            self.note("shutting down while the drone may be in the air: sending land")
            try:
                sdk.send("land")
            except Exception as exc:
                self.note(f"land on exit failed: {exc}")
        if self.grabber is not None:
            try:
                self.grabber.close()
            except Exception:
                pass

    def _send(self, command: str) -> None:
        """Raw send, no reply wanted (rc, emergency, an urgent land)."""
        assert self.sdk is not None
        self.sdk.send(command)
        self.last_command = command

    def _query(self, command: str, timeout: float = 5) -> str:
        """Reply-bearing command. The caller holds cmd_lock."""
        assert self.sdk is not None
        self.last_command = command
        reply = self.sdk.query(command, timeout=timeout)
        self.last_reply = f"{command} -> {reply}"
        self.note(self.last_reply)
        return reply

    # ---- connection -----------------------------------------------------------------

    def _connect_loop(self) -> None:
        while not self._stop.is_set():
            if self.link != "up":
                self.connect()
            self._stop.wait(3.0)

    def connect(self) -> bool:
        """Put the drone in SDK mode, read the battery, start the camera. Never moves it."""
        if self.sdk is None:
            self.error("no SDK: the Tello link is not open")
            return False
        if not self.cmd_lock.acquire(timeout=3):
            return False
        try:
            with self.lock:
                if self._connecting:
                    return False
                self._connecting = True
                self.link = "connecting"
            try:
                reply = self._query("command", timeout=3)
                if reply != "ok":
                    raise RuntimeError(f"command -> {reply}")
                try:
                    battery = int(self._query("battery?", timeout=3))
                    with self.lock:
                        self.battery, self.battery_at = battery, self._clock()
                except (ValueError, OSError) as exc:
                    self.error(f"battery? failed: {exc}")
                with self.lock:
                    self.link = "up"
                    self.last_rc_at = -1e9
                self.note("link up")
            except Exception as exc:
                with self.lock:
                    self.link = "down"
                self.error(f"no link: {exc} (is this laptop on the Tello wifi?)")
                return False
            finally:
                with self.lock:
                    self._connecting = False
        finally:
            self.cmd_lock.release()
        self.start_video()
        return True

    def reconnect(self) -> dict:
        with self.lock:
            self.link = "down"
        self._spawn(self.connect)
        return {"ok": True}

    # ---- video ----------------------------------------------------------------------

    def start_video(self) -> dict:
        """Camera on, decoder started. Runs apart from control: failure only marks video down."""
        if self._grabber_factory is None:
            self.video, self.video_error = "down", "video disabled"
            return {"ok": False, "error": self.video_error}
        with self.lock:
            if self.video == "starting":
                return {"ok": True}
            self.video = "starting"
        self._spawn(self._video_worker)
        return {"ok": True}

    def _video_worker(self) -> None:
        try:
            old, self.grabber = self.grabber, None
            if old is not None:
                old.close()
            if not self.cmd_lock.acquire(timeout=3):
                raise RuntimeError("drone busy, try Restart video")
            try:
                reply = self._query("streamon", timeout=3)
            finally:
                self.cmd_lock.release()
            if reply != "ok":
                raise RuntimeError(f"streamon -> {reply}")
            grabber = self._grabber_factory()
            grabber.log = self.note
            grabber.start()
            self.grabber = grabber
            with self.lock:
                self.video, self.video_error = "ok", ""
        except Exception as exc:
            with self.lock:
                self.video, self.video_error = "down", str(exc)
            self.note(f"video down: {exc} (flying still works)")

    def video_state(self, now: float | None = None) -> str:
        now = self._clock() if now is None else now
        if self.video == "ok":
            grabber = self.grabber
            if grabber is None:
                return "down"
            try:
                _image, at = grabber.latest()
            except Exception:
                return "down"
            if _image is None or now - at > FRAME_STALE_S:
                return "waiting"
        return self.video

    def frame_jpeg(self) -> bytes | None:
        """Newest frame as JPEG, or None when there is no fresh one. Never blocks control."""
        grabber = self.grabber
        if grabber is None:
            return None
        try:
            image, at = grabber.latest()
        except Exception:
            return None
        if image is None or self._clock() - at > FRAME_STALE_S:
            return None
        cached = self._jpeg
        if cached is not None and cached[0] == at:
            return cached[1]
        small = image.convert("RGB").resize((640, 480))
        buffer = BytesIO()
        small.save(buffer, "JPEG", quality=65)
        data = buffer.getvalue()
        self._jpeg = (at, data)
        return data

    # ---- telemetry ------------------------------------------------------------------

    def telemetry(self, now: float | None = None) -> tuple[dict, float | None]:
        """Latest telemetry fields and its age in seconds (None when none was ever heard)."""
        now = self._clock() if now is None else now
        if self.sdk is None:
            return {}, None
        try:
            snap = self.sdk.snapshot()
        except Exception:
            return {}, None
        at = snap.get("at")
        if at is None:
            return snap, None
        return snap, max(0.0, now - at)

    def _refresh(self, now: float) -> None:
        """Take over a drone that is already flying (we were started mid-flight)."""
        if self.state != GROUNDED or self.link != "up" or now < self.adopt_block_until:
            return
        snap, age = self.telemetry(now)
        if age is None or age > TELEMETRY_STALE_S:
            return
        if snap.get("h", 0) >= ADOPT_HEIGHT_CM:
            self._set_airborne(now, adopted=True)

    def _set_airborne(self, now: float, adopted: bool = False) -> None:
        self.state = AIRBORNE
        self.last_rc = ZERO
        self.last_rc_at = -1e9  # first keep-alive goes out at once
        self.zero_burst = 0
        self.airborne_since = -1e9 if adopted else now
        self.note("drone is flying: taking over" if adopted else "airborne")

    def battery_now(self, now: float | None = None) -> int | None:
        """Newest battery: fresh telemetry, else the last reading."""
        now = self._clock() if now is None else now
        snap, age = self.telemetry(now)
        if age is not None and age <= TELEMETRY_STALE_S and "bat" in snap:
            self.battery, self.battery_at = int(snap["bat"]), now
        return self.battery

    # ---- sticks ---------------------------------------------------------------------

    def set_sticks(self, lr, fb, ud, yaw, sid: str | None = None, seq=None, now=None) -> dict:
        """Last writer wins. Out-of-order packets from the same page are dropped."""
        now = self._clock() if now is None else now
        with self.lock:
            if sid is not None and isinstance(seq, int) and not isinstance(seq, bool):
                if sid == self.stick_sid and seq <= self.stick_seq:
                    return {"ok": True, "stale": True}
                self.stick_sid, self.stick_seq = sid, seq
            if self.state != AIRBORNE or now - self.airborne_since < STICK_LOCKOUT_S:
                self.axes = (0.0, 0.0, 0.0, 0.0)
                self.stick_at = now
                return {"ok": True, "ignored": True}
            self.axes = tuple(clean_axis(v) for v in (lr, fb, ud, yaw))
            self.stick_at = now
            self.watchdog_tripped = False
            return {"ok": True, "rc": list(map_sticks(self.axes, self.speed))}

    def hover(self) -> dict:
        with self.lock:
            self.axes = (0.0, 0.0, 0.0, 0.0)
            self.stick_at = self._clock()
        return {"ok": True}

    def set_speed(self, value) -> dict:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return {"ok": False, "error": "speed must be a number"}
        if not math.isfinite(number):
            return {"ok": False, "error": "speed must be a number"}
        with self.lock:
            self.speed = int(clamp(round(number), MIN_SPEED, MAX_SPEED))
            return {"ok": True, "speed": self.speed}

    def _current_rc(self, now: float) -> tuple[int, int, int, int]:
        if now - self.stick_at > WATCHDOG_S:
            if any(self.axes):
                self.watchdog_tripped = True
                self.note("deadman: no stick update, sticks zeroed")
            self.axes = (0.0, 0.0, 0.0, 0.0)
        return map_sticks(self.axes, self.speed)

    # ---- the sender -----------------------------------------------------------------

    def _send_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                self.error(f"send loop: {exc}")
            self._stop.wait(0.02)

    def tick(self, now: float | None = None) -> str | None:
        """One sender step. Returns the rc command sent, or None.

        Sends only while airborne and no takeoff or land is pending. Active sticks go out
        at most every RC_PERIOD_S; a release sends zero at once, repeated ZERO_BURST times;
        an idle hover sends `rc 0 0 0 0` every KEEPALIVE_S.
        """
        now = self._clock() if now is None else now
        with self.lock:
            self._refresh(now)
            if self.sdk is None or self.state != AIRBORNE:
                return None  # grounded, or a takeoff/land is pending: never fight it
            rc = self._current_rc(now)
            since = now - self.last_rc_at
            if rc != ZERO:
                due = since >= RC_PERIOD_S
                self.zero_burst = ZERO_BURST
            elif self.last_rc != ZERO:
                due = True  # released: stop at once
                self.zero_burst = ZERO_BURST - 1
            elif self.zero_burst > 0:
                due = since >= RC_PERIOD_S
                if due:
                    self.zero_burst -= 1
            else:
                due = since >= KEEPALIVE_S
            if not due:
                return None
            command = "rc {} {} {} {}".format(*rc)
            try:
                self._send(command)
            except Exception as exc:
                self.errors.append((now, f"rc send failed: {exc}"))
                return None
            self.last_rc, self.last_rc_at = rc, now
            return command

    # ---- takeoff / land / emergency --------------------------------------------------

    def takeoff(self) -> dict:
        now = self._clock()
        with self.lock:
            if self.sdk is None or self.link != "up":
                return {"ok": False, "error": "no drone link"}
            if self.state != GROUNDED:
                return {"ok": False, "error": f"cannot take off while {self.state}"}
            battery = self.battery_now(now)
            if battery is None:
                return {"ok": False, "error": "battery unknown: refusing to take off"}
            if battery < MIN_TAKEOFF_BATTERY:
                return {"ok": False, "error": f"battery {battery}% is below {MIN_TAKEOFF_BATTERY}%"}
            snap, age = self.telemetry(now)
            if age is not None and age <= TELEMETRY_STALE_S and snap.get("h", 0) >= ADOPT_HEIGHT_CM:
                return {"ok": False, "error": "telemetry says it is already in the air"}
            self.state = TAKING_OFF
            self.axes = (0.0, 0.0, 0.0, 0.0)
        self.note("takeoff")
        self._spawn(self._takeoff_worker)
        return {"ok": True}

    def _takeoff_worker(self) -> None:
        if not self.cmd_lock.acquire(timeout=3):
            with self.lock:
                if self.state == TAKING_OFF:
                    self.state = GROUNDED
            self.error("drone busy: takeoff not sent, try again")
            return
        reply = None
        failure = ""
        try:
            reply = self._query("takeoff", timeout=20)
        except Exception as exc:
            failure = str(exc)
        finally:
            self.cmd_lock.release()
        now = self._clock()
        with self.lock:
            land_first = self.state == LANDING  # Land was pressed while this was pending
            if land_first:
                return  # the land flow owns the state now
            if reply == "ok":
                self._set_airborne(now)
            elif failure:
                # No answer: it may be flying. Assume so, so keep-alive and Land keep working.
                self.error(f"takeoff reply missing ({failure}); assuming airborne: land if it is not")
                self._set_airborne(now, adopted=True)
            else:
                self.state = GROUNDED
                self.error(f"takeoff refused: {reply}")

    def land(self) -> dict:
        """Always allowed. Zeroes the sticks and sends land at once, even mid-takeoff."""
        now = self._clock()
        with self.lock:
            self.axes = (0.0, 0.0, 0.0, 0.0)
            self.stick_at = now
            self.armed_until = -1e9
            if self.sdk is None:
                return {"ok": False, "error": "no drone link: land on the Tello's own app or power it off"}
            inflight = self.landing_inflight
            self.landing_inflight = True
            self.state = LANDING
        self.note("LAND")
        got = False if inflight else self.cmd_lock.acquire(blocking=False)
        if not got:
            # A takeoff, a status query or an earlier land holds the reply channel.
            # Do not wait behind it: send land raw now, the worker confirms after.
            try:
                self._send("land")
            except Exception as exc:
                self.error(f"land send failed: {exc}")
        if inflight:
            return {"ok": True, "note": "land already in progress; sent again"}
        self._spawn(lambda: self._land_worker(got))
        return {"ok": True}

    def _land_worker(self, have_lock: bool) -> None:
        if not have_lock:
            have_lock = self.cmd_lock.acquire(timeout=30)
        grounded = False
        problem = ""
        try:
            for attempt in range(2):
                try:
                    reply = self._query("land", timeout=15) if have_lock else None
                except Exception as exc:
                    problem = f"land: {exc}"
                    continue
                if reply is not None and reply.startswith("ok"):
                    grounded = True
                    break
                problem = f"land -> {reply}"
                break
            if not grounded and have_lock:
                try:
                    if parse_height_cm(self._query("height?", timeout=3)) == 0:
                        grounded = True
                except Exception as exc:
                    problem = f"{problem}; height? {exc}"
        finally:
            if have_lock:
                self.cmd_lock.release()
        now = self._clock()
        with self.lock:
            self.landing_inflight = False
            if grounded:
                self.state = GROUNDED
                self.adopt_block_until = now + ADOPT_HOLDOFF_S
                self.axes = (0.0, 0.0, 0.0, 0.0)
                self.last_rc = ZERO
                self.note("landed")
            else:
                # Not confirmed down: back to airborne so keep-alive resumes and Land can retry.
                self._set_airborne(now, adopted=True)
        if not grounded:
            self.error(f"land not confirmed ({problem}); press Land again")

    def emergency_arm(self) -> dict:
        now = self._clock()
        with self.lock:
            self.armed_at = now
            self.armed_until = now + EMERGENCY_WINDOW_S
        self.note("emergency ARMED")
        return {"ok": True, "armed_for": EMERGENCY_WINDOW_S}

    def emergency(self) -> dict:
        """Cut the motors. Only after emergency_arm, and not as part of the same click."""
        now = self._clock()
        with self.lock:
            if now > self.armed_until:
                return {"ok": False, "error": "emergency not armed (or it timed out): arm it first"}
            if now - self.armed_at < EMERGENCY_MIN_GAP_S:
                return {"ok": False, "error": "confirm after arming, not in the same click"}
            if self.sdk is None:
                return {"ok": False, "error": "no drone link"}
            self.armed_until = -1e9
            self.axes = (0.0, 0.0, 0.0, 0.0)
            self.state = GROUNDED
            self.adopt_block_until = now + ADOPT_HOLDOFF_S
            self.last_rc = ZERO
        self.note("EMERGENCY: motors cut")
        try:
            self._send("emergency")
            self._send("emergency")  # one lost datagram must not leave the motors running
        except Exception as exc:
            self.error(f"emergency send failed: {exc}")
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    # ---- page -----------------------------------------------------------------------

    def status(self, now: float | None = None) -> dict:
        now = self._clock() if now is None else now
        snap, age = self.telemetry(now)
        battery = self.battery_now(now)
        with self.lock:
            rc = map_sticks(self.axes, self.speed) if now - self.stick_at <= WATCHDOG_S else ZERO
            link_ok = self.link == "up" and age is not None and age <= TELEMETRY_STALE_S
            return {
                "state": self.state,
                "link": self.link,
                "telemetry_age": None if age is None else round(age, 2),
                "link_ok": link_ok,
                "battery": battery,
                "battery_low": battery is not None and battery < LOW_BATTERY,
                "battery_min": MIN_TAKEOFF_BATTERY,
                "h": snap.get("h"),
                "tof": snap.get("tof"),
                "yaw": snap.get("yaw"),
                "speed": self.speed,
                "rc": list(rc),
                "last_command": self.last_command,
                "last_reply": self.last_reply,
                "errors": [text for _at, text in self.errors][-4:],
                "events": list(self.events)[-12:],
                "video": self.video_state(now),
                "video_error": self.video_error,
                "emergency_armed": now <= self.armed_until,
                "deadman": self.watchdog_tripped,
            }

    def command(self, body: dict) -> dict:
        action = body.get("action")
        if action == "land":
            return self.land()
        if action == "takeoff":
            return self.takeoff()
        if action == "hover":
            return self.hover()
        if action == "speed":
            return self.set_speed(body.get("value"))
        if action == "emergency_arm":
            return self.emergency_arm()
        if action == "emergency":
            return self.emergency()
        if action == "reconnect":
            return self.reconnect()
        if action == "video_restart":
            return self.start_video()
        return {"ok": False, "error": f"unknown action {action!r}"}


# ---- simulated drone for --fake ------------------------------------------------------


class FakeSDK:
    """Stands in for TelloSDK. Records what would have been sent. Opens no socket."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.height = 0
        self.battery = 87
        self.yaw = 0
        self._at = time.monotonic()

    def send(self, command: str) -> None:
        self.sent.append(command)
        if command.startswith("rc "):
            parts = [int(v) for v in command.split()[1:5]]
            self.height = max(0, self.height + parts[2] // 10)
            self.yaw = (self.yaw + parts[3] // 10 + 180) % 360 - 180
            if parts != [0, 0, 0, 0]:
                print(f"[fake drone] {command}", flush=True)
        elif command == "land":
            self.height = 0
            print("[fake drone] land", flush=True)
        elif command == "emergency":
            self.height = 0
            print("[fake drone] EMERGENCY motors cut", flush=True)

    def query(self, command: str, timeout: float = 5) -> str:
        self.sent.append(command)
        print(f"[fake drone] {command}", flush=True)
        if command == "battery?":
            return str(self.battery)
        if command == "height?":
            return f"{self.height // 10}dm"
        if command == "takeoff":
            time.sleep(1.0)
            self.height = 80
            return "ok"
        if command == "land":
            time.sleep(1.0)
            self.height = 0
            return "ok"
        return "ok"

    def snapshot(self) -> dict:
        return {
            "h": self.height,
            "tof": self.height,
            "bat": self.battery,
            "yaw": self.yaw,
            "at": time.monotonic(),
        }

    def close(self) -> None:
        return None


class FakeGrabber:
    """A moving test picture in place of the Tello camera."""

    def __init__(self) -> None:
        self.log = None
        self._started = time.monotonic()

    def start(self) -> None:
        return None

    def latest(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (640, 480), (40, 56, 72))
        draw = ImageDraw.Draw(image)
        x = int((time.monotonic() - self._started) * 60) % 600
        draw.rectangle((x, 200, x + 40, 240), fill=(230, 160, 60))
        draw.text((20, 20), "FAKE CAMERA (no drone)", fill=(255, 255, 255))
        return image, time.monotonic()

    def close(self) -> None:
        return None


# ---- http ----------------------------------------------------------------------------


def host_ok(header: str | None, port: int = PORT) -> bool:
    """Only the loopback name this server was opened on. Blocks DNS rebinding."""
    return (header or "") in (f"127.0.0.1:{port}", f"localhost:{port}")


class Handler(BaseHTTPRequestHandler):
    ctrl: Controller
    port: int = PORT

    def do_GET(self) -> None:
        if not host_ok(self.headers.get("Host"), self.port):
            self.send_error(403)
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._bytes(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/state.json":
            self._bytes(json.dumps(self.ctrl.status()).encode(), "application/json")
        elif path == "/frame.jpg":
            frame = self.ctrl.frame_jpeg()
            if frame is None:
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            else:
                self._bytes(frame, "image/jpeg")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        # JSON content type makes a cross-site form or fetch fail its CORS preflight,
        # so a random web page cannot fly the drone through the browser.
        if not host_ok(self.headers.get("Host"), self.port):
            self.send_error(403)
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if ctype != "application/json":
            self.send_error(415)
            return
        path = self.path.split("?", 1)[0]
        if path not in ("/sticks", "/cmd"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length > 2048:
            self.send_error(413)
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = None
        if not isinstance(body, dict):
            self._bytes(b'{"ok":false,"error":"bad json"}', "application/json")
            return
        if path == "/sticks":
            result = self.ctrl.set_sticks(
                body.get("lr"), body.get("fb"), body.get("ud"), body.get("yaw"),
                sid=body.get("sid") if isinstance(body.get("sid"), str) else None,
                seq=body.get("seq"),
            )
        else:
            result = self.ctrl.command(body)
        self._bytes(json.dumps(result).encode(), "application/json")

    def _bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual Tello flight controller")
    parser.add_argument("--fake", action="store_true", help="simulated drone, no radio, no UDP")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)

    if args.fake:
        sdk = FakeSDK()
        grabber_factory = FakeGrabber
        print("FAKE mode: nothing is sent to any drone")
    else:
        from patrol.drone.pilot import FrameGrabber
        from patrol.drone.tello_sdk import TELLO_IP, TelloSDK

        try:
            sdk = open_sdk(TelloSDK)
        except LinkBusy as exc:
            print(exc, file=sys.stderr)
            return 2
        grabber_factory = FrameGrabber
        print(f"Tello at {TELLO_IP}")

    ctrl = Controller(sdk, grabber_factory)
    Handler.ctrl = ctrl
    Handler.port = args.port
    try:
        server = ThreadingHTTPServer((HOST, args.port), Handler)
    except OSError as exc:
        print(f"Cannot serve on {HOST}:{args.port}: {exc} (another manual controller running?)", file=sys.stderr)
        sdk.close()
        return 2
    ctrl.start()
    print(f"open http://{HOST}:{args.port}   (starting never moves the drone; takeoff is in the page)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        ctrl.shutdown()
        server.server_close()
        try:
            sdk.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
