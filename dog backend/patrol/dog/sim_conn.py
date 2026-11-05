"""Simulated Go2 WebRTC connection (no robot, no vendor lib, no network).

Drop-in for `UnitreeWebRTCConnection` via `RealDog(_conn_factory=...)`, so the real
adapter code (caps, timeouts, motion lock) runs unchanged on top of it. Used by
`python -m patrol.dog.joystick --fake` and by the tests.

- Sport `Move` sets a commanded velocity; the body velocity follows it with a short
  lag and integrates into position/heading. A Move expires after `move_expiry_s`.
- Remote-controller sticks on WIRELESS_CONTROLLER (publish_without_callback) also set the
  commanded velocity (STICK_SCALE: 1.0 = 1 m/s / 1 rad/s, sim only), expiring like Move. With
  `avoid` on, only stick commands are filtered: forward is held while a synthetic-room point is
  within AVOID_DISTANCE_M of the nose (Move is never filtered, as seen on the real dog).
  `stick_hold=True` models the real-dog unknown at its worst: a held stick never expires and
  StopMove does not clear it; only a zero stick message (or lying down) stops it.
- StopMove zeroes the command. StandDown lies down slowly, StandUp + BalanceStand
  stand up again. Damp is recorded (tests check it is never sent) and drops the dog.
- VUI brightness get/set (api 1006/1005), volume get/set (1004/1003), obstacle-avoid
  get/set, motion-mode read.
- Audio: `pc.getTransceivers()` has one audio transceiver; its sender pulls the
  speaker track in real time (like aiortc would) and records what was "played".
  `audio.switchAudioChannel(True)` starts a fake mic: 48 kHz stereo s16 frames with
  quiet noise plus the speaker output at -10 dB (the dog hears itself).
- Fake camera: a generated top-down image with a moving marker and a timestamp.
- Fake LiDAR: while subscribed to ULIDAR_ARRAY, `LIDAR_HZ` voxel-map messages of a fixed
  6 x 5 m room (patrol.dog.lidar.synthetic_room_points, world frame). With
  `lidar_needs_switch=True` nothing is sent until the "on" message reaches ULIDAR_SWITCH
  (like a dog whose sensor is off). `set_decoder` / `disableTrafficSaving` are recorded.

Reusable across re-arms: connect() resets subscriptions, disconnect() stops streams,
the simulated body (position, posture, brightness) persists like the real dog.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime, timezone

SPORT_STATE_HZ = 20.0
SLOW_STATE_S = 1.0
LIDAR_HZ = 5.0
STICK_SCALE = 1.0        # sim only: stick 1.0 = 1 m/s forward/sideways, 1 rad/s turn
AVOID_DISTANCE_M = 0.5   # sim avoidance: obstacle closer than this to the nose => no forward


def _ok(data: dict | None = None) -> dict:
    out: dict = {"data": {"header": {"status": {"code": 0}}}}
    if data is not None:
        out["data"]["data"] = json.dumps(data)
    return out


class SimPubSub:
    def __init__(self, conn: "SimConn") -> None:
        self.conn = conn
        self.subs: dict = {}

    def subscribe(self, topic, cb=None):
        self.subs[topic] = cb

    async def publish_request_new(self, topic, options):
        return await self.conn._handle(topic, options)

    def publish_without_callback(self, topic, data=None):
        self.conn.sent.append((topic, None, data, time.monotonic()))
        if topic == "ULIDAR_SWITCH" and data == "on":
            self.conn.lidar_on = True
        elif topic == "WIRELESS_CONTROLLER" and isinstance(data, dict):
            self.conn._sticks(data)


class SimFrame:
    def __init__(self, img) -> None:
        self._img = img

    def to_ndarray(self, format="bgr24"):
        return self._img


class SimTrack:
    def __init__(self, conn: "SimConn") -> None:
        self.conn = conn
        self.closed = False

    async def recv(self):
        await asyncio.sleep(1.0 / self.conn.fps)
        if self.closed:
            raise ConnectionError("track closed")
        return SimFrame(self.conn.render())


class SimVideo:
    def __init__(self, conn: "SimConn") -> None:
        self.conn = conn
        self.cb = None
        self.track: SimTrack | None = None
        self._task = None

    def add_track_callback(self, cb):
        self.cb = cb

    def switchVideoChannel(self, on):
        if on and self.conn.camera and self.cb is not None and self.track is None:
            self.track = SimTrack(self.conn)
            self._task = asyncio.get_running_loop().create_task(self.cb(self.track))
        elif not on:
            self.stop()

    def stop(self):
        if self.track is not None:
            self.track.closed = True
            self.track = None


class SimSender:
    """Pulls the speaker track at real-time pace, like aiortc's RTP sender."""

    def __init__(self, conn: "SimConn") -> None:
        self.conn = conn
        self.track = None
        self._task: asyncio.Task | None = None

    def replaceTrack(self, track) -> None:
        self.track = track
        if track is not None and self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._pump())

    async def _pump(self) -> None:
        import numpy as np
        while True:
            tr = self.track
            if tr is None:
                await asyncio.sleep(0.02)
                continue
            try:
                f = await tr.recv()
            except Exception:
                self.track = None
                continue
            a = np.frombuffer(bytes(f.planes[0])[: f.samples * 2], dtype="<i2")
            self.conn.frames_played += 1
            if np.any(a):
                self.conn.audio_played_s += f.samples / 48000
                self.conn.peak_played = max(self.conn.peak_played, int(np.max(np.abs(a))))
            if self.conn.volume_mutes and self.conn.volume == 0:
                a = np.zeros_like(a)         # the speaker plays nothing at volume 0
            self.conn._loopback.append(a)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.track = None


