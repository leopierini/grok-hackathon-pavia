"""Joystick workflow buttons: run a selftest step from the page (then automatic re-arm),
auto-connect when the dog becomes reachable, and shut down the server. Simulated dog only."""

import asyncio
import json
import time

from patrol.dog.joystick import CHECK_STEPS, Controller
from patrol.dog.real import RealDog
from patrol.dog.sim_conn import SimConn

from tests.dog.test_joystick import log_events, run, serve, ws_open


def make_dog(tmp_path, sim):
    return RealDog(config={"interface": "simulated", "command_timeout_s": 0.3},
                   output_dir=tmp_path, _conn_factory=lambda ip: sim)


def make_ctl(tmp_path, sim, made=None, **kw):
    def factory():
        d = make_dog(tmp_path, sim)
        if made is not None:
            made.append(d)
        return d
    return Controller(factory, log_path=tmp_path / "joystick.jsonl", fake=True, verbose=False,
                      out_dir=tmp_path, **kw)


def sport_apis(sim, since=0):
    return [s[1] for s in sim.sent[since:] if s[0] == "SPORT_MOD"]


async def wait_for(pred, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        await asyncio.sleep(0.05)
    return False


def checks(tmp_path):
    return [e for e in log_events(tmp_path) if e.get("event") == "check"]


def session(tmp_path):
    p = tmp_path / "session.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


# ------------------------------------------------------------------ Run test button

def test_only_non_motion_steps_can_run_from_the_page():
    assert set(CHECK_STEPS) == {"read", "audio"}


def test_audio_check_runs_selftest_then_rearms_without_motion(tmp_path):
    sim = SimConn(camera=False, volume=2)
    made = []

    async def go():
        ctl = make_ctl(tmp_path, sim, made)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            first = ctl.dog
            await ws.send_json({"t": "check", "step": "audio", "volume": 6})
            assert await wait_for(lambda: ctl.busy == "check", 3)
            assert await wait_for(lambda: any(e.get("action") == "done" for e in checks(tmp_path)))
            assert await ctl.wait_connected(5.0)
            await ws.close()
            return first, ctl.dog

    first, after = run(go())
    recs = session(tmp_path)
    assert len(recs) == 1
    r = recs[0]
    assert r["step"] == "audio" and r["ok"] is True and r["source"] == "joystick"
    assert r["loopback_heard"] is True and r["volume_set"] == 6 and r["volume_restored"] == 2
    assert sim.volume == 2                                    # restored
    assert len(made) == 3 and after is made[2] and after is not first   # startup, check, re-arm
    assert after.motion_lock() is None
    assert sport_apis(sim) == []                              # no motion at all
    done = [e for e in checks(tmp_path) if e.get("action") == "done"][0]
    assert done["ok"] is True and done["step"] == "audio"
    conn = [e for e in log_events(tmp_path) if e.get("event") == "connection" and e.get("action") == "connected"]
    assert conn[-1]["reason"] == "after_check"


def test_read_check_saves_status_and_photo(tmp_path):
    sim = SimConn()

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await ws.send_json({"t": "check", "step": "read"})
            assert await wait_for(lambda: any(e.get("action") == "done" for e in checks(tmp_path)))
            assert await ctl.wait_connected(5.0)
            await ws.close()

    run(go())
    r = session(tmp_path)[0]
    assert r["step"] == "read" and r["ok"] is True and r["photo"].endswith(".jpg")
    assert sport_apis(sim) == []


def test_check_refused_for_motion_steps_view_only_and_while_busy(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)                        # controller
            viewer = await ws_open(client)                    # view-only
            await ws.send_json({"t": "check", "step": "move"})
            await ws.send_json({"t": "check", "step": "expiry"})
            await viewer.send_json({"t": "check", "step": "audio"})
            await asyncio.sleep(0.3)
            assert ctl.busy is None
            await ws.send_json({"t": "drive", "x": 1, "y": 0, "yaw": 0, "speed": 1})
            await ws.send_json({"t": "check", "step": "audio"})     # sticks held: refused
            await asyncio.sleep(0.3)
            busy_while_driving = ctl.busy
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.5)
            await ws.close()
            await viewer.close()
            return busy_while_driving

    assert run(go()) is None
    assert session(tmp_path) == []
    refused = [e for e in checks(tmp_path) if e.get("action") == "refused"]
    assert len(refused) >= 3


