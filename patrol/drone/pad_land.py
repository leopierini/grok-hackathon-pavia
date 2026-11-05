"""Land on a mission pad by steering on the pad's own x and y, ten times a second.

`go x y z speed mN` stops a few centimeters off and keeps stopping at the same
offset, and it refuses to hover lower than about 30 cm, so the last drop is
blind. Here the sticks close the loop instead: the drone reads where the pad
center is, nudges toward it, and only sinks while it is centered.

The pad's x and y are in the pad's frame, not the drone's, and the drone can
face the pad any way round. Two short stick pulses at the start measure which
way "forward" and "right" move the drone over the pad, so no sign is guessed.
"""

from __future__ import annotations

import math
import time

TICK_S = 0.1
PULSE_STICK = 20
PULSE_S = 0.5
SETTLE_S = 0.7
MIN_PULSE_CM = 3.0
KP = 0.7
KI = 0.25
I_LIMIT = 8.0
STICK_MAX = 15
STICK_MIN = 5
SINK_STICK = -12
CENTER_CM = 2.0
SINK_CM = 5.0
LOW_Z_CM = 30
STEADY_TICKS = 5
LOST_S = 1.0
SERVO_LIMIT_S = 30.0


def visible(snap: dict, wanted: int | None) -> bool:
    mid = snap.get("mid")
    if mid is None or not 1 <= int(mid) <= 8:
        return False
    return wanted is None or int(mid) == int(wanted)


def clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def stick(cm_per_s: float) -> int:
    """Round a stick command, and lift tiny ones above the Tello's dead zone."""
    value = clamp(cm_per_s, STICK_MAX)
    if abs(value) < 0.5:
        return 0
    if abs(value) < STICK_MIN:
        value = math.copysign(STICK_MIN, value)
    return int(round(value))


