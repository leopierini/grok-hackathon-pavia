"""Safety envelope (fence / speed / tilt / route overshoot), Set home, the on/off switch and
joystick control takeover. Simulated / scripted connections only: no robot, no network."""

import asyncio
import json
import math
import time
from contextlib import asynccontextmanager
from threading import Event

import pytest
from aiohttp.test_utils import TestClient, TestServer

from patrol.contract import AdapterError, RunContext
from patrol.dog.joystick import Controller, build_app
from patrol.dog.real import RealDog
from patrol.dog.sim_conn import SimConn


def run(coro):
    return asyncio.run(coro)


def ctx(seconds=10.0):
    return RunContext(mission_id="t", deadline_monotonic=time.monotonic() + seconds, cancel=Event())


# ------------------------------------------------------------------ scripted connection

class ScriptPubSub:
    def __init__(self, conn):
        self.conn = conn
        self.subs = {}

    def subscribe(self, topic, cb=None):
        self.subs[topic] = cb

    async def publish_request_new(self, topic, options):
        api = options["api_id"]
        self.conn.sent.append((topic, api, options.get("parameter"), time.monotonic()))
        if topic == "SPORT_MOD":
            if api == 1008:
                p = options["parameter"]
                self.conn.cmd = (p["x"], p["y"])
                self.conn.cmd_t = time.monotonic()
            elif api in (1003, 1005):
                self.conn.cmd = (0.0, 0.0)
        if topic == "OBSTACLES_AVOID" and api == 1002:
            return {"data": {"header": {"status": {"code": 0}}, "data": json.dumps({"enable": True})}}
        return {"data": {"header": {"status": {"code": 0}}}}


class ScriptConn:
    """Test sets pos / vel / rpy directly. With `gain`, odometry advances at gain x the
    commanded velocity while the reported velocity equals the command (bad odometry)."""

    def __init__(self, *, gain=None):
        self.sent = []
        self.pos = [0.0, 0.0]
        self.vel = [0.0, 0.0]
        self.rpy = [0.0, 0.0, 0.0]
        self.gain = gain
        self.cmd = (0.0, 0.0)
        self.cmd_t = 0.0
        self.datachannel = type("DC", (), {})()
        self.datachannel.pub_sub = ScriptPubSub(self)
        self.video = type("V", (), {"add_track_callback": lambda s, cb: None,
                                    "switchVideoChannel": lambda s, on: None})()
        self._task = None

    async def connect(self):
        self._task = asyncio.get_running_loop().create_task(self._stream())

    async def disconnect(self):
        if self._task:
            self._task.cancel()

    async def _stream(self):
        subs = self.datachannel.pub_sub.subs
        last = time.monotonic()
        while True:
            now = time.monotonic()
            dt, last = now - last, now
            if self.gain is not None:
                if now - self.cmd_t > 0.5:
                    self.cmd = (0.0, 0.0)
                self.vel = list(self.cmd)
                self.pos[0] += self.cmd[0] * self.gain * dt
                self.pos[1] += self.cmd[1] * self.gain * dt
            if "LF_SPORT_MOD_STATE" in subs:
                subs["LF_SPORT_MOD_STATE"]({"data": {
                    "mode": 1, "body_height": 0.32, "velocity": list(self.vel) + [0.0], "yaw_speed": 0.0,
                    "position": None if self.pos is None else list(self.pos) + [0.3],
                    "imu_state": {"rpy": list(self.rpy)}}})
            if "LOW_STATE" in subs:
                subs["LOW_STATE"]({"data": {}})
            if "MULTIPLE_STATE" in subs:
                subs["MULTIPLE_STATE"]({"data": json.dumps({"obstaclesAvoidSwitch": True})})
            await asyncio.sleep(0.02)

    def apis(self):
        return [s[1] for s in self.sent if s[0] == "SPORT_MOD"]


def make_dog(tmp_path, conn, **cfg):
    config = {"interface": "simulated", "command_timeout_s": 0.3, **cfg}
    return RealDog(config=config, output_dir=tmp_path, _conn_factory=lambda ip: conn)


async def drive_until(dog, cond, timeout=4.0, v=(0.5, 0.0, 0.0)):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not cond():
        try:
            await dog.drive(*v)
        except AdapterError:
            pass
        await asyncio.sleep(0.1)
    return cond()


# ------------------------------------------------------------------ RealDog: defaults + config

