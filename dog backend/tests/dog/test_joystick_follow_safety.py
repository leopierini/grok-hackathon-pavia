"""Follow demo safety: signal point inside the fence, every stop path ends following, every start
precondition refuses, exactly one StopMove on arrival (simulated dog)."""

import asyncio
import math
import time

import pytest

from patrol.contract import AdapterError
from patrol.dog.sim_conn import SimConn
from tests.dog.test_dodge import FAR, set_mode, sticks
from tests.dog.test_joystick import log_events, make_ctl, run, serve
from tests.dog.test_joystick_follow import FENCE, events_of, follow_of, start_following
from tests.dog.test_joystick_lidar import collecting_ws, of, until


def refusals(tmp_path, event):
    return [e["reason"] for e in events_of(tmp_path, event) if e.get("action") == "refused"]


def said(ws, text):
    return any(text in m["msg"] for m in of(ws, "event"))


# ------------------------------------------------------------------ signal point vs fence

def test_point_outside_fence_margin_refused_inside_accepted(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))          # default fence 3 m => point <= 1.5 m
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            assert await until(lambda: ctl._brake_view is not None, 3.0)
            await ws.send_json({"t": "beacon_place", "x": 2.0, "y": 0.0})
            await until(lambda: said(ws, "signal point not placed"), 2.0)
            after_far = ctl.beacon
            await ws.send_json({"t": "beacon_place", "x": -1.4, "y": 0.0})
            await until(lambda: ctl.beacon is not None, 2.0)
            near = ctl.beacon.point_xy if ctl.beacon else None
            await ws.send_json({"t": "beacon_place", "x": 0.0, "y": 1.6})       # moving it out: refused, stays
            await asyncio.sleep(0.3)
            kept = ctl.beacon.point_xy
            await asyncio.sleep(0.4)
            st = [m["follow"] for m in of(ws, "status") if m.get("follow")][-1]
            await ws.close()
            return after_far, near, kept, st

    after_far, near, kept, st = run(go())
    assert after_far is None and near == (-1.4, 0.0) and kept == (-1.4, 0.0)
    r = refusals(tmp_path, "beacon_place")
    assert len(r) == 2 and all("fence" in x for x in r)
    assert st["last_refusal"] and "fence" in st["last_refusal"]["reason"]       # shown on the page


