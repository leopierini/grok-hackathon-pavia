"""Follow a signal by its strength only (docs/Lidar + SLAM.md §8 stage 5 v1, §8b demo mode).

Pure logic: no I/O, no asyncio, no vendor imports. The joystick Controller feeds `Follower.tick`
at ~10 Hz and sends the result through its normal drive path (LiDAR brake, drive mode, caps,
safety envelope). The follower only ever sees an RSSI number, never where the source is.

- `SignalSource`: anything with `read() -> dBm | None`.
- `VirtualBeacon`: demo source. Turns the dog's odometry distance to a point into a fake RSSI
  (-40 - 25 log10(d) dBm, Gaussian noise, clamped). Later the Pi's Wi-Fi RSSI replaces it.
- `Follower`: idle -> following <-> probing -> arrived, plus stopped(reason). Output is forward
  speed + turn rate only (never sideways).
- Dodge: when the joystick passes the LiDAR's free distance per direction (`clear`, see
  patrol.dog.lidar.clearance), a leg whose heading is blocked within DODGE_NEED_M is steered to the
  nearest free heading (within DODGE_CONE_DEG, same side kept while it stays open), and it only walks
  while the way it faces is clear past DODGE_WALK_FREE_M. The joystick's 0.5 m brake and the stuck
  rule stay underneath as the backstop. No `clear` = no dodge (old behaviour).
"""

from __future__ import annotations

import math
import random
from collections import deque
from typing import Callable, NamedTuple, Protocol

# --------------------------------------------------------------- constants (spec §8b, verbatim)
WINDOW_S = 4.0           # sample window for the plane fit
MIN_SAMPLES = 6
MIN_SPREAD_M = 0.4       # samples must cover at least this much ground
MIN_GRAD_DB_M = 1.5      # weaker slope = "the samples don't tell" -> probe
ARRIVE_DBM = -38.0       # ~0.8 m from the virtual point (was -43 = 1.3 m: stopped too far, real dog 2026-11-04)
RESUME_DBM = -43.0       # ~1.3 m: hysteresis, so "arrived" doesn't jitter
RUN_LIMIT_S = 60.0
MAX_VX = 0.3             # m/s forward (never backward, never sideways)
MAX_VYAW = 0.5           # rad/s
K_YAW = 1.5              # turn rate per rad of heading error
HEADING_OK_RAD = 0.5     # walk only when pointing within this of the goal heading
LEG_M = 1.0              # walk ~1 m, then re-estimate
PROBE_STEP_M = 0.6
PROBE_ANGLE_RAD = math.radians(75)   # probes / stuck turns: 60-90 deg from the current heading
PROBE_MEMORY_S = 10.0    # don't re-probe a direction tried this recently
TRIED_SAME_RAD = math.radians(45)
BACKTRACK_RAD = math.radians(60)     # estimate points back along the leg just walked => passed the peak
STUCK_MOVE_M = 0.15
STUCK_WINDOW_S = 4.0
BRAKE_STUCK_S = 1.0      # braked this long while asking for forward => stuck (was 2.0 before the dodge)
MEDIAN_N = 5
EMA_ALPHA = 0.3
RECENCY_S = 2.0          # sample weight = exp(-age / RECENCY_S)
RIDGE_M2 = 0.01          # keeps the fit sane along an unobserved axis (samples on a line)
NEAR_STOP_M = 0.5        # nearest obstacle ahead below this counts as "braked" (= lidar.BRAKE_DISTANCE_M)
DODGE_NEED_M = 0.8       # a heading counts as free when nothing is closer than this along it
DODGE_RELEASE_M = 1.0    # while dodging, the goal heading must be clear past this to stop dodging
DODGE_CONE_DEG = 120     # search this far either side of the goal heading; beyond => blocked, probe
DODGE_WALK_FREE_M = 0.6  # while dodging, walk only if the way the dog FACES is clear past this (> brake 0.5)
TURN_RADIUS_M = 0.50     # no body point is farther than ~0.40 m from the centre (0.35 x 0.20 half-size):
                         # turning in place only hits things closer than that; +0.10 m for LiDAR lag
                         # (near_m is from the last frame, <= 5 Hz) and the coarse voxel map
