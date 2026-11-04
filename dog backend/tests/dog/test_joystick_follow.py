"""Joystick "follow a virtual signal point" (demo mode) on the simulated dog.

Following is autonomous motion: it must go through the joystick's own drive path (LiDAR brake,
drive mode, caps, envelope) and every existing stop must end it."""

import asyncio
import math
import time

import pytest

from patrol.dog.joystick import JOY_MAX_VX, JOY_MAX_VYAW
from patrol.dog.sim_conn import SimConn
from tests.dog.test_dodge import NEAR, set_mode, sticks
from tests.dog.test_joystick import log_events, make_ctl, run, serve
from tests.dog.test_joystick_lidar import collecting_ws, of, until


# The signal point must lie within fence radius - 1.5 m of home. These runs use points 2.5 m away,
# so they use a 4.5 m fence (the real-dog runbook uses 3 m with dog and point 1.5 m either side).
FENCE = 4.5


def follow_of(ctl):
    return ctl.follower.state


def events_of(tmp_path, name):
    return [e for e in log_events(tmp_path) if e["event"] == name]


async def keepalive(ws, period=0.25):
    """What the page does while following: a follow_alive every 250 ms (the follow dead-man)."""
    try:
        while not ws.closed:
            await ws.send_json({"t": "follow_alive"})
            await asyncio.sleep(period)
    except Exception:
        pass


async def start_following(ctl, ws, x, y, noise=0.0, alive=True):
    ctl.beacon_noise_db = noise
    if alive:
        ws._alive = asyncio.create_task(keepalive(ws))
    assert await until(lambda: ctl._brake_view is not None and ctl.dog.lidar_pose() is not None, 3.0)
    await ws.send_json({"t": "beacon_place", "x": x, "y": y})
    assert await until(lambda: ctl.beacon is not None, 2.0)
    await ws.send_json({"t": "follow_start"})
    assert await until(lambda: follow_of(ctl) in ("following", "probing"), 3.0), \
        [m["msg"] for m in of(ws, "event")]


def in_box(x, y, margin=0.0):
    return abs(x - 1.5) < 0.2 + margin and abs(y) < 0.2 + margin


# ------------------------------------------------------------------ refusals

def test_start_refused_without_beacon_and_for_view_only(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            ws1 = await collecting_ws(client)          # controller
            ws2 = await collecting_ws(client)          # view-only
            assert await until(lambda: ctl._brake_view is not None, 3.0)
            await ws1.send_json({"t": "follow_start"})
            assert await until(lambda: any("follow refused" in m["msg"] for m in of(ws1, "event")), 2.0)
            await ws2.send_json({"t": "beacon_place", "x": 1.0, "y": 0.0})
            await ws2.send_json({"t": "follow_start"})
            await asyncio.sleep(0.3)
            viewer = (ctl.beacon, follow_of(ctl))
            evs = [m["msg"] for m in of(ws1, "event")]
            await ws1.close()
            await ws2.close()
            return viewer, evs

    viewer, evs = run(go())
    assert viewer == (None, "idle")
    assert any("signal point" in m for m in evs if "follow refused" in m)
    refused = [e for e in events_of(tmp_path, "follow_start") if e.get("action") == "refused"]
    assert refused and "signal point" in refused[0]["reason"]


@pytest.mark.parametrize("case", ["not_standing", "brake_off", "envelope_off", "stick_held"])
def test_start_refused_unless_safe(tmp_path, case):
    sim = SimConn(camera=False, standing=case != "not_standing")

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            if case != "not_standing":
                assert await until(lambda: ctl._brake_view is not None, 3.0)
            else:
                await asyncio.sleep(0.5)
            await ws.send_json({"t": "beacon_place", "x": -2.0, "y": 0.0})
            if case == "brake_off":
                await ws.send_json({"t": "lidar_brake", "enabled": False})
            elif case == "envelope_off":
                await ws.send_json({"t": "safety", "enabled": False})
                assert await until(lambda: ctl.envelope_enabled is False, 2.0)
            elif case == "stick_held":
                await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 1, "speed": 1.0})
            await asyncio.sleep(0.2)
            await ws.send_json({"t": "follow_start"})
            ok = await until(lambda: any("follow refused" in m["msg"] for m in of(ws, "event")), 2.0)
            st = follow_of(ctl)
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await ws.close()
            return ok, st

    ok, st = run(go())
    assert ok and st == "idle"
    reasons = [e["reason"] for e in events_of(tmp_path, "follow_start") if e.get("action") == "refused"]
    word = {"not_standing": "standing", "brake_off": "brake", "envelope_off": "safety",
            "stick_held": "stick"}[case]
    assert reasons and word in reasons[0].lower()


