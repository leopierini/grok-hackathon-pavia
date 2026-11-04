"""RealDog safety logic against a scripted fake WebRTC connection (no robot, no vendor lib)."""

import asyncio
from pathlib import Path
import json
import time
from threading import Event

import pytest

from patrol.contract import AdapterError, RunContext
from patrol.dog.real import RealDog


class FakePubSub:
    def __init__(self, conn):
        self.conn = conn
        self.subs = {}

    def subscribe(self, topic, cb=None):
        self.subs[topic] = cb

    async def publish_request_new(self, topic, options):
        api = options["api_id"]
        self.conn.sent.append((topic, api, options.get("parameter")))
        if topic == "SPORT_MOD":
            if api == 1008:
                if self.conn.hang_on_move:
                    await asyncio.sleep(3600)
                p = options["parameter"]
                self.conn.vel = [p["x"], p["y"]]
            elif api == 1003:
                self.conn.vel = [0.0, 0.0]
        if topic == "OBSTACLES_AVOID" and api == 1002:
            return {"data": {"header": {"status": {"code": 0}},
                             "data": json.dumps({"enable": self.conn.avoid})}}
        return {"data": {"header": {"status": {"code": 0}}}}


class FakeVideo:
    def add_track_callback(self, cb):
        pass

    def switchVideoChannel(self, on):
        pass


class FakeConn:
    def __init__(self, *, avoid=True, publish_multi=True, hang_on_move=False):
        self.sent = []
        self.vel = [0.0, 0.0]
        self.avoid = avoid
        self.publish_multi = publish_multi
        self.hang_on_move = hang_on_move
        self.datachannel = type("DC", (), {})()
        self.datachannel.pub_sub = FakePubSub(self)
        self.video = FakeVideo()
        self._task = None

    async def connect(self):
        self._task = asyncio.get_running_loop().create_task(self._stream())

    async def disconnect(self):
        if self._task:
            self._task.cancel()

    async def _stream(self):
        subs = self.datachannel.pub_sub.subs
        while True:
            if "LF_SPORT_MOD_STATE" in subs:
                subs["LF_SPORT_MOD_STATE"]({"data": {
                    "mode": 1, "body_height": 0.32, "velocity": list(self.vel) + [0.0],
                    "yaw_speed": 0.0, "position": [0.0, 0.0, 0.3]}})
            if "LOW_STATE" in subs:
                subs["LOW_STATE"]({"data": {"bms_state": {"soc": 80}}})
            if self.publish_multi and "MULTIPLE_STATE" in subs:
                subs["MULTIPLE_STATE"]({"data": json.dumps({"obstaclesAvoidSwitch": self.avoid})})
            await asyncio.sleep(0.02)

    def moves(self):
        return [s for s in self.sent if s[0] == "SPORT_MOD" and s[1] == 1008]

    def stops(self):
        return [s for s in self.sent if s[0] == "SPORT_MOD" and s[1] == 1003]


def make(tmp_path, conn, **cfg):
    config = {"interface": "10.0.0.1", "command_timeout_s": 0.3, **cfg}
    return RealDog(config=config, output_dir=tmp_path, _conn_factory=lambda ip: conn)


def ctx(seconds=10.0):
    return RunContext(mission_id="t", deadline_monotonic=time.monotonic() + seconds, cancel=Event())


def run(coro):
    return asyncio.run(coro)


