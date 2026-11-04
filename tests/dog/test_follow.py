"""follow.py units: virtual beacon, smoothing, plane fit, probing, stuck, arrive/resume, limits."""

import math
import random

import numpy as np
import pytest

from patrol.dog import follow as F
from patrol.dog.follow import Follower, FollowCommand, VirtualBeacon


def rssi_formula(d):
    return max(-95.0, min(-30.0, -40.0 - 25.0 * math.log10(max(d, 0.3))))


# ------------------------------------------------------------------ beacon

def test_constants_verbatim():
    assert (F.WINDOW_S, F.ARRIVE_DBM, F.RESUME_DBM, F.RUN_LIMIT_S) == (4.0, -38.0, -43.0, 60.0)
    assert (F.MAX_VX, F.MAX_VYAW, F.PROBE_STEP_M) == (0.3, 0.5, 0.6)


@pytest.mark.parametrize("d", [0.0, 0.2, 0.3, 1.0, 1.318, 2.0, 4.0, 10.0])
def test_beacon_noise_zero_is_exact_formula(d):
    b = VirtualBeacon((d, 0.0), lambda: (0.0, 0.0, 1.2, None), noise_db=0.0)
    assert b.read() == pytest.approx(rssi_formula(d))


def test_beacon_clamps_and_pose_none():
    near = VirtualBeacon((0.0, 0.0), lambda: (0.0, 0.0, 0.0, None), noise_db=0.0)
    assert near.read() <= -30.0
    far = VirtualBeacon((1e6, 0.0), lambda: (0.0, 0.0, 0.0, None), noise_db=0.0)
    assert far.read() == -95.0
    loud = VirtualBeacon((0.0, 0.0), lambda: (0.0, 0.0, 0.0, None), rng=random.Random(1), noise_db=200.0)
    vals = [loud.read() for _ in range(200)]
    assert min(vals) >= -95.0 and max(vals) <= -30.0
    assert VirtualBeacon((1.0, 1.0), lambda: None).read() is None


def test_beacon_noise_is_seeded_gaussian_and_move_to():
    pose = lambda: (0.0, 0.0, 0.0, None)
    a = VirtualBeacon((2.0, 0.0), pose, rng=random.Random(7))
    b = VirtualBeacon((2.0, 0.0), pose, rng=random.Random(7))
    va, vb = [a.read() for _ in range(400)], [b.read() for _ in range(400)]
    assert va == vb
    mean = sum(va) / len(va)
    sd = math.sqrt(sum((v - mean) ** 2 for v in va) / len(va))
    assert mean == pytest.approx(rssi_formula(2.0), abs=0.5) and 2.4 < sd < 3.6
    a.move_to((1.0, 0.0))
    assert a.point_xy == (1.0, 0.0)
    a.noise_db = 0.0
    assert a.read() == pytest.approx(-40.0)


# ------------------------------------------------------------------ smoothing + fit (pure helpers)

def test_smoothing_median_then_ema():
    f = Follower()
    f.start(0.0)
    out = [f.smooth(v) for v in (-50.0, -50.0, -20.0, -50.0, -50.0)]   # one spike: the median removes it
    assert all(o == pytest.approx(-50.0) for o in out)
    f2 = Follower()
    f2.start(0.0)
    f2.smooth(-60.0)
    assert f2.smooth(-50.0) == pytest.approx(0.3 * -55.0 + 0.7 * -60.0)   # median of 2 = mean, then EMA 0.3


@pytest.mark.parametrize("true_dir", [0.0, 1.0, -2.0, 3.0])
def test_plane_fit_picks_uphill_direction(true_dir):
    rng = random.Random(3)
    g = (math.cos(true_dir) * 4.0, math.sin(true_dir) * 4.0)   # 4 dB/m uphill
    samples = []
    for i in range(30):
        x, y = rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5)
        samples.append((i * 0.1, x, y, -60.0 + g[0] * x + g[1] * y + rng.gauss(0, 0.3)))
    fit = F.fit_direction(samples, now=3.0)
    assert fit.ok
    err = math.atan2(math.sin(fit.direction - true_dir), math.cos(fit.direction - true_dir))
    assert abs(err) < 0.2 and fit.grad_db_m == pytest.approx(4.0, rel=0.25)