def test_stop_during_check_lies_down_on_the_check_connection(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            n = len(sim.sent)
            await ws.send_json({"t": "check", "step": "audio", "volume": 5})
            assert await wait_for(lambda: ctl.busy == "check" and ctl._check_dog is not None
                                  and getattr(ctl._check_dog, "_connected", False), 5)
            await asyncio.sleep(0.5)
            await ws.send_json({"t": "stop"})
            assert await wait_for(lambda: 1005 in sport_apis(sim, n), 10)
            assert await wait_for(lambda: any(e.get("action") == "done" for e in checks(tmp_path)))
            assert await ctl.wait_connected(5.0)
            lock_after = ctl.dog.motion_lock()
            await ws.close()
            return n, lock_after

    n, lock_after = run(go())
    assert lock_after and "STOP" in lock_after       # the automatic re-arm keeps the STOP latched
    apis = sport_apis(sim, n)
    assert 1003 in apis and 1005 in apis and 1001 not in apis   # StopMove + StandDown, never Damp
    rests = [e for e in log_events(tmp_path) if e.get("event") == "rest"]
    assert rests and rests[0]["report"]["standdown_sent"] is True


# ------------------------------------------------------------------ auto-connect

class FlakyConn(SimConn):
    """Connect fails while `cable` is False (dog unplugged)."""
    cable = False

    async def connect(self):
        if not self.cable:
            raise ConnectionError("no route to host")
        return await super().connect()


def test_auto_connect_once_the_dog_is_reachable(tmp_path):
    sim = FlakyConn(camera=False)
    probes = []

    async def reachable():
        probes.append(time.monotonic())
        return sim.cable

    async def go():
        ctl = make_ctl(tmp_path, sim, auto_connect_s=0.1, reachable=reachable)
        await ctl.start()
        await asyncio.sleep(0.6)
        attempts_unplugged = sum(1 for e in log_events(tmp_path) if e.get("action") == "connect_failed")
        sim.cable = True                                       # plug the cable in
        ok = await wait_for(lambda: ctl.dog is not None and getattr(ctl.dog, "_connected", False), 5)
        await ctl.shutdown()
        return attempts_unplugged, ok

    attempts_unplugged, ok = run(go())
    assert ok
    assert attempts_unplugged == 1          # only the startup try: no connect spam while unreachable
    assert len(probes) >= 3
    conn = [e for e in log_events(tmp_path) if e.get("action") == "connected"]
    assert conn and conn[-1]["reason"] == "auto"
    assert sport_apis(sim) == []


def test_auto_connect_never_clears_a_stop_lock(tmp_path):
    sim = SimConn(camera=False)
    made = []

    async def reachable():
        return True

    async def go():
        ctl = make_ctl(tmp_path, sim, made, auto_connect_s=0.1, reachable=reachable)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await ws.send_json({"t": "stop"})
            await asyncio.sleep(1.5)
            locked = ctl.dog.motion_lock()
            await ws.close()
            return locked

    locked = run(go())
    assert locked                                   # STOP latched the lock ...
    assert len(made) == 1                           # ... and nothing re-armed it automatically


def test_auto_connect_off_without_probe(tmp_path):
    sim = FlakyConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)               # no reachable probe: feature off
        await ctl.start()
        assert await wait_for(lambda: ctl.connect_error is not None, 3)   # startup try failed
        sim.cable = True
        await asyncio.sleep(0.5)
        connected = getattr(ctl.dog, "_connected", False)
        await ctl.shutdown()
        return connected

    assert run(go()) is False


# ------------------------------------------------------------------ shut down button

def test_shutdown_button_controller_only(tmp_path):
    sim = SimConn(camera=False)
    exits = []

    async def go():
        ctl = make_ctl(tmp_path, sim)
        ctl.on_exit = exits.append
        async with serve(ctl) as client:
            ws = await ws_open(client)
            viewer = await ws_open(client)
            await viewer.send_json({"t": "shutdown"})
            await asyncio.sleep(0.2)
            n_view = len(exits)
            await ws.send_json({"t": "shutdown"})
            assert await wait_for(lambda: exits, 2)
            await ws.close()
            await viewer.close()
            return n_view

    assert run(go()) == 0
    assert exits == ["browser:shutdown"]
    assert any(e.get("event") == "shutdown_requested" for e in log_events(tmp_path))


def test_page_audio_check_never_runs_at_volume_zero(tmp_path):
    # Real dog 2026-11-04: the slider showed the dog's volume (0), the test ran silent.
    sim = SimConn(camera=False, volume=0, volume_mutes=True)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await ws.send_json({"t": "check", "step": "audio", "volume": 0})
            assert await wait_for(lambda: any(e.get("action") == "done" for e in checks(tmp_path)))
            assert await ctl.wait_connected(5.0)
            await ws.close()

    run(go())
    r = session(tmp_path)[0]
    assert r["volume_set"] == 5 and r["volume_restored"] == 0 and sim.volume == 0
    assert r["ok"] is True and r["loopback_heard"] is True
