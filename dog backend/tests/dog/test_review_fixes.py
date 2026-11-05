"""Whole-system safety review fixes (2026-11-04): read-only avoidance, LiDAR switch only while
standing, StandDown code 4201, zero_sticks on a closed channel, dead-man survives a raising check."""

import asyncio
import time

import pytest

from patrol.contract import AdapterError, RunContext
from patrol.dog import real as real_mod
from patrol.dog import real_selftest
from patrol.dog.sim_conn import SimConn
from tests.dog.test_dodge import sticks
from tests.dog.test_joystick import drive_for, log_events, make_ctl, make_dog, run, serve, ws_open

REFUSED = "avoidance not confirmed on — motion refused; ask staff"
LIDAR_LYING = "LiDAR streams only while the dog is standing — press Stand up"


def avoid_sets(sim):
    return [s for s in sim.sent if s[0] == "OBSTACLES_AVOID" and s[1] == 1001]


def ctx(seconds=15.0):
    from threading import Event
    return RunContext(mission_id="t", deadline_monotonic=time.monotonic() + seconds, cancel=Event())


def record_say(ctl):
    said = []
    orig = ctl._say

    def say(msg, level="info"):
        said.append((level, msg))
        orig(msg, level)
    ctl._say = say
    return said


# ------------------------------------------------------------------ 1. avoidance is read-only

@pytest.mark.parametrize("avoid,publish_multi", [(False, True), (True, False)])
def test_prepare_never_writes_avoidance(tmp_path, avoid, publish_multi):
    sim = SimConn(camera=False, lidar=False, standing=False, avoid=avoid, publish_multi=publish_multi)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        st = await dog.prepare(ctx())
        with pytest.raises(AdapterError) as e:
            await dog.drive(0.2, 0, 0)
        await dog.close()
        return st, e.value.code

    st, code = run(go())
    assert avoid_sets(sim) == []                      # never SWITCH_SET
    assert 1004 in sim.apis()                         # still stood up
    assert st.standing is True and st.avoidance_enabled is not True
    assert code == "unsafe_state" and sim.moves() == []


def test_no_switch_set_anywhere_in_dog_package():
    from pathlib import Path
    for p in Path(real_mod.__file__).parent.glob("*.py"):
        if p.name == "sim_conn.py":
            continue
        assert "SWITCH_SET" not in p.read_text(), p.name


def test_joystick_stand_reports_avoidance_not_confirmed(tmp_path):
    sim = SimConn(camera=False, lidar=False, standing=False, avoid=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            said = record_say(ctl)
            ws = await ws_open(client)
            await ws.send_json({"t": "stand"})
            end = time.monotonic() + 8
            while time.monotonic() < end and not any("stand done" in m for _, m in said):
                await asyncio.sleep(0.1)
            block = ctl._drive_block(await ctl.dog.get_status())
            await ws.close()
            return said, block

    said, block = run(go())
    assert avoid_sets(sim) == []
    assert any(REFUSED in m for _, m in said), said
    assert block and REFUSED in block


def test_selftest_prepare_reports_avoidance_not_confirmed(tmp_path):
    sim = SimConn(camera=False, lidar=False, standing=False, avoid=False)

    async def go():
        dog = make_dog(tmp_path, sim)
        return await real_selftest._run("prepare", {"interface": "simulated"}, tmp_path, dog=dog, keys=False)

    rec = run(go())
    assert avoid_sets(sim) == []
    assert rec["status_after_prepare"]["standing"] is True
    assert rec["ok"] is False and REFUSED in rec["error"]


# ------------------------------------------------------------------ 2. LiDAR switch only while standing

def test_lidar_switch_refused_while_lying(tmp_path):
    sim = SimConn(camera=False, standing=False, lidar_needs_switch=True)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            with pytest.raises(AdapterError) as e:
                await dog.lidar_switch_on()
            return e.value.code
        finally:
            await dog.close()

    assert run(go()) == "unsafe_state"
    assert [s for s in sim.sent if s[0] == "ULIDAR_SWITCH"] == []


def test_joystick_lidar_on_refused_while_lying(tmp_path):
    sim = SimConn(camera=False, standing=False, lidar_needs_switch=True)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            said = record_say(ctl)
            ws = await ws_open(client)
            await ws.send_json({"t": "lidar_on"})
            await asyncio.sleep(0.5)
            await ws.close()
            return said

    said = run(go())
    assert [s for s in sim.sent if s[0] == "ULIDAR_SWITCH"] == []
    assert any("standing" in m.lower() and "lidar" in m.lower() for _, m in said), said
    assert not [e for e in log_events(tmp_path) if e["event"] == "lidar_switch" and e.get("ok")]


def test_page_lidar_button_only_while_standing(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False, lidar=False))
        async with serve(ctl) as client:
            return await (await client.get("/")).text()

    page = run(go())
    assert LIDAR_LYING in page
    warn = page.split("function renderLidarWarn")[1].split("drawLidar();")[0]
    assert "s.standing === true" in warn               # button + "sensor may be off" only while standing