def test_point_refused_when_home_unknown(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            ctl.dog.safety_status = lambda: {"home": None, "radius_m": 3.0}
            await ws.send_json({"t": "beacon_place", "x": 0.5, "y": 0.0})
            await until(lambda: said(ws, "signal point not placed"), 2.0)
            await ws.close()
            return ctl.beacon

    assert run(go()) is None
    assert "home" in refusals(tmp_path, "beacon_place")[0]


# ------------------------------------------------------------------ start refusals

@pytest.mark.parametrize("case", ["avoid_off", "avoid_unknown", "not_stationary", "outside_fence", "locked",
                                  "stale_lidar", "beacon_outside_fence", "lost_control"])
def test_start_refused(tmp_path, case):
    sim = SimConn(camera=False, avoid=case != "avoid_off", publish_multi=case != "avoid_unknown")
    cfg = {"fence_radius_m": FENCE}
    if case == "outside_fence":
        cfg["home"] = [0.0, 0.0]
        sim.x = FENCE + 0.5

    async def go():
        ctl = make_ctl(tmp_path, sim, **cfg)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            ws2 = await collecting_ws(client)
            if case == "stale_lidar":
                ctl.dog.lidar_view = lambda: {**FAR, "stale": True}
            await until(lambda: ctl.dog.lidar_pose() is not None, 3.0)
            await asyncio.sleep(0.5)
            if case == "outside_fence":
                ctl.beacon = __import__("patrol.dog.follow", fromlist=["VirtualBeacon"]).VirtualBeacon(
                    (FENCE, 0.0), ctl._pose)                 # bypass placement: start must still refuse
            else:
                await ws.send_json({"t": "beacon_place", "x": -1.0, "y": 0.0})
                assert await until(lambda: ctl.beacon is not None, 2.0)
            if case == "not_stationary":                      # e.g. staff controller turning it
                sim.cmd, sim.cmd_t = (0.0, 0.0, 0.5), time.monotonic()
                await asyncio.sleep(0.3)
            elif case == "locked":
                await ctl.dog.halt()
            elif case == "beacon_outside_fence":
                ctl.beacon.move_to((0.0, FENCE))              # e.g. home moved since placement
            if case == "lost_control":
                ctl.request_follow_start(ws)                  # requested by ws, but control moves first
                ctl.take_control(ws2)
            else:
                await ws.send_json({"t": "follow_start"})
            ok = await until(lambda: said(ws, "follow refused") or said(ws2, "follow refused"), 2.0)
            st = follow_of(ctl)
            await ws.close()
            await ws2.close()
            return ok, st

    ok, st = run(go())
    assert ok and st == "idle"
    reasons = refusals(tmp_path, "follow_start")
    word = {"avoid_off": "avoidance", "avoid_unknown": "avoidance", "not_stationary": "stationary",
            "outside_fence": "fence", "locked": "locked", "stale_lidar": "lidar",
            "beacon_outside_fence": "fence", "lost_control": "control"}[case]
    assert reasons and word in reasons[-1].lower(), reasons
    assert sim.moves() == [] and 1001 not in sim.apis()


# ------------------------------------------------------------------ stop paths

@pytest.mark.parametrize("case", ["rearm", "take_control", "safety_trip", "motion_lock", "refused_drive"])
def test_stop_path_ends_following(tmp_path, case):
    sim = SimConn(camera=False)
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            ws2 = await collecting_ws(client)
            await start_following(ctl, ws, -2.5, 0.0)
            await asyncio.sleep(1.0)
            n_stop = len(sim.stops())
            if case == "rearm":
                await ws.send_json({"t": "rearm"})
            elif case == "take_control":
                await ws2.send_json({"t": "claim"})
            elif case == "safety_trip":
                ctl.dog._trip("tilt", "safety: tilt test", {"roll_deg": 30.0})
            elif case == "motion_lock":
                await ctl.dog.halt()
            elif case == "refused_drive":
                async def refuse(*a, **k):
                    raise AdapterError("unsafe_state", "refused for the test")
                ctl.dog.drive = refuse
            ok = await until(lambda: follow_of(ctl) == "stopped", 3.0)
            await asyncio.sleep(2.0)
            await ws.close()
            await ws2.close()
            return ok, ctl.follower.reason, len(sim.stops()) - n_stop

    ok, reason, new_stops = run(go())
    word = {"rearm": "re-arm", "take_control": "control taken", "safety_trip": "safety trip",
            "motion_lock": "locked", "refused_drive": "refused"}[case]
    assert ok and word in reason.lower(), reason
    assert new_stops >= 1                                   # StopMove went out
    assert 1001 not in sim.apis()                          # never Damp
    if case == "safety_trip":
        assert 1005 in sim.apis()                          # the trip lies it down softly
    else:
        assert 1005 not in sim.apis()                      # automatic stop: stays standing
    assert [e for e in events_of(tmp_path, "follow_stop") if word in e["reason"].lower()]


# ------------------------------------------------------------------ arrival: exactly one StopMove

@pytest.mark.parametrize("mode", ["move", "sticks"])
def test_arrival_sends_exactly_one_stopmove(tmp_path, mode):
    sim = SimConn(camera=False, stick_hold=(mode == "sticks"))   # sticks: only a zero stick stops it
    sim.heading = math.pi

    async def go():
        ctl = make_ctl(tmp_path, sim, fence_radius_m=FENCE)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            if mode == "sticks":
                await set_mode(ctl, ws, "sticks")
            await start_following(ctl, ws, -2.5, 0.0)
            ok = await until(lambda: follow_of(ctl) == "arrived", 60.0)
            await asyncio.sleep(2.0)
            speed = math.hypot(*sim.v)
            t_close = time.monotonic()                 # closing the tab ends the run with its own StopMove
            await ws.close()
            return ok, speed, t_close

    ok, speed, t_close = run(go())
    assert ok and speed < 0.05 and sim._standing()
    if mode == "move":
        last_drive = sim.moves()[-1][3]
    else:
        last_drive = [t for d, t in sticks(sim) if any(d[k] for k in ("lx", "ly", "rx"))][-1]
    stops_after = [s[3] for s in sim.stops() if last_drive < s[3] < t_close]
    t_arr = [e for e in events_of(tmp_path, "stop") if e["kind"] == "follow_arrived"]
    assert t_arr and len(stops_after) == 1, stops_after          # exactly one StopMove on entering arrived
    if mode == "sticks":
        zeros = [t for d, t in sticks(sim) if last_drive < t < t_close and not any(d[k] for k in ("lx", "ly", "rx", "ry"))]
        assert zeros and zeros[0] <= stops_after[0] + 0.01        # zero sticks first
        assert sim.moves() == []
    assert 1005 not in sim.apis() and 1001 not in sim.apis()
