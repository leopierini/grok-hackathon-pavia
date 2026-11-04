"""Simulated Go2 WebRTC connection (no robot, no vendor lib, no network).

Drop-in for `UnitreeWebRTCConnection` via `RealDog(_conn_factory=...)`, so the real
adapter code (caps, timeouts, motion lock) runs unchanged on top of it. Used by
`python -m patrol.dog.joystick --fake` and by the tests.

- Sport `Move` sets a commanded velocity; the body velocity follows it with a short
  lag and integrates into position/heading. A Move expires after `move_expiry_s`.
- StopMove zeroes the command. StandDown lies down slowly, StandUp + BalanceStand
  stand up again. Damp is recorded (tests check it is never sent) and drops the dog.
- VUI brightness get/set (api 1006/1005), obstacle-avoid get/set, motion-mode read.
- Fake camera: a generated top-down image with a moving marker and a timestamp.

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


class SimConn:
    def __init__(self, *, avoid: bool = True, publish_multi: bool = True, hang_on_move: bool = False,
                 standing: bool = True, camera: bool = True, fps: float = 15.0,
                 move_expiry_s: float = 1.0, tau_s: float = 0.15, brightness: int = 0) -> None:
        self.sent: list[tuple] = []          # (topic, api_id, parameter, monotonic time)
        self.avoid = avoid
        self.publish_multi = publish_multi
        self.hang_on_move = hang_on_move
        self.camera = camera
        self.fps = fps
        self.move_expiry_s = move_expiry_s
        self.tau_s = tau_s
        self.brightness = brightness
        self.connects = 0
        # body
        self.x = self.y = self.heading = 0.0
        self.v = [0.0, 0.0]                  # world-frame velocity
        self.w = 0.0
        self.cmd = (0.0, 0.0, 0.0)           # body-frame vx, vy, vyaw
        self.cmd_t = 0.0
        self.height = 0.32 if standing else 0.08
        self.height_target = self.height
        self.mode = 1 if standing else 5
        self.balance_pending = False
        self.soc = 80.0
        self.datachannel = type("DC", (), {})()
        self.datachannel.pub_sub = SimPubSub(self)
        self.video = SimVideo(self)
        self._task: asyncio.Task | None = None
        self._frame_n = 0

    # ---------------------------------------------------------- connection
    async def connect(self):
        self.connects += 1
        self.datachannel.pub_sub.subs = {}
        self.video.cb = None
        self._task = asyncio.get_running_loop().create_task(self._stream())

    async def disconnect(self):
        if self._task:
            self._task.cancel()
            self._task = None
        self.video.stop()

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
            elif api == 1003:                                # StopMove
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
            return _ok()
        if topic == "MOTION_SWITCHER" and api == 1001:
            return _ok({"name": "normal"})
        return _ok()

    def _standing(self) -> bool:
        return self.mode in (0, 1, 2, 3) and self.height >= 0.25

    # ---------------------------------------------------------- physics + state
    def _step(self, dt: float) -> None:
        now = time.monotonic()
        if now - self.cmd_t > self.move_expiry_s:
            self.cmd = (0.0, 0.0, 0.0)
        if not self._standing():
            self.cmd = (0.0, 0.0, 0.0)
        cvx, cvy, cw = self.cmd
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
                        "obstaclesAvoidSwitch": self.avoid, "brightness": self.brightness, "volume": 0})})
            await asyncio.sleep(1.0 / SPORT_STATE_HZ)

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