def test_fit_poor_when_few_samples_small_spread_or_flat():
    few = [(i * 0.1, i * 0.2, 0.0, -50.0 + i) for i in range(4)]
    assert not F.fit_direction(few, now=0.5).ok
    tight = [(i * 0.1, 0.01 * (i % 3), 0.0, -50.0 + (i % 3)) for i in range(20)]
    assert not F.fit_direction(tight, now=2.0).ok
    flat = [(i * 0.1, 0.1 * i, 0.05 * i, -50.0) for i in range(20)]
    assert not F.fit_direction(flat, now=2.0).ok


# ------------------------------------------------------------------ state machine

def drive(f, steps, *, x=0.0, y=0.0, yaw=0.0, rssi=-60.0, t0=0.0, dt=0.1, near=None, braking=False):
    cmds = []
    for i in range(steps):
        cmds.append(f.tick(t0 + i * dt, (x, y, yaw, None), rssi, near, braking))
    return cmds


def test_idle_and_stopped_command_nothing():
    f = Follower()
    c = f.tick(0.0, (0, 0, 0, None), -50.0, None, False)
    assert isinstance(c, FollowCommand) and (c.vx, c.vyaw, c.state) == (0.0, 0.0, "idle")
    f.start(0.0)
    f.stop("button")
    c = f.tick(0.1, (0, 0, 0, None), -50.0, None, False)
    assert (c.vx, c.vyaw, c.state, c.reason) == (0.0, 0.0, "stopped", "button")


def test_probing_when_samples_poor_and_never_sideways_within_caps():
    f = Follower()
    f.start(0.0)
    cmds = drive(f, 20, rssi=-60.0)         # standing still, flat signal: nothing to fit
    assert any(c.state == "probing" for c in cmds)
    assert all(c.vyaw != 0.0 or c.vx != 0.0 for c in cmds[1:])   # probing turns or walks
    for c in cmds:
        assert len(c) == 6 and abs(c.vx) <= 0.3 + 1e-9 and abs(c.vyaw) <= 0.5 + 1e-9 and c.vx >= 0.0


def test_probe_alternates_sides():
    f = Follower()
    f.start(0.0)
    c1 = drive(f, 3)[-1]
    first = math.copysign(1, c1.vyaw)
    f.start(20.0)                             # a fresh run keeps alternating from the last side
    c2 = drive(f, 3, t0=20.0)[-1]
    assert c1.state == c2.state == "probing" and math.copysign(1, c2.vyaw) == -first


def test_following_turns_toward_estimate_then_walks():
    f = Follower()
    f.start(0.0)
    # Clean uphill field toward +y while the "dog" walks along y at 0.3 m/s: direction = +pi/2.
    t = 0.0
    for i in range(40):
        x, y = 0.05 * math.sin(i), -0.6 + 0.03 * i
        f.tick(t, (x, y, 0.0, None), -60.0 + 4.0 * y, None, False)
        t += 0.1
    f.reestimate()                            # drop the current leg: the next tick decides from the fit
    c = f.tick(t, (0.0, 0.0, 0.0, None), -60.0, None, False)
    assert c.state == "following"
    assert c.est_dir_rad is not None and abs(c.est_dir_rad - math.pi / 2) < 0.5
    assert c.vyaw == pytest.approx(0.5) and c.vx == 0.0          # error > 0.5 rad: turn only, capped
    aligned = f.tick(t + 0.1, (0.0, 0.0, c.est_dir_rad, None), -60.0, None, False)
    assert aligned.state == "following" and aligned.vx == pytest.approx(0.3) and abs(aligned.vyaw) < 0.2


def test_heading_rule_unit():
    vx, vyaw = F.steer(heading_err=0.2)
    assert vx == 0.3 and vyaw == pytest.approx(0.3)
    vx, vyaw = F.steer(heading_err=-0.6)
    assert vx == 0.0 and vyaw == pytest.approx(-0.5)


def test_stuck_when_braked_more_than_2s():
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=0.0, length=1.0)      # walking straight ahead
    cmds = drive(f, 30, rssi=-60.0, braking=True)
    assert cmds[0].vx > 0
    stuck = [c for c in cmds if c.reason and c.reason.startswith("stuck")]
    assert stuck and stuck[0].state == "probing"
    i = cmds.index(stuck[0])
    assert F.BRAKE_STUCK_S <= i * 0.1 <= F.BRAKE_STUCK_S + 0.3 and stuck[0].vx == 0.0 and abs(stuck[0].vyaw) > 0


def test_stuck_when_no_progress_4s():
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=0.0, length=1.0)
    cmds = drive(f, 50, rssi=-60.0)           # commanding forward, pose never changes
    stuck = [i for i, c in enumerate(cmds) if c.reason and "no progress" in c.reason]
    assert stuck and 4.0 <= stuck[0] * 0.1 <= 4.3


