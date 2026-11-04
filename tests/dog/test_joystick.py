"""Joystick server + RealDog joystick helpers, against the simulated connection (no robot)."""

import asyncio
import json
import math
import time
from contextlib import asynccontextmanager

import pytest
from aiohttp.test_utils import TestClient, TestServer

from patrol.contract import AdapterError
from patrol.dog.joystick import (JOY_MAX_VX, JOY_MAX_VY, JOY_MAX_VYAW, Controller, TerminalKeys,
                                 build_app)
from patrol.dog.real import RealDog
from patrol.dog.sim_conn import SimConn


def run(coro):
    return asyncio.run(coro)


def make_dog(tmp_path, sim, **cfg):
    config = {"interface": "simulated", "command_timeout_s": 0.3, **cfg}
    return RealDog(config=config, output_dir=tmp_path, _conn_factory=lambda ip: sim)


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
    """Open a WS and keep reading it (like a browser), so heartbeat pings get answered."""
    ws = await client.ws_connect("/ws")
    hello = await ws.receive_json()

    async def drain():
        async for _ in ws:
            pass
    ws._drain = asyncio.create_task(drain())
    ws.hello = hello
    return ws


def log_events(tmp_path):
    p = tmp_path / "joystick.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def sport(sim):
    return [(s[1], s[3]) for s in sim.sent if s[0] == "SPORT_MOD"]


async def drive_for(ws, seconds, x=1.0, speed=1.0, period=0.06):
    end = time.monotonic() + seconds
    t_last = None
    while time.monotonic() < end:
        await ws.send_json({"t": "drive", "x": x, "y": 0, "yaw": 0, "speed": speed})
        t_last = time.monotonic()
        await asyncio.sleep(period)
    return t_last


# ------------------------------------------------------------------ RealDog.drive