# ------------------------------------------------------------------ reaching the point

def test_follow_reaches_point_in_open_space_and_holds_standing(tmp_path):
    sim = SimConn(camera=False)
    sim.heading = math.pi                      # facing -x: open floor, wall 3 m away

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            t0 = time.monotonic()
            await start_following(ctl, ws, -2.5, 0.0)
            ok = await until(lambda: follow_of(ctl) == "arrived", 60.0)
            t_arr = time.monotonic()
            await asyncio.sleep(1.0)
            speed = math.hypot(*sim.v)
            st = [m["follow"] for m in of(ws, "status") if m.get("follow")]
            lid = [m for m in of(ws, "lidar") if m.get("pose")]
            await ws.close()
            return ok, t_arr - t0, speed, st, lid

    ok, took, speed, st, lid = run(go())
    assert ok and took < 60.0
    assert math.hypot(sim.x + 2.5, sim.y) < 1.6
    assert speed < 0.05 and sim._standing()
    assert 1005 not in sim.apis() and 1001 not in sim.apis()       # holds standing, never Damp
    assert [s for s in sim.stops()]                                 # StopMove on arrival
    arrived_stop = [e for e in events_of(tmp_path, "stop") if e["kind"] == "follow_arrived"]
    assert arrived_stop
    assert any(s["state"] == "arrived" for s in st)
    s = st[-1]
    for k in ("state", "reason", "rssi", "rssi_smoothed", "est_dir_rad", "elapsed_s", "limit_s",
              "beacon_xy", "drive_mode"):
        assert k in s
    assert s["limit_s"] == 60.0 and s["beacon_xy"] == [-2.5, 0.0]
    assert lid and len(lid[-1]["pose"]) == 3
    for m in sim.moves():
        assert 0.0 <= m[2]["x"] <= JOY_MAX_VX + 1e-9 and m[2]["y"] == 0.0 and abs(m[2]["z"]) <= JOY_MAX_VYAW
    samples = events_of(tmp_path, "follow_sample")
    assert samples and {"pose", "rssi", "rssi_s", "state", "cmd"} <= set(samples[0])
    assert events_of(tmp_path, "follow_start") and events_of(tmp_path, "beacon_place")


def test_follow_goes_around_the_box_without_entering_it(tmp_path):
    sim = SimConn(camera=False)                # box at (1.5, 0), 0.4 m; dog at origin facing it

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        track = []
        async with serve(ctl) as client:
            ws = await collecting_ws(client)

            async def watch():
                while True:
                    track.append((sim.x, sim.y))
                    await asyncio.sleep(0.02)
            w = asyncio.create_task(watch())
            await start_following(ctl, ws, 2.5, 0.0)
            ok = await until(lambda: follow_of(ctl) == "arrived", 60.0)
            w.cancel()
            await ws.close()
            return ok, track

    ok, track = run(go())
    assert ok
    assert not any(in_box(x, y, margin=0.05) for x, y in track)
    assert math.hypot(sim.x - 2.5, sim.y) < 1.6
    assert max(abs(y) for _, y in track) > 0.3          # went to the side, not through


@pytest.mark.parametrize("mode", ["move", "sticks"])
def test_follow_dodges_the_box_with_the_lidar_and_barely_brakes(tmp_path, mode):
    """Box straight between dog and point: the follower steers round it from the LiDAR's free
    directions instead of driving up to it and waiting on the brake."""
    sim = SimConn(camera=False)                # box at (1.5, 0), 0.4 m; dog at origin facing it
    clears = []

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        track = []
        orig_tick = ctl.follower.tick

        def tick(*a, **kw):                     # what the follower is fed (the wiring under test)
            clears.append(kw.get("clear"))
            return orig_tick(*a, **kw)
        ctl.follower.tick = tick
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            if mode == "sticks":
                await set_mode(ctl, ws, "sticks")

            async def watch():
                while True:
                    track.append((sim.x, sim.y))
                    await asyncio.sleep(0.02)
            w = asyncio.create_task(watch())
            await start_following(ctl, ws, 2.5, 0.0)
            ctl.follower.force_leg(heading=0.0, length=3.0)   # straight at the box: the dodge must act
            ok = await until(lambda: follow_of(ctl) == "arrived", 60.0)
            w.cancel()
            await ws.close()
            return ok, track

    ok, track = run(go())
    assert ok, [e.get("reason") for e in events_of(tmp_path, "follow_state")]
    assert not any(in_box(x, y, margin=0.2) for x, y in track)        # kept the body's half-width off it
    engaged = [e for e in events_of(tmp_path, "lidar_brake") if e["action"] == "engaged"]
    assert len(engaged) <= 1, engaged
    fed = [c for c in clears if c is not None]
    assert fed and len(fed[0]["m"]) == 24 and "near_m" in fed[0]          # the LiDAR directions reach it
    starts = [e for e in events_of(tmp_path, "follow_dodge") if e["action"] == "start"]
    assert starts and starts[0]["side"] in ("left", "right") and starts[0]["reason"].startswith("dodging")
    samples = events_of(tmp_path, "follow_sample")
    assert all("dodge" in s and "near_m" in s and "turn_room" in s for s in samples)