def test_stuck_turns_alternate_sides():
    f = Follower()
    f.start(0.0)
    sides = []
    for k in range(2):
        f.force_leg(heading=0.0, length=1.0)
        cmds = drive(f, 25, t0=k * 10.0, rssi=-60.0, braking=True)
        st = next(c for c in cmds if c.reason and c.reason.startswith("stuck"))
        sides.append(math.copysign(1, st.vyaw))
    assert sides[0] == -sides[1]


def test_arrive_and_resume_hysteresis():
    f = Follower()
    f.start(0.0)
    c = drive(f, 10, rssi=-37.0)[-1]
    assert (c.state, c.vx, c.vyaw) == ("arrived", 0.0, 0.0)
    c = drive(f, 10, rssi=-41.0, t0=1.0)[-1]   # between -43 and -38: still arrived
    assert c.state == "arrived"
    c = drive(f, 15, rssi=-50.0, t0=2.0)[-1]
    assert c.state in ("following", "probing")


def test_time_limit_stops():
    f = Follower()
    f.start(100.0)
    c = f.tick(159.9, (0, 0, 0, None), -60.0, None, False)
    assert c.state != "stopped"
    c = f.tick(160.0, (0, 0, 0, None), -60.0, None, False)
    assert (c.state, c.reason, c.vx, c.vyaw) == ("stopped", "time limit", 0.0, 0.0)
    assert f.elapsed(500.0) == pytest.approx(60.0)


def test_no_pose_or_signal_holds_still():
    f = Follower()
    f.start(0.0)
    c = f.tick(0.1, None, -50.0, None, False)
    assert (c.vx, c.vyaw) == (0.0, 0.0) and c.reason == "position unknown"
    c = f.tick(0.2, (0, 0, 0, None), None, None, False)
    assert (c.vx, c.vyaw) == (0.0, 0.0) and c.reason == "no signal"


# ------------------------------------------------------------------ closed loop (kinematics only)

def simulate(point, *, start=(0.0, 0.0, 0.0), seed=0, noise=3.0, limit=60.0, dt=0.1):
    x, y, yaw = start
    pose = lambda: (x, y, yaw, None)
    b = VirtualBeacon(point, pose, rng=random.Random(seed), noise_db=noise)
    f = Follower()
    f.start(0.0)
    t = 0.0
    while t < limit + 1:
        c = f.tick(t, pose(), b.read(), None, False)
        assert abs(c.vx) <= 0.3 + 1e-9 and abs(c.vyaw) <= 0.5 + 1e-9
        if c.state in ("arrived", "stopped"):
            return c.state, t, math.hypot(point[0] - x, point[1] - y)
        yaw += c.vyaw * dt
        x += c.vx * math.cos(yaw) * dt
        y += c.vx * math.sin(yaw) * dt
        t += dt
    return "timeout", t, None


@pytest.mark.parametrize("point", [(2.5, 0.0), (0.0, 3.0), (-3.0, -1.0), (-2.0, 2.0)])
def test_closed_loop_reaches_point_without_noise(point):
    state, t, d = simulate(point, noise=0.0)
    assert state == "arrived" and t < 60.0 and d < 1.4


def test_closed_loop_with_3db_noise_mostly_reaches_point():
    """sigma 3 dB is noisy: the spec expects wandering. Most runs must still arrive within 60 s."""
    runs = [simulate(p, seed=s) for p in [(2.5, 0.0), (0.0, 3.0), (-3.0, -1.0)] for s in range(12)]
    arrived = [r for r in runs if r[0] == "arrived"]
    assert len(arrived) >= 0.85 * len(runs)
    assert all(d < 2.0 for _, _, d in arrived)       # arrived = really close, not a noise fluke far away


# ------------------------------------------------------------------ dodge (LiDAR free distance per direction)

from patrol.dog import lidar as L


def clear_view(yaw=0.0, blocked=(), free=4.0, near=0.3):
    """A LiDAR view's "clear" block: body-frame bins in `blocked` (degrees) at `near` m, the rest free."""
    m = [free] * L.CLEAR_BINS
    for deg in blocked:
        m[L.clear_bin(math.radians(deg))] = near
    return {"yaw": yaw, "step_deg": 15, "m": m}


def test_brake_stuck_is_quick():
    assert F.BRAKE_STUCK_S <= 1.0