def test_selftest_lidar_no_data_while_lying(tmp_path, monkeypatch):
    monkeypatch.setattr(real_selftest, "LIDAR_FIRST_SCAN_S", 0.6)

    async def go():
        sim = SimConn(camera=False, standing=False, lidar_needs_switch=True)
        dog = make_dog(tmp_path, sim)
        return await real_selftest._run("lidar", {"interface": "simulated"}, tmp_path, dog=dog, keys=False)

    rec = run(go())
    assert rec["ok"] is False
    assert "dog is lying down: LiDAR streams only while standing" in rec["lidar"]["reason"]


# ------------------------------------------------------------------ 3. StandDown code 4201

def sim_4201(lies_down: bool) -> SimConn:
    sim = SimConn(camera=False, lidar=False)
    orig = sim._handle

    async def handle(topic, options):
        resp = await orig(topic, options) if (lies_down or options.get("api_id") != 1005) else None
        if topic == "SPORT_MOD" and options.get("api_id") == 1005:
            if resp is None:
                sim.sent.append((topic, 1005, options.get("parameter"), time.monotonic()))
            return {"data": {"header": {"status": {"code": 4201}}}}
        return resp
    sim._handle = handle
    return sim


def test_rest_4201_lying_confirmed_is_not_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(real_mod, "POSTURE_TIMEOUT_S", 3.0)
    sim = sim_4201(lies_down=True)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        rep = await dog.rest()
        await asyncio.sleep(0.3)
        await dog.close()
        return rep

    rep = run(go())
    assert sim.apis().count(1005) == 1                # no second StandDown
    assert 1001 not in sim.apis()
    assert rep["standdown_sent"] is True and rep["standdown_code"] == 4201
    assert rep["lying_confirmed"] is True


def test_rest_4201_not_lying_keeps_loud_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(real_mod, "POSTURE_TIMEOUT_S", 1.0)
    sim = sim_4201(lies_down=False)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        rep = await dog.rest()
        await dog.close()
        return rep

    rep = run(go())
    assert sim.apis().count(1005) == 1
    assert rep["standdown_sent"] is not True and rep["lying_confirmed"] is False


@pytest.mark.parametrize("lies_down", [True, False])
def test_joystick_stop_with_4201(tmp_path, monkeypatch, lies_down):
    monkeypatch.setattr(real_mod, "POSTURE_TIMEOUT_S", 2.0)
    sim = sim_4201(lies_down=lies_down)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            said = record_say(ctl)
            ws = await ws_open(client)
            await ws.send_json({"t": "stop"})
            end = time.monotonic() + 5
            while time.monotonic() < end and not [e for e in log_events(tmp_path) if e["event"] == "rest"]:
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.2)
            await ws.close()
            return said

    said = run(go())
    events = [e["event"] for e in log_events(tmp_path)]
    assert "standdown_code_4201" in events
    warned = any("STOP MAY NOT HAVE ARRIVED" in m for _, m in said)
    assert warned is (not lies_down)
    assert sim.apis().count(1005) == 1 and 1001 not in sim.apis()


# ------------------------------------------------------------------ 4. zero_sticks on a closed channel

class ClosedChannel:
    readyState = "closed"


