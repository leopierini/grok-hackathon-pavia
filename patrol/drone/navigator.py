"""What the drone does next, from what the reflex and Jev saw. No radio here.

The reflex reads meters ahead from the newest frame about ten times a
second. Jev reads the newest frame about twice a second and says whether
something is close, which way to steer, and whether a person is in view.
Either one can brake the drone; it only speeds up when both agree.

Headings are degrees clockwise from where the drone faced at takeoff.
x is meters forward along heading 0, y meters to its right.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

CELL_M = 0.5
VISITED_WEIGHT = 0.5
BACK_WEIGHT = 0.35
AVOID_DEG = 30.0
SMOOTH = 0.4
YAW_SMOOTH = 0.35
BALANCE_GAIN = 2.0
STEER_RESET_S = 0.5


@dataclass(frozen=True)
class Limits:
    cruise_mps: float = 0.5
    brake_m: float = 1.0
    slow_m: float = 2.0
    slow_mps: float = 0.2
    reflex_only_mps: float = 0.2
    reflex_stale_s: float = 0.5
    jev_fresh_s: float = 1.5
    jev_slow_s: float = 3.0
    jev_brake_s: float = 6.0
    blocked_limit: float = 0.5
    person_limit: float = 0.6
    person_streak: int = 2
    steer_dps: float = 20.0
    steer_confidence: float = 0.3
    side_steer_dps: float = 40.0
    side_gentle: float = 0.25
    side_deadband: float = 0.08
    clear_margin_m: float = 0.5
    room_min_m: float = 1.0
    geofence_m: float = 4.0

    @property
    def clear_m(self) -> float:
        """A heading picked after a scan needs this much room by the reflex."""
        return self.brake_m + self.clear_margin_m


@dataclass(frozen=True)
class Command:
    mode: str
    fb_mps: float = 0.0
    yaw_dps: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class Seen:
    """One Jev guide answer and the capture time of the frame it judged."""

    blocked: float
    steer: str
    steer_confidence: float
    person: float
    at: float


@dataclass
class Pose:
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    visited: set = field(default_factory=lambda: {(0, 0)})

    def advance(self, fb_mps: float, seconds: float) -> None:
        rad = math.radians(self.heading)
        self.x += fb_mps * seconds * math.cos(rad)
        self.y += fb_mps * seconds * math.sin(rad)
        self.visited.add(self.cell())

    def turn_to(self, heading: float) -> None:
        self.heading = heading % 360

    def cell(self, x: float | None = None, y: float | None = None) -> tuple[int, int]:
        x = self.x if x is None else x
        y = self.y if y is None else y
        return (round(x / CELL_M), round(y / CELL_M))

    def ahead(self, heading: float, meters: float) -> tuple[float, float]:
        rad = math.radians(heading)
        return self.x + meters * math.cos(rad), self.y + meters * math.sin(rad)

    def distance(self) -> float:
        return math.hypot(self.x, self.y)

    def leaves(self, heading: float, geofence_m: float, meters: float = 1.0) -> bool:
        """Flying `meters` this way ends outside the fence, and farther out than now."""
        x, y = self.ahead(heading, meters)
        out = math.hypot(x, y)
        return out > geofence_m and out > self.distance()

    def seen_ahead(self, heading: float, meters: float = 1.0) -> bool:
        return self.cell(*self.ahead(heading, meters)) in self.visited


def obstacle_m(reading) -> float:
    """The closer of the horizon and the floor. The floor is absent on old readings."""
    near = getattr(reading, "near_m", None)
    if near is None:
        return reading.center_m
    return min(reading.center_m, near)


def speed_for(distance_m: float, limits: Limits) -> float:
    """Full cruise from `slow_m` out, nothing inside `brake_m`, a straight ramp between."""
    if distance_m < limits.brake_m:
        return 0.0
    if distance_m >= limits.slow_m:
        return limits.cruise_mps
    share = (distance_m - limits.brake_m) / (limits.slow_m - limits.brake_m)
    return limits.cruise_mps * share


class Navigator:
    """Per tick: hold, cruise at some speed, scan, or stop for a person."""

    def __init__(self, limits: Limits, brain: str = "jev", started_at: float = 0.0) -> None:
        if brain not in ("local", "jev", "reflex-only"):
            raise ValueError(brain)
        self.limits = limits
        self.brain = brain
        self.started_at = started_at
        self.pose = Pose()
        self._last_seen_at: float | None = None
        self._person_count = 0
        self.stop_on_person = True
        self._sides: tuple[float, float, float] | None = None
        self._sides_at = 0.0
        self._closing_mps = 0.0
        self._yaw = 0.0
        self._steered_at = -math.inf

    def note(self, seen: Seen) -> None:
        """Count a new Jev answer. Two in a row with a person in view stop the drone."""
        if self._last_seen_at is not None and seen.at <= self._last_seen_at:
            return
        self._last_seen_at = seen.at
        if seen.person >= self.limits.person_limit:
            self._person_count += 1
        else:
            self._person_count = 0

    def reset_person(self) -> None:
        self._person_count = 0

    def step(self, now: float, reading, seen: Seen | None) -> Command:
        limits = self.limits
        if reading is None or now - reading.at > limits.reflex_stale_s:
            return Command("hold", reason="reflex stale")
        near = obstacle_m(reading)
        if near < limits.brake_m:
            return Command("scan", reason=f"obstacle {near:.2f} m")
        if self.pose.leaves(self.pose.heading, limits.geofence_m, meters=0.5):
            return Command("scan", reason="geofence")
        speed = speed_for(near, limits)
        yaw = 0.0
        if self.brain == "reflex-only":
            yaw = self._side_steer(now, reading)
            speed = min(self._turning_speed(speed, yaw), limits.reflex_only_mps)
            return Command("cruise", speed, yaw, "reflex only")
        if seen is not None and now - seen.at <= limits.jev_fresh_s:
            if seen.blocked >= limits.blocked_limit:
                return Command("scan", reason=f"jev blocked {seen.blocked:.2f}")
            if self.stop_on_person and self._person_count >= limits.person_streak:
                return Command("person", reason=f"person {seen.person:.2f}")
            if seen.steer != "straight" and seen.steer_confidence >= limits.steer_confidence:
                yaw = limits.steer_dps if seen.steer == "right" else -limits.steer_dps
            elif self.brain == "local":
                yaw = self._side_steer(now, reading)
                speed = self._turning_speed(speed, yaw)
            return Command("cruise", speed, yaw, "clear")
        last = seen.at if seen is not None else self.started_at
        silence = now - last
        if silence > limits.jev_brake_s:
            return Command("scan", reason=f"jev silent {silence:.1f} s")
        if self.brain == "local":
            yaw = self._side_steer(now, reading)
            speed = self._turning_speed(speed, yaw)
        if silence > limits.jev_slow_s:
            return Command("cruise", min(speed, limits.slow_mps), yaw, "jev late")
        return Command("cruise", min(speed, limits.cruise_mps / 2), yaw, "jev pending")

    def _side_steer(self, now: float, reading) -> float:
        """Always lean toward the roomier side: gently in the open, hard when the way ahead closes in.

        Each new reflex reading updates a running average of the three
        distances and how fast the middle one is shrinking. A pause longer
        than STEER_RESET_S (a scan, a turn) starts the averages over, since
        the view behind them is gone.
        """
        limits = self.limits
        sides = (reading.left_m, reading.center_m, reading.right_m)
        if self._sides is None or now - self._steered_at > STEER_RESET_S:
            self._sides, self._sides_at = sides, reading.at
            self._closing_mps = 0.0
            self._yaw = 0.0
        elif reading.at > self._sides_at:
            previous = self._sides
            self._sides = tuple(old + SMOOTH * (new - old) for old, new in zip(previous, sides))
            closing = (previous[1] - self._sides[1]) / (reading.at - self._sides_at)
            self._closing_mps += SMOOTH * (closing - self._closing_mps)
            self._sides_at = reading.at
        self._steered_at = now

        left, center, right = self._sides
        balance = (right - left) / max(right + left, 0.1)
        if abs(balance) < limits.side_deadband:
            balance = 0.0
        near = (limits.slow_m - center) / (limits.slow_m - limits.brake_m)
        closing = self._closing_mps / max(limits.cruise_mps, 0.1)
        urgency = min(1.0, max(0.0, near, closing))
        strength = limits.side_gentle + (1 - limits.side_gentle) * urgency
        target = limits.side_steer_dps * strength * max(-1.0, min(1.0, balance * BALANCE_GAIN))
        self._yaw += YAW_SMOOTH * (target - self._yaw)
        return self._yaw

    def _turning_speed(self, speed: float, yaw: float) -> float:
        """Up to half speed off in the hardest turn, so the drone does not run wide."""
        return speed * (1 - 0.5 * min(1.0, abs(yaw) / self.limits.side_steer_dps))


@dataclass(frozen=True)
class View:
    """One scan direction: reflex meters, and Jev's judgment when there is one."""

    reflex_m: float
    blocked: float | None = None
    room_m: float | None = None
    person: float | None = None


