"""Obstacle dodging: "sticks" drive mode (remote-controller path) + LiDAR forward brake (simulated dog)."""

import asyncio
import math
import time

import pytest

from patrol.contract import AdapterError
from patrol.dog.joystick import JOY_MAX_VX, Controller
from patrol.dog.lidar import BRAKE_DISTANCE_M, brake_forward
from patrol.dog.real import STICK_MAX
from patrol.dog.sim_conn import SimConn
from tests.dog.test_joystick import drive_for, log_events, make_ctl, make_dog, run, serve
from tests.dog.test_joystick_lidar import collecting_ws, of, until

NEAR = {"t": "lidar", "n": 0, "pts": [], "age_s": 0.1, "stale": False, "nearest_ahead_m": 0.3,
        "frame_id": "odom", "radius_m": 4.0, "reason": None}
FAR = {**NEAR, "nearest_ahead_m": 2.0}


def sticks(sim):
    """(data, monotonic time) of every publish on the remote-controller topic."""
    return [(s[2], s[3]) for s in sim.sent if s[0] == "WIRELESS_CONTROLLER"]


def is_zero(d):
    return d["lx"] == 0 and d["ly"] == 0 and d["rx"] == 0 and d["ry"] == 0


def zeros_after(sim, t0, t1):
    return [t for d, t in sticks(sim) if is_zero(d) and t0 <= t <= t1]


def nonzero_after_first_zero(sim, t0):
    seq = [(d, t) for d, t in sticks(sim) if t >= t0]
    first = next((i for i, (d, _) in enumerate(seq) if is_zero(d)), None)
    return [] if first is None else [d for d, _ in seq[first:] if not is_zero(d)]


async def set_mode(ctl, ws, mode):
    await ws.send_json({"t": "drive_mode", "mode": mode})
    assert await until(lambda: ctl.drive_mode == mode, 2.0), f"mode {mode} not applied"


# ------------------------------------------------------------------ brake_forward (pure)

def test_brake_forward_unit():
    assert BRAKE_DISTANCE_M == 0.5
    v, why = brake_forward(0.2, 0.3)
    assert v == 0.0 and why and "0.30" in why
    assert brake_forward(0.2, 0.49)[0] == 0.0
    assert brake_forward(0.2, 0.5) == (0.2, None)          # at the limit: not closer than 0.5
    assert brake_forward(0.2, 1.2) == (0.2, None)
    assert brake_forward(0.2, None) == (0.2, None)         # nothing ahead
    assert brake_forward(0.0, 0.1) == (0.0, None)          # standing / turning only
    assert brake_forward(-0.2, 0.1) == (-0.2, None)        # backward never braked


# ------------------------------------------------------------------ RealDog.send_sticks / zero_sticks