# ------------------------------------------------------------------ ending it

def test_manual_stick_input_ends_following_and_manual_continues(tmp_path):
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await start_following(ctl, ws, -2.5, 0.0)
            await asyncio.sleep(0.5)
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})     # a zero (e.g. release) is ignored
            await asyncio.sleep(0.2)
            still = follow_of(ctl)
            n = len(sim.moves())
            for _ in range(5):
                await ws.send_json({"t": "drive", "x": -1, "y": 0, "yaw": 0, "speed": 1.0})
                await asyncio.sleep(0.06)
            after = (follow_of(ctl), ctl.follower.reason)
            manual = [m[2] for m in sim.moves()[n:]]
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.3)
            await ws.send_json({"t": "beacon_clear"})
            await asyncio.sleep(0.2)
            beacon = ctl.beacon
            await ws.close()
            return still, after, manual, beacon

    still, after, manual, beacon = run(go())
    assert still in ("following", "probing")
    assert after == ("stopped", "manual takeover")
    assert manual and manual[-1]["x"] < 0                          # the page's stick drives now
    assert beacon is None
    stops = events_of(tmp_path, "follow_stop")
    assert stops and stops[0]["reason"] == "manual takeover"
    assert events_of(tmp_path, "beacon_clear")


def test_stop_ends_following_and_lies_down_never_damp(tmp_path):
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await start_following(ctl, ws, -2.5, 0.0)
            await asyncio.sleep(1.0)
            await ws.send_json({"t": "stop"})
            await asyncio.sleep(2.5)
            st = (follow_of(ctl), ctl.follower.reason)
            await ws.close()
            return st

    state, reason = run(go())
    assert state == "stopped" and "STOP" in reason
    assert 1005 in sim.apis() and 1001 not in sim.apis()
    assert not sim._standing() or sim.height_target < 0.1


def test_time_limit_stops_with_stopmove_and_stays_standing(tmp_path):
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            ctl.follow_limit_s = 2.0
            await start_following(ctl, ws, -2.5, 0.0)
            t0 = time.monotonic()
            ok = await until(lambda: follow_of(ctl) == "stopped", 4.0)
            took = time.monotonic() - t0
            await asyncio.sleep(1.0)
            st = [m["follow"] for m in of(ws, "status") if m.get("follow")][-1]
            await ws.close()
            return ok, took, ctl.follower.reason, st

    ok, took, reason, st = run(go())
    assert ok and took < 2.6 and reason == "time limit"
    assert st["state"] == "stopped" and st["reason"] == "time limit" and st["elapsed_s"] == pytest.approx(2.0, abs=0.2)
    assert sim.stops() and 1005 not in sim.apis() and 1001 not in sim.apis()
    assert sim._standing() and math.hypot(*sim.v) < 0.05
    assert any(e["reason"] == "time limit" for e in events_of(tmp_path, "follow_stop"))


def test_ws_loss_ends_following_with_stopmove(tmp_path):
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await start_following(ctl, ws, -2.5, 0.0)
            await asyncio.sleep(0.8)
            n = len(sim.stops())
            await ws.close()
            ok = await until(lambda: follow_of(ctl) == "stopped", 2.0)
            await asyncio.sleep(0.5)
            return ok, ctl.follower.reason, len(sim.stops()) - n

    ok, reason, new_stops = run(go())
    assert ok and "controller lost" in reason and new_stops >= 1
    assert 1005 not in sim.apis()