def test_connect_sends_no_motion(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        st = await dog.connect()
        await dog.close()
        return st

    st = run(go())
    assert st.connected and st.standing is True and st.stationary is True and st.avoidance_enabled is True
    assert [s for s in conn.sent if s[0] == "SPORT_MOD"] == []


def test_short_move_then_stop(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        res = await dog.run_segments([{"vx": 0.2, "duration_s": 0.3}], ctx())
        await dog.close()
        return res

    res = run(go())
    assert res.completed and res.stopped
    assert len(conn.moves()) >= 2 and len(conn.stops()) >= 1


def test_velocity_is_clamped(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        await dog.run_segments([{"vx": 5.0, "vyaw": -9.0, "duration_s": 0.1}], ctx())
        await dog.close()

    run(go())
    p = conn.moves()[0][2]
    assert p["x"] == 0.5 and p["z"] == -0.8


def test_halt_mid_route_is_fast_and_locks(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        task = asyncio.create_task(dog.run_segments([{"vx": 0.2, "duration_s": 5.0}], ctx()))
        await asyncio.sleep(0.3)
        t = time.monotonic()
        await dog.halt()
        res = await asyncio.wait_for(task, 2.0)
        elapsed = time.monotonic() - t
        with pytest.raises(AdapterError) as e:
            await dog.run_segments([{"vx": 0.2, "duration_s": 0.2}], ctx())
        await dog.close()
        return res, elapsed, e.value.code

    res, elapsed, code = run(go())
    assert not res.completed and res.stopped and "halted" in res.detail
    assert elapsed < 0.5
    assert code == "unsafe_state"
    assert len(conn.stops()) >= 1


def test_timed_out_move_is_not_retried(tmp_path):
    conn = FakeConn(hang_on_move=True)

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        res = await dog.run_segments([{"vx": 0.2, "duration_s": 2.0}], ctx())
        with pytest.raises(AdapterError):
            await dog.run_segments([{"vx": 0.2, "duration_s": 0.2}], ctx())
        await dog.close()
        return res

    res = run(go())
    assert not res.completed
    assert len(conn.moves()) == 1          # exactly one attempt, no retry
    assert len(conn.stops()) >= 1          # stop was attempted


def test_unknown_avoidance_blocks_walking(tmp_path):
    conn = FakeConn(publish_multi=False)

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        st = await dog.get_status()
        with pytest.raises(AdapterError) as e:
            await dog.run_segments([{"vx": 0.2, "duration_s": 0.2}], ctx())
        await dog.close()
        return st, e.value.code

    st, code = run(go())
    assert st.avoidance_enabled is None
    assert code == "unsafe_state"
    assert conn.moves() == []


def test_avoidance_off_blocks_walking(tmp_path):
    conn = FakeConn(avoid=False)

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        with pytest.raises(AdapterError):
            await dog.run_segments([{"vx": 0.2, "duration_s": 0.2}], ctx())
        await dog.close()

    run(go())
    assert conn.moves() == []


def test_cancel_mid_route(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        c = ctx()
        task = asyncio.create_task(dog.run_segments([{"vx": 0.2, "duration_s": 5.0}], c))
        await asyncio.sleep(0.2)
        c.cancel.set()
        res = await asyncio.wait_for(task, 2.0)
        await dog.close()
        return res

    res = run(go())
    assert not res.completed and res.stopped and "cancelled" in res.detail


def test_stale_state_is_unknown(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        await conn.disconnect()          # state stream stops
        await asyncio.sleep(1.2)
        st = await dog.get_status()
        await dog.close()
        return st

    st = run(go())
    assert st.connected and st.standing is None and st.stationary is None


def test_uncalibrated_route_is_unsupported(tmp_path):
    routes = tmp_path / "routes.json"
    routes.write_text(json.dumps({"room_2": {"calibrated": False, "segments": []}}))
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn, routes_path=str(routes))
        await dog.connect()
        out = []
        for zone in ("room_2", "entrance"):
            with pytest.raises(AdapterError) as e:
                await dog.run_route(zone, ctx())
            out.append(e.value.code)
        await dog.close()
        return out

    assert run(go()) == ["unsupported", "unsupported"]
    assert conn.moves() == []


def test_methods_require_connect(tmp_path):
    dog = make(tmp_path, FakeConn())
    with pytest.raises(AdapterError) as e:
        run(dog.run_segments([{"vx": 0.1, "duration_s": 0.1}], ctx()))
    assert e.value.code == "not_connected"
    run(dog.halt())   # safe when not connected
    run(dog.close())  # idempotent


def _sport_apis(conn):
    return [s[1] for s in conn.sent if s[0] == "SPORT_MOD"]


def test_rest_mid_route_stops_then_lies_down_slowly(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        task = asyncio.create_task(dog.run_segments([{"vx": 0.2, "duration_s": 5.0}], ctx()))
        await asyncio.sleep(0.3)
        report = await dog.rest()
        res = await asyncio.wait_for(task, 2.0)
        await dog.close()
        return report, res

    report, res = run(go())
    apis = _sport_apis(conn)
    assert report["standdown_sent"] is True
    assert not res.completed
    assert 1001 not in apis                       # never Damp
    first_standdown = apis.index(1005)
    assert 1003 in apis[:first_standdown]         # StopMove before StandDown
    assert 1008 not in apis[first_standdown:]     # no Move after rest


def test_rest_works_after_halt_and_locks_motion(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        await dog.halt()
        report = await dog.rest()
        with pytest.raises(AdapterError) as e:
            await dog.run_segments([{"vx": 0.2, "duration_s": 0.2}], ctx())
        await dog.close()
        return report, e.value.code

    report, code = run(go())
    assert report["standdown_sent"] is True and code == "unsafe_state"
    assert 1005 in _sport_apis(conn)


def test_rest_when_not_connected_is_safe(tmp_path):
    report = run(make(tmp_path, FakeConn()).rest())
    assert report["standdown_sent"] is False


def test_capture_writes_complete_jpeg(tmp_path):
    import numpy as np
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()

        async def feed():
            await asyncio.sleep(0.1)
            dog._frame = np.zeros((72, 128, 3), dtype=np.uint8)
            dog._frame_t = time.monotonic()
            dog._frame_utc = "2026-11-04T12:00:00+00:00"
        asyncio.create_task(feed())
        frame = await dog.capture_frame("room_2", ctx())
        await dog.close()
        return frame

    frame = run(go())
    p = Path(frame.path)
    assert p.is_absolute() and p.suffix == ".jpg" and p.read_bytes()[:2] == b"\xff\xd8"
    assert frame.simulated is False and frame.source == "dog"
    assert not list(tmp_path.glob(".tmp_*"))


def test_nan_in_route_is_rejected(tmp_path):
    with pytest.raises(AdapterError) as e:
        RealDog._validate_segment({"vx": float("nan"), "duration_s": 1.0})
    assert e.value.code == "invalid_input"
    with pytest.raises(AdapterError):
        RealDog._validate_segment({"vyaw": float("inf"), "duration_s": 1.0})


def test_dead_webrtc_link_reports_disconnected_and_blocks_motion(tmp_path):
    conn = FakeConn()

    async def go():
        dog = make(tmp_path, conn)
        await dog.connect()
        conn.pc = type("PC", (), {"connectionState": "failed"})()   # cable pulled
        st = await dog.get_status()
        with pytest.raises(AdapterError) as e:
            await dog.run_segments([{"vx": 0.2, "duration_s": 0.2}], ctx())
        await dog.close()
        return st, e.value.code

    st, code = run(go())
    assert st.connected is False and code == "not_connected"
    assert conn.moves() == []