class PadLander:
    """Calibrate the stick directions over the pad, then center and sink on the sticks."""

    low_z_cm = LOW_Z_CM
    center_cm = CENTER_CM
    sink_cm = SINK_CM
    what = "pad"

    def __init__(self, sdk, wanted: int | None, say=print, sleep=time.sleep) -> None:
        self.sdk = sdk
        self.wanted = wanted
        self.say = say
        self.sleep = sleep
        self.forward: tuple[float, float] | None = None
        self.right: tuple[float, float] | None = None
        self.last: tuple[float, float, int | None] | None = None
        self.pulse_stick = PULSE_STICK
        self.pulse_s = PULSE_S
        self._miss: str | None = None

    def _rc(self, lr: int = 0, fb: int = 0, ud: int = 0) -> None:
        self.sdk.send(f"rc {lr} {fb} {ud} 0")

    def _fresh(self, after: float, timeout: float = 0.6) -> dict:
        """The first telemetry packet newer than `after`; the latest one if none comes."""
        deadline = time.monotonic() + timeout
        snap = self.sdk.snapshot()
        while snap.get("at", after + 1) <= after and time.monotonic() < deadline:
            self.sleep(0.02)
            snap = self.sdk.snapshot()
        return snap

    def _read(self, after: float, timeout: float) -> tuple[float, float, int | None] | None:
        """Target offset (x, y in cm) and height, measured after `after`; None when out of view."""
        snap = self._fresh(after, timeout)
        if not visible(snap, self.wanted) or snap.get("x") is None or snap.get("y") is None:
            return None
        return float(snap["x"]), float(snap["y"]), snap.get("z")

    def _where(self) -> tuple[float, float] | None:
        reading = self._read(time.monotonic(), 0.6)
        if reading is None:
            return None
        self.last = reading
        return reading[0], reading[1]

    def _drive(self, lr: int, fb: int) -> None:
        end = time.monotonic() + self.pulse_s
        while time.monotonic() < end:
            self._rc(lr, fb)
            self.sleep(TICK_S)
        self._rc()
        self.sleep(SETTLE_S)

    def _pulse(self, lr: int, fb: int) -> tuple[float, float] | None:
        before = self._where()
        if before is None:
            return None
        self._drive(lr, fb)
        after = self._where()
        if after is None:
            self._drive(-lr, -fb)
            return None
        return after[0] - before[0], after[1] - before[1]

    def _measured(self, lr: int, fb: int) -> tuple[float, float] | None:
        moved = self._pulse(lr, fb)
        if moved is None:
            self.say(f"{self.what} left the picture ({self._miss or 'no reading'}); back, and again")
            moved = self._pulse(lr, fb)
        return moved

    def calibrate(self) -> bool:
        """Forward then back, right then left, so the drone ends where it started."""
        stick = self.pulse_stick
        forward = self._measured(0, stick)
        back = self._measured(0, -stick)
        right = self._measured(stick, 0)
        left = self._measured(-stick, 0)
        if None in (forward, back, right, left):
            self.say(f"{self.what} lost while measuring the sticks ({self._miss or 'no reading'})")
            return False
        f = ((forward[0] - back[0]) / 2, (forward[1] - back[1]) / 2)
        r = ((right[0] - left[0]) / 2, (right[1] - left[1]) / 2)
        f_len, r_len = math.hypot(*f), math.hypot(*r)
        if f_len < MIN_PULSE_CM or r_len < MIN_PULSE_CM:
            self.say(f"stick pulses barely moved the drone ({f_len:.0f}, {r_len:.0f} cm)")
            return False
        f_unit = (f[0] / f_len, f[1] / f_len)
        r_unit = (r[0] / r_len, r[1] / r_len)
        cross = f_unit[0] * r_unit[1] - f_unit[1] * r_unit[0]
        if abs(cross) < 0.7:
            self.say(f"forward and right are not square over the pad ({cross:.2f})")
            return False
        self.forward, self.right = f_unit, r_unit
        self.say(f"sticks over the {self.what} ({f_len:.1f}, {r_len:.1f} cm): forward {f_unit[0]:+.2f},{f_unit[1]:+.2f} right {r_unit[0]:+.2f},{r_unit[1]:+.2f}")
        return True

    def _split(self, dx: float, dy: float) -> tuple[float, float]:
        """How far to move along forward and along right to cover (dx, dy) on the pad."""
        f, r = self.forward, self.right
        det = f[0] * r[1] - f[1] * r[0]
        along_f = (dx * r[1] - dy * r[0]) / det
        along_r = (f[0] * dy - f[1] * dx) / det
        return along_f, along_r

    def servo(self) -> str:
        """Center within `center_cm`, sink while within `sink_cm`, land from `low_z_cm`.

        The integral term takes out a steady push, like a draft or a trim
        that makes `go` stop at the same offset every time.
        """
        assert self.forward is not None and self.right is not None
        sum_f = sum_r = 0.0
        steady = 0
        lost_since: float | None = None
        started = time.monotonic()
        last_tick = started
        while time.monotonic() - started < SERVO_LIMIT_S:
            now = time.monotonic()
            dt = min(0.3, now - last_tick)
            last_tick = now
            reading = self._read(now - TICK_S, 0.3)
            if reading is None:
                self._rc()
                low = self.last is not None and self.last[2] is not None and self.last[2] <= self.low_z_cm + 10
                if low:
                    return self._note(f"{self.what} out of view just above it; landing")
                lost_since = lost_since or now
                if now - lost_since > LOST_S:
                    return self._note(f"{self.what} lost; landing in place")
                self.sleep(TICK_S)
                continue
            lost_since = None
            x, y, z = reading
            self.last = reading
            off = math.hypot(x, y)
            along_f, along_r = self._split(-x, -y)
            sum_f = clamp(sum_f + along_f * dt, I_LIMIT / KI)
            sum_r = clamp(sum_r + along_r * dt, I_LIMIT / KI)
            # The smallest stick that moves the drone crosses the center circle in
            # one tick, so inside it the sticks rest rather than hunt.
            inside = off <= self.center_cm
            fb = 0 if inside else stick(KP * along_f + KI * sum_f)
            lr = 0 if inside else stick(KP * along_r + KI * sum_r)
            low = z is not None and int(z) <= self.low_z_cm
            ud = SINK_STICK if off <= self.sink_cm and not low else 0
            steady = steady + 1 if low and inside else 0
            self._rc(lr, fb, ud)
            if steady >= STEADY_TICKS:
                self._rc()
                return self._note(f"{self.what} centered at {x:.1f}, {y:.1f} cm, {z} cm up")
            self.sleep(max(0.0, TICK_S - (time.monotonic() - now)))
        self._rc()
        return self._note(f"{self.what} centering ran out of time; landing")

    def _note(self, text: str) -> str:
        self.say(text)
        return text