def test_dodge_steers_to_nearest_free_heading_and_keeps_walking():
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=0.0, length=3.0)
    cv = clear_view(blocked=(-15, 0, 15, 30))
    c = f.tick(0.0, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=cv)
    assert c.reason.startswith("dodging") and "right" in c.reason       # -30 deg is the nearest free heading
    assert c.vyaw < 0 and c.vx == 0.0                                   # facing the obstacle (0.3 m): turn first
    c = f.tick(0.1, (0.0, 0.0, math.radians(-25), None), -60.0, None, False, clear=cv)
    assert c.vx > 0                                                     # facing free space near -30 deg: walks


def test_dodge_keeps_its_side_while_that_side_is_open():
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=0.0, length=3.0)
    c = f.tick(0.0, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=clear_view(blocked=(-15, 0, 15, 30)))
    assert c.vyaw < 0                                                   # right
    # now both sides are equally close: it must not flip to the left
    c = f.tick(0.1, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=clear_view(blocked=(-15, 0, 15)))
    assert c.vyaw < 0 and "right" in c.reason


def test_no_dodge_when_the_way_is_clear_or_unknown():
    for clear in (clear_view(blocked=(90, -90, 180)), None):
        f = Follower()
        f.start(0.0)
        f.force_leg(heading=0.0, length=3.0)
        c = f.tick(0.0, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=clear)
        assert c.vx > 0 and c.vyaw == pytest.approx(0.0) and not (c.reason or "").startswith("dodging")


def test_dodge_uses_the_bins_own_yaw():
    """Bins are relative to the scan's yaw: the dog has turned 90 deg left since, goal = odom 0."""
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=0.0, length=3.0)
    # odom heading 0 is body -90 deg in a scan taken at yaw +90 deg: blocked there
    c = f.tick(0.0, (0.0, 0.0, math.pi / 2, None), -60.0, None, False,
               clear=clear_view(yaw=math.pi / 2, blocked=(-60, -75, -90, -105, -120)))
    assert c.reason.startswith("dodging")


def test_dodge_gives_up_beyond_its_cone_and_leaves_it_to_the_brake():
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=0.0, length=3.0)
    blocked = tuple(range(-120, 121, 15))
    c = f.tick(0.0, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=clear_view(blocked=blocked))
    assert (c.reason or "").startswith("blocked") and c.vx == 0.0   # no walking into it; brake/stuck rule next


def test_stuck_probe_picks_the_freer_side():
    """Probes (stuck / signal unclear) take the first free candidate when the LiDAR is known."""
    for blocked, want_sign in (((60, 75, 90), -1), ((-60, -75, -90), 1)):
        f = Follower()
        f.start(0.0)
        f._clear = clear_view(blocked=(0,) + blocked)
        f._start_probe(0.0, 0.0, "stuck: test", blocked=True)
        assert math.copysign(1, F.wrap(f._leg.heading)) == want_sign, blocked


def simulate_with_obstacle(point, obstacle, *, dodge=True, start=(0.0, 0.0, 0.0), limit=60.0, dt=0.1):
    """Kinematic closed loop with a real LiDAR picture: obstacle = (N, 3) world points. The joystick's
    0.5 m forward brake is applied like the real drive path. Returns (state, t, braked_s, track)."""
    obs = np.asarray(obstacle, dtype=np.float64)
    x, y, yaw = start
    b = VirtualBeacon(point, lambda: (x, y, yaw, None), noise_db=0.0)
    f = Follower()
    f.start(0.0)
    t, braked_s, braking, track = 0.0, 0.0, False, []
    while t < limit + 1:
        body = L.to_body(obs, (x, y, yaw, 0.0))
        near = L.nearest_ahead(body)
        clear = ({"yaw": yaw, "step_deg": 15, "m": L.clearance(body), "near_m": L.turn_clearance(body),
                  "turn_room": L.turn_room(body)} if dodge else None)
        c = f.tick(t, (x, y, yaw, None), b.read(), near, braking, clear=clear)
        assert 0.0 <= c.vx <= 0.3 + 1e-9 and abs(c.vyaw) <= 0.5 + 1e-9
        if c.state in ("arrived", "stopped"):
            return c.state, t, braked_s, track
        vx, why = L.brake_forward(c.vx, near)
        braking = why is not None
        braked_s += dt if braking else 0.0
        yaw += c.vyaw * dt
        x += vx * math.cos(yaw) * dt
        y += vx * math.sin(yaw) * dt
        track.append((x, y))
        t += dt
    return "timeout", t, braked_s, track