def test_zero_sticks_dropped_on_closed_channel(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        sim.datachannel.pub_sub.channel = ClosedChannel()
        res = await dog.zero_sticks()                 # never raises
        del sim.datachannel.pub_sub.channel
        ok = await dog.zero_sticks()
        await dog.close()
        return res, ok

    res, ok = run(go())
    assert res["sent"] == 0 and res["dropped"] > 0
    assert ok["sent"] > 0 and ok["dropped"] == 0


def test_joystick_logs_zero_sticks_dropped(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        ctl.drive_mode = "sticks"
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        sim.datachannel.pub_sub.channel = ClosedChannel()
        await ctl._zero_sticks_on_new(dog, "test")
        await dog.close()

    run(go())
    zs = [e for e in log_events(tmp_path) if e["event"].startswith("zero_sticks")]
    assert zs and "zero_sticks dropped (data channel not open)" in str(zs[-1])
    assert not [s for s in sim.sent if s[0] == "WIRELESS_CONTROLLER"]


# ------------------------------------------------------------------ 5. dead-man survives a raising check

def test_deadman_still_stops_when_safety_check_raises(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await drive_for(ws, 0.4)

            def boom(dog):
                raise RuntimeError("check broke")
            ctl._check_safety_events = boom
            t_last = time.monotonic()
            await asyncio.sleep(0.8)                  # silent: dead-man must fire
            dm = ctl.deadman_count
            await ws.close()
            return t_last, dm

    t_last, dm = run(go())
    assert dm == 1
    assert [s for s in sim.stops() if s[3] > t_last]


def test_deadman_still_stops_when_drive_block_raises(tmp_path):
    sim = SimConn(camera=False, lidar=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await drive_for(ws, 0.4)

            def boom(st=None):
                raise RuntimeError("block check broke")
            ctl._drive_block = boom
            t_patch = time.monotonic()
            t_last = await drive_for(ws, 0.6)         # stick still held: input stays fresh
            moving = ctl.moving
            await ws.close()
            return t_patch, t_last, moving

    t_patch, t_last, moving = run(go())
    assert moving is False                            # a broken check = not active = stop
    assert [s for s in sim.stops() if t_patch < s[3] < t_last]


def test_is_lying_now_is_strict_about_body_height(tmp_path):
    """A StandDown is only confirmed by a low body; an unusual mode at full height is NOT lying."""
    import time as _time
    from patrol.dog.real import RealDog
    from patrol.dog.sim_conn import SimConn
    dog = RealDog(config={"interface": "simulated"}, output_dir=tmp_path, _conn_factory=lambda ip: SimConn())
    dog._sport, dog._sport_t = {"mode": 8, "body_height": 0.32}, _time.monotonic()
    assert dog._is_lying_now() is False
    dog._sport, dog._sport_t = {"mode": 5, "body_height": 0.08}, _time.monotonic()
    assert dog._is_lying_now() is True
    dog._sport_t = _time.monotonic() - 10            # stale -> not confirmed
    assert dog._is_lying_now() is False


# ------------------------------------------------------------------ 2026-11-04 evening review

def test_is_lying_now_accepts_lie_down_mode_at_reported_full_height(tmp_path):
    """Real dog 19:31-19:35: after StandDown the reported body_height stayed >= 0.25 (never
    confirmed in 8 s) while the next connect said standing: false, i.e. the mode changed.
    Lie-down (5) and damping (7) modes confirm; recovery (8) at full height still does not."""
    from patrol.dog.real import RealDog
    dog = RealDog(config={"interface": "simulated"}, output_dir=tmp_path, _conn_factory=lambda ip: SimConn())
    for mode, want in ((5, True), (7, True), (8, False), (1, False), (3, False)):
        dog._sport, dog._sport_t = {"mode": mode, "body_height": 0.32}, time.monotonic()
        assert dog._is_lying_now() is want, mode


def test_rest_report_has_raw_posture_state(tmp_path, monkeypatch):
    """So the next real STOP tells us what the dog actually reports while lying."""
    monkeypatch.setattr(real_mod, "POSTURE_TIMEOUT_S", 3.0)
    sim = sim_4201(lies_down=True)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        rep = await dog.rest()
        await dog.close()
        return rep

    rep = run(go())
    assert set(rep["posture_after"]) == {"mode", "body_height"}
    assert rep["posture_after"]["mode"] == 5


def test_close_zeroes_sticks_even_when_stationary(tmp_path):
    """A held stick the dog's own avoidance blocks reads as stationary: close() must still zero it."""
    sim = SimConn(camera=False, lidar=False)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        dog.mark_sticks_used()
        n = len(sticks(sim))
        await dog.close()
        return [d for d, _ in sticks(sim)[n:]]

    sent = run(go())
    assert sent and not any(sent[0][k] for k in ("lx", "ly", "rx", "ry"))