def test_drive_clamps_to_realdog_caps(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        p = await dog.drive(5.0, -5.0, 9.0)
        with pytest.raises(AdapterError) as e:
            await dog.drive(float("nan"), 0, 0)
        await dog.close()
        return p, e.value.code

    p, code = run(go())
    assert p == {"x": 0.5, "y": -0.3, "z": 0.8}
    assert sim.moves()[0][2] == {"x": 0.5, "y": -0.3, "z": 0.8}
    assert code == "invalid_input" and len(sim.moves()) == 1


@pytest.mark.parametrize("case", ["locked", "avoidance_unknown", "not_standing", "avoidance_off"])
def test_drive_refused(tmp_path, case):
    sim = SimConn(camera=False, publish_multi=case != "avoidance_unknown",
                  standing=case != "not_standing", avoid=case != "avoidance_off")

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        if case == "locked":
            await dog.halt()
        with pytest.raises(AdapterError) as e:
            await dog.drive(0.1, 0, 0)
        await dog.close()
        return e.value.code

    assert run(go()) == "unsafe_state"
    assert sim.moves() == []


def test_drive_timeout_locks_and_is_not_retried(tmp_path):
    sim = SimConn(camera=False, hang_on_move=True)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        with pytest.raises(AdapterError) as e:
            await dog.drive(0.1, 0, 0)
        lock = dog.motion_lock()
        with pytest.raises(AdapterError):
            await dog.drive(0.1, 0, 0)
        await asyncio.sleep(0.05)
        await dog.close()
        return e.value.code, lock

    code, lock = run(go())
    assert code == "timeout" and lock and len(sim.moves()) == 1 and sim.stops()


# ------------------------------------------------------------------ controller caps

def test_controller_clamps_to_joystick_caps(tmp_path):
    ctl = make_ctl(tmp_path, SimConn(camera=False))
    assert ctl.set_target(5, -5, 5, 7) == (JOY_MAX_VX, -JOY_MAX_VY, JOY_MAX_VYAW)
    assert ctl.set_target(1, 1, -1, None) == pytest.approx((0.15, 0.1, -0.3))   # default speed 50 %
    assert ctl.set_target(float("nan"), "junk", float("inf"), 1) == (0.0, 0.0, 0.0)
    assert JOY_MAX_VX <= 0.3 and JOY_MAX_VY <= 0.2 and JOY_MAX_VYAW <= 0.6


def test_ws_drive_is_capped_and_rate_limited(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await drive_for(ws, 1.0, x=9.0, speed=9.0, period=0.01)    # client spams at 100 Hz
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.3)
            await ws.close()

    run(go())
    moves = sim.moves()
    assert moves and all(m[2]["x"] == JOY_MAX_VX for m in moves)
    gaps = [b[3] - a[3] for a, b in zip(moves, moves[1:])]
    assert min(gaps) >= 0.049                         # <= 20 Hz
    assert len(moves) <= 21
    assert sim.stops() and sim.stops()[-1][3] > moves[-1][3]   # release sent StopMove


# ------------------------------------------------------------------ dead-man / ws close

def test_deadman_sends_stopmove_after_300ms_silence(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            t_last = await drive_for(ws, 0.5)
            await asyncio.sleep(0.7)                  # browser goes silent, socket stays open
            dm = ctl.deadman_count
            await ws.close()
            return t_last, dm

    t_last, dm = run(go())
    stops_after = [s[3] for s in sim.stops() if s[3] > t_last]
    assert stops_after, "no StopMove after silence"
    delay = stops_after[0] - t_last
    assert 0.28 <= delay <= 0.45, delay
    assert not [m for m in sim.moves() if m[3] > stops_after[0]]
    assert dm == 1
    assert any(e["event"] == "deadman" for e in log_events(tmp_path))
    assert any(e["event"] == "stop" and e["kind"] == "deadman" for e in log_events(tmp_path))
    assert 1005 not in sim.apis()                     # dead-man stays standing


def test_ws_close_stops(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await drive_for(ws, 0.4)
            t_close = time.monotonic()
            await ws.close()
            await asyncio.sleep(0.4)
            return t_close

    t_close = run(go())
    stops = [s[3] for s in sim.stops() if s[3] >= t_close]
    assert stops and stops[0] - t_close < 0.15
    assert not [m for m in sim.moves() if m[3] > stops[0]]
    assert any(e["event"] == "stop" and e["kind"] == "ws_close" for e in log_events(tmp_path))


def test_view_only_client_cannot_drive_but_can_stop(tmp_path):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws1 = await ws_open(client)
            ws2 = await ws_open(client)
            hello2 = ws2.hello
            await drive_for(ws2, 0.3)
            moves_from_viewer = len(sim.moves())
            await ws2.send_json({"t": "stop"})
            await asyncio.sleep(1.6)
            await ws1.close()
            await ws2.close()
            return hello2, moves_from_viewer

    hello2, n = run(go())
    assert hello2["role"] == "view" and n == 0
    assert 1005 in sim.apis() and 1001 not in sim.apis()


# ------------------------------------------------------------------ STOP = soft lie-down

@pytest.mark.parametrize("msg", ["stop", "rest"])
def test_stop_overrides_driving_and_lies_down_softly(tmp_path, msg):
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            driver = asyncio.create_task(drive_for(ws, 1.5))      # keeps pushing the stick
            await asyncio.sleep(0.5)
            await ws.send_json({"t": msg})
            await driver
            await asyncio.sleep(0.5)
            lock = ctl.dog.motion_lock()
            st = await ctl.dog.get_status()
            await ws.close()
            return lock, st

    lock, st = run(go())
    apis = [a for a, _ in sport(sim)]
    assert 1001 not in apis                               # never Damp
    first_sd = apis.index(1005)                           # StandDown sent
    assert 1003 in apis[:first_sd]                        # StopMove before StandDown
    assert 1008 not in apis[first_sd:]                    # no Move after, though the stick kept pushing
    assert lock and st.standing is False
    assert any(e["event"] == "rest" for e in log_events(tmp_path))


def test_terminal_keys_q_and_enter_rest(tmp_path):
    async def go(ch):
        sim = SimConn(camera=False)
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl):
            TerminalKeys(ctl).handle(ch)
            await asyncio.wait_for(ctl._rest_task, 3.0)
        return sim.apis()

    for ch in (b"q", b"Q", b"\n", b"\r"):
        apis = run(go(ch))
        assert 1005 in apis and 1001 not in apis


# ------------------------------------------------------------------ re-arm + stand

def test_rearm_creates_fresh_adapter_without_motion(tmp_path):
    sim = SimConn(camera=False)
    made = []

    async def go():
        ctl = make_ctl(tmp_path, sim, made)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await ws.send_json({"t": "stop"})
            await asyncio.sleep(2.0)                      # lies down
            old = ctl.dog
            assert old.motion_lock()
            n_before = len(sim.sent)
            await ws.send_json({"t": "rearm"})
            await asyncio.sleep(0.3)
            assert await ctl.wait_connected(5.0)
            new = ctl.dog
            lock_new = new.motion_lock()
            rearm_sport = [s for s in sim.sent[n_before:] if s[0] == "SPORT_MOD"]
            await ws.send_json({"t": "stand"})            # stand up again, then drive
            await asyncio.sleep(4.5)
            st = await new.get_status()
            await drive_for(ws, 0.3)
            await ws.send_json({"t": "drive", "x": 0, "y": 0, "yaw": 0})
            await asyncio.sleep(0.2)
            await ws.close()
            return old, new, rearm_sport, st, lock_new

    old, new, rearm_sport, st, lock_new = run(go())
    assert new is not old and len(made) == 2 and sim.connects == 2
    assert lock_new is None                               # fresh adapter: motion allowed
    assert rearm_sport == []                              # connecting sends no motion
    apis = sim.apis()
    assert 1004 in apis and 1002 in apis and st.standing is True
    assert sim.moves()[-1][3] > [s for s in sim.sent if s[1] == 1004][0][3]
    assert 1001 not in apis


# ------------------------------------------------------------------ head light

def test_brightness_uses_vui_1005_clamped(tmp_path):
    sim = SimConn(camera=False, brightness=3)

    async def go():
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        got = await dog.get_brightness()
        sent = [await dog.set_brightness(v) for v in (15, -3, 4.6)]
        with pytest.raises(AdapterError):
            await dog.set_brightness(float("nan"))
        await dog.close()
        return got, sent

    got, sent = run(go())
    assert got == 3 and sent == [10, 0, 5]
    vui = [s for s in sim.sent if s[0] == "VUI"]
    assert [s[1] for s in vui] == [1006, 1005, 1005, 1005]
    assert [s[2] for s in vui[1:]] == [{"brightness": 10}, {"brightness": 0}, {"brightness": 5}]


def test_light_via_ws_reads_on_connect_and_logs(tmp_path):
    sim = SimConn(camera=False, brightness=2)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            b0 = ctl.brightness
            ws = await ws_open(client)
            await ws.send_json({"t": "light", "level": 99})
            await asyncio.sleep(0.2)
            await ws.close()
            return b0, ctl.brightness

    assert run(go()) == (2, 10)
    assert sim.brightness == 10
    assert any(e["event"] == "brightness" and e["new"] == 10 for e in log_events(tmp_path))


# ------------------------------------------------------------------ http: page, video, photo

def test_page_video_and_photo(tmp_path):
    sim = SimConn(camera=True)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            page = await (await client.get("/")).text()
            resp = await client.get("/video.mjpg")
            chunk = b""
            while b"\xff\xd9" not in chunk:
                chunk += await asyncio.wait_for(resp.content.readany(), 3.0)
            ctype = resp.headers["Content-Type"]
            resp.close()
            ws = await ws_open(client)
            await ws.send_json({"t": "photo", "zone": "room_2"})
            await asyncio.sleep(0.6)
            await ws.close()
            return page, chunk, ctype, ctl.last_photo

    page, chunk, ctype, photo = run(go())
    assert "STOP (lie down softly)" in page
    assert ctype.startswith("multipart/x-mixed-replace")
    assert chunk.startswith(b"--frame") and b"\xff\xd8" in chunk
    assert photo and photo.endswith(".jpg") and open(photo, "rb").read(2) == b"\xff\xd8"
    assert any(e["event"] == "photo" for e in log_events(tmp_path))


# ------------------------------------------------------------------ review regressions

def test_foreign_origin_and_host_are_rejected(tmp_path):
    import aiohttp
    sim = SimConn(camera=False)

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            with pytest.raises(aiohttp.WSServerHandshakeError) as e:
                await client.ws_connect("/ws", headers={"Origin": "http://evil.example.com"})
            r_host = await client.get("/", headers={"Host": "evil.example.com"})
            r_vid = await client.get("/video.mjpg", headers={"Host": "rebind.attacker.net:8765"})
            port = client.server.port
            ok = await client.ws_connect("/ws", headers={"Origin": f"http://127.0.0.1:{port}"})
            hello = await ok.receive_json()
            await ok.close()
            return e.value.status, r_host.status, r_vid.status, hello["role"], ctl.controller_ws

    status, host_status, vid_status, role, _ = run(go())
    assert status == 403 and host_status == 403 and vid_status == 403
    assert role == "control"                     # our own page still works
    assert sim.moves() == []


def test_stop_during_rearm_is_delivered_on_old_adapter(tmp_path):
    sim = SimConn(camera=False)
    real_disconnect = sim.disconnect

    async def slow_disconnect():
        await asyncio.sleep(1.5)                 # old adapter takes a while to close
        await real_disconnect()

    async def go():
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            sim.disconnect = slow_disconnect
            await ws.send_json({"t": "rearm"})
            await asyncio.sleep(0.3)             # re-arm is now closing the old adapter
            n = len(sim.sent)
            t = time.monotonic()
            await ws.send_json({"t": "stop"})
            while time.monotonic() - t < 1.0 and 1005 not in [s[1] for s in sim.sent[n:]]:
                await asyncio.sleep(0.01)
            dt = time.monotonic() - t
            sim.disconnect = real_disconnect
            await asyncio.sleep(2.0)
            await ws.close()
            return dt, [s[1] for s in sim.sent[n:] if s[0] == "SPORT_MOD"]

    dt, apis = run(go())
    assert 1005 in apis and dt < 0.5             # soft lie-down went out right away
    assert 1001 not in apis


def test_stop_with_no_connection_is_reported_not_silently_dropped(tmp_path):
    class DeadConn(SimConn):
        async def connect(self):
            raise ConnectionError("cable pulled")

    async def go():
        ctl = make_ctl(tmp_path, DeadConn(camera=False))
        await ctl.start()
        await asyncio.sleep(0.3)
        ctl.request_rest("test")
        await asyncio.sleep(0.3)
        await ctl.shutdown()

    run(go())
    rests = [e for e in log_events(tmp_path) if e.get("event") == "rest" or e.get("kind") == "rest"
             or "rest" == e.get("type")]
    text = (tmp_path / "joystick.jsonl").read_text()
    assert '"standdown_sent": false' in text
    assert rests or "not connected" in text


def test_huge_numbers_from_browser_are_harmless(tmp_path):
    ctl = make_ctl(tmp_path, SimConn(camera=False))
    assert ctl.set_target(10 ** 400, -(10 ** 400), "nan", 10 ** 400) == (0.0, 0.0, 0.0)