def box_points(cx, cy, half_x, half_y, step=0.05):
    pts = []
    for u in np.arange(-half_x, half_x + 1e-9, step):
        for v in np.arange(-half_y, half_y + 1e-9, step):
            if abs(abs(u) - half_x) < 1e-6 or abs(abs(v) - half_y) < 1e-6:
                pts += [[cx + u, cy + v, 0.2], [cx + u, cy + v, 0.4]]
    return pts


@pytest.mark.parametrize("half_y", [0.2, 0.5])          # a 0.4 m box and a 1 m wide panel
def test_closed_loop_dodges_an_obstacle_between_dog_and_point(half_y):
    """The box sits on the straight line to the point. With the dodge it goes around, barely braking."""
    obstacle = box_points(1.3, 0.0, 0.2, half_y)
    state, t, braked_s, track = simulate_with_obstacle((3.0, 0.0), obstacle)
    assert state == "arrived" and t < 60.0
    body_r = 0.2                                     # never closer than the body's half-width to the box
    assert all(not (abs(px - 1.3) < 0.2 + body_r and abs(py) < half_y + body_r) for px, py in track)
    assert braked_s <= 1.0, braked_s


def test_without_dodge_the_same_box_costs_much_more_braking():
    """Guard for the test above: the obstacle really is in the way."""
    obstacle = box_points(1.3, 0.0, 0.2, 0.5)
    _, _, braked_with, _ = simulate_with_obstacle((3.0, 0.0), obstacle)
    _, _, braked_without, _ = simulate_with_obstacle((3.0, 0.0), obstacle, dodge=False)
    assert braked_without > braked_with + 1.0


def test_turn_guard_uses_the_swept_footprint_room():
    """Sim found it: turning in place beside a box corner swings a corner into it. The LiDAR view
    says how far the footprint can turn each way (turn_room, degrees); the follower respects it."""
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=math.pi / 2, length=3.0)              # wants to turn 90 deg left
    cv = clear_view()
    cv["near_m"], cv["turn_room"] = 0.40, (90, 90)
    c = f.tick(0.0, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=cv)
    assert 0 < c.vyaw <= F.TURN_SLOW_VYAW                      # room: turns, slowly (something near)
    cv["turn_room"] = (0, 90)                                  # left blocked, right free
    c = f.tick(0.1, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=cv)
    assert c.vyaw < 0 and c.vx == 0.0                          # turns the long way round, safely
    cv["turn_room"] = (20, 80)                                 # left opens a bit: still the long way (latched)
    c = f.tick(0.15, (0.0, 0.0, -0.2, None), -60.0, None, False, clear=cv)
    assert c.vyaw < 0
    f._turn_latch = None
    cv["turn_room"] = (0, 30)                                  # long way only partly open: don't start it
    c = f.tick(0.18, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=cv)
    assert c.vyaw == 0.0
    f._step_out_from = None
    cv["turn_room"] = (0, 0)                                   # no room either way, ahead free
    c = f.tick(0.2, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=cv)
    assert c.vyaw == 0.0 and c.vx > 0 and "turn" in c.reason  # step out straight first
    cv = clear_view(blocked=(0,))
    cv["near_m"], cv["turn_room"] = 0.40, (0, 0)
    c = f.tick(0.3, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=cv)
    assert (c.vx, c.vyaw) == (0.0, 0.0)                        # ahead blocked too: hold still
    cv = clear_view()
    cv["near_m"], cv["turn_room"] = 1.0, (90, 90)
    c = f.tick(0.4, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=cv)
    assert c.vyaw == pytest.approx(F.MAX_VYAW)