TURN_ROOM_MIN_DEG = 20   # turn toward a side only if the swept footprint has this much room (lag margin)
TURN_CHECK_MAX = 90      # = lidar.TURN_CHECK_MAX_DEG: less room than this on a side => turn slowly
STEP_OUT_MAX_M = 0.4     # turn guard "step out straight": at most this far, then hold still
DODGE_LEG_FACTOR = 2.0   # a dodging leg ends after this x its length (or DODGE_MAX_S) => re-check the signal
DODGE_MAX_S = 10.0       # > a slow 120 deg turn (0.25 rad/s => ~8 s)
TURN_SLOW_M = 0.6        # something this close: turn at most TURN_SLOW_VYAW
TURN_SLOW_VYAW = 0.25

BEACON_TX_DBM = -40.0
BEACON_PATH_LOSS = 25.0  # 10 * n, n = 2.5 (typical indoors)
BEACON_MIN_D = 0.3
RSSI_MIN, RSSI_MAX = -95.0, -30.0

Pose = tuple  # (x, y, yaw, ground_z | None), patrol.dog.lidar.Pose


def wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _clear_ok(c) -> bool:
    """A usable LiDAR "clear" block: {"yaw": finite, "m": list of finite floats}."""
    try:
        m = c["m"]
        n = c.get("near_m")
        return (math.isfinite(float(c["yaw"])) and isinstance(m, (list, tuple)) and len(m) >= 8
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in m)
                and (n is None or (isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n))))
    except Exception:
        return False


def _room_ok(r) -> bool:
    """turn_room absent (None) or two finite non-negative numbers (left_deg, right_deg)."""
    if r is None:
        return True
    return (isinstance(r, (list, tuple)) and len(r) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
                    for v in r))


class SignalSource(Protocol):
    def read(self) -> float | None: ...


class VirtualBeacon:
    """Simulated signal source at a fixed odom-frame point (demo mode)."""

    def __init__(self, point_xy: tuple[float, float], pose_fn: Callable[[], Pose | None], *,
                 rng: random.Random | None = None, noise_db: float = 3.0) -> None:
        self.point_xy = (float(point_xy[0]), float(point_xy[1]))
        self.pose_fn = pose_fn
        self.rng = rng if rng is not None else random.Random()
        self.noise_db = float(noise_db)

    def move_to(self, point_xy: tuple[float, float]) -> None:
        self.point_xy = (float(point_xy[0]), float(point_xy[1]))

    def distance(self) -> float | None:
        pose = self.pose_fn()
        if pose is None:
            return None
        return math.hypot(self.point_xy[0] - pose[0], self.point_xy[1] - pose[1])

    def read(self) -> float | None:
        d = self.distance()
        if d is None:
            return None
        noise = self.rng.gauss(0.0, self.noise_db) if self.noise_db > 0 else 0.0
        v = BEACON_TX_DBM - BEACON_PATH_LOSS * math.log10(max(d, BEACON_MIN_D)) + noise
        return _clamp(v, RSSI_MIN, RSSI_MAX)


class FollowCommand(NamedTuple):
    vx: float
    vyaw: float
    state: str
    reason: str | None
    est_dir_rad: float | None
    rssi_smoothed: float | None


class Fit(NamedTuple):
    ok: bool
    direction: float | None   # odom-frame heading of rising RSSI
    grad_db_m: float
    n: int
    spread_m: float