class SimTransceiver:
    kind = "audio"

    def __init__(self, conn: "SimConn") -> None:
        self.sender = SimSender(conn)
        self.currentDirection = "sendrecv"


class SimPC:
    def __init__(self, conn: "SimConn") -> None:
        self.connectionState = "new"
        self._transceivers = [SimTransceiver(conn)]

    def getTransceivers(self):
        return list(self._transceivers)


class SimAudio:
    """Fake mic channel (vendor: conn.audio)."""

    def __init__(self, conn: "SimConn") -> None:
        self.conn = conn
        self.cbs: list = []
        self._task: asyncio.Task | None = None

    def add_track_callback(self, cb) -> None:
        self.cbs.append(cb)

    def switchAudioChannel(self, on: bool) -> None:
        self.conn.audio_switches.append(bool(on))
        if on and self._task is None and self.conn.mic:
            self._task = asyncio.get_running_loop().create_task(self._mic())
        elif not on:
            self.stop()

    async def _mic(self) -> None:
        import av
        import numpy as np
        rng = np.random.default_rng(1)
        n, t0, k = 960, time.monotonic(), 0
        while True:
            k += 1
            await asyncio.sleep(max(0.0, t0 + k * 0.02 - time.monotonic()))
            mono = rng.normal(0, 30, n)                       # ~ -60 dBFS room noise
            if self.conn._loopback:
                lb = self.conn._loopback.popleft().astype(np.float64)
                mono[: len(lb)] += 0.3 * lb[:n]
            st = np.repeat(np.clip(mono, -32768, 32767).astype("<i2"), 2).reshape(1, -1)
            fr = av.AudioFrame.from_ndarray(st, format="s16", layout="stereo")
            fr.sample_rate = 48000
            fr.pts = k * n
            for cb in list(self.cbs):
                await cb(fr)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None


