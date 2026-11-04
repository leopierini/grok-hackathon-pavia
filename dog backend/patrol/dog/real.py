"""RealDog: Unitree Go2 adapter over WebRTC (unitree_webrtc_connect), contract v1.0.

Safety design
- connect() never moves, stands or changes settings. It opens WebRTC, subscribes
  to state topics and turns on the session video stream. It also subscribes to the
  LiDAR voxel-map topic (native decoder) and sets the WebRTC transport flag
  "disable traffic saving", which lasts for this session only and is not a dog
  setting. connect() never publishes the LiDAR switch: only lidar_switch_on() does,
  on an explicit operator action (it only powers the sensor, never moves the dog).
  Config `lidar_enabled: false` skips all of it (no decoder switch, no flag, no topic).
- Every vendor request has a timeout. A timed-out motion command is never retried:
  the adapter sends StopMove, locks itself and reports the failure.
- halt() never waits behind a route: it latches a flag that the route loop checks
  every tick and immediately sends StopMove (high priority) itself.
- After halt() (or any motion fault) the adapter refuses new routes. Ground must
  recreate the adapter (plan §7.2: no adapter reset()).
- Unknown state is reported as None, never as a successful default.
- Movement uses the sport `Move` velocity command, re-sent at `move_rate_hz`.
  Velocities are clamped to hard caps below whatever the route file says.
- Joystick "sticks" mode instead publishes simulated remote-controller sticks on
  rt/wirelesscontroller (send_sticks, clamped to STICK_MAX), the path the dog's own obstacle
  avoidance filters. Runtime input only. Every stop path (halt, rest, stop_move) zeroes the
  sticks first (and again for ~0.2 s) once sticks were used on this adapter.
- Nothing here writes firmware, switches motion modes, or touches the system.
- Obstacle avoidance is read-only: prepare() never switches it on. Not confirmed on => motion refused.
- Audio (extras): the speaker streams PCM over the session's WebRTC audio track
  (nothing is uploaded or stored on the dog); the mic channel is switched on only
  while someone is subscribed (listen / record) and off again after. Volume is the
  dog's VUI setting (0..10, api 1004 read / 1003 set). Audio never affects motion.
- Safety envelope (on by default; config `safety_envelope_enabled`, or
  set_safety_envelope(), which refuses to turn it off while moving): every sport-state message is checked
  against a fence around "home", a sustained speed limit, a sustained tilt limit and
  (during routes) a travel-overshoot limit. A trip latches the motion lock and
  schedules ONE rest() (StopMove, then StandDown; never Damp). See _check_envelope.

Vendor imports happen lazily inside connect(), so importing this module is cheap.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from patrol.contract import (
    AdapterError,
    DogStatus,
    Frame,
    RouteResult,
    RunContext,
    Zone,
)
from patrol.dog import lidar as lidar_mod

ZONES = ("entrance", "room_2", "display")

# Hard caps, applied after the route file. Deliberately slow for a museum floor.
MAX_VX = 0.5      # m/s forward/back
MAX_VY = 0.3      # m/s sideways
MAX_VYAW = 0.8    # rad/s
MAX_SEGMENT_S = 10.0

POSTURE_TIMEOUT_S = 8.0      # StandUp / StandDown / BalanceStand reply when the motion is done
POSTURE_CMDS = {"StandUp", "StandDown", "BalanceStand"}
ODOM_JUMP_M = 0.5            # position change between two ~20 Hz readings that can't be real walking
STATE_STALE_S = 1.0          # sport state older than this => unknown
FRAME_MAX_AGE_S = 5.0        # plan §6.3
STANDING_MIN_HEIGHT_M = 0.25
STATIONARY_MAX_SPEED = 0.05  # m/s
STATIONARY_MAX_YAW = 0.10    # rad/s
STOP_VERIFY_S = 2.0
STANDDOWN_BUSY_CODE = 4201  # StandDown reply seen on the real dog (2026-11-04 16:24, 17:11, 17:13) while it
                            # DID lie down: treated as accepted/busy, confirmed via state, never re-sent

# Go2 sportmodestate.mode values that mean "on its feet" (0 idle/default stand,
# 1 balance stand, 2 pose, 3 locomotion). Everything else (lie down, damping,
# sit, recovery...) counts as not standing.
STANDING_MODES = {0, 1, 2, 3}
# Modes that confirm a StandDown arrived: 5 lie down, 7 damping (never sent by us, but the body
# is down). Real dog 2026-11-04 19:31-19:35: body_height did NOT drop below the standing minimum
# after StandDown (8 s, never confirmed) while the next connect read standing: false (= the mode).
LYING_MODES = {5, 7}

SPORT_API = {"StopMove": 1003, "StandUp": 1004, "BalanceStand": 1002, "Move": 1008,
             "StandDown": 1005}
# Never used: "Damp" (1001) = motors go limp and the dog drops. Emergency rest uses StandDown.
# Obstacle avoidance is READ-ONLY: only the get call (1002). We never send the set call (1001):
# if avoidance is not confirmed on, motion is refused and staff decide.
AVOID_API = {"SWITCH_GET": 1002}
AVOID_REFUSED = "avoidance not confirmed on — motion refused; ask staff"
VUI_API = {"SET_BRIGHTNESS": 1005, "GET_BRIGHTNESS": 1006,   # head light, 0..10
           "SET_VOLUME": 1003, "GET_VOLUME": 1004}           # speaker volume, 0..10

# Safety envelope defaults (config keys of the same name override them).
SAFETY_DEFAULTS = {
    "fence_radius_m": 3.0,                               # horizontal distance from home
    "max_speed_mps": 0.6,                                # measured horizontal speed
    "max_tilt_deg": 25.0,                                # abs(roll) or abs(pitch)
    "route_overshoot": {"factor": 1.3, "margin_m": 0.3},  # travel > planned * factor + margin
}
SPEED_SUSTAIN_S = 0.3        # over-speed must last this long (gait peaks are short)
TILT_SUSTAIN_S = 0.2
MOTION_RECENT_S = 1.0        # a Move sent within this window counts as "moving" for the fence
LIDAR_TRAFFIC_TIMEOUT_S = 3.0   # disableTrafficSaving reply (session-only transport flag)
LIDAR_RATE_WINDOW = 20          # arrival times kept for the rate estimate
LIDAR_RATE_STALE_S = 3.0        # no scan for this long => rate 0
LIDAR_LYING_MSG = "LiDAR streams only while the dog is standing — press Stand up"
ODOM_STEP_M = 0.02           # route travel is accumulated in steps >= this (filters odometry jitter)
# Remote-controller sticks (rt/wirelesscontroller, the path the dog's obstacle avoidance filters).
# Speed per stick unit depends on the dog's speed level (unknown): keep it small; the
# measured-speed trip (max_speed_mps) is the backstop.
STICK_MAX = 0.3
ZERO_STICKS_REPEATS = 4      # after the immediate zero: 4 more, ZERO_STICKS_GAP_S apart (~0.2 s)
ZERO_STICKS_GAP_S = 0.05


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cfg_number(name: str, v: Any, *, allow_zero: bool = False) -> float:
    """Positive finite number from config (bools and strings rejected) or AdapterError."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise AdapterError("invalid_input", f"config.{name} must be a number, got {v!r}")
    f = float(v)
    if not math.isfinite(f) or f < 0 or (f == 0 and not allow_zero):
        raise AdapterError("invalid_input", f"config.{name} must be a positive finite number, got {v!r}")
    return f


def _xy(p: Any) -> tuple[float, float] | None:
    """(x, y) from a position-like sequence, or None if missing/non-finite."""
    try:
        x, y = float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return (x, y)


def _parse_home(v: Any, where: str) -> tuple[float, float]:
    if isinstance(v, (str, bytes)) or isinstance(v, bool):
        raise AdapterError("invalid_input", f"{where} must be [x, y] in metres, got {v!r}")
    xy = _xy(v)
    if xy is None or any(isinstance(c, bool) for c in list(v)[:2]):
        raise AdapterError("invalid_input", f"{where} must be [x, y] in metres, got {v!r}")
    return xy


def av_errors() -> type[BaseException]:
    try:
        import av
        return av.error.FFmpegError
    except Exception:  # pragma: no cover
        return OSError


def subprocess_errors() -> type[BaseException]:
    import subprocess
    return subprocess.SubprocessError


def _clamp(v: float, cap: float) -> float:
    return max(-cap, min(cap, float(v)))