def fit_direction(samples, now: float, *, window_s: float = WINDOW_S, min_samples: int = MIN_SAMPLES,
                  min_spread_m: float = MIN_SPREAD_M, min_grad: float = MIN_GRAD_DB_M) -> Fit:
    """Recency-weighted least-squares plane rssi ~ a + b x + c y over (t, x, y, rssi) samples
    from the last `window_s`. Direction = atan2(c, b) when the fit is good."""
    pts = [s for s in samples if now - s[0] <= window_s]
    n = len(pts)
    if n == 0:
        return Fit(False, None, 0.0, 0, 0.0)
    xs, ys = [p[1] for p in pts], [p[2] for p in pts]
    spread = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    ws = [math.exp(-max(0.0, now - p[0]) / RECENCY_S) for p in pts]
    W = sum(ws)
    mx = sum(w * p[1] for w, p in zip(ws, pts)) / W
    my = sum(w * p[2] for w, p in zip(ws, pts)) / W
    mr = sum(w * p[3] for w, p in zip(ws, pts)) / W
    sxx = sxy = syy = sxr = syr = 0.0
    for w, (_, x, y, r) in zip(ws, pts):
        dx, dy, dr = x - mx, y - my, r - mr
        sxx += w * dx * dx
        sxy += w * dx * dy
        syy += w * dy * dy
        sxr += w * dx * dr
        syr += w * dy * dr
    lam = RIDGE_M2 * W
    a11, a22 = sxx + lam, syy + lam
    det = a11 * a22 - sxy * sxy
    if det <= 1e-12:
        return Fit(False, None, 0.0, n, spread)
    b = (a22 * sxr - sxy * syr) / det
    c = (a11 * syr - sxy * sxr) / det
    grad = math.hypot(b, c)
    ok = n >= min_samples and spread >= min_spread_m and grad >= min_grad
    return Fit(ok, math.atan2(c, b) if grad > 0 else None, grad, n, spread)


def steer(heading_err: float, *, k: float = K_YAW, max_vx: float = MAX_VX, max_vyaw: float = MAX_VYAW,
          ok_rad: float = HEADING_OK_RAD) -> tuple[float, float]:
    """Turn toward the goal; walk forward at max_vx only when pointing within ok_rad of it."""
    vyaw = _clamp(k * heading_err, -max_vyaw, max_vyaw)
    vx = max_vx if abs(heading_err) < ok_rad else 0.0
    return vx, vyaw


class _Leg:
    __slots__ = ("heading", "length", "kind", "start", "from_block", "turn_blocked", "from_turn_block")

    def __init__(self, heading: float, length: float, kind: str) -> None:
        self.heading = heading
        self.length = length
        self.kind = kind          # "following" | "probing"
        self.start: tuple[float, float] | None = None
        self.from_block = False   # probe started because the dodge found nothing free: don't re-probe
        self.turn_blocked = False # the turn guard closed both ways on this leg: no more turning attempts
        self.from_turn_block = False  # leg chosen because the previous one couldn't be turned to