def admits(heading: float, view: View, pose: Pose, limits: Limits) -> str | None:
    """None when the heading may be flown, else why not."""
    if view.reflex_m < limits.clear_m:
        return f"reflex {view.reflex_m:.2f} m"
    if view.blocked is not None and view.blocked >= limits.blocked_limit:
        return f"jev blocked {view.blocked:.2f}"
    if view.room_m is not None and view.room_m < limits.room_min_m:
        return f"jev room {view.room_m:.1f} m"
    if pose.leaves(heading, limits.geofence_m):
        return "geofence"
    return None


def _near(heading: float, others: list[float], degrees: float = AVOID_DEG) -> bool:
    return any(abs((heading - other + 180) % 360 - 180) <= degrees for other in others)


def choose_heading(
    views: dict[float, View],
    jev_choice: float | None,
    pose: Pose,
    limits: Limits,
    back: float | None = None,
    avoid: list[float] | None = None,
) -> tuple[float | None, dict[float, str | None]]:
    """Jev's pick when it passes every check, else the roomiest heading that does, else None.

    `avoid` holds headings the glass veto just refused. They lose to any other
    open heading, and stay available when they are the only way out.
    """
    why = {heading: admits(heading, view, pose, limits) for heading, view in views.items()}
    allowed = [heading for heading, reason in why.items() if reason is None]
    if not allowed:
        return None, why
    fresh = [heading for heading in allowed if not _near(heading, avoid or [])]
    pool = fresh or allowed
    for heading in allowed:
        if heading not in pool:
            why[heading] = "just blocked"
    if jev_choice is not None and jev_choice in pool:
        return jev_choice, why

    def worth(heading: float) -> float:
        view = views[heading]
        room = view.reflex_m if view.room_m is None else min(view.reflex_m, view.room_m)
        if pose.seen_ahead(heading):
            room *= VISITED_WEIGHT
        if back is not None and heading == back:
            room *= BACK_WEIGHT
        return room

    return max(pool, key=worth), why