class RealDog:
    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        output_dir: Path,
        home: Any = None,
        _conn_factory: Callable[[str], Any] | None = None,
    ) -> None:
        if not isinstance(config, Mapping):
            raise AdapterError("invalid_input", "config must be a mapping")
        mode = config.get("connection_mode", "LocalSTA")
        if mode != "LocalSTA":
            raise AdapterError("unsupported", f"connection_mode {mode!r} not supported (use LocalSTA)")
        ip = config.get("interface")
        if not ip or not isinstance(ip, str):
            raise AdapterError("invalid_input", "config.interface must be the dog's IP address")
        self._ip = ip
        self._command_timeout_s = float(config.get("command_timeout_s", 3.0))
        self._connect_timeout_s = float(config.get("connect_timeout_s", 25.0))
        self._max_route_s = float(config.get("max_route_s", 30.0))
        self._move_rate_hz = float(config.get("move_rate_hz", 10.0))
        self._routes_path = config.get("routes_path")
        self._output_dir = Path(output_dir).resolve()
        self._conn_factory = _conn_factory

        self._conn: Any = None
        self._connected = False
        self._halted = asyncio.Event()     # latched; never cleared
        self._faulted: str | None = None   # reason routes are refused
        self._route_lock = asyncio.Lock()

        self._sport: dict | None = None
        self._sport_t = 0.0
        self._multi: dict | None = None
        self._multi_t = 0.0
        self._low: dict | None = None
        # ---- LiDAR (voxel map stream, world frame)
        self._lidar: lidar_mod.LidarScan | None = None
        self._lidar_msgs = 0
        self._lidar_bad = 0
        self._lidar_times: deque = deque(maxlen=LIDAR_RATE_WINDOW)
        self._lidar_error: str | None = None   # connect-time note ("warning: ..." = still subscribed)
        self._lidar_switch_sent = False
        lidar_enabled = config.get("lidar_enabled", True)
        if not isinstance(lidar_enabled, bool):
            raise AdapterError("invalid_input", f"config.lidar_enabled must be true/false, got {lidar_enabled!r}")
        self._lidar_enabled = lidar_enabled

        self._frame: Any = None            # numpy BGR image
        self._frame_t = 0.0                # monotonic receive time
        self._frame_utc: str | None = None
        self._video_task_running = False
        self._closed = False
        self._loop: asyncio.AbstractEventLoop | None = None

        # ---- audio (lazy: patrol.dog.audio is imported on first use)
        self._speaker: Any = None          # audio.SpeakerTrack once attached
        self._speaker_sender: Any = None
        self._speaker_transceiver: Any = None
        self._mic: Any = None              # audio.MicTap, created at connect
        self._mic_on = False
        self._mic_subs: set = set()
        self._pcm_conv: dict = {}          # (rate, channels) -> PcmConverter for play_pcm streams

        # ---- safety envelope (on by default)
        enabled = config.get("safety_envelope_enabled", True)
        if not isinstance(enabled, bool):
            raise AdapterError("invalid_input", f"config.safety_envelope_enabled must be true/false, got {enabled!r}")
        self._envelope_enabled = enabled
        self._fence_grace = False   # re-enabled while outside: no fence trip until back inside / set_home
        self._fence_r = _cfg_number("fence_radius_m", config.get("fence_radius_m", SAFETY_DEFAULTS["fence_radius_m"]))
        self._max_speed = _cfg_number("max_speed_mps", config.get("max_speed_mps", SAFETY_DEFAULTS["max_speed_mps"]))
        self._max_tilt = _cfg_number("max_tilt_deg", config.get("max_tilt_deg", SAFETY_DEFAULTS["max_tilt_deg"]))
        ro = config.get("route_overshoot", SAFETY_DEFAULTS["route_overshoot"])
        if not isinstance(ro, Mapping):
            raise AdapterError("invalid_input", f"config.route_overshoot must be an object, got {ro!r}")
        ro_d = SAFETY_DEFAULTS["route_overshoot"]
        self._ro_factor = _cfg_number("route_overshoot.factor", ro.get("factor", ro_d["factor"]))
        self._ro_margin = _cfg_number("route_overshoot.margin_m", ro.get("margin_m", ro_d["margin_m"]),
                                      allow_zero=True)
        self._home: tuple[float, float] | None = None
        self._home_source: str | None = None
        if home is not None:
            self._home, self._home_source = _parse_home(home, "home"), "constructor"
        elif config.get("home") is not None:
            self._home, self._home_source = _parse_home(config["home"], "config.home"), "config"
        self._home_changes: list[dict] = []
        self._trips: list[dict] = []          # first entry is the latched trip
        self._safety_rest_scheduled = False
        self._safety_rest_task: asyncio.Task | None = None
        self._speed_since: float | None = None
        self._tilt_since: float | None = None
        self._last_move_cmd_t = 0.0
        self._sticks_used = False          # a stick input was published on this adapter
        self._zero_task: asyncio.Task | None = None
        self._route_track: dict | None = None
        self._envelope_error: str | None = None

    # ------------------------------------------------------------------ public

    async def connect(self) -> DogStatus:
        if self._connected:
            return await self.get_status()
        self._loop = asyncio.get_running_loop()
        conn = self._make_conn()
        try:
            await asyncio.wait_for(conn.connect(), self._connect_timeout_s)
        except asyncio.TimeoutError as e:
            await self._discard_conn(conn)   # don't hold the dog's single WebRTC slot
            raise AdapterError("timeout", f"WebRTC connect to {self._ip} timed out") from e
        except Exception as e:  # vendor errors (busy, signaling, data channel)
            await self._discard_conn(conn)
            raise AdapterError("device_error", f"connect failed: {type(e).__name__}: {e}") from e
        self._conn = conn
        self._connected = True

        topics = self._topics()
        ps = conn.datachannel.pub_sub
        ps.subscribe(topics["LF_SPORT_MOD_STATE"], self._on_sport)
        ps.subscribe(topics["MULTIPLE_STATE"], self._on_multi)
        ps.subscribe(topics["LOW_STATE"], self._on_low)
        conn.video.add_track_callback(self._on_track)
        conn.video.switchVideoChannel(True)
        audio_ch = getattr(conn, "audio", None)
        if audio_ch is not None:            # mic frames arrive only after mic_subscribe()
            from patrol.dog import audio as _audio
            self._mic = _audio.MicTap()
            audio_ch.add_track_callback(self._on_audio_frame)
        await self._lidar_subscribe(conn, topics)

        # Wait briefly for the first fresh state so the status is meaningful.
        await self._wait_for(lambda: self._sport is not None and self._multi is not None
                             and self._low is not None, 4.0)
        return await self.get_status()

    async def prepare(self, ctx: RunContext) -> DogStatus:
        self._require_connected()
        self._require_motion_allowed()
        self._check_ctx(ctx)
        self._require_envelope_ok()            # unknown home/position is never safe either
        st = await self.get_status()
        if st.standing is not True:
            await self._sport_request("StandUp")
            await self._sleep_checked(2.0, ctx)
            await self._sport_request("BalanceStand")
            await self._sleep_checked(1.5, ctx)
        # Avoidance is read-only: never switched on here. If it is not confirmed on, the status
        # says so (avoidance_enabled None/False) and drive/send_sticks/routes refuse.
        st = await self.get_status()
        return st

    async def get_status(self) -> DogStatus:
        if not self._connected or not self._link_alive():
            return DogStatus(connected=False, standing=None, stationary=None, avoidance_enabled=None)
        now = time.monotonic()
        standing = stationary = None
        s = self._sport
        if s is not None and now - self._sport_t <= STATE_STALE_S:
            try:
                height = float(s["body_height"])
                standing = int(s["mode"]) in STANDING_MODES and height >= STANDING_MIN_HEIGHT_M
                vx, vy = float(s["velocity"][0]), float(s["velocity"][1])
                yaw = float(s["yaw_speed"])
                stationary = math.hypot(vx, vy) <= STATIONARY_MAX_SPEED and abs(yaw) <= STATIONARY_MAX_YAW
            except (KeyError, TypeError, ValueError, IndexError):
                standing = stationary = None
        avoidance = None
        m = self._multi
        if m is not None and now - self._multi_t <= 5.0:
            v = m.get("obstaclesAvoidSwitch")
            avoidance = v if isinstance(v, bool) else None
        return DogStatus(connected=True, standing=standing, stationary=stationary, avoidance_enabled=avoidance)

    async def run_route(self, zone: Zone, ctx: RunContext) -> RouteResult:
        self._require_connected()
        if zone not in ZONES:
            raise AdapterError("invalid_input", f"unknown zone {zone!r}")
        segments = self._load_route(zone)
        route_id = f"{zone}"
        async with self._route_lock:
            self._require_motion_allowed()
            st = await self.get_status()
            if st.standing is not True or st.stationary is not True or st.avoidance_enabled is not True:
                raise AdapterError("unsafe_state", f"refusing to walk with status {st}")
            self._require_envelope_ok()
            return await self._run_segments(segments, ctx, route_id)

    async def capture_frame(self, zone: Zone, ctx: RunContext) -> Frame:
        self._require_connected()
        if zone not in ZONES:
            raise AdapterError("invalid_input", f"unknown zone {zone!r}")
        requested = time.monotonic()
        limit = min(ctx.deadline_monotonic, requested + 3.0)
        while True:
            if ctx.cancel.is_set():
                raise AdapterError("cancelled", "capture cancelled")
            if self._frame is not None and self._frame_t > requested:
                break
            if time.monotonic() >= limit:
                raise AdapterError("timeout", "no fresh camera frame")
            await asyncio.sleep(0.03)
        img, t_recv, utc = self._frame, self._frame_t, self._frame_utc
        if time.monotonic() - t_recv > FRAME_MAX_AGE_S:
            raise AdapterError("device_error", "frame older than 5 s")
        import cv2  # lazy

        self._output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        final = self._output_dir / f"{ctx.mission_id}_dog_{zone}_{stamp}.jpg"
        tmp = final.with_name(f".tmp_{final.name}")   # keep .jpg so OpenCV picks the JPEG writer
        ok = await asyncio.to_thread(self._write_jpeg, cv2, str(tmp), img)
        if not ok:
            raise AdapterError("device_error", "JPEG encode failed")
        os.replace(tmp, final)
        return Frame(path=str(final), source="dog", zone=zone, captured_at=utc, simulated=False)

    async def halt(self) -> None:
        """Latch halt, stop accepting motion, send StopMove now (doesn't wait for the route)."""
        self._halted.set()
        if self._faulted is None:
            self._faulted = "halted"
        if not self._connected:
            return
        self._zero_sticks_first()
        # Send StopMove a few times without waiting on responses, then one awaited.
        for _ in range(3):
            self._sport_fire("StopMove", priority=True)
            await asyncio.sleep(0.05)
        try:
            await self._sport_request("StopMove", priority=True, lock_on_timeout=False)
        except AdapterError:
            pass  # already latched; StopMove was also fired without waiting

    async def rest(self) -> dict:
        """EMERGENCY REST: stop walking, then lie down slowly (StandDown, never Damp).

        Overrides everything: ignores the motion lock and the route lock, latches
        the lock afterwards. Safe to call repeatedly. Returns a small report.
        """
        self._halted.set()
        self._rest_started = True
        if not (self._faulted or "").startswith("safety:"):
            self._faulted = "emergency rest"   # a safety trip keeps its own reason
        report: dict = {"standdown_sent": False}
        if not self._connected:
            report["error"] = "not connected"
            return report
        t0 = time.monotonic()
        self._zero_sticks_first()
        for _ in range(3):
            self._sport_fire("StopMove", priority=True)
            await asyncio.sleep(0.05)
        still = await self._wait_for(lambda: self._is_stationary_now(), 1.0)
        report["stationary_before_standdown"] = still
        t_sd = time.monotonic()
        try:
            resp = await self._sport_request("StandDown", priority=True, lock_on_timeout=False,
                                             accept_codes=(STANDDOWN_BUSY_CODE,))
            if self._resp_code(resp) == STANDDOWN_BUSY_CODE:
                # Accepted/busy: no second StandDown. Confirm "lying down" from state within the
                # same posture wait; only if that fails is it reported as not arrived.
                report["standdown_code"] = STANDDOWN_BUSY_CODE
                wait_s = max(POSTURE_TIMEOUT_S, self._command_timeout_s)
                lying = await self._wait_for(self._is_lying_now,
                                             max(0.0, wait_s - (time.monotonic() - t_sd)))
                report["lying_confirmed"] = lying
                if lying:
                    report["standdown_sent"] = True
                else:
                    report["standdown_sent"] = f"code {STANDDOWN_BUSY_CODE}, lying down not confirmed"
                    report["error"] = (f"StandDown returned code {STANDDOWN_BUSY_CODE} and the state did not "
                                       f"show the dog lying down within {wait_s:g} s")
            else:
                report["standdown_sent"] = True
        except AdapterError as e:
            self._sport_fire("StandDown", priority=True)   # one unawaited fallback send
            report["standdown_sent"] = "fired (no reply)"
            report["error"] = str(e)
        report["posture_after"] = self._posture_raw()
        report["rest_call_s"] = round(time.monotonic() - t0, 3)
        return report

    async def close(self) -> None:
        if not self._connected:
            return
        t = self._safety_rest_task
        if t is not None and not t.done():     # never cut off a trip's soft lie-down
            try:
                await asyncio.wait_for(asyncio.shield(t), 6.0)
            except Exception:
                pass
        try:
            # Sticks first: a held stick that the dog's own avoidance blocks reads as stationary,
            # so the halt below would skip it. No-op unless sticks were used on this adapter.
            self._zero_sticks_first()
        except Exception:
            pass
        try:
            st = await self.get_status()
            if st.stationary is not True:
                await self.halt()
        except Exception:
            pass
        try:
            self._conn.video.switchVideoChannel(False)
        except Exception:
            pass
        self._audio_shutdown()
        try:
            await asyncio.wait_for(self._conn.disconnect(), 5.0)
        except Exception:
            pass
        self._closed = True
        self._connected = False
        self._conn = None

    # ------------------------------------------------- extras (not in contract)

    async def _lidar_subscribe(self, conn, topics: dict) -> None:
        """Receive the LiDAR stream. Never fatal, never publishes the sensor switch.
        Without the native decoder we do not subscribe at all: the vendor's default libvoxel
        decoder would decode every LiDAR message on the event loop (and we would reject them)."""
        if not self._lidar_enabled:
            return                       # config lidar_enabled: false -> no decoder, no traffic flag, no topic
        dc = conn.datachannel
        set_decoder = getattr(dc, "set_decoder", None)
        if not callable(set_decoder):
            self._lidar_error = ("LiDAR not subscribed: this vendor library has no set_decoder "
                                 "(the default decoder would load the event loop)")
            return
        try:
            set_decoder(decoder_type="native")
        except Exception as e:
            self._lidar_error = f"LiDAR not subscribed: set_decoder failed ({type(e).__name__}: {e})"
            return
        try:
            ok = await asyncio.wait_for(dc.disableTrafficSaving(True), LIDAR_TRAFFIC_TIMEOUT_S)
            if ok is False:
                self._lidar_error = "warning: disableTrafficSaving was refused by the dog"
        except asyncio.TimeoutError:
            self._lidar_error = f"warning: disableTrafficSaving: no reply in {LIDAR_TRAFFIC_TIMEOUT_S:g} s"
        except Exception as e:
            self._lidar_error = f"warning: disableTrafficSaving: {type(e).__name__}: {e}"
        try:
            dc.pub_sub.subscribe(topics["ULIDAR_ARRAY"], self._on_lidar)
        except Exception as e:
            self._lidar_error = f"LiDAR not subscribed: subscribe: {type(e).__name__}: {e}"

    @property
    def lidar_enabled(self) -> bool:
        return self._lidar_enabled

    def latest_lidar(self) -> "lidar_mod.LidarScan | None":
        return self._lidar

    def lidar_pose(self) -> "lidar_mod.Pose | None":
        """(x, y, yaw, ground_z) from fresh sport state, or None. ground_z None if height unknown."""
        s = self._sport
        if not self._sport_fresh() or not isinstance(s, Mapping):
            return None
        try:
            pos = s["position"]
            yaw = float(s["imu_state"]["rpy"][2])
            x, y = float(pos[0]), float(pos[1])
            if not all(math.isfinite(v) for v in (x, y, yaw)):
                return None
        except Exception:
            return None
        ground = None
        try:
            g = float(pos[2]) - float(s["body_height"])
            if math.isfinite(g):
                ground = g
        except Exception:
            pass
        return (x, y, yaw, ground)

    def lidar_view(self) -> dict:
        """The frame the joystick panel draws (body frame, centimetres). Safe off the loop thread."""
        return lidar_mod.build_view(self.latest_lidar(), self.lidar_pose(), time.monotonic())

    def lidar_status(self) -> dict:
        scan, now = self._lidar, time.monotonic()
        times = list(self._lidar_times)
        rate = None
        if len(times) >= 2 and times[-1] > times[0]:
            rate = 0.0 if now - times[-1] > LIDAR_RATE_STALE_S else round((len(times) - 1) / (times[-1] - times[0]), 2)
        error = self._lidar_error        # connect-time note; stream problems are derived (clear on a valid scan)
        if self._lidar_bad and self._lidar_msgs == 0:
            error = f"{self._lidar_bad} LiDAR message(s) arrived but could not be decoded"
        return {
            "enabled": self._lidar_enabled,
            "msgs": self._lidar_msgs,
            "bad": self._lidar_bad,
            "age_s": round(max(0.0, now - scan.t), 2) if scan is not None else None,
            "points": len(scan.points) if scan is not None else 0,
            "rate_hz": rate,
            "frame_id": scan.frame_id if scan is not None else None,
            "switch_sent": self._lidar_switch_sent,
            "error": error,
        }

    async def lidar_switch_on(self) -> dict:
        """Power the LiDAR sensor on (explicit operator action; connect() never does this).
        Not a motion command, so it is allowed while the motion lock is set. Only while the dog
        is standing (confirmed): lying down, the LiDAR does not stream anyway (real dog)."""
        if not self._lidar_enabled:
            raise AdapterError("unsupported", "LiDAR disabled by config (lidar_enabled: false)")
        self._require_connected()
        st = await self.get_status()
        if st.standing is not True:
            raise AdapterError("unsafe_state", f"{LIDAR_LYING_MSG} (standing: {st.standing})")
        ps = self._conn.datachannel.pub_sub
        if getattr(getattr(ps, "channel", None), "readyState", "open") != "open":
            raise AdapterError("not_connected", "data channel is not open")
        try:
            ps.publish_without_callback(self._topics()["ULIDAR_SWITCH"], "on")
        except Exception as e:
            raise AdapterError("device_error", f"LiDAR switch failed: {type(e).__name__}: {e}") from e
        self._lidar_switch_sent = True
        return {"utc": _utc_now_iso()}

    async def get_avoidance(self) -> bool | None:
        """Ask the obstacle-avoid service directly. None if unknown."""
        resp = await self._avoid_request("SWITCH_GET")
        try:
            data = resp["data"]["data"]
            return bool(json.loads(data).get("enable")) if data else None
        except Exception:
            return None

    async def get_motion_mode(self) -> str | None:
        """Read-only query of the motion switcher (e.g. 'normal', 'ai', 'mcf')."""
        resp = await self._request(self._topics()["MOTION_SWITCHER"], {"api_id": 1001}, lock_on_timeout=False)
        try:
            return json.loads(resp["data"]["data"]).get("name")
        except Exception:
            return None

    def raw_state(self) -> dict:
        return {"sport": self._sport, "multi": self._multi, "low": self._low,
                "sport_age_s": round(time.monotonic() - self._sport_t, 3) if self._sport else None}

    async def run_segments(self, segments: list[dict], ctx: RunContext, route_id: str = "manual") -> RouteResult:
        """Same control path as run_route, for supervised tests (HAC-3)."""
        self._require_connected()
        segs = [self._validate_segment(s) for s in segments]
        async with self._route_lock:
            self._require_motion_allowed()
            st = await self.get_status()
            if st.standing is not True or st.stationary is not True or st.avoidance_enabled is not True:
                raise AdapterError("unsafe_state", f"refusing to walk with status {st}")
            self._require_envelope_ok()
            return await self._run_segments(segs, ctx, route_id)

    async def send_single_move(self, vx: float) -> None:
        """Command-expiry probe: send ONE Move and nothing else. Caller must halt after."""
        self._require_connected()
        self._require_motion_allowed()
        self._require_envelope_ok()
        await self._sport_request("Move", {"x": _clamp(vx, 0.3), "y": 0.0, "z": 0.0})

    # ------------------------------------------------ joystick (patrol.dog.joystick)

    async def drive(self, vx: float, vy: float, vyaw: float) -> dict:
        """Send ONE sport Move (joystick). The caller re-sends while the stick is held
        and calls stop_move() on release.

        Clamped to the hard caps. Refused unless connected, motion allowed, no route
        running, standing is True and avoidance is True (unknown => refused).
        Any failure of the Move (timeout included) locks the adapter and fires
        StopMove; it is never retried.
        """
        self._require_connected()
        self._require_motion_allowed()
        vals = (vx, vy, vyaw)
        try:
            ok = all(math.isfinite(float(v)) for v in vals)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            raise AdapterError("invalid_input", f"non-finite velocity {vals!r}")
        if self._route_lock.locked():
            raise AdapterError("unsafe_state", "a route is running")
        st = await self.get_status()
        if st.standing is not True or st.avoidance_enabled is not True:
            raise AdapterError("unsafe_state", f"refusing to drive with status {st}")
        self._require_envelope_ok()         # inside the fence, position + home known
        params = {"x": _clamp(vx, MAX_VX), "y": _clamp(vy, MAX_VY), "z": _clamp(vyaw, MAX_VYAW)}
        self._require_motion_allowed()      # re-check right before sending
        try:
            await self._sport_request("Move", params)
        except AdapterError as e:
            self._faulted = self._faulted or f"drive error: {e.code}"
            self._sport_fire("StopMove", priority=True)
            raise
        return params

    async def stop_move(self) -> None:
        """Joystick release: one StopMove, the dog stays standing. Always allowed
        (even when locked) and does not latch the motion lock, unless StopMove gets
        no reply: then the adapter locks and fires one unawaited StopMove."""
        if not self._connected:
            return
        self._zero_sticks_first()
        try:
            await self._sport_request("StopMove", priority=True, lock_on_timeout=False)
        except AdapterError as e:
            self._faulted = self._faulted or f"StopMove failed: {e.code}"
            self._sport_fire("StopMove", priority=True)

    async def send_sticks(self, lx: float, ly: float, rx: float, ry: float = 0.0) -> dict:
        """Publish ONE simulated remote-controller stick input on rt/wirelesscontroller (the
        path the dog's own obstacle avoidance filters; vendor example obstacles_avoid.py).
        Runtime control only: no setting is changed. Same preconditions as drive(); each
        value clamped to +-STICK_MAX. lx + = strafe right, ly + = forward, rx + = turn RIGHT
        (rx measured on the real dog 2026-11-04; lx/ly from the vendor example, not measured). A non-zero send counts as a motion command for the fence.
        A failed publish locks the adapter, zeroes the sticks and fires StopMove."""
        self._require_connected()
        self._require_motion_allowed()
        vals = (lx, ly, rx, ry)
        try:
            ok = all(math.isfinite(float(v)) for v in vals)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            raise AdapterError("invalid_input", f"non-finite stick value {vals!r}")
        if self._route_lock.locked():
            raise AdapterError("unsafe_state", "a route is running")
        st = await self.get_status()
        if st.standing is not True or st.avoidance_enabled is not True:
            raise AdapterError("unsafe_state", f"refusing to drive with status {st}")
        self._require_envelope_ok()
        data = {"lx": _clamp(lx, STICK_MAX), "ly": _clamp(ly, STICK_MAX), "rx": _clamp(rx, STICK_MAX),
                "ry": _clamp(ry, STICK_MAX), "keys": 0}
        self._require_motion_allowed()      # re-check right before sending
        ps = self._conn.datachannel.pub_sub
        try:
            if getattr(getattr(ps, "channel", None), "readyState", "open") != "open":
                raise AdapterError("not_connected", "data channel is not open")
            if any(data[k] for k in ("lx", "ly", "rx", "ry")):
                self._sticks_used = True
                self._last_move_cmd_t = time.monotonic()
            ps.publish_without_callback(self._topics()["WIRELESS_CONTROLLER"], data)
        except AdapterError as e:
            self._stick_fault(e.code)
            raise
        except Exception as e:
            self._stick_fault("device_error")
            raise AdapterError("device_error", f"stick publish failed: {type(e).__name__}: {e}") from e
        return data

    def _stick_fault(self, code: str) -> None:
        self._faulted = self._faulted or f"drive error: {code}"
        self._zero_sticks_first()
        self._sport_fire("StopMove", priority=True)

    async def zero_sticks(self) -> dict:
        """Publish zero sticks now and a few more times over ~0.2 s. A stop: allowed even
        when motion is locked. Never raises. Returns {"sent", "dropped", "failed"} counts:
        "dropped" = data channel not open (the vendor would drop it silently)."""
        counts = {"sent": 0, "dropped": 0, "failed": 0}
        counts[self._publish_zero_sticks()] += 1
        await self._repeat_zero_sticks(counts)
        return counts

    def mark_sticks_used(self) -> None:
        """Sticks were used on an earlier adapter (or the joystick is in sticks mode): this
        adapter's stop paths zero the sticks too. Sends nothing."""
        self._sticks_used = True

    def _publish_zero_sticks(self) -> str:
        """One zero-stick publish: "sent", "dropped" (no connection / data channel not open)
        or "failed" (the publish raised). Never raises."""
        try:
            if self._conn is None:
                return "dropped"
            ps = self._conn.datachannel.pub_sub
            if getattr(getattr(ps, "channel", None), "readyState", "open") != "open":
                return "dropped"
            ps.publish_without_callback(
                self._topics()["WIRELESS_CONTROLLER"], {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "keys": 0})
            return "sent"
        except Exception:
            return "failed"

    async def _repeat_zero_sticks(self, counts: dict | None = None) -> None:
        for _ in range(ZERO_STICKS_REPEATS):
            await asyncio.sleep(ZERO_STICKS_GAP_S)
            r = self._publish_zero_sticks()
            if counts is not None:
                counts[r] += 1

    def _zero_sticks_first(self) -> None:
        """Stop paths: if sticks were used on this adapter, zero them right now (no await, so
        StopMove is not delayed) and repeat in the background for ~0.2 s. Never raises."""
        if not self._sticks_used:
            return
        self._publish_zero_sticks()
        try:
            if self._zero_task is None or self._zero_task.done():
                self._zero_task = asyncio.get_running_loop().create_task(self._repeat_zero_sticks())
        except Exception:
            pass

    def latch_lock(self, reason: str) -> None:
        """Latch the motion lock without sending anything (e.g. a STOP that happened on an
        earlier connection). Like every lock, only a new adapter (Re-arm) clears it."""
        self._halted.set()
        if self._faulted is None:
            self._faulted = reason

    def motion_lock(self) -> str | None:
        """Why motion is refused (None = allowed). Latched until the adapter is recreated."""
        if self._faulted:
            return self._faulted
        return "halted" if self._halted.is_set() else None

    def latest_frame(self) -> tuple[Any, float | None]:
        """(latest BGR frame, monotonic receive time), or (None, None)."""
        if self._frame is None:
            return None, None
        return self._frame, self._frame_t

    async def get_brightness(self) -> int | None:
        """Head light brightness 0..10 (VUI api 1006). None if unknown."""
        self._require_connected()
        resp = await self._request(self._topics()["VUI"], {"api_id": VUI_API["GET_BRIGHTNESS"]},
                                   lock_on_timeout=False)
        try:
            return int(json.loads(resp["data"]["data"])["brightness"])
        except Exception:
            return None

    async def set_brightness(self, level: float) -> int:
        """Set head light brightness (VUI api 1005), clamped to 0..10. Returns the level sent."""
        self._require_connected()
        try:
            lvl = float(level)
        except (TypeError, ValueError) as e:
            raise AdapterError("invalid_input", f"bad brightness {level!r}") from e
        if not math.isfinite(lvl):
            raise AdapterError("invalid_input", f"bad brightness {level!r}")
        lvl_i = int(max(0, min(10, round(lvl))))
        resp = await self._request(self._topics()["VUI"],
                                   {"api_id": VUI_API["SET_BRIGHTNESS"], "parameter": {"brightness": lvl_i}},
                                   lock_on_timeout=False)
        code = self._resp_code(resp)
        if code not in (0, None):
            raise AdapterError("device_error", f"set brightness returned code {code}")
        return lvl_i

    # ------------------------------------------------------------ audio (extras)

    async def get_volume(self) -> int | None:
        """Speaker volume 0..10 (VUI api 1004). None if unknown."""
        self._require_connected()
        resp = await self._request(self._topics()["VUI"], {"api_id": VUI_API["GET_VOLUME"]},
                                   lock_on_timeout=False)
        try:
            return int(json.loads(resp["data"]["data"])["volume"])
        except Exception:
            return None

    async def set_volume(self, level: float) -> int:
        """Set speaker volume (VUI api 1003), clamped to 0..10. Returns the level sent."""
        self._require_connected()
        try:
            lvl = float(level)
        except (TypeError, ValueError) as e:
            raise AdapterError("invalid_input", f"bad volume {level!r}") from e
        if not math.isfinite(lvl):
            raise AdapterError("invalid_input", f"bad volume {level!r}")
        lvl_i = int(max(0, min(10, round(lvl))))
        resp = await self._request(self._topics()["VUI"],
                                   {"api_id": VUI_API["SET_VOLUME"], "parameter": {"volume": lvl_i}},
                                   lock_on_timeout=False)
        code = self._resp_code(resp)
        if code not in (0, None):
            raise AdapterError("device_error", f"set volume returned code {code}")
        return lvl_i

    def volume_readback(self) -> int | None:
        """Volume as last reported by the dog's own state stream (multiplestate, ~1 Hz)."""
        v = (self._multi or {}).get("volume")
        if time.monotonic() - self._multi_t > 5.0:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def play_pcm(self, pcm: bytes, rate: int = 48000, channels: int = 1, *,
                 interrupt: bool = False, max_lag_s: float | None = None) -> float:
        """Queue s16 PCM on the dog's speaker (e.g. a Grok Voice / TTS stream, chunk by
        chunk). Returns seconds queued. `interrupt` drops what is still queued first.
        `max_lag_s` (live talk) keeps the queue at most that long by dropping old audio."""
        sp = self._ensure_speaker()
        from patrol.dog import audio as _audio
        key = (rate, channels)
        try:
            conv = self._pcm_conv.get(key)
            if conv is None:
                conv = self._pcm_conv[key] = _audio.PcmConverter(rate, channels)
            data = conv.convert(pcm)
        except (ValueError, TypeError) as e:
            raise AdapterError("invalid_input", f"bad PCM: {e}") from e
        if interrupt:
            sp.clear()
        try:
            return sp.enqueue(data, max_lag_s=max_lag_s)
        except OverflowError as e:
            raise AdapterError("invalid_input", str(e)) from e

    def play_chime(self, *, interrupt: bool = True) -> float:
        """Short two-tone test sound. Returns its length in seconds."""
        from patrol.dog import audio as _audio
        return self._queue_pcm48(_audio.chime_pcm(), interrupt)

    async def play_audio_file(self, path: str | os.PathLike, *, interrupt: bool = True) -> float:
        """Decode an audio file (wav/mp3/aiff/...) on a worker thread and play it.
        Returns its length in seconds. Does not wait for playback to finish."""
        self._ensure_speaker()
        from patrol.dog import audio as _audio
        try:
            pcm = await asyncio.to_thread(_audio.decode_file, path)
        except (OSError, ValueError, av_errors()) as e:
            raise AdapterError("invalid_input", f"cannot play {path}: {e}") from e
        return self._queue_pcm48(pcm, interrupt)

    async def say(self, text: str, voice: str = "Alice", *, interrupt: bool = True) -> float:
        """Offline TTS test with macOS `say` (voice "Alice" = Italian, "Samantha" = English).
        A stand-in for Grok TTS. Returns the speech length in seconds."""
        self._ensure_speaker()
        from patrol.dog import audio as _audio
        try:
            pcm = await asyncio.to_thread(_audio.tts_macos, text, voice)
        except ValueError as e:
            raise AdapterError("invalid_input", str(e)) from e
        except (RuntimeError, OSError, subprocess_errors()) as e:
            raise AdapterError("unsupported", str(e)) from e
        return self._queue_pcm48(pcm, interrupt)

    def stop_audio(self) -> None:
        """Drop everything still queued for the speaker. Never raises."""
        sp = self._speaker
        if sp is not None:
            sp.clear()
        for c in self._pcm_conv.values():
            c.flush()
        self._pcm_conv.clear()

    async def wait_audio_done(self, timeout: float = 60.0) -> bool:
        """True once the speaker queue is empty (playback finished or stopped)."""
        return await self._wait_for(lambda: self._speaker is None or not self._speaker.active, timeout)

    def speaker_status(self) -> dict:
        sp = self._speaker
        tr = self._speaker_transceiver
        return {
            "attached": sp is not None,
            "playing": bool(sp is not None and sp.active),
            "queued_s": round(sp.buffered_s, 2) if sp is not None else 0.0,
            "level_dbfs": sp.level_dbfs() if sp is not None else None,
            "audio_sent_s": round(sp.audio_frames_sent * 0.02, 1) if sp is not None else 0.0,
            "direction": getattr(tr, "currentDirection", None),
        }

    def mic_subscribe(self, rate: int = 48000, max_chunks: int = 500) -> asyncio.Queue:
        """Queue of the dog's mic audio as mono s16 chunks (~20 ms) at `rate`.
        The first subscriber switches the mic channel on. Call mic_unsubscribe() when done."""
        self._require_connected()
        if self._mic is None:
            raise AdapterError("unsupported", "this connection has no audio channel")
        if not isinstance(rate, int) or not 8000 <= rate <= 48000:
            raise AdapterError("invalid_input", f"bad mic rate {rate!r}")
        q = self._mic.subscribe(rate, max_chunks)
        self._mic_subs.add(q)
        if not self._mic_on:
            try:
                self._conn.audio.switchAudioChannel(True)
            except Exception as e:
                self._mic.unsubscribe(q)
                self._mic_subs.discard(q)
                raise AdapterError("device_error", f"mic switch on failed: {e}") from e
            self._mic_on = True
        return q

    def mic_unsubscribe(self, q: asyncio.Queue) -> None:
        """Never raises. The last subscriber switches the mic channel off."""
        if q not in self._mic_subs:
            return
        self._mic_subs.discard(q)
        if self._mic is not None:
            self._mic.unsubscribe(q)
        if not self._mic_subs and self._mic_on:
            self._mic_on = False
            try:
                self._conn.audio.switchAudioChannel(False)
            except Exception:
                pass

    async def record_audio(self, seconds: float = 5.0, name: str | None = None,
                           rate: int = 48000) -> dict:
        """Record the dog's mic to a mono WAV in output_dir. Returns path, seconds, level."""
        try:
            secs = float(seconds)
        except (TypeError, ValueError) as e:
            raise AdapterError("invalid_input", f"bad seconds {seconds!r}") from e
        if not math.isfinite(secs) or not 0.2 <= secs <= 60:
            raise AdapterError("invalid_input", "seconds must be 0.2..60")
        from patrol.dog import audio as _audio
        q = self.mic_subscribe(rate)
        try:
            pcm = await _audio.collect(q, secs, rate)
        except TimeoutError as e:
            raise AdapterError("timeout", str(e)) from e
        finally:
            self.mic_unsubscribe(q)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe = "".join(ch for ch in (name or "mic") if ch.isalnum() or ch in "-_")[:40] or "mic"
        path = await asyncio.to_thread(_audio.write_wav, self._output_dir / f"{safe}_{stamp}.wav", pcm, rate)
        levels = _audio.level_series(pcm, rate)
        return {"path": path, "seconds": round(len(pcm) / 2 / rate, 2), "rate": rate,
                "peak_dbfs": max(levels) if levels else None, "levels_dbfs_100ms": levels}

    def mic_status(self) -> dict:
        st = self._mic.status() if self._mic is not None else {
            "frames": 0, "level_dbfs": None, "last_frame_age_s": None, "format": None}
        return {"on": self._mic_on, "subscribers": len(self._mic_subs), **st}

    def _ensure_speaker(self):
        self._require_connected()
        if self._speaker is not None and self._speaker.readyState == "live":
            return self._speaker
        pc = getattr(self._conn, "pc", None)
        sender = tr = None
        for t in (pc.getTransceivers() if pc is not None else []):
            if getattr(t, "kind", None) == "audio":
                sender, tr = t.sender, t
                break
        if sender is None:
            raise AdapterError("unsupported", "this connection has no audio transceiver")
        from patrol.dog import audio as _audio
        sp = _audio.SpeakerTrack()
        sender.replaceTrack(sp)
        self._speaker, self._speaker_sender, self._speaker_transceiver = sp, sender, tr
        return sp

    def _queue_pcm48(self, pcm: bytes, interrupt: bool) -> float:
        sp = self._ensure_speaker()
        if interrupt:
            sp.clear()
        try:
            sp.enqueue(pcm)
        except OverflowError as e:
            raise AdapterError("invalid_input", str(e)) from e
        return round(len(pcm) / 2 / 48000, 2)

    def _audio_shutdown(self) -> None:
        for q in list(self._mic_subs):
            self.mic_unsubscribe(q)
        sp, self._speaker = self._speaker, None
        if sp is not None:
            try:
                if self._speaker_sender is not None:
                    self._speaker_sender.replaceTrack(None)
            except Exception:
                pass
            sp.stop()
        self._speaker_sender = None

    async def _on_audio_frame(self, frame) -> None:
        try:
            if self._mic is not None and not self._closed:
                self._mic.feed(frame)
        except Exception:
            pass                            # never kill the vendor's audio loop

    # ------------------------------------------------------------ safety envelope

    @property
    def last_safety_trip(self) -> dict | None:
        """The latched safety trip of this adapter (None = no trip). Same object until re-created."""
        return self._trips[0] if self._trips else None

    def safety_status(self) -> dict:
        """Snapshot of the envelope: home, distance, limits, latest measurements, trips."""
        pos = self._fresh_pos()
        dist = self._distance_now()
        s = self._sport if self._sport_fresh() else None
        speed = self._speed_of(s) if s is not None else None
        tilt = self._tilt_of(s) if s is not None else None
        block = self.safety_block()
        trip = self.last_safety_trip
        if trip is not None:
            state = "tripped"
        elif not self._envelope_enabled:
            state = "off"
        elif dist is not None and dist > self._fence_r:
            state = "outside_fence"
        elif block is not None:
            state = "unknown"
        else:
            state = "ok"
        rt = self._route_track
        return {
            "state": state,
            "enabled": self._envelope_enabled,
            "fence_grace": self._fence_grace,
            "block": block,
            "home": list(self._home) if self._home is not None else None,
            "home_source": self._home_source,
            "position": [round(c, 3) for c in pos] if pos is not None else None,
            "distance_from_home_m": round(dist, 3) if dist is not None else None,
            "radius_m": self._fence_r,
            "speed_mps": round(speed, 3) if speed is not None else None,
            "tilt_deg": {"roll": round(tilt[0], 1), "pitch": round(tilt[1], 1)} if tilt is not None else None,
            "limits": {"fence_radius_m": self._fence_r, "max_speed_mps": self._max_speed,
                       "speed_sustain_s": SPEED_SUSTAIN_S, "max_tilt_deg": self._max_tilt,
                       "tilt_sustain_s": TILT_SUSTAIN_S,
                       "route_overshoot": {"factor": self._ro_factor, "margin_m": self._ro_margin}},
            "route": ({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rt.items() if k != "anchor"}
                      if rt is not None else None),
            "last_trip": trip,
            "trips": list(self._trips),
            "home_changes": list(self._home_changes),
            "envelope_error": self._envelope_error,
        }

    def safety_block(self) -> str | None:
        """Why the envelope refuses to START motion now (None = allowed). Unknown is never safe.
        None when the envelope is switched off (the operator owns that decision)."""
        if not self._envelope_enabled:
            return None
        if self._envelope_error:
            return f"safety: envelope check failed ({self._envelope_error})"
        if self._home is None:
            return "safety: home position unknown"
        d = self._distance_now()
        if d is None:
            return "safety: position unknown (no fresh odometry)"
        if d > self._fence_r:
            return (f"safety: outside fence ({d:.2f} m > {self._fence_r:g} m from home); "
                    "press 'Set home here' (set_home) to accept this spot")
        return None

    def set_home(self) -> dict:
        """Move home to the current position. Only while connected, stationary, no route
        and no Move in the last second. Returns {"utc", "old", "new"} (caller logs it)."""
        self._require_connected()
        if self._route_lock.locked():
            raise AdapterError("unsafe_state", "set_home refused: a route is running")
        pos = self._fresh_pos()
        if pos is None:
            raise AdapterError("unsafe_state", "set_home refused: position unknown")
        if not self._is_stationary_now() or time.monotonic() - self._last_move_cmd_t < MOTION_RECENT_S:
            raise AdapterError("unsafe_state", "set_home refused: dog is moving (must be stationary)")
        rec = {"utc": _utc_now_iso(), "old": list(self._home) if self._home else None, "new": list(pos)}
        self._home, self._home_source = pos, "set_home"
        self._fence_grace = False
        if (self._envelope_error or "").startswith("odometry jump"):
            self._envelope_error = None        # operator accepted the new position frame
        self._home_changes.append(rec)
        return rec

    @property
    def safety_envelope_enabled(self) -> bool:
        return self._envelope_enabled

    def set_safety_envelope(self, enabled: bool) -> dict:
        """Switch the automatic threshold trips (fence/speed/tilt/overshoot) on or off.

        Off: values are still measured and reported, nothing trips, safety_block() allows
        motion. Caps, motion lock, halt/rest are unaffected. Turning it off while connected
        needs a stationary dog, no route and no Move in the last second. Turning it on
        takes effect at once; if the dog is outside the fence then, it is not laid down
        but motion is refused until it is back inside or set_home() is called.
        Returns {"enabled", "outside_fence"}.
        """
        if not isinstance(enabled, bool):
            raise AdapterError("invalid_input", f"enabled must be true/false, got {enabled!r}")
        if not enabled and self._envelope_enabled and self._connected:
            if self._route_lock.locked():
                raise AdapterError("unsafe_state", "safety thresholds can't be turned off during a route")
            if not self._is_stationary_now() or time.monotonic() - self._last_move_cmd_t < MOTION_RECENT_S:
                raise AdapterError("unsafe_state", "safety thresholds can only be turned off while stationary")
        d = self._distance_now()
        outside = d is not None and d > self._fence_r
        if enabled and not self._envelope_enabled:
            self._speed_since = self._tilt_since = None    # sustain timers start fresh
            self._fence_grace = outside
        self._envelope_enabled = enabled
        return {"enabled": enabled, "outside_fence": outside}

    def adopt_home(self, home: Any) -> None:
        """Use a known home (e.g. from the previous adapter on re-arm). Only before connect()."""
        if self._connected:
            raise AdapterError("unsafe_state", "adopt_home only before connect(); use set_home()")
        self._home, self._home_source = _parse_home(home, "home"), "adopted"

    # ----------------------------------------------------------------- internals

    def _sport_fresh(self) -> bool:
        return self._sport is not None and time.monotonic() - self._sport_t <= STATE_STALE_S

    def _fresh_pos(self) -> tuple[float, float] | None:
        if not self._sport_fresh() or not isinstance(self._sport, Mapping):
            return None
        return _xy(self._sport.get("position"))

    def _distance_now(self) -> float | None:
        pos = self._fresh_pos()
        if pos is None or self._home is None:
            return None
        return math.hypot(pos[0] - self._home[0], pos[1] - self._home[1])

    @staticmethod
    def _speed_of(s: Mapping) -> float | None:
        v = _xy(s.get("velocity"))
        return math.hypot(*v) if v is not None else None

    @staticmethod
    def _tilt_of(s: Mapping) -> tuple[float, float] | None:
        imu = s.get("imu_state")
        rpy = _xy(imu.get("rpy")) if isinstance(imu, Mapping) else None
        return (math.degrees(rpy[0]), math.degrees(rpy[1])) if rpy is not None else None

    def _motion_active(self, now: float, s: Mapping) -> bool:
        """For the fence: route running, a Move sent recently, or measurably moving."""
        if self._route_lock.locked() or now - self._last_move_cmd_t <= MOTION_RECENT_S:
            return True
        speed = self._speed_of(s)
        try:
            yaw = abs(float(s.get("yaw_speed", 0.0)))
        except (TypeError, ValueError):
            yaw = 0.0
        return (speed is not None and speed > STATIONARY_MAX_SPEED) or yaw > STATIONARY_MAX_YAW

    def _check_envelope(self, s: Mapping, now: float) -> None:
        """Runs synchronously on every sport-state message (~20 Hz). Cheap, no I/O.

        - fence: trips only while motion is possible (route, recent Move, or measured
          motion). A dog standing still outside the fence (odometry drift, or after a
          trip + re-arm) is not laid down, but safety_block() refuses new motion.
        - speed / tilt: trip whenever sustained, moving or not.
        - route overshoot: only while _run_segments is tracking a route.
        """
        pos = _xy(s.get("position"))
        if pos is not None:
            prev, prev_t = getattr(self, "_last_pos", None), getattr(self, "_last_pos_t", 0.0)
            self._last_pos, self._last_pos_t = pos, now
            if prev is not None and now - prev_t < 0.5:
                jump = math.hypot(pos[0] - prev[0], pos[1] - prev[1])
                if jump > ODOM_JUMP_M:
                    # Odometry reset or glitch: the fence centre can no longer be trusted.
                    self._envelope_error = f"odometry jump {jump:.2f} m; check the dog, then Set home here"
                    if self._motion_active(now, s):
                        self._trip("odometry", f"safety: odometry jump {jump:.2f} m",
                                   {"jump_m": round(jump, 3), "from": list(prev), "to": list(pos)})
            if self._home is None:
                self._home, self._home_source = pos, "auto (first position after connect)"
            d = math.hypot(pos[0] - self._home[0], pos[1] - self._home[1])
            if self._fence_grace and d <= self._fence_r:
                self._fence_grace = False                   # back inside: fence armed again
            if d > self._fence_r and not self._fence_grace and self._motion_active(now, s):
                self._trip("fence", f"safety: fence {d:.2f} m > {self._fence_r:g} m",
                           {"distance_m": round(d, 3), "radius_m": self._fence_r,
                            "position": [round(c, 3) for c in pos], "home": list(self._home)})
            rt = self._route_track
            if rt is not None:
                step = math.hypot(pos[0] - rt["anchor"][0], pos[1] - rt["anchor"][1])
                if step >= ODOM_STEP_M:
                    rt["travel_m"] += step
                    rt["anchor"] = pos
                if rt["travel_m"] > rt["limit_m"]:
                    self._trip("route_overshoot",
                               f"safety: route overshoot {rt['travel_m']:.2f} m > {rt['limit_m']:.2f} m "
                               f"(planned {rt['planned_m']:.2f} m)",
                               {"route_id": rt["route_id"], "travel_m": round(rt["travel_m"], 3),
                                "planned_m": round(rt["planned_m"], 3), "limit_m": round(rt["limit_m"], 3)})
        speed = self._speed_of(s)
        if speed is not None and speed > self._max_speed:
            if self._speed_since is None:
                self._speed_since = now
            if now - self._speed_since >= SPEED_SUSTAIN_S:
                self._trip("speed", f"safety: speed {speed:.2f} m/s > {self._max_speed:g} m/s "
                                    f"for {now - self._speed_since:.2f} s",
                           {"speed_mps": round(speed, 3), "max_speed_mps": self._max_speed,
                            "sustained_s": round(now - self._speed_since, 3)})
        else:
            self._speed_since = None
        tilt = self._tilt_of(s)
        if tilt is not None and max(abs(tilt[0]), abs(tilt[1])) > self._max_tilt:
            if self._tilt_since is None:
                self._tilt_since = now
            if now - self._tilt_since >= TILT_SUSTAIN_S:
                self._trip("tilt", f"safety: tilt roll {tilt[0]:.0f} deg / pitch {tilt[1]:.0f} deg "
                                   f"> {self._max_tilt:g} deg",
                           {"roll_deg": round(tilt[0], 1), "pitch_deg": round(tilt[1], 1),
                            "max_tilt_deg": self._max_tilt, "sustained_s": round(now - self._tilt_since, 3)})
        else:
            self._tilt_since = None

    def _trip(self, kind: str, reason: str, values: dict) -> None:
        """Latch: the first trip locks motion and schedules ONE rest(). Later trips of a
        different kind are recorded only (no extra rest). Nothing trips while the envelope is off."""
        if not self._envelope_enabled or any(t["kind"] == kind for t in self._trips):
            return
        rec = {"kind": kind, "reason": reason, "values": values, "utc": _utc_now_iso(),
               "monotonic": round(time.monotonic(), 3), "rest_scheduled": False}
        first = not self._trips
        self._trips.append(rec)
        if not first:
            return
        self._halted.set()                 # route loop breaks on its next tick
        if self._faulted is None or self._faulted == "halted":
            self._faulted = reason
        if getattr(self, "_rest_started", False):
            rec["rest_report"] = {"skipped": "a rest (STOP) was already in progress"}
            return                         # operator STOP already lying it down: no 2nd StandDown
        if self._connected and not self._safety_rest_scheduled:
            self._safety_rest_scheduled = True
            rec["rest_scheduled"] = True
            self._schedule(lambda: self._safety_rest(rec))

    def _schedule(self, make_coro: Callable[[], Any]) -> None:
        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None and (loop is None or running is loop):
            self._safety_rest_task = running.create_task(make_coro())
        elif loop is not None:            # callback from another thread
            def _go():
                self._safety_rest_task = loop.create_task(make_coro())
            loop.call_soon_threadsafe(_go)

    async def _safety_rest(self, rec: dict) -> None:
        try:
            rec["rest_report"] = await self.rest()
        except Exception as e:  # rest() itself never raises in practice; record anyway
            rec["rest_report"] = {"standdown_sent": False, "error": f"{type(e).__name__}: {e}"}

    def _require_envelope_ok(self) -> None:
        block = self.safety_block()
        if block is not None:
            raise AdapterError("unsafe_state", block)

    @staticmethod
    async def _discard_conn(conn) -> None:
        try:
            await asyncio.wait_for(conn.disconnect(), 5.0)
        except Exception:
            pass

    def _link_alive(self) -> bool:
        """False once the WebRTC peer connection has failed/closed (cable pulled, dog off)."""
        pc = getattr(self._conn, "pc", None)
        state = getattr(pc, "connectionState", None)
        return state not in ("failed", "closed", "disconnected")

    def _make_conn(self):
        if self._conn_factory is not None:
            return self._conn_factory(self._ip)
        try:
            from unitree_webrtc_connect.webrtc_driver import (
                UnitreeWebRTCConnection,
                WebRTCConnectionMethod,
            )
        except ImportError as e:
            raise AdapterError("unsupported", "unitree_webrtc_connect is not installed") from e
        return UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip=self._ip)

    def _topics(self) -> dict:
        if self._conn_factory is not None:
            return {k: k for k in ("LF_SPORT_MOD_STATE", "MULTIPLE_STATE", "LOW_STATE",
                                   "SPORT_MOD", "OBSTACLES_AVOID", "MOTION_SWITCHER", "VUI",
                                   "ULIDAR_ARRAY", "ULIDAR_SWITCH", "WIRELESS_CONTROLLER")}
        from unitree_webrtc_connect.constants import RTC_TOPIC
        return RTC_TOPIC

    def _require_connected(self) -> None:
        if not self._connected or not self._link_alive():
            raise AdapterError("not_connected", "dog not connected (or WebRTC link lost)")

    def _require_motion_allowed(self) -> None:
        if self._halted.is_set() or self._faulted:
            raise AdapterError("unsafe_state", f"motion locked ({self._faulted}); recreate the adapter")

    def _check_ctx(self, ctx: RunContext) -> None:
        if ctx.cancel.is_set():
            raise AdapterError("cancelled", "cancelled")
        if time.monotonic() >= ctx.deadline_monotonic:
            raise AdapterError("timeout", "deadline passed")

    async def _sleep_checked(self, seconds: float, ctx: RunContext) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._halted.is_set():
                raise AdapterError("cancelled", "halted")
            self._check_ctx(ctx)
            await asyncio.sleep(0.05)

    def _is_lying_now(self) -> bool:
        """Fresh sport state says the body is DOWN: a lie-down / damping mode (LYING_MODES), or
        body height below the standing minimum. Used to confirm a StandDown, so it is strict: any
        other mode at full height (e.g. 8 recovery) is NOT lying. Unknown / stale => False
        (fail toward "not confirmed")."""
        s = self._sport
        if s is None or time.monotonic() - self._sport_t > STATE_STALE_S:
            return False
        try:
            mode = s.get("mode")
            if mode is not None and int(mode) in LYING_MODES:
                return True
            return float(s["body_height"]) < STANDING_MIN_HEIGHT_M
        except (KeyError, TypeError, ValueError):
            return False

    def _posture_raw(self) -> dict:
        """Raw sport mode + body height for reports (None when unknown). Never raises."""
        s = self._sport if isinstance(self._sport, dict) else {}
        return {"mode": s.get("mode"), "body_height": s.get("body_height")}

    def _is_stationary_now(self) -> bool:
        s = self._sport
        if s is None or time.monotonic() - self._sport_t > STATE_STALE_S:
            return False
        try:
            return (math.hypot(float(s["velocity"][0]), float(s["velocity"][1])) <= STATIONARY_MAX_SPEED
                    and abs(float(s["yaw_speed"])) <= STATIONARY_MAX_YAW)
        except (KeyError, TypeError, ValueError, IndexError):
            return False

    async def _wait_for(self, cond: Callable[[], bool], timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            await asyncio.sleep(0.05)
        return cond()

    async def _request(self, topic: str, options: dict, lock_on_timeout: bool,
                       timeout: float | None = None) -> dict:
        try:
            return await asyncio.wait_for(
                self._conn.datachannel.pub_sub.publish_request_new(topic, options),
                timeout if timeout is not None else self._command_timeout_s,
            )
        except asyncio.TimeoutError as e:
            if lock_on_timeout:
                self._faulted = f"timeout on api {options.get('api_id')}"
            raise AdapterError("timeout", f"request api_id={options.get('api_id')} timed out") from e
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError("device_error", f"request failed: {e}") from e

    async def _sport_request(self, name: str, parameter: dict | None = None, *,
                             priority: bool = False, lock_on_timeout: bool = True,
                             accept_codes: tuple[int, ...] = ()) -> dict:
        opts: dict = {"api_id": SPORT_API[name]}
        if parameter is not None:
            opts["parameter"] = parameter
        if priority:
            opts["priority"] = 1
        if name == "Move":
            self._last_move_cmd_t = time.monotonic()
        # Posture changes reply only when finished (real Go2: StandDown > 3 s), so they get
        # a longer limit; Move/StopMove keep the short command timeout.
        timeout = max(POSTURE_TIMEOUT_S, self._command_timeout_s) if name in POSTURE_CMDS else None
        resp = await self._request(self._topics()["SPORT_MOD"], opts, lock_on_timeout, timeout)
        code = self._resp_code(resp)
        if code not in (0, None) and code not in accept_codes:
            raise AdapterError("device_error", f"{name} returned code {code}")
        return resp

    def _sport_fire(self, name: str, *, priority: bool = False) -> None:
        """Send a sport request without awaiting the reply (used by halt/rest)."""
        if self._conn is None:
            return
        try:
            opts: dict = {"api_id": SPORT_API[name]}
            if priority:
                opts["priority"] = 1
            asyncio.get_running_loop().create_task(
                self._conn.datachannel.pub_sub.publish_request_new(self._topics()["SPORT_MOD"], opts)
            )
        except Exception:
            pass

    async def _avoid_request(self, name: str, parameter: dict | None = None) -> dict:
        opts: dict = {"api_id": AVOID_API[name]}
        if parameter is not None:
            opts["parameter"] = parameter
        return await self._request(self._topics()["OBSTACLES_AVOID"], opts, lock_on_timeout=False)

    @staticmethod
    def _resp_code(resp: Any) -> int | None:
        try:
            return int(resp["data"]["header"]["status"]["code"])
        except Exception:
            return None

    def _load_route(self, zone: str) -> list[dict]:
        if not self._routes_path:
            raise AdapterError("unsupported", "no routes_path configured; no calibrated routes")
        try:
            routes = json.loads(Path(self._routes_path).read_text())
        except FileNotFoundError as e:
            raise AdapterError("unsupported", f"routes file not found: {self._routes_path}") from e
        except json.JSONDecodeError as e:
            raise AdapterError("invalid_input", f"routes file is not valid JSON: {e}") from e
        route = routes.get(zone)
        if not route or not route.get("calibrated"):
            raise AdapterError("unsupported", f"route for {zone!r} is not calibrated")
        return [self._validate_segment(s) for s in route["segments"]]

    @staticmethod
    def _validate_segment(s: Mapping[str, Any]) -> dict:
        try:
            seg = {
                "vx": float(s.get("vx", 0.0)),
                "vy": float(s.get("vy", 0.0)),
                "vyaw": float(s.get("vyaw", 0.0)),
                "duration_s": float(s["duration_s"]),
            }
        except (KeyError, TypeError, ValueError) as e:
            raise AdapterError("invalid_input", f"bad route segment {s!r}") from e
        if not all(math.isfinite(v) for v in seg.values()):
            raise AdapterError("invalid_input", f"non-finite value in route segment {s!r}")
        if not (0 < seg["duration_s"] <= MAX_SEGMENT_S):
            raise AdapterError("invalid_input", f"segment duration out of range: {seg['duration_s']}")
        seg["vx"], seg["vy"], seg["vyaw"] = (
            _clamp(seg["vx"], MAX_VX), _clamp(seg["vy"], MAX_VY), _clamp(seg["vyaw"], MAX_VYAW))
        return seg

    async def _run_segments(self, segments: list[dict], ctx: RunContext, route_id: str) -> RouteResult:
        route_deadline = min(ctx.deadline_monotonic, time.monotonic() + self._max_route_s)
        period = 1.0 / self._move_rate_hz
        reason = "completed"
        planned = sum(math.hypot(s["vx"], s["vy"]) * s["duration_s"] for s in segments)
        start = self._fresh_pos()
        if start is not None:
            self._route_track = {"route_id": route_id, "planned_m": planned, "travel_m": 0.0,
                                 "limit_m": planned * self._ro_factor + self._ro_margin, "anchor": start}
        try:
            for i, seg in enumerate(segments):
                seg_end = time.monotonic() + seg["duration_s"]
                while time.monotonic() < seg_end:
                    if self._halted.is_set():
                        f = self._faulted or ""
                        reason = f if f.startswith("safety:") else "halted"
                        break
                    if ctx.cancel.is_set():
                        reason = "cancelled"
                        break
                    if time.monotonic() >= route_deadline:
                        reason = "timeout"
                        break
                    blk = self.safety_block()
                    if blk is not None:
                        reason = blk
                        break
                    await self._sport_request("Move", {"x": seg["vx"], "y": seg["vy"], "z": seg["vyaw"]})
                    await asyncio.sleep(period)
                if reason != "completed":
                    break
        except AdapterError as e:
            reason = f"error: {e}"
            self._faulted = self._faulted or f"route error: {e.code}"
        finally:
            self._route_track = None
        stopped = await self._stop_and_verify()
        completed = reason == "completed"
        if not completed:
            # After any incomplete route, refuse new routes until Ground recreates us.
            self._faulted = self._faulted or reason
        elif not stopped:
            self._faulted = self._faulted or "stop not verified"
        return RouteResult(completed=completed, stopped=stopped, route_id=route_id,
                           detail=f"{reason}; stop {'verified' if stopped else 'NOT verified'}")

    async def _stop_and_verify(self) -> bool:
        if not self._connected:
            return False
        self._zero_sticks_first()
        try:
            await self._sport_request("StopMove", priority=True, lock_on_timeout=False)
        except AdapterError:
            self._sport_fire("StopMove", priority=True)
        end = time.monotonic() + STOP_VERIFY_S
        while time.monotonic() < end:
            st = await self.get_status()
            if st.stationary is True:
                return True
            await asyncio.sleep(0.05)
        return False

    @staticmethod
    def _write_jpeg(cv2, path: str, img) -> bool:
        return bool(cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 90]))

    # ------------------------------------------------------------- callbacks

    def _on_sport(self, msg: dict) -> None:
        self._sport = msg.get("data")
        self._sport_t = time.monotonic()
        try:
            if isinstance(self._sport, Mapping):
                self._check_envelope(self._sport, self._sport_t)
        except Exception as e:  # never kill the vendor callback; fail closed instead
            self._envelope_error = f"{type(e).__name__}: {e}"

    def _on_multi(self, msg: dict) -> None:
        d = msg.get("data")
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except json.JSONDecodeError:
                return
        if isinstance(d, dict):
            self._multi = d
            self._multi_t = time.monotonic()

    def _on_low(self, msg: dict) -> None:
        self._low = msg.get("data")

    def _on_lidar(self, msg: dict) -> None:
        try:
            now = time.monotonic()
            scan = lidar_mod.scan_from_message(msg, now)
            if scan is None:
                self._lidar_bad += 1
                return
            self._lidar = scan
            self._lidar_msgs += 1
            self._lidar_times.append(now)
        except Exception:  # vendor callbacks never raise
            self._lidar_bad += 1

    async def _on_track(self, track) -> None:
        self._video_task_running = True
        try:
            while not self._closed:
                frame = await track.recv()
                self._frame = frame.to_ndarray(format="bgr24")
                self._frame_t = time.monotonic()
                self._frame_utc = _utc_now_iso()
        except Exception:
            pass
        finally:
            self._video_task_running = False