def test_defaults_on_and_home_set_on_connect(tmp_path):
    conn = ScriptConn()
    conn.pos = [1.5, -2.0]

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        s = dog.safety_status()
        await dog.close()
        return s

    s = run(go())
    assert s["enabled"] is True and s["state"] == "ok"
    assert s["home"] == [1.5, -2.0] and s["home_source"].startswith("auto")
    assert s["distance_from_home_m"] == 0.0 and s["radius_m"] == 3.0
    assert s["limits"]["max_speed_mps"] == 0.6 and s["limits"]["max_tilt_deg"] == 25.0
    assert s["limits"]["route_overshoot"] == {"factor": 1.3, "margin_m": 0.3}
    assert s["last_trip"] is None and [a for a in conn.apis()] == []


@pytest.mark.parametrize("cfg", [
    {"fence_radius_m": -1}, {"fence_radius_m": 0}, {"fence_radius_m": float("nan")},
    {"fence_radius_m": float("inf")}, {"fence_radius_m": "3"}, {"fence_radius_m": True},
    {"max_speed_mps": 0}, {"max_tilt_deg": -5}, {"route_overshoot": {"factor": 0}},
    {"route_overshoot": {"margin_m": -0.1}}, {"route_overshoot": 1.3},
    {"safety_envelope_enabled": "no"}, {"home": "here"}, {"home": [0.0]}, {"home": [float("nan"), 0]},
])
def test_invalid_safety_config_rejected(tmp_path, cfg):
    with pytest.raises(AdapterError) as e:
        make_dog(tmp_path, ScriptConn(), **cfg)
    assert e.value.code == "invalid_input"


def test_home_from_config_and_constructor(tmp_path):
    conn = ScriptConn()

    async def go():
        a = make_dog(tmp_path, conn, home=[2.0, 0.0])
        b = RealDog(config={"interface": "x"}, output_dir=tmp_path, home=(0.5, 0.5),
                    _conn_factory=lambda ip: conn)
        await a.connect()
        s = a.safety_status()
        await a.close()
        return s, b.safety_status()

    sa, sb = run(go())
    assert sa["home"] == [2.0, 0.0] and sa["home_source"] == "config" and sa["distance_from_home_m"] == 2.0
    assert sb["home"] == [0.5, 0.5] and sb["home_source"] == "constructor"


# ------------------------------------------------------------------ fence