def test_send_sticks_clamps_publishes_and_counts_as_motion(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        t_before = dog._last_move_cmd_t
        sent = await dog.send_sticks(0.9, -0.9, 0.5)
        t_after = dog._last_move_cmd_t
        moving = dog._motion_active(time.monotonic(), {"velocity": [0, 0, 0], "yaw_speed": 0.0})
        await dog.zero_sticks()
        t_zero = dog._last_move_cmd_t
        with pytest.raises(AdapterError) as e:
            await dog.send_sticks(float("nan"), 0, 0)
        await dog.close()
        return sent, t_before, t_after, t_zero, moving, e.value.code

    sent, t_before, t_after, t_zero, moving, code = run(go())
    data = [d for d, _ in sticks(sim)]
    assert data[0] == {"lx": STICK_MAX, "ly": -STICK_MAX, "rx": STICK_MAX, "ry": 0.0, "keys": 0}
    assert sent == data[0]
    assert all(is_zero(d) for d in data[1:]) and len(data) >= 2    # zero_sticks: zeros only
    assert t_after > t_before and t_zero == t_after                # zeros are not motion commands
    assert moving                                                  # the fence sees a recent stick send
    assert code == "invalid_input"
    assert sim.moves() == []                                       # sticks never send Move


@pytest.mark.parametrize("case", ["locked", "avoidance_off", "not_standing", "avoidance_unknown"])
def test_send_sticks_refused_like_move_but_zero_always_allowed(tmp_path, case):
    sim = SimConn(camera=False, lidar=False, avoid=case != "avoidance_off",
                  standing=case != "not_standing", publish_multi=case != "avoidance_unknown")

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        if case == "locked":
            dog.latch_lock("test")
        with pytest.raises(AdapterError) as e:
            await dog.send_sticks(0.1, 0.1, 0.0)
        await dog.zero_sticks()                    # a stop: allowed even when locked
        await dog.close()
        return e.value.code

    assert run(go()) == "unsafe_state"
    data = [d for d, _ in sticks(sim)]
    assert data and all(is_zero(d) for d in data)


def test_stop_paths_zero_sticks_first_only_when_sticks_were_used(tmp_path):
    async def go(use_sticks):
        sim = SimConn(camera=False, lidar=False)
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        if use_sticks:
            await dog.send_sticks(0.0, 0.2, 0.0)
        t0 = time.monotonic()
        await dog.stop_move()
        await asyncio.sleep(0.4)
        t1 = time.monotonic()
        await dog.rest()
        await asyncio.sleep(0.4)
        await dog.close()
        return sim, t0, t1

    sim, t0, t1 = run(go(True))
    stop1 = [t for t in (s[3] for s in sim.stops()) if t >= t0][0]
    z1 = zeros_after(sim, t0, t0 + 0.35)
    assert z1 and z1[0] <= stop1                      # zero sticks before StopMove
    assert len(z1) >= 3                               # and repeated over ~0.2 s
    stop2 = [t for t in (s[3] for s in sim.stops()) if t >= t1][0]
    z2 = zeros_after(sim, t1, t1 + 0.35)
    assert z2 and z2[0] <= stop2 and len(z2) >= 3
    apis = sim.apis()
    assert 1005 in apis and 1001 not in apis          # rest = StandDown, never Damp

    sim, _, _ = run(go(False))
    assert sticks(sim) == []                          # Move-only session: no remote-controller traffic


# ------------------------------------------------------------------ drive mode switch

def test_drive_mode_default_move_status_and_reset_on_restart(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False, lidar=False))
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            ok = await until(lambda: of(ws, "status"), 2.0)
            first = of(ws, "status")[0]["drive_mode"] if ok else None
            await set_mode(ctl, ws, "sticks")
            ok2 = await until(lambda: [m for m in of(ws, "status") if m.get("drive_mode") == "sticks"], 2.0)
            await ws.close()
        ctl2 = make_ctl(tmp_path, SimConn(camera=False, lidar=False))     # server restart
        return first, ok2, ctl2.drive_mode

    first, ok2, after_restart = run(go())
    assert first == "move" and ok2 and after_restart == "move"
    ev = [e for e in log_events(tmp_path) if e["event"] == "drive_mode"]
    assert ev and ev[-1]["new"] == "sticks" and ev[-1]["old"] == "move"