class SimConn:
    def __init__(self, *, avoid: bool = True, publish_multi: bool = True, hang_on_move: bool = False,
                 standing: bool = True, camera: bool = True, fps: float = 15.0,
                 move_expiry_s: float = 1.0, tau_s: float = 0.15, brightness: int = 0,
                 volume: int = 0, mic: bool = True, audio: bool = True,
                 volume_mutes: bool = False, lidar: bool = True,
                 lidar_needs_switch: bool = False, stick_hold: bool = False) -> None:
        self.sent: list[tuple] = []          # (topic, api_id, parameter, monotonic time)
        self.avoid = avoid
        self.stick_hold = stick_hold         # True: held sticks never expire, StopMove ignores them; only zero sticks stop
        self.publish_multi = publish_multi
        self.hang_on_move = hang_on_move
        self.camera = camera
        self.fps = fps
        self.move_expiry_s = move_expiry_s
        self.tau_s = tau_s
        self.brightness = brightness
        self.volume = volume
        self.volume_mutes = volume_mutes     # True: like the real dog, volume 0 = silent speaker
        self.mic = mic
        self.lidar = lidar
        self.lidar_needs_switch = lidar_needs_switch
        self.lidar_on = not lidar_needs_switch   # the sensor's state persists across sessions
        self.decoder_calls: list[str] = []
        self.traffic_saving_calls: list[bool] = []
        self._lidar_points = None
        self.connects = 0
        # audio
        from collections import deque
        self._loopback: deque = deque(maxlen=50)   # speaker output the fake mic hears
        self.frames_played = 0
        self.audio_played_s = 0.0
        self.peak_played = 0
        self.audio_switches: list[bool] = []
        self.pc = SimPC(self)
        if audio:
            self.audio = SimAudio(self)
        # body
        self.x = self.y = self.heading = 0.0
        self.v = [0.0, 0.0]                  # world-frame velocity
        self.w = 0.0
        self.cmd = (0.0, 0.0, 0.0)           # body-frame vx, vy, vyaw
        self.cmd_t = 0.0
        self.cmd_src = "move"                # "move" (sport Move) or "sticks" (remote-controller topic)
        self.avoid_blocked = False           # simulated avoidance is holding forward motion
        self.height = 0.32 if standing else 0.08
        self.height_target = self.height
        self.mode = 1 if standing else 5
        self.balance_pending = False
        self.soc = 80.0
        self.datachannel = type("DC", (), {})()
        self.datachannel.pub_sub = SimPubSub(self)
        self.datachannel.set_decoder = self._set_decoder
        self.datachannel.disableTrafficSaving = self._disable_traffic_saving
        self.video = SimVideo(self)
        self._task: asyncio.Task | None = None
        self._frame_n = 0

    # ---------------------------------------------------------- connection
    async def connect(self):
        self.connects += 1
        self.datachannel.pub_sub.subs = {}
        self.video.cb = None
        if hasattr(self, "audio"):
            self.audio.cbs = []
        self.pc = SimPC(self)
        self.pc.connectionState = "connected"
        self._task = asyncio.get_running_loop().create_task(self._stream())

    async def disconnect(self):
        if self._task:
            self._task.cancel()
            self._task = None
        self.video.stop()
        if hasattr(self, "audio"):
            self.audio.stop()
        for t in self.pc.getTransceivers():
            t.sender.stop()
        self.pc.connectionState = "closed"

    def _set_decoder(self, decoder_type: str = "libvoxel") -> None:
        self.decoder_calls.append(decoder_type)

    async def _disable_traffic_saving(self, switch: bool) -> None:
        self.traffic_saving_calls.append(bool(switch))

    # ---------------------------------------------------------- helpers for tests
    def apis(self, topic: str = "SPORT_MOD") -> list[int]:
        return [s[1] for s in self.sent if s[0] == topic]

    def moves(self):
        return [s for s in self.sent if s[0] == "SPORT_MOD" and s[1] == 1008]

    def stops(self):
        return [s for s in self.sent if s[0] == "SPORT_MOD" and s[1] == 1003]

    # ---------------------------------------------------------- requests
    async def _handle(self, topic, options):
        api = options.get("api_id")
        param = options.get("parameter")
        self.sent.append((topic, api, param, time.monotonic()))
        if topic == "SPORT_MOD":
            if api == 1008:                                  # Move
                if self.hang_on_move:
                    await asyncio.sleep(3600)
                if self._standing():
                    self.cmd = (float(param["x"]), float(param["y"]), float(param["z"]))
                    self.cmd_t = time.monotonic()
                    self.cmd_src = "move"
            elif api == 1003:                                # StopMove
                if not (self.stick_hold and self.cmd_src == "sticks"):
                    self.cmd = (0.0, 0.0, 0.0)
            elif api == 1005:                                # StandDown (slow)
                self.cmd = (0.0, 0.0, 0.0)
                self.mode, self.height_target, self.balance_pending = 5, 0.08, False
            elif api == 1004:                                # StandUp
                self.mode, self.height_target = 6, 0.32
            elif api == 1002:                                # BalanceStand
                self.balance_pending = True
            elif api == 1001:                                # Damp: never used by our code
                self.cmd = (0.0, 0.0, 0.0)
                self.mode, self.height, self.height_target = 7, 0.0, 0.0
            return _ok()
        if topic == "OBSTACLES_AVOID":
            if api == 1002:
                return _ok({"enable": self.avoid})
            if api == 1001 and isinstance(param, dict):
                self.avoid = bool(param.get("enable"))
            return _ok()
        if topic == "VUI":
            if api == 1006:
                return _ok({"brightness": self.brightness})
            if api == 1005 and isinstance(param, dict):
                self.brightness = int(param["brightness"])
            if api == 1004:
                return _ok({"volume": self.volume})
            if api == 1003 and isinstance(param, dict):
                self.volume = int(param["volume"])
            return _ok()
        if topic == "MOTION_SWITCHER" and api == 1001:
            return _ok({"name": "normal"})
        return _ok()

    def _standing(self) -> bool:
        return self.mode in (0, 1, 2, 3) and self.height >= 0.25

    def _sticks(self, d: dict) -> None:
        """Remote-controller sticks (sim scale: 1.0 = 1 m/s forward/sideways, 1 rad/s turn).
        ly + = forward, lx + = strafe right (body vy -), rx + = turn RIGHT (body vyaw -), as the
        real dog does (measured 2026-11-04 19:30: rx + made the yaw decrease). Expire like Move."""
        try:
            lx, ly, rx = float(d.get("lx", 0.0)), float(d.get("ly", 0.0)), float(d.get("rx", 0.0))
        except (TypeError, ValueError):
            return
        if self._standing():
            self.cmd = (ly * STICK_SCALE, -lx * STICK_SCALE, -rx * STICK_SCALE)
            self.cmd_t = time.monotonic()
            self.cmd_src = "sticks"

    def _obstacle_ahead(self) -> bool:
        """Simulated avoidance: a synthetic-room point within AVOID_DISTANCE_M of the nose."""
        from patrol.dog.lidar import nearest_ahead, synthetic_room_points, to_body
        if self._lidar_points is None:
            self._lidar_points = synthetic_room_points()
        d = nearest_ahead(to_body(self._lidar_points, (self.x, self.y, self.heading, 0.0)))
        return d is not None and d < AVOID_DISTANCE_M

    # ---------------------------------------------------------- physics + state
    def _step(self, dt: float) -> None:
        now = time.monotonic()
        held = self.stick_hold and self.cmd_src == "sticks"
        if now - self.cmd_t > self.move_expiry_s and not held:
            self.cmd = (0.0, 0.0, 0.0)
        if not self._standing():
            self.cmd = (0.0, 0.0, 0.0)
        cvx, cvy, cw = self.cmd
        # The obstacle-avoid service filters only the remote-controller path (sport Move is not
        # filtered: real dog, 2026-11-04 18:08). Sim: just hold forward motion near an obstacle.
        self.avoid_blocked = bool(self.avoid and self.cmd_src == "sticks" and cvx > 0 and self._obstacle_ahead())
        if self.avoid_blocked:
            cvx = 0.0
        c, s = math.cos(self.heading), math.sin(self.heading)
        tx, ty = cvx * c - cvy * s, cvx * s + cvy * c
        k = min(1.0, dt / self.tau_s)
        self.v[0] += (tx - self.v[0]) * k
        self.v[1] += (ty - self.v[1]) * k
        self.w += (cw - self.w) * k
        for i in (0, 1):
            if abs(self.v[i]) < 1e-3:
                self.v[i] = 0.0
        if abs(self.w) < 1e-3:
            self.w = 0.0
        self.x += self.v[0] * dt
        self.y += self.v[1] * dt
        self.heading = (self.heading + self.w * dt + math.pi) % (2 * math.pi) - math.pi
        if self.mode in (1, 3):
            self.mode = 3 if (any(self.cmd) or math.hypot(*self.v) > 0.02) else 1
        rate = 0.2 * dt / 1.0                               # ~1.2 s for a full stand/lie
        if self.height < self.height_target:
            self.height = min(self.height_target, self.height + rate)
        elif self.height > self.height_target:
            self.height = max(self.height_target, self.height - rate)
        if self.balance_pending and self.height >= 0.30:
            self.mode, self.balance_pending = 1, False
        self.soc = max(5.0, self.soc - dt * 0.002)

    async def _stream(self):
        subs = self.datachannel.pub_sub.subs
        last = time.monotonic()
        last_slow = 0.0
        last_lidar = 0.0
        while True:
            now = time.monotonic()
            self._step(now - last)
            last = now
            if "LF_SPORT_MOD_STATE" in subs:
                subs["LF_SPORT_MOD_STATE"]({"data": {
                    "mode": self.mode, "body_height": round(self.height, 4),
                    "velocity": [self.v[0], self.v[1], 0.0], "yaw_speed": self.w,
                    "position": [self.x, self.y, round(self.height, 4)],
                    "imu_state": {"rpy": [0.0, 0.0, self.heading]}}})
            if now - last_slow >= SLOW_STATE_S:
                last_slow = now
                if "LOW_STATE" in subs:
                    subs["LOW_STATE"]({"data": {"bms_state": {"soc": int(self.soc)}}})
                if self.publish_multi and "MULTIPLE_STATE" in subs:
                    subs["MULTIPLE_STATE"]({"data": json.dumps({
                        "obstaclesAvoidSwitch": self.avoid, "brightness": self.brightness, "volume": self.volume})})
            if (self.lidar and "ULIDAR_ARRAY" in subs and self.lidar_on
                    and now - last_lidar >= 1.0 / LIDAR_HZ):
                last_lidar = now
                subs["ULIDAR_ARRAY"](self._lidar_message(now))
            await asyncio.sleep(1.0 / SPORT_STATE_HZ)

    def _lidar_message(self, now: float) -> dict:
        if self._lidar_points is None:
            from patrol.dog.lidar import synthetic_room_points
            self._lidar_points = synthetic_room_points()
        return {"topic": "ULIDAR_ARRAY", "data": {
            "origin": [-3.0, -2.5, 0.0], "resolution": 0.05, "frame_id": "odom", "stamp": now,
            "data": {"points": self._lidar_points}}}

    # ---------------------------------------------------------- fake camera
    def render(self):
        import cv2
        import numpy as np

        self._frame_n += 1
        h, w = 360, 640
        base = 30 + 6 * self.brightness
        img = np.full((h, w, 3), (base, base + 4, base + 8), dtype=np.uint8)
        scale = 80.0                                          # px per metre
        cx, cy = w // 2, h // 2
        ox, oy = self.x * scale, self.y * scale
        step = int(scale / 2)
        for gx in range(-int(ox) % step, w, step):            # floor grid moves with the dog
            cv2.line(img, (gx, 0), (gx, h), (70, 70, 70), 1)
        for gy in range(int(oy) % step, h, step):
            cv2.line(img, (0, gy), (w, gy), (70, 70, 70), 1)
        ax, ay = int(cx - ox), int(cy + oy)                   # world origin marker
        cv2.drawMarker(img, (ax, ay), (0, 200, 255), cv2.MARKER_CROSS, 24, 2)
        hx = int(cx + 30 * math.cos(self.heading))
        hy = int(cy - 30 * math.sin(self.heading))
        color = (0, 220, 0) if self._standing() else (0, 140, 255)
        cv2.circle(img, (cx, cy), 14, color, -1)
        cv2.arrowedLine(img, (cx, cy), (hx, hy), (255, 255, 255), 3, tipLength=0.4)
        utc = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        lines = [f"SIMULATED CAMERA  #{self._frame_n}  {utc} UTC",
                 f"pos ({self.x:+.2f}, {self.y:+.2f}) m  heading {math.degrees(self.heading):+.0f} deg",
                 f"speed {math.hypot(*self.v):.2f} m/s  yaw {self.w:+.2f} rad/s  mode {self.mode}"
                 f"  h {self.height:.2f}  light {self.brightness}"]
        for i, t in enumerate(lines):
            cv2.putText(img, t, (10, 22 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                        cv2.LINE_AA)
        return img