class Follower:
    """Signal-following state machine. Feed it `tick` at ~10 Hz; send what it returns."""

    def __init__(self, *, max_vx: float = MAX_VX, max_vyaw: float = MAX_VYAW,
                 arrive_dbm: float = ARRIVE_DBM, resume_dbm: float = RESUME_DBM,
                 run_limit_s: float = RUN_LIMIT_S, window_s: float = WINDOW_S,
                 probe_step_m: float = PROBE_STEP_M, leg_m: float = LEG_M, k_yaw: float = K_YAW,
                 heading_ok_rad: float = HEADING_OK_RAD, min_samples: int = MIN_SAMPLES,
                 min_spread_m: float = MIN_SPREAD_M, min_grad_db_m: float = MIN_GRAD_DB_M,
                 stuck_move_m: float = STUCK_MOVE_M, stuck_window_s: float = STUCK_WINDOW_S,
                 brake_stuck_s: float = BRAKE_STUCK_S, probe_memory_s: float = PROBE_MEMORY_S,
                 median_n: int = MEDIAN_N, ema_alpha: float = EMA_ALPHA) -> None:
        self.max_vx, self.max_vyaw = max_vx, max_vyaw
        self.arrive_dbm, self.resume_dbm = arrive_dbm, resume_dbm
        self.run_limit_s, self.window_s = run_limit_s, window_s
        self.probe_step_m, self.leg_m, self.k_yaw, self.heading_ok_rad = probe_step_m, leg_m, k_yaw, heading_ok_rad
        self.min_samples, self.min_spread_m, self.min_grad_db_m = min_samples, min_spread_m, min_grad_db_m
        self.stuck_move_m, self.stuck_window_s, self.brake_stuck_s = stuck_move_m, stuck_window_s, brake_stuck_s
        self.probe_memory_s, self.median_n, self.ema_alpha = probe_memory_s, median_n, ema_alpha
        self.state = "idle"
        self.reason: str | None = None
        self.t0: float | None = None
        self.t_end: float | None = None
        self._side = 1.0              # next probe / stuck turn: +1 left, -1 right (alternates, kept across runs)
        self.bad_turn_room = 0        # LiDAR views whose turn_room was malformed (logged by the joystick)
        self._reset()

    def _reset(self) -> None:
        self._raw: deque = deque(maxlen=self.median_n)
        self._ema: float | None = None
        self.rssi_smoothed: float | None = None
        self._samples: deque = deque()
        self._leg: _Leg | None = None
        self._done_heading: float | None = None   # heading of the following leg that just finished
        self._tried: list[tuple[float, float]] = []
        self._last_vx = 0.0
        self._fwd_hist: deque = deque()
        self._fwd_since: float | None = None
        self._brake_since: float | None = None
        self.est_dir_rad: float | None = None
        self.note: str | None = None
        self._clear: dict | None = None
        self.dodge_side: float | None = None      # +1 left / -1 right while dodging, else None
        self._dodge_since: float | None = None
        self._step_out_from: tuple[float, float] | None = None
        self._turn_latch: tuple | None = None     # (leg, sign): going the long way round on this leg

    @property
    def active(self) -> bool:
        return self.state in ("following", "probing", "arrived")

    # ------------------------------------------------------------ lifecycle
    def start(self, now: float) -> None:
        self._reset()
        self.state, self.reason, self.t0, self.t_end = "following", None, now, None

    def stop(self, reason: str, now: float | None = None) -> None:
        """End the run (any reason). The first reason sticks."""
        if self.state == "stopped":
            return
        self.state, self.reason = "stopped", reason
        if now is not None and self.t0 is not None:
            self.t_end = now
        self._leg = None

    def elapsed(self, now: float) -> float:
        if self.t0 is None:
            return 0.0
        end = self.t_end if self.t_end is not None else now
        return min(max(0.0, end - self.t0), self.run_limit_s)

    # ------------------------------------------------------------ pieces (also used by tests)
    def smooth(self, rssi: float) -> float:
        """Median of the last MEDIAN_N readings, then EMA (alpha EMA_ALPHA)."""
        self._raw.append(float(rssi))
        vals = sorted(self._raw)
        m = len(vals)
        med = vals[m // 2] if m % 2 else 0.5 * (vals[m // 2 - 1] + vals[m // 2])
        self._ema = med if self._ema is None else self.ema_alpha * med + (1 - self.ema_alpha) * self._ema
        self.rssi_smoothed = self._ema
        return self._ema

    def reestimate(self) -> None:
        """Drop the current leg: the next tick decides again from the fit (e.g. the source moved)."""
        self._leg = None
        self._done_heading = None

    def force_leg(self, heading: float, length: float) -> None:
        """Tests: walk `length` m along `heading` (as if the fit had said so)."""
        self._leg = _Leg(heading, length, "following")
        self.state = "following"
        self.note = None

    # ------------------------------------------------------------ main step
    def _cmd(self, vx: float, vyaw: float, reason: str | None = None) -> FollowCommand:
        self._last_vx = vx
        if reason is not None:
            self.note = reason
        r = self.reason if self.state == "stopped" else self.note
        return FollowCommand(vx, vyaw, self.state, r, self.est_dir_rad, self.rssi_smoothed)

    def tick(self, now: float, pose: Pose | None, rssi: float | None,
             nearest_ahead_m: float | None, braking: bool, clear: dict | None = None) -> FollowCommand:
        self._clear = clear if _clear_ok(clear) else None
        if self._clear is not None and not _room_ok(self._clear.get("turn_room")):
            # A bad swept-turn field must not switch the whole guard off: drop just it (radial fallback).
            self._clear = {**self._clear, "turn_room": None}
            self.bad_turn_room += 1
        if self.state in ("idle", "stopped"):
            return self._cmd(0.0, 0.0)
        if self.t0 is not None and now - self.t0 >= self.run_limit_s:
            self.stop("time limit", now)
            return self._cmd(0.0, 0.0)
        if pose is None:
            return self._cmd(0.0, 0.0, "position unknown")
        if rssi is None:
            return self._cmd(0.0, 0.0, "no signal")
        x, y, yaw = float(pose[0]), float(pose[1]), float(pose[2])
        rs = self.smooth(rssi)
        self._samples.append((now, x, y, rs))
        while self._samples and now - self._samples[0][0] > self.window_s:
            self._samples.popleft()
        fit = fit_direction(self._samples, now, window_s=self.window_s, min_samples=self.min_samples,
                            min_spread_m=self.min_spread_m, min_grad=self.min_grad_db_m)
        self.est_dir_rad = fit.direction if fit.ok else None

        if self.state == "arrived":
            if rs >= self.resume_dbm:
                return self._cmd(0.0, 0.0)
            self.state, self._leg = "following", None
            self.note = f"signal dropped below {self.resume_dbm:g} dBm: resuming"
        elif rs >= self.arrive_dbm and len(self._raw) >= self.median_n:   # never on the first noisy reading
            self.state, self._leg = "arrived", None
            self._fwd_since, self._brake_since = None, None
            return self._cmd(0.0, 0.0, f"signal {rs:.1f} dBm >= {self.arrive_dbm:g} dBm")

        stuck = self._stuck(now, x, y, braking, nearest_ahead_m)
        if stuck:
            self._start_probe(now, yaw, stuck, blocked=True)

        for _ in range(3):                       # a finished leg re-decides in the same tick
            if self._leg is None:
                back = (fit.ok and self._done_heading is not None
                        and abs(wrap(fit.direction - self._done_heading - math.pi)) < BACKTRACK_RAD)
                self._done_heading = None
                if back:
                    # A straight leg only tells the slope along itself: pointing back means we passed
                    # the closest point and the source is off to one side. Probe sideways, don't retrace.
                    self._start_probe(now, yaw, "passed the peak: probing sideways")
                elif fit.ok:
                    self._leg = _Leg(fit.direction, self.leg_m, "following")
                    self.state = "following"
                    self.note = f"uphill {math.degrees(fit.direction):.0f} deg, {fit.grad_db_m:.1f} dB/m"
                else:
                    why = (f"{fit.n} samples" if fit.n < self.min_samples else
                           f"spread {fit.spread_m:.2f} m" if fit.spread_m < self.min_spread_m else
                           f"slope {fit.grad_db_m:.1f} dB/m")
                    self._start_probe(now, yaw, f"signal unclear ({why})")
            leg = self._leg
            heading, dodging = leg.heading, False
            if self._clear is not None:
                heading, dodging, blocked_note = self._dodge(leg.heading)
                if blocked_note is not None:
                    if leg.kind == "following" or not getattr(leg, "from_block", False):
                        self._start_probe(now, yaw, blocked_note, freest=heading)
                        self._leg.from_block = True
                        continue
                    self.note = blocked_note       # boxed in: hold still, the 60 s limit / STOP end it
                    return self._cmd(0.0, 0.0)
            vx, vyaw = steer(wrap(heading - yaw), k=self.k_yaw, max_vx=self.max_vx,
                             max_vyaw=self.max_vyaw, ok_rad=self.heading_ok_rad)
            if dodging and vx > 0 and (self._free(yaw) or 0.0) < DODGE_WALK_FREE_M:
                vx = 0.0                           # facing the obstacle: turn first, don't push at it
            if dodging:
                if self._dodge_since is None:
                    self._dodge_since = now
                walked = 0.0 if leg.start is None else math.hypot(x - leg.start[0], y - leg.start[1])
                if walked >= DODGE_LEG_FACTOR * leg.length or now - self._dodge_since >= DODGE_MAX_S:
                    # Bounded: never follow a wall for metres without asking the signal again.
                    took = now - self._dodge_since
                    self.dodge_side, self._dodge_since = None, None
                    self._start_probe(now, yaw, f"dodge took {walked:.1f} m / {took:.0f} s: re-checking the signal")
                    continue
            else:
                self._dodge_since = None
            near_c = self._clear.get("near_m") if self._clear is not None else None
            room = self._clear.get("turn_room") if self._clear is not None else None
            if room is not None:
                # Swept-footprint check from the LiDAR: turn only toward a side with real room.
                room_of = lambda sg: room[0] if sg > 0 else room[1]
                latch = self._turn_latch
                if latch is not None and latch[0] is leg and room_of(latch[1]) < TURN_ROOM_MIN_DEG:
                    leg.turn_blocked = True                  # both ways tried and closed: stop trying
                if latch is not None and (latch[0] is not leg or abs(wrap(heading - yaw)) < self.heading_ok_rad
                                          or room_of(latch[1]) < TURN_ROOM_MIN_DEG):
                    latch = self._turn_latch = None          # new leg, facing it, or that side closed up
                if leg.turn_blocked and vyaw != 0.0:
                    blocked_turn = True
                elif latch is not None and vyaw != 0.0:
                    vyaw, vx, blocked_turn = latch[1] * TURN_SLOW_VYAW, 0.0, False
                elif vyaw == 0.0 or room_of(vyaw) >= TURN_ROOM_MIN_DEG:
                    blocked_turn = False
                elif room_of(-vyaw) >= TURN_CHECK_MAX and vx == 0.0:
                    # The near way is blocked, the far way is wide open: go the long way round, and
                    # keep going that way (latched) so it can't dither at the room threshold.
                    sg = -math.copysign(1.0, vyaw)
                    self._turn_latch = (leg, sg)
                    vyaw, blocked_turn = sg * TURN_SLOW_VYAW, False
                    self.note = f"no room to turn {'right' if sg > 0 else 'left'}: turning the other way round"
                else:
                    blocked_turn = True
                if not blocked_turn and vyaw != 0.0 and (min(room) < TURN_CHECK_MAX
                                                         or (near_c is not None and near_c < TURN_SLOW_M)):
                    vyaw = _clamp(vyaw, -TURN_SLOW_VYAW, TURN_SLOW_VYAW)
            else:                                  # no swept check in the view: radial fallback
                blocked_turn = vyaw != 0.0 and near_c is not None and near_c < TURN_RADIUS_M
            if not blocked_turn:
                self._step_out_from = None
            if blocked_turn:
                # Turning would swing a corner into something: step out straight (bounded), else hold.
                if self._step_out_from is None:
                    self._step_out_from = (x, y)
                out = math.hypot(x - self._step_out_from[0], y - self._step_out_from[1])
                if (self._free(yaw) or 0.0) >= DODGE_WALK_FREE_M and out < STEP_OUT_MAX_M:
                    return self._cmd(self.max_vx, 0.0, f"obstacle {near_c if near_c is not None else 0:.2f} m "
                                                       f"from the body: stepping out straight before it can turn")
                if room is not None and not leg.from_turn_block:
                    # Can't turn to this leg from here: take a short leg it CAN turn to, then re-decide.
                    sg = 1.0 if room[0] >= room[1] else -1.0
                    if room_of(sg) >= TURN_ROOM_MIN_DEG:
                        h = wrap(yaw + sg * math.radians(room_of(sg) - TURN_ROOM_MIN_DEG / 2))
                        self._leg = _Leg(h, self.probe_step_m, "probing")
                        self._leg.from_turn_block = True
                        self.state, self._turn_latch, self._step_out_from = "probing", None, None
                        self.note = (f"can't turn to {math.degrees(heading):.0f} deg here: short leg "
                                     f"{'left' if sg > 0 else 'right'} {room_of(sg)} deg first")
                        continue
                return self._cmd(0.0, 0.0, f"obstacle {near_c if near_c is not None else 0:.2f} m from the body, "
                                           f"no room to turn and ahead blocked: holding still")
            if room is None and near_c is not None and near_c < TURN_SLOW_M:
                vyaw = _clamp(vyaw, -TURN_SLOW_VYAW, TURN_SLOW_VYAW)
            if vx > 0:
                if leg.start is None:
                    leg.start = (x, y)
                elif (math.hypot(x - leg.start[0], y - leg.start[1]) >= leg.length
                      and not dodging):            # never end a leg half-way round an obstacle
                    self._done_heading = leg.heading if leg.kind == "following" else None
                    self._leg = None
                    continue
            return self._cmd(vx, vyaw)
        return self._cmd(0.0, 0.0)

    # ------------------------------------------------------------ dodge
    def _free(self, heading: float) -> float | None:
        """Free distance (m) along an odom-frame heading from the latest LiDAR bins, or None."""
        c = self._clear
        if c is None:
            return None
        m = c["m"]
        step = 2 * math.pi / len(m)
        i = int(round(wrap(heading - float(c["yaw"])) / step)) % len(m)
        return float(m[i])

    def _dodge(self, goal: float) -> tuple[float, bool, str | None]:
        """(heading to steer, dodging?, blocked note). Goal free => (goal, False, None)."""
        f_goal = self._free(goal)
        release = DODGE_RELEASE_M if self.dodge_side is not None else DODGE_NEED_M   # hysteresis
        if f_goal is None or f_goal >= release:
            if self.dodge_side is not None:
                self.note = "way to the goal is clear again"
            self.dodge_side = None
            return goal, False, None
        m = self._clear["m"]
        step = 2 * math.pi / len(m)
        kmax = int(round(math.radians(DODGE_CONE_DEG) / step))
        free = lambda side, k: self._free(goal + side * k * step) >= DODGE_NEED_M
        pick = None
        if self.dodge_side is not None:          # keep the side while it stays open (no zig-zag)
            pick = next(((self.dodge_side, k) for k in range(1, kmax + 1) if free(self.dodge_side, k)), None)
        if pick is None:
            for k in range(1, kmax + 1):
                opts = [sd for sd in (1.0, -1.0) if free(sd, k)]
                if opts:
                    sd = max(opts, key=lambda sd: self._free(goal + sd * (k + 1) * step))
                    pick = (sd, k)
                    break
        if pick is None:
            self.dodge_side = None
            freest = max(range(len(m)), key=lambda i: m[i])
            h = wrap(float(self._clear["yaw"]) + freest * step)
            if m[freest] < DODGE_NEED_M:
                return h, False, f"blocked all around (best {m[freest]:.2f} m): holding still"
            return h, False, (f"blocked: obstacle {f_goal:.2f} m toward the goal and nothing free "
                              f"within {DODGE_CONE_DEG} deg: probing the freest side")
        sd, k = pick
        self.dodge_side = sd
        h = wrap(goal + sd * k * step)
        self.note = (f"dodging: obstacle {f_goal:.2f} m toward the goal, going "
                     f"{'left' if sd > 0 else 'right'} {math.degrees(k * step):.0f} deg")
        return h, True, None

    # ------------------------------------------------------------ probing + stuck
    def _start_probe(self, now: float, yaw: float, why: str, blocked: bool = False,
                     freest: float | None = None) -> None:
        self._tried = [(t, h) for t, h in self._tried if now - t <= self.probe_memory_s]
        if blocked:
            self._tried.append((now, yaw))
        recent = lambda h: any(abs(wrap(h - th)) < TRIED_SAME_RAD for _, th in self._tried)
        side = self._side
        cands = [yaw + side * PROBE_ANGLE_RAD, yaw - side * PROBE_ANGLE_RAD, yaw + math.pi]
        if freest is not None:
            cands = [freest] + cands
        fresh = [h for h in cands if not recent(h)] or cands[:1]
        if self._clear is not None:              # LiDAR known: first candidate that is free, else the freest
            heading = next((h for h in fresh if self._free(h) >= DODGE_NEED_M),
                           max(fresh, key=lambda h: self._free(h)))
        else:
            heading = fresh[0]
        self._side = -side
        heading = wrap(heading)
        self._tried.append((now, heading))
        self._leg = _Leg(heading, self.probe_step_m, "probing")
        self.state = "probing"
        self.note = why
        self._fwd_hist.clear()
        self._fwd_since, self._brake_since = None, None

    def _stuck(self, now: float, x: float, y: float, braking: bool, near: float | None) -> str | None:
        fwd = self._last_vx > 0
        held = fwd and (braking or (near is not None and near < NEAR_STOP_M))
        if held:
            if self._brake_since is None:
                self._brake_since = now
            elif now - self._brake_since > self.brake_stuck_s:
                return f"stuck: braked for {now - self._brake_since:.1f} s"
        else:
            self._brake_since = None
        if not fwd:
            self._fwd_hist.clear()
            self._fwd_since = None
            return None
        if self._fwd_since is None:
            self._fwd_since = now
        self._fwd_hist.append((now, x, y))
        while len(self._fwd_hist) > 1 and self._fwd_hist[1][0] <= now - self.stuck_window_s:
            self._fwd_hist.popleft()
        t_old, x_old, y_old = self._fwd_hist[0]
        if now - self._fwd_since >= self.stuck_window_s and t_old <= now - self.stuck_window_s + 1e-9:
            moved = math.hypot(x - x_old, y - y_old)
            if moved < self.stuck_move_m:
                return f"stuck: no progress ({moved:.2f} m in {self.stuck_window_s:g} s)"
        return None