def test_drive_mode_refused_for_view_only_and_while_moving(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws1 = await collecting_ws(client)          # controller
            ws2 = await collecting_ws(client)          # view-only
            await ws2.send_json({"t": "drive_mode", "mode": "sticks"})
            await asyncio.sleep(0.3)
            after_viewer = ctl.drive_mode
            driver = asyncio.create_task(drive_for(ws1, 1.0))
            await asyncio.sleep(0.4)
            await ws1.send_json({"t": "drive_mode", "mode": "sticks"})
            await asyncio.sleep(0.2)
            during_drive = ctl.drive_mode
            await driver
            await ws1.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await ws1.send_json({"t": "drive_mode", "mode": "bogus"})
            await asyncio.sleep(0.3)
            bogus = ctl.drive_mode
            events = [m["msg"] for m in of(ws1, "event")]
            await ws1.close()
            await ws2.close()
            return after_viewer, during_drive, bogus, events

    after_viewer, during_drive, bogus, events = run(go())
    assert after_viewer == "move" and during_drive == "move" and bogus == "move"
    assert any("drive mode" in m.lower() for m in events)      # refusal is said, not silent
    assert sticks(sim) == []
    changed = [e for e in log_events(tmp_path) if e["event"] == "drive_mode" and e.get("new")]
    assert changed == []


# ------------------------------------------------------------------ sticks mode driving

def test_sticks_mode_sends_signed_capped_sticks_not_move(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await set_mode(ctl, ws, "sticks")
            out = {}
            for name, msg in (("fwd", {"x": 1, "y": 0, "yaw": 0}), ("left", {"x": 0, "y": 1, "yaw": 0}),
                              ("turnleft", {"x": 0, "y": 0, "yaw": 1}), ("back", {"x": -0.5, "y": 0, "yaw": 0})):
                n = len(sticks(sim))
                for _ in range(6):
                    await ws.send_json({"t": "drive", **msg, "speed": 1.0})
                    await asyncio.sleep(0.06)
                out[name] = [d for d, _ in sticks(sim)[n:] if not is_zero(d)]
                await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
                await asyncio.sleep(0.4)
            st = [m for m in of(ws, "status") if m.get("drive_mode") == "sticks"]
            await ws.close()
            return out, st

    out, st = run(go())
    assert st
    for name in out:
        assert out[name], name
        for d in out[name]:
            assert all(abs(d[k]) <= STICK_MAX + 1e-9 for k in ("lx", "ly", "rx", "ry")) and d["keys"] == 0
    assert all(d["ly"] == pytest.approx(STICK_MAX) and d["lx"] == 0 and d["rx"] == 0 for d in out["fwd"])
    assert all(d["lx"] == pytest.approx(-STICK_MAX) and d["ly"] == 0 for d in out["left"])   # left = lx -
    assert all(d["rx"] == pytest.approx(-STICK_MAX) and d["ly"] == 0 for d in out["turnleft"])  # turn left = rx - (real dog)
    assert all(d["ly"] == pytest.approx(-0.5 * STICK_MAX) for d in out["back"])
    assert sim.moves() == []                     # no sport Move in sticks mode


def test_sim_stick_hold_keeps_walking_without_zero_sticks(tmp_path):
    """Control for the stick_hold tests: StopMove alone does not stop held sticks; a zero stick does."""
    sim = SimConn(camera=False, lidar=False, stick_hold=True)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        await dog.send_sticks(0.0, 0.2, 0.0)
        dog._sticks_used = False                  # pretend the adapter never zeroes the sticks
        await dog.stop_move()                     # StopMove only
        await asyncio.sleep(1.5)                  # longer than the Move expiry (1.0 s)
        held = math.hypot(*sim.v)
        await dog.zero_sticks()
        await asyncio.sleep(0.6)
        stopped = math.hypot(*sim.v)
        await dog.close()
        return held, stopped

    held, stopped = run(go())
    assert held > 0.1 and stopped < 0.02


@pytest.mark.parametrize("kind", ["release", "deadman", "ws_close"])
def test_sticks_automatic_stops_zero_sticks_and_stopmove(tmp_path, kind):
    sim = SimConn(camera=False, lidar=False, stick_hold=True)     # only a zero stick stops it

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await set_mode(ctl, ws, "sticks")
            await drive_for(ws, 0.5)
            last_cmd = ctl.dog._last_move_cmd_t
            t0 = time.monotonic()
            if kind == "release":
                await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            elif kind == "ws_close":
                await ws.close()
            await asyncio.sleep(1.5)          # dead-man: just go silent (and past the Move expiry)
            speed = math.hypot(*sim.v)
            if kind != "ws_close":
                await ws.close()
            return t0, last_cmd, speed

    t0, last_cmd, speed = run(go())
    assert speed < 0.02                                # the zero sticks stopped the held stick
    assert last_cmd > 0                                # stick sends counted as motion commands
    stops = [s[3] for s in sim.stops() if s[3] >= t0]
    assert stops, "no StopMove"
    zs = zeros_after(sim, t0, stops[0] + 0.4)
    assert zs and zs[0] <= stops[0] + 0.01             # zero sticks no later than StopMove
    assert len(zs) >= 3                                # repeated over ~0.2 s
    assert nonzero_after_first_zero(sim, t0) == []     # the stick stream can't keep it walking
    assert 1005 not in sim.apis() and 1001 not in sim.apis()   # automatic stop: stays standing
    kinds = {"release": "release", "deadman": "deadman", "ws_close": "ws_close"}
    assert any(e["event"] == "stop" and e["kind"] == kinds[kind] for e in log_events(tmp_path))


def test_sticks_stop_button_is_zero_stopmove_standdown_never_damp(tmp_path):
    sim = SimConn(camera=False, lidar=False, stick_hold=True)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await set_mode(ctl, ws, "sticks")
            driver = asyncio.create_task(drive_for(ws, 1.2))     # keeps pushing the stick
            await asyncio.sleep(0.5)
            t0 = time.monotonic()
            await ws.send_json({"t": "stop"})
            await driver
            await asyncio.sleep(1.0)
            lock = ctl.dog.motion_lock()
            await ws.close()
            return t0, lock

    t0, lock = run(go())
    apis = [s[1] for s in sim.sent if s[0] == "SPORT_MOD"]
    assert 1001 not in apis
    sd = [s[3] for s in sim.sent if s[0] == "SPORT_MOD" and s[1] == 1005]
    st = [s[3] for s in sim.stops() if s[3] >= t0]
    zs = zeros_after(sim, t0, t0 + 1.0)
    assert sd and st and zs and zs[0] <= st[0] + 0.01 and st[0] <= sd[0]
    assert nonzero_after_first_zero(sim, t0) == []
    assert lock


def test_rearm_after_link_loss_zeroes_held_sticks(tmp_path):
    """Link dies mid-walk in sticks mode: the release zero is lost and the dog keeps the held stick.
    Re-arm: the new adapter publishes a zero burst right after connect, and its STOP zeroes too."""
    sim = SimConn(camera=False, lidar=False, stick_hold=True)
    ps = sim.datachannel.pub_sub
    real_connect = sim.connect

    async def dead_request(topic, options):
        raise ConnectionError("link down")

    def link_down():
        ps.publish_without_callback = lambda topic, data=None: None      # sends vanish
        ps.publish_request_new = dead_request
        sim.pc.connectionState = "failed"

    async def connect_with_link_back():
        del ps.publish_without_callback, ps.publish_request_new        # cable back in
        await real_connect()

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await set_mode(ctl, ws, "sticks")
            await drive_for(ws, 0.4)
            link_down()
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.5)
            still_walking = math.hypot(*sim.v)
            sim.connect = connect_with_link_back
            old = ctl.dog
            await ws.send_json({"t": "rearm"})
            assert await until(lambda: ctl.dog is not None and ctl.dog is not old and ctl.busy is None, 5.0)
            t_conn = time.monotonic()
            await asyncio.sleep(0.6)
            stopped = math.hypot(*sim.v)
            marked = ctl.dog._sticks_used
            t_stop = time.monotonic()
            await ws.send_json({"t": "stop"})
            await asyncio.sleep(0.5)
            await ws.close()
            return still_walking, stopped, marked, t_conn, t_stop

    still_walking, stopped, marked, t_conn, t_stop = run(go())
    assert still_walking > 0.1                          # the lost release left the stick held
    assert stopped < 0.02 and marked                    # zero burst after re-arm stopped it
    zs = [t for d, t in sticks(sim) if is_zero(d)]
    assert [t for t in zs if t_conn - 1.0 <= t <= t_conn + 0.3]
    assert len([t for t in zs if t >= t_stop]) >= 3     # STOP on the new adapter zeroes too
    assert 1001 not in sim.apis()
    assert [e for e in log_events(tmp_path) if e["event"] == "zero_sticks"]


def test_new_adapter_in_move_mode_without_sticks_sends_no_stick_traffic(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await ws.send_json({"t": "rearm"})
            await asyncio.sleep(0.3)
            assert await ctl.wait_connected(5.0)
            await asyncio.sleep(0.4)
            await ws.close()

    run(go())
    assert sticks(sim) == []


# ------------------------------------------------------------------ simulated avoidance (the real-dog finding)

def test_sim_avoidance_applies_to_sticks_not_to_move(tmp_path):
    """Box face 1.3 m ahead of the dog (nose at +0.35 m). Brake OFF: only the dog's own avoidance acts."""
    async def go(mode):
        sim = SimConn(camera=False)
        ctl = make_ctl(tmp_path / mode, sim)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await ws.send_json({"t": "lidar_brake", "enabled": False})
            assert await until(lambda: ctl.lidar_brake_enabled is False, 2.0)
            if mode == "sticks":
                await set_mode(ctl, ws, "sticks")
            await drive_for(ws, 4.5)
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.4)
            await ws.close()
        return sim.x

    x_sticks = run(go("sticks"))
    x_move = run(go("move"))
    assert 0.2 < x_sticks < 1.3 - 0.35 - 0.3          # stopped about 0.5 m short of the box
    assert x_move + 0.35 > 1.3                         # Move walked into the box (avoidance ignored)


def test_lidar_brake_stops_move_mode_short_of_box(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            await drive_for(ws, 4.5)
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.4)
            await ws.close()
        return sim.x

    x = run(go())
    assert 0.2 < x < 1.3 - 0.35 - 0.3


# ------------------------------------------------------------------ LiDAR brake in the controller

def brake_logs(tmp_path):
    return [e for e in log_events(tmp_path) if e["event"] == "lidar_brake"]


def test_brake_zeroes_forward_allows_backward_and_turn(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ctl.dog.lidar_view = lambda: dict(NEAR)
            ws = await collecting_ws(client)
            assert await until(lambda: ctl._brake_view is not None, 2.0)
            n = len(sim.moves())
            await drive_for(ws, 0.5, x=1.0)
            fwd = sim.moves()[n:]
            st = [m for m in of(ws, "status") if m.get("lidar_brake", "").startswith("braking")]
            n = len(sim.moves())
            await drive_for(ws, 0.4, x=-1.0)
            back = sim.moves()[n:]
            n = len(sim.moves())
            for _ in range(6):
                await ws.send_json({"t": "drive", "x": 1, "y": 0, "yaw": 1, "speed": 1.0})
                await asyncio.sleep(0.06)
            turn = sim.moves()[n:]
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.3)
            await ws.close()
            return fwd, back, turn, st

    fwd, back, turn, st = run(go())
    assert fwd and all(m[2]["x"] == 0.0 for m in fwd)
    assert back and all(m[2]["x"] < 0 for m in back)
    assert turn and all(m[2]["x"] == 0.0 and m[2]["z"] > 0 for m in turn)
    assert st


def test_brake_in_sticks_mode_zeroes_ly(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ctl.dog.lidar_view = lambda: dict(NEAR)
            ws = await collecting_ws(client)
            assert await until(lambda: ctl._brake_view is not None, 2.0)
            await set_mode(ctl, ws, "sticks")
            n = len(sticks(sim))
            for _ in range(6):
                await ws.send_json({"t": "drive", "x": 1, "y": 0, "yaw": 1, "speed": 1.0})
                await asyncio.sleep(0.06)
            sent = [d for d, _ in sticks(sim)[n:]]
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.3)
            await ws.close()
            return sent

    sent = run(go())
    assert sent and all(d["ly"] == 0 for d in sent) and any(d["rx"] < 0 for d in sent)


@pytest.mark.parametrize("case", ["stale", "no_view", "old_view", "no_scan", "old_scan"])
def test_brake_fails_open_and_reports_inactive(tmp_path, case):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            if case == "stale":
                ctl.dog.lidar_view = lambda: {**NEAR, "stale": True}
            elif case == "old_scan":            # fresh push of a ~3 s old scan (not yet "stale")
                ctl.dog.lidar_view = lambda: {**NEAR, "age_s": 3.0}
            elif case == "no_scan":
                ctl.dog.lidar_view = lambda: {**NEAR, "nearest_ahead_m": None, "reason": "no scan"}
            elif case == "no_view":
                ctl.dog.lidar_view = None
            ws = await collecting_ws(client)
            if case == "old_view":
                ctl.dog.lidar_view = lambda: dict(NEAR)
                assert await until(lambda: ctl._brake_view is not None, 2.0)
                ctl.dog.lidar_view = None            # pushes stop; the last view ages out
                await asyncio.sleep(1.3)
            else:
                await asyncio.sleep(0.5)
            n = len(sim.moves())
            await drive_for(ws, 0.4, x=1.0)
            fwd = sim.moves()[n:]
            await asyncio.sleep(0.3)
            st = of(ws, "status")[-1]
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.2)
            await ws.close()
            return fwd, st

    fwd, st = run(go())
    assert fwd and all(m[2]["x"] > 0 for m in fwd)       # fail open: not braked
    assert st["lidar_brake"] == "inactive (no fresh LiDAR)"
    assert brake_logs(tmp_path) == []