def test_fence_trip_lies_down_softly_once(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        dog = make_dog(tmp_path, sim, fence_radius_m=0.4)
        await dog.connect()
        tripped = await drive_until(dog, lambda: dog.last_safety_trip is not None)
        await asyncio.sleep(2.0)                   # still outside, lying down: no new trips / rests
        with pytest.raises(AdapterError) as e:
            await dog.drive(0.2, 0, 0)
        s = dog.safety_status()
        lock = dog.motion_lock()
        await dog.close()
        return tripped, s, lock, e.value.code

    tripped, s, lock, code = run(go())
    apis = sim.apis()
    assert tripped and code == "unsafe_state"
    assert "fence" in lock and lock.startswith("safety:")
    assert s["last_trip"]["kind"] == "fence" and s["last_trip"]["rest_scheduled"] is True
    assert s["last_trip"]["values"]["distance_m"] > 0.4
    assert s["last_trip"]["rest_report"]["standdown_sent"] is True
    assert len(s["trips"]) == 1                   # latched
    assert apis.count(1005) == 1                  # rest scheduled once
    assert 1001 not in apis                       # never Damp
    sd = apis.index(1005)
    assert 1003 in apis[:sd] and 1008 not in apis[sd:]
    assert s["distance_from_home_m"] < 0.4 + 0.3  # stopped soon after crossing


def test_stationary_outside_fence_is_reported_blocks_motion_until_set_home(tmp_path):
    conn = ScriptConn()

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()                        # home = (0, 0)
        for i in range(1, 36):                     # slow odometry drift while standing still
            conn.pos = [0.1 * i, 0.0]              # 0.1 m per reading: below the jump detector
            await asyncio.sleep(0.03)
        await asyncio.sleep(0.3)
        s = dog.safety_status()
        with pytest.raises(AdapterError) as e:
            await dog.drive(0.1, 0, 0)
        with pytest.raises(AdapterError) as e2:
            await dog.run_segments([{"vx": 0.1, "duration_s": 0.2}], ctx())
        rec = dog.set_home()
        await dog.drive(0.1, 0, 0)
        s2 = dog.safety_status()
        await dog.close()
        return s, str(e.value), e2.value.code, rec, s2

    s, msg, code2, rec, s2 = run(go())
    assert s["state"] == "outside_fence" and s["last_trip"] is None   # no lie-down for drift
    assert "outside fence" in msg and code2 == "unsafe_state"
    assert 1005 not in conn.apis()
    assert rec["old"] == [0.0, 0.0] and rec["new"] == [3.5, 0.0]
    assert s2["state"] == "ok" and s2["home_changes"]


def test_unknown_position_blocks_motion(tmp_path):
    conn = ScriptConn()
    conn.pos = None

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        with pytest.raises(AdapterError) as e:
            await dog.drive(0.1, 0, 0)
        with pytest.raises(AdapterError):
            dog.set_home()
        s = dog.safety_status()
        await dog.close()
        return str(e.value), s

    msg, s = run(go())
    assert "home position unknown" in msg or "position unknown" in msg
    assert s["state"] == "unknown" and [s_ for s_ in conn.sent if s_[1] == 1008] == []


def test_set_home_refused_while_moving(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        for _ in range(4):
            await dog.drive(0.3, 0, 0)
            await asyncio.sleep(0.08)
        with pytest.raises(AdapterError) as e:
            dog.set_home()
        await dog.stop_move()
        await asyncio.sleep(1.3)
        rec = dog.set_home()
        await dog.close()
        return e.value, rec

    err, rec = run(go())
    assert err.code == "unsafe_state" and "moving" in str(err)
    assert rec["new"][0] > 0.05


# ------------------------------------------------------------------ speed + tilt

def test_speed_spike_does_not_trip_sustained_does(tmp_path):
    conn = ScriptConn()

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        conn.vel = [1.0, 0.0]
        await asyncio.sleep(0.15)                  # gait-peak-like spike
        conn.vel = [0.0, 0.0]
        await asyncio.sleep(0.2)
        after_spike = dog.last_safety_trip
        conn.vel = [0.0, 0.9]
        await asyncio.sleep(0.6)
        conn.vel = [0.0, 0.0]
        await asyncio.sleep(0.4)
        trip, lock = dog.last_safety_trip, dog.motion_lock()
        await dog.close()
        return after_spike, trip, lock

    after_spike, trip, lock = run(go())
    assert after_spike is None
    assert trip["kind"] == "speed" and trip["values"]["sustained_s"] >= 0.3 and "speed" in lock
    assert 1005 in conn.apis() and 1001 not in conn.apis()


def test_tilt_trip(tmp_path):
    conn = ScriptConn()

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        conn.rpy = [0.0, math.radians(35), 0.0]
        await asyncio.sleep(0.1)
        conn.rpy = [0.0, 0.0, 0.0]
        await asyncio.sleep(0.1)
        short = dog.last_safety_trip
        conn.rpy = [math.radians(-30), 0.0, 0.0]
        await asyncio.sleep(0.5)
        trip = dog.last_safety_trip
        s = dog.safety_status()
        await dog.close()
        return short, trip, s

    short, trip, s = run(go())
    assert short is None
    assert trip["kind"] == "tilt" and trip["values"]["roll_deg"] < -25
    assert s["tilt_deg"]["roll"] < -25
    assert conn.apis().count(1005) == 1 and 1001 not in conn.apis()


# ------------------------------------------------------------------ route overshoot

def test_route_overshoot_trips(tmp_path):
    conn = ScriptConn(gain=3.0)                    # odometry shows 3x the commanded travel

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        t0 = time.monotonic()
        res = await dog.run_segments([{"vx": 0.3, "duration_s": 2.0}], ctx())
        dt = time.monotonic() - t0
        await asyncio.sleep(0.3)
        s = dog.safety_status()
        await dog.close()
        return res, s, dt

    res, s, dt = run(go())
    trip = s["last_trip"]
    assert trip["kind"] == "route_overshoot"
    assert trip["values"]["planned_m"] == pytest.approx(0.6)
    assert trip["values"]["travel_m"] > 0.6 * 1.3 + 0.3
    assert not res.completed and "overshoot" in res.detail and dt < 2.0
    assert 1005 in conn.apis() and 1001 not in conn.apis()
    assert s["route"] is None


def test_normal_route_does_not_overshoot(tmp_path):
    conn = ScriptConn(gain=1.0)

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        res = await dog.run_segments([{"vx": 0.3, "duration_s": 1.0}], ctx())
        s = dog.safety_status()
        await dog.close()
        return res, s

    res, s = run(go())
    assert res.completed and s["last_trip"] is None


# ------------------------------------------------------------------ on / off switch

def test_envelope_off_no_trip_on_again_outside_needs_set_home(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        dog = make_dog(tmp_path, sim, fence_radius_m=0.3)
        await dog.connect()
        assert dog.safety_status()["enabled"] is True
        for _ in range(3):                          # moving: off is refused
            await dog.drive(0.3, 0, 0)
            await asyncio.sleep(0.08)
        with pytest.raises(AdapterError) as e:
            dog.set_safety_envelope(False)
        await dog.stop_move()
        await asyncio.sleep(1.3)
        dog.set_safety_envelope(False)
        await drive_until(dog, lambda: (dog.safety_status()["distance_from_home_m"] or 0) > 0.6)
        await dog.stop_move()
        await asyncio.sleep(0.2)
        off = dog.safety_status()
        res = dog.set_safety_envelope(True)         # back on while still coasting/outside
        await asyncio.sleep(0.8)
        on = dog.safety_status()
        with pytest.raises(AdapterError) as e2:
            await dog.drive(0.2, 0, 0)
        await asyncio.sleep(1.0)
        dog.set_home()
        await dog.drive(0.2, 0, 0)
        await dog.stop_move()
        await dog.close()
        return e.value.code, off, res, on, str(e2.value)

    code, off, res, on, msg = run(go())
    assert code == "unsafe_state"
    assert off["enabled"] is False and off["state"] == "off" and off["last_trip"] is None
    assert off["distance_from_home_m"] > 0.3        # still measured while off
    assert res["outside_fence"] is True
    assert on["state"] == "outside_fence" and on["last_trip"] is None   # no instant trip
    assert "outside fence" in msg
    assert 1005 not in sim.apis()


def test_envelope_off_from_config(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        dog = make_dog(tmp_path, sim, fence_radius_m=0.3, safety_envelope_enabled=False)
        await dog.connect()
        await drive_until(dog, lambda: (dog.safety_status()["distance_from_home_m"] or 0) > 0.5)
        s = dog.safety_status()
        await dog.close()
        return s

    s = run(go())
    assert s["enabled"] is False and s["last_trip"] is None and 1005 not in sim.apis()


# ------------------------------------------------------------------ joystick

def make_ctl(tmp_path, sim, made=None, **cfg):
    def factory():
        d = make_dog(tmp_path, sim, **cfg)
        if made is not None:
            made.append(d)
        return d
    return Controller(factory, log_path=tmp_path / "joystick.jsonl", fake=True, verbose=False)


@asynccontextmanager
async def serve(ctl):
    async with TestClient(TestServer(build_app(ctl))) as client:
        assert await ctl.wait_connected(5.0)
        yield client


async def ws_open(client):
    ws = await client.ws_connect("/ws")
    ws.hello = await ws.receive_json()
    ws.got = []

    async def drain():
        async for m in ws:
            try:
                ws.got.append(json.loads(m.data))
            except Exception:
                pass
    ws._drain = asyncio.create_task(drain())
    return ws


async def drive_for(ws, seconds, x=1.0, speed=1.0, period=0.06):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        await ws.send_json({"t": "drive", "x": x, "y": 0, "yaw": 0, "speed": speed})
        await asyncio.sleep(period)
    await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0, "speed": speed})


def events(tmp_path):
    p = tmp_path / "joystick.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_joystick_trip_rearm_keeps_home_and_needs_set_home(tmp_path):
    sim = SimConn(camera=False)
    made = []

    async def go():
        ctl = make_ctl(tmp_path, sim, made, fence_radius_m=0.3)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await drive_for(ws, 2.0)                       # 0.3 m/s: crosses 0.3 m after ~1 s
            await asyncio.sleep(1.5)                       # lies down
            first = ctl.dog
            trip = first.last_safety_trip
            await ws.send_json({"t": "rearm"})
            await asyncio.sleep(0.3)
            assert await ctl.wait_connected(5.0)
            new = ctl.dog
            s_new = new.safety_status()
            await ws.send_json({"t": "stand"})             # refused: outside fence
            await asyncio.sleep(0.3)
            n_moves = len(sim.moves())
            await drive_for(ws, 0.3)                       # sticks inactive
            moves_outside = len(sim.moves()) - n_moves
            status = await ctl.status()
            await ws.send_json({"t": "set_home"})
            await asyncio.sleep(0.2)
            s_home = new.safety_status()
            await ws.send_json({"t": "stand"})
            await asyncio.sleep(4.5)
            n_moves = len(sim.moves())
            await drive_for(ws, 0.3)
            moves_after = len(sim.moves()) - n_moves
            await asyncio.sleep(0.2)
            await ws.close()
            return first, new, trip, s_new, moves_outside, status, s_home, moves_after

    first, new, trip, s_new, moves_outside, status, s_home, moves_after = run(go())
    assert new is not first and trip["kind"] == "fence"
    assert s_new["home"] == [0.0, 0.0] and s_new["home_source"] == "adopted"   # home kept
    assert s_new["state"] == "outside_fence" and s_new["last_trip"] is None
    assert moves_outside == 0 and "outside fence" in status["drive_block"]
    assert status["safety"]["state"] == "outside_fence"
    assert s_home["state"] == "ok" and s_home["home"] != [0.0, 0.0]
    assert moves_after > 0
    ev = events(tmp_path)
    trips = [e for e in ev if e["event"] == "safety_trip"]
    assert len(trips) == 1 and "fence" in trips[0]["reason"]
    assert any(e["event"] == "set_home" for e in ev)
    assert any(e["event"] == "stop" and e["kind"] == "safety_trip" for e in ev)
    apis = sim.apis()
    assert 1001 not in apis and apis.count(1005) == 1


def test_joystick_safety_toggle(tmp_path):
    sim = SimConn(camera=False)
    made = []

    async def go():
        ctl = make_ctl(tmp_path, sim, made, fence_radius_m=0.3)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            default = (await ctl.status())["safety_enabled"], ctl.dog.safety_status()["enabled"]
            driver = asyncio.create_task(drive_for(ws, 0.5))
            await asyncio.sleep(0.25)
            await ws.send_json({"t": "safety", "enabled": False})   # refused while moving
            await driver
            await asyncio.sleep(0.1)
            still_on = ctl.envelope_enabled
            await asyncio.sleep(1.3)
            await ws.send_json({"t": "safety", "enabled": False})
            await asyncio.sleep(0.2)
            off = ctl.envelope_enabled, ctl.dog.safety_status()["enabled"]
            await drive_for(ws, 2.5)                                # 0.75 m: past the fence, no trip
            await asyncio.sleep(1.3)
            past = ctl.dog.safety_status()
            await ws.send_json({"t": "rearm"})                      # re-arm: thresholds back ON
            await asyncio.sleep(0.3)
            assert await ctl.wait_connected(5.0)
            after_rearm = ctl.dog.safety_status()["enabled"]
            await ws.send_json({"t": "safety", "enabled": True})
            await asyncio.sleep(0.3)
            on = ctl.dog.safety_status()
            block = ctl._drive_block()
            await ws.close()
        ctl2 = make_ctl(tmp_path, sim)                              # "server restart"
        return default, still_on, off, past, after_rearm, on, block, ctl2.envelope_enabled

    default, still_on, off, past, after_rearm, on, block, restart = run(go())
    assert default == (True, True)
    assert still_on is True
    assert off == (False, False)
    assert past["last_trip"] is None and past["distance_from_home_m"] > 0.3
    assert after_rearm is True                                  # never carried over (review #4)
    assert on["enabled"] is True and on["state"] == "outside_fence" and on["last_trip"] is None
    assert "outside fence" in block
    assert restart is True
    ev = [e["event"] for e in events(tmp_path)]
    assert ev.count("safety_envelope_off") == 1 and ev.count("safety_envelope_on") == 1
    assert "safety_trip" not in ev and 1005 not in sim.apis()


def test_take_control_stops_first_and_moves_control(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws1 = await ws_open(client)
            ws2 = await ws_open(client)
            driver = asyncio.create_task(drive_for(ws1, 1.2))
            await asyncio.sleep(0.4)
            t_claim = time.monotonic()
            await ws2.send_json({"t": "claim"})
            await driver                                   # old tab keeps pushing: ignored
            await asyncio.sleep(0.2)
            moves_after_claim = [m for m in sim.moves() if m[3] > t_claim + 0.05]
            stops_after_claim = [s for s in sim.stops() if s[3] >= t_claim]
            n = len(sim.moves())
            await drive_for(ws2, 0.3)
            new_moves = len(sim.moves()) - n
            await asyncio.sleep(0.2)
            await ws1.close()
            await ws2.close()
            return ws1, ws2, moves_after_claim, stops_after_claim, new_moves, t_claim

    ws1, ws2, moves_after_claim, stops_after_claim, new_moves, t_claim = run(go())
    assert ws1.hello["role"] == "control" and ws2.hello["role"] == "view"
    assert stops_after_claim and stops_after_claim[0][3] - t_claim < 0.2   # StopMove first
    assert moves_after_claim == []                                       # old tab can't drive
    assert new_moves > 0                                                 # new tab can
    assert any(m.get("t") == "role" and m.get("role") == "view" for m in ws1.got)
    assert any(m.get("t") == "event" and "control taken" in m.get("msg", "") for m in ws1.got)
    assert any(m.get("t") == "role" and m.get("role") == "control" for m in ws2.got)
    assert any(e["event"] == "control_taken" for e in events(tmp_path))
    assert 1005 not in sim.apis()                                        # dog stays standing


# ------------------------------------------------------------------ review #2 regressions

def test_prepare_refused_when_position_unknown(tmp_path):
    conn = ScriptConn()
    conn.pos = None                                   # no odometry at all

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        with pytest.raises(AdapterError) as e:
            await dog.prepare(ctx())
        await dog.close()
        return e.value

    err = run(go())
    assert err.code == "unsafe_state" and "unknown" in err.detail
    assert 1004 not in conn.apis() and 1002 not in conn.apis()


def test_close_waits_for_the_trip_lie_down(tmp_path):
    conn = ScriptConn()

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        conn.rpy = [math.radians(35), 0.0, 0.0]       # tilt trip (sustained 0.2 s)
        await asyncio.sleep(0.3)
        assert dog.last_safety_trip is not None
        await dog.close()                             # immediately, like a fast Re-arm

    run(go())
    assert 1005 in conn.apis() and 1001 not in conn.apis()


def test_stop_then_trip_sends_only_one_standdown(tmp_path):
    conn = ScriptConn()

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        rest = asyncio.create_task(dog.rest())        # operator STOP
        await asyncio.sleep(0.05)
        conn.rpy = [math.radians(35), 0.0, 0.0]       # ...and a trip right after
        await rest
        await asyncio.sleep(0.6)
        trip = dog.last_safety_trip
        await dog.close()
        return trip

    trip = run(go())
    assert conn.apis().count(1005) == 1
    assert trip is not None and trip["rest_report"].get("skipped")


def test_odometry_jump_blocks_until_set_home(tmp_path):
    conn = ScriptConn()

    async def go():
        dog = make_dog(tmp_path, conn)
        await dog.connect()
        conn.pos = [2.0, 0.0]                         # 2 m between two readings: a reset/glitch
        await asyncio.sleep(0.2)
        block = dog.safety_block()
        with pytest.raises(AdapterError):
            await dog.drive(0.1, 0, 0)
        dog.set_home()
        block2 = dog.safety_block()
        await dog.drive(0.1, 0, 0)
        await dog.close()
        return block, block2

    block, block2 = run(go())
    assert block and "odometry jump" in block
    assert block2 is None


def test_route_stops_when_thresholds_turned_on_outside_fence(tmp_path):
    conn = ScriptConn(gain=1.0)

    async def go():
        dog = make_dog(tmp_path, conn, fence_radius_m=0.3, safety_envelope_enabled=False)
        await dog.connect()
        task = asyncio.create_task(dog.run_segments([{"vx": 0.5, "duration_s": 4.0}], ctx()))
        await asyncio.sleep(1.2)                      # ~0.6 m: outside the 0.3 m fence, nothing tripped
        dog.set_safety_envelope(True)
        t = time.monotonic()
        res = await asyncio.wait_for(task, 3.0)
        dt = time.monotonic() - t
        await dog.close()
        return res, dt

    res, dt = run(go())
    assert not res.completed and "outside fence" in res.detail
    assert dt < 2.5                                    # stopped instead of finishing the 4 s route


def test_page_shows_the_adapters_real_safety_setting(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl):
            on = (await ctl.status())["safety_enabled"]
            ctl.dog.set_safety_envelope(False)        # adapter changed behind the server's back
            off = (await ctl.status())["safety_enabled"]
            ctl.busy = "connecting"
            ctl.request_safety(True)                   # refused while (re)connecting
            still_off = ctl.dog.safety_envelope_enabled
            ctl.busy = None
            ctl.dog = None
            unknown = (await ctl.status())["safety_enabled"]
        return on, off, still_off, unknown

    on, off, still_off, unknown = run(go())
    assert on is True and off is False and still_off is False and unknown is None