def test_page_silence_is_a_follow_deadman(tmp_path):
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await start_following(ctl, ws, -2.5, 0.0)
            await asyncio.sleep(1.5)
            still = follow_of(ctl)
            ws._alive.cancel()                         # page frozen: ws open, but nothing arrives
            t0 = time.monotonic()
            ok = await until(lambda: follow_of(ctl) == "stopped", 3.0)
            took = time.monotonic() - t0
            await asyncio.sleep(0.8)
            speed = math.hypot(*sim.v)
            await ws.close()
            return still, ok, took, ctl.follower.reason, speed

    still, ok, took, reason, speed = run(go())
    assert still in ("following", "probing")
    assert ok and took < 1.6 and reason.startswith("dead-man")
    assert sim.stops() and 1005 not in sim.apis() and speed < 0.05


def test_page_follow_stop_with_blur_reason(tmp_path):
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await start_following(ctl, ws, -2.5, 0.0)
            await ws.send_json({"t": "follow_stop", "reason": "blur"})
            ok = await until(lambda: follow_of(ctl) == "stopped", 2.0)
            await ws.close()
            return ok, ctl.follower.reason

    ok, reason = run(go())
    assert ok and reason == "tab blur"
    assert sim.stops() and 1005 not in sim.apis()


def test_follow_commands_go_through_the_brake(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ctl.dog.lidar_view = lambda: dict(NEAR)        # obstacle 0.3 m ahead, always
            ws = await collecting_ws(client)
            await start_following(ctl, ws, 2.5, 0.0)
            n = len(sim.moves())
            await asyncio.sleep(6.0)
            sent = [m[2] for m in sim.moves()[n:]]
            wanted_fwd = ctl._follow_wanted_fwd
            await ws.send_json({"t": "follow_stop"})
            await asyncio.sleep(0.3)
            await ws.close()
            return sent, wanted_fwd

    sent, wanted_fwd = run(go())
    assert sent and all(m["x"] == 0.0 for m in sent)       # braked: never forward
    assert wanted_fwd                                        # the follower did ask for forward
    assert any(abs(m["z"]) > 0 for m in sent)                # turning still allowed
    assert [e for e in events_of(tmp_path, "lidar_brake") if e["action"] == "engaged"]


def test_follow_in_sticks_mode_uses_sticks(tmp_path):
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await set_mode(ctl, ws, "sticks")
            await start_following(ctl, ws, -2.5, 0.0)
            await asyncio.sleep(2.0)
            mode_change = ctl.drive_mode
            await ws.send_json({"t": "drive_mode", "mode": "move"})         # refused while following
            await asyncio.sleep(0.3)
            refused_mode = ctl.drive_mode
            await ws.send_json({"t": "follow_stop"})
            await asyncio.sleep(0.5)
            await ws.close()
            return mode_change, refused_mode

    mode, refused_mode = run(go())
    assert mode == "sticks" and refused_mode == "sticks"
    assert sim.moves() == [] and any(d["rx"] != 0 or d["ly"] != 0 for d, _ in sticks(sim))


def test_follow_in_sticks_mode_turns_toward_its_leg_and_arrives(tmp_path):
    """Real dog 2026-11-04 19:30: in sticks mode the turn sign was mirrored, so the dog turned
    away from the leg heading and dithered at heading + 180 deg, stepping in place, never walking.
    The sim now turns like the real dog (rx + = turn right); following must still arrive."""
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await set_mode(ctl, ws, "sticks")
            await start_following(ctl, ws, -2.5, 0.0)
            ok = await until(lambda: follow_of(ctl) == "arrived", 60.0)
            await ws.close()
            return ok

    ok = run(go())
    assert ok, [e.get("reason") for e in events_of(tmp_path, "follow_state")]
    assert math.hypot(sim.x + 2.5, sim.y) < 1.6
    assert sim.moves() == []


def test_page_has_follow_panel(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False, lidar=False))
        async with serve(ctl) as client:
            return await (await client.get("/")).text()

    page = run(go())
    for s in ("Follow signal (demo)", "Place signal point", "Start following", "Stop following",
              "simulated", "dog's own avoidance is off", "follow_start", "beacon_place", "b-follow",
              "followrefused", "follow_alive"):
        assert s in page, s
    # The follow panel renders last and inside try/catch: it can never stop the safety banners updating.
    i_follow = page.index("try { renderFollow(s); }")
    for safety in ('$("lockbar")', 'setBadge("b-safe"', '$("tripbar")', 'setBadge("b-brake"'):
        assert page.index(safety) < i_follow, safety
    assert page.count("renderFollow(s)") == 2 and page.count("function renderFollow(s)") == 1   # def + one call