def test_brake_logs_one_event_per_transition(tmp_path):
    sim = SimConn(camera=False, lidar=False)
    view = {"v": dict(NEAR)}

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ctl.dog.lidar_view = lambda: dict(view["v"])
            ws = await collecting_ws(client)
            assert await until(lambda: ctl._brake_view is not None, 2.0)
            driver = asyncio.create_task(drive_for(ws, 1.6, x=1.0))
            await asyncio.sleep(0.8)
            view["v"] = dict(FAR)                         # obstacle gone
            await driver
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.3)
            events = [m["msg"] for m in of(ws, "event") if "brake" in m["msg"].lower()]
            await ws.close()
            return events

    events = run(go())
    logs = brake_logs(tmp_path)
    assert [e["action"] for e in logs] == ["engaged", "released"]
    assert logs[0]["nearest_ahead_m"] == 0.3
    assert len(events) == 2
    assert sim.moves()[-1][2]["x"] > 0                    # released: forward again


def test_brake_checkbox_off_no_brake_logged_controller_only(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ctl.dog.lidar_view = lambda: dict(NEAR)
            ws1 = await collecting_ws(client)
            ws2 = await collecting_ws(client)              # view-only
            assert await until(lambda: ctl._brake_view is not None, 2.0)
            default = ctl.lidar_brake_enabled
            await ws2.send_json({"t": "lidar_brake", "enabled": False})
            await asyncio.sleep(0.3)
            after_viewer = ctl.lidar_brake_enabled
            await ws1.send_json({"t": "lidar_brake", "enabled": False})
            assert await until(lambda: ctl.lidar_brake_enabled is False, 2.0)
            n = len(sim.moves())
            await drive_for(ws1, 0.4, x=1.0)
            fwd = sim.moves()[n:]
            await asyncio.sleep(0.3)
            st = of(ws1, "status")[-1]
            await ws1.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.2)
            await ws1.close()
            await ws2.close()
            return default, after_viewer, fwd, st

    default, after_viewer, fwd, st = run(go())
    assert default is True and after_viewer is True
    assert fwd and all(m[2]["x"] > 0 for m in fwd)
    assert st["lidar_brake"] == "off" and st["lidar_brake_enabled"] is False
    assert [e for e in log_events(tmp_path) if e["event"] == "lidar_brake_off"]
    assert brake_logs(tmp_path) == []
    assert Controller(lambda: None, log_path=tmp_path / "x.jsonl").lidar_brake_enabled is True   # ON at start


def test_page_has_dodge_controls(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False, lidar=False))
        async with serve(ctl) as client:
            return await (await client.get("/")).text()

    page = run(go())
    assert "Drive via remote-controller path" in page and "staff controller stop must still win" in page
    assert "LiDAR brake (0.5 m)" in page
    assert JOY_MAX_VX <= 0.3