def test_closed_loop_never_overlaps_the_obstacle_over_many_runs():
    """Footprint check (0.70 x 0.32 m body, incl. while turning) over noisy runs and layouts."""
    import random as _r
    layouts = [(box_points(1.3, 0, 0.2, 0.5), (3.0, 0.0), (0, 0, 0)),
               (box_points(1.5, 0.3, 0.1, 0.5), (3.0, 0.0), (0, 0, 0.5)),
               (box_points(1.4, 0, 0.1, 0.8), (3.0, 0.2), (0, 0, 0))]
    arrived = 0
    for obs, pt, st in layouts:
        obs = np.asarray(obs, dtype=float)
        for seed in range(8):
            x, y, yaw = st
            b = VirtualBeacon(pt, lambda: (x, y, yaw, None), rng=_r.Random(seed), noise_db=2.0)  # = joystick BEACON_NOISE_DB
            f = Follower()
            f.start(0.0)
            t, braking = 0.0, False
            while t < 61:
                body = L.to_body(obs, (x, y, yaw, 0.0))
                near = L.nearest_ahead(body)
                c = f.tick(t, (x, y, yaw, None), b.read(), near, braking,
                           clear={"yaw": yaw, "m": L.clearance(body), "near_m": L.turn_clearance(body),
                                  "turn_room": L.turn_room(body)})
                if c.state in ("arrived", "stopped"):
                    arrived += c.state == "arrived"
                    break
                vx, why = L.brake_forward(c.vx, near)
                braking = why is not None
                yaw += c.vyaw * 0.1
                x += vx * math.cos(yaw) * 0.1
                y += vx * math.sin(yaw) * 0.1
                t += 0.1
                bd = L.to_body(obs, (x, y, yaw, 0.0))
                assert not ((np.abs(bd[:, 0]) < 0.35) & (np.abs(bd[:, 1]) < 0.16)).any(), (seed, t, x, y)
    # 0.8 m arrive circle (2026-11-04): 14/24 arrive in 60 s (was 16/24 with the 1.3 m circle); the
    # misses are slow detours round the box, not collisions (no-overlap is asserted above). 90 s: 19/24.
    assert arrived >= 0.55 * 24, arrived


def _run_kinematic(f, obs, point, start, secs, dt=0.1):
    """Closed loop like simulate_with_obstacle but with a given follower; returns the track."""
    obs = np.asarray(obs, dtype=float)
    x, y, yaw = start
    b = VirtualBeacon(point, lambda: (x, y, yaw, None), noise_db=0.0)
    t, braking, track = 0.0, False, [(x, y)]
    while t < secs:
        body = L.to_body(obs, (x, y, yaw, 0.0))
        near = L.nearest_ahead(body)
        c = f.tick(t, (x, y, yaw, None), b.read(), near, braking,
                   clear={"yaw": yaw, "m": L.clearance(body), "near_m": L.turn_clearance(body),
                                  "turn_room": L.turn_room(body)})
        if c.state in ("arrived", "stopped"):
            break
        vx, why = L.brake_forward(c.vx, near)
        braking = why is not None
        yaw += c.vyaw * dt
        x += vx * math.cos(yaw) * dt
        y += vx * math.sin(yaw) * dt
        track.append((x, y))
        t += dt
    return track


def test_turn_guard_step_out_is_bounded():
    """Review: wall 0.18 m beside the dog, signal behind it: stepping out straight walked 18 m away."""
    wall = [[x, 0.38, z] for x in np.arange(-6, 12, 0.05) for z in (0.2, 0.4)]
    f = Follower()
    f.start(0.0)
    track = _run_kinematic(f, wall, (-1.5, 0.0), (0.0, 0.0, 0.0), 20.0)
    assert max(math.hypot(px, py) for px, py in track) <= F.STEP_OUT_MAX_M + 0.15


def test_dodge_leg_is_bounded_along_a_long_wall():
    """Review: a long wall across the goal heading: one dodge leg walked 17 m along it."""
    wall = [[1.0, y, z] for y in np.arange(-10, 10, 0.05) for z in (0.2, 0.4)]
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=0.0, length=1.0)
    seen = []
    orig = f._start_probe

    def spy(*a, **kw):
        seen.append(a[2] if len(a) > 2 else kw.get("why"))
        return orig(*a, **kw)
    f._start_probe = spy
    track = _run_kinematic(f, wall, (3.0, 0.0), (0.0, 0.0, 0.0), 30.0)
    # the first dodge leg must hand back to the signal within ~2 legs of walking
    walked = 0.0
    for (ax, ay), (bx, by) in zip(track, track[1:]):
        walked += math.hypot(bx - ax, by - ay)
        if seen:
            break
    assert seen and walked <= 2 * F.LEG_M + 0.5, (walked, seen[:3])


def test_bad_turn_room_keeps_the_radial_turn_guard():
    """Review: a malformed turn_room used to drop ALL LiDAR guarding silently."""
    f = Follower()
    f.start(0.0)
    f.force_leg(heading=math.pi / 2, length=3.0)
    cv = clear_view(blocked=(0,))
    cv["near_m"], cv["turn_room"] = 0.30, ["x", None]
    c = f.tick(0.0, (0.0, 0.0, 0.0, None), -60.0, None, False, clear=cv)
    assert (c.vx, c.vyaw) == (0.0, 0.0)          # radial fallback: 0.30 m < 0.50 m, ahead blocked => hold
    assert f.bad_turn_room == 1
