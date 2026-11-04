"""Joystick LiDAR push: lidar messages, status field, controller-only lidar_on (simulated dog)."""

import asyncio
import threading

from patrol.dog.sim_conn import SimConn
from tests.dog.test_joystick import log_events, make_ctl, run, serve

VIEW = {"t": "lidar", "n": 3, "pts": [100, 0, 20, 150, 30, 40, -50, 10, 5], "age_s": 0.1, "stale": False,
        "nearest_ahead_m": 1.0, "frame_id": "odom", "radius_m": 4.0, "reason": None}


async def collecting_ws(client):
    """WS that records every JSON message (a browser tab)."""
    ws = await client.ws_connect("/ws")
    ws.hello = await ws.receive_json()
    ws.msgs = []

    async def pump():
        async for m in ws:
            if m.type.name == "TEXT":
                ws.msgs.append(m.json())
    ws._pump = asyncio.create_task(pump())
    return ws


async def until(pred, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if pred():
            return True
        await asyncio.sleep(0.02)
    return pred()


def of(ws, t):
    return [m for m in ws.msgs if m.get("t") == t]


def test_lidar_pushed_to_view_clients(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            ctl.dog.lidar_view = lambda: dict(VIEW)
            ws1 = await collecting_ws(client)      # controller
            ws2 = await collecting_ws(client)      # view-only
            assert ws2.hello["role"] == "view"
            ok = await until(lambda: of(ws2, "lidar"), 1.0)
            msg = of(ws2, "lidar")[0] if ok else None
            got1 = bool(of(ws1, "lidar"))
            await ws1.close()
            await ws2.close()
            return ok, msg, got1

    ok, msg, got1 = run(go())
    assert ok and msg["n"] == 3 and msg["pts"] == VIEW["pts"] and msg["nearest_ahead_m"] == 1.0
    assert got1


def test_lidar_rate_is_capped(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            ctl.dog.lidar_view = lambda: dict(VIEW)
            ws = await collecting_ws(client)
            await asyncio.sleep(1.0)
            n = len(of(ws, "lidar"))
            await ws.close()
            return n

    assert run(go()) <= 6      # 5 Hz + one


def test_lidar_view_built_in_thread(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            seen = []

            def view():
                seen.append(threading.get_ident())
                return dict(VIEW)
            ctl.dog.lidar_view = view
            ws = await collecting_ws(client)
            assert await until(lambda: seen)
            await ws.close()
            return seen[0], threading.get_ident()

    worker, loop_thread = run(go())
    assert worker != loop_thread


def test_status_has_lidar(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            ctl.dog.lidar_status = lambda: {"msgs": 7, "age_s": 0.2, "points": 900, "rate_hz": 5.0,
                                            "frame_id": "odom", "switch_sent": False, "error": None}
            ws = await collecting_ws(client)
            ok = await until(lambda: [m for m in of(ws, "status") if m.get("lidar")], 2.0)
            msgs = [m for m in of(ws, "status") if m.get("lidar")]
            await ws.close()
            return ok, msgs

    ok, msgs = run(go())
    assert ok and msgs[0]["lidar"]["msgs"] == 7


def test_lidar_on_controller_only(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            calls = []

            async def switch_on():
                calls.append(1)
                return {"utc": "2026-11-04T10:00:00+00:00"}
            ctl.dog.lidar_switch_on = switch_on
            ws1 = await collecting_ws(client)      # controller
            ws2 = await collecting_ws(client)      # view-only
            await ws2.send_json({"t": "lidar_on"})
            await asyncio.sleep(0.3)
            from_viewer = len(calls)
            await ws1.send_json({"t": "lidar_on"})
            ok = await until(lambda: calls, 2.0)
            await asyncio.sleep(0.2)
            await ws1.close()
            await ws2.close()
            return from_viewer, ok, len(calls)

    from_viewer, ok, n = run(go())
    assert from_viewer == 0 and ok and n == 1
    assert [e for e in log_events(tmp_path) if e["event"] == "lidar_switch"]


def test_lidar_on_allowed_while_motion_locked(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            calls = []

            async def switch_on():
                calls.append(1)
                return {"utc": "x"}
            ctl.dog.lidar_switch_on = switch_on
            ctl.dog.latch_lock("test lock")
            assert ctl.dog.motion_lock()
            ws = await collecting_ws(client)
            await ws.send_json({"t": "lidar_on"})
            ok = await until(lambda: calls, 2.0)
            await ws.close()
            return ok

    assert run(go())


def test_lidar_on_refused_when_not_connected_or_unsupported(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            ctl.dog.lidar_switch_on = None         # dog without the method
            await ws.send_json({"t": "lidar_on"})
            ok1 = await until(lambda: [e for e in of(ws, "event") if "lidar" in e["msg"].lower()], 2.0)
            ctl.dog = None                         # not connected at all
            n_before = len(of(ws, "event"))
            await ws.send_json({"t": "lidar_on"})
            ok2 = await until(lambda: len(of(ws, "event")) > n_before, 2.0)
            await ws.close()
            return ok1, ok2

    ok1, ok2 = run(go())
    assert ok1 and ok2
    assert not [e for e in log_events(tmp_path) if e["event"] == "lidar_switch"]


def test_lidar_loop_survives_no_dog(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            # The real dog gains the methods later: simulate "without" by shadowing with None.
            ctl.dog.lidar_view = None
            ctl.dog.lidar_status = None
            await asyncio.sleep(0.4)
            ws.msgs.clear()              # drop anything sent before the methods were shadowed
            await asyncio.sleep(0.2)
            real_dog = ctl.dog
            ctl.dog = None
            await asyncio.sleep(0.6)
            ctl.dog = real_dog
            n_status = len(of(ws, "status"))
            await asyncio.sleep(0.5)
            alive = [t.done() for t in ctl._loops]
            await ws.close()
            return of(ws, "lidar"), n_status, len(of(ws, "status")), alive, [m.get("lidar", "absent") for m in of(ws, "status")]

    lidar, n1, n2, alive, status_lidar = run(go())
    assert lidar == []
    assert n2 > n1                       # status still flows
    assert not any(alive)                # no loop died
    assert all(v is None for v in status_lidar)


def test_lidar_view_error_printed_once_and_loop_keeps_going(tmp_path, capsys):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            state = {"n": 0}

            def view():
                state["n"] += 1
                if state["n"] <= 3:
                    raise RuntimeError("boom")
                return dict(VIEW)
            ctl.dog.lidar_view = view
            ctl.verbose = True
            ws = await collecting_ws(client)
            ok = await until(lambda: of(ws, "lidar"), 3.0)
            await ws.close()
            return ok

    assert run(go())
    out = capsys.readouterr().out
    assert out.count("lidar error: RuntimeError: boom") == 1


def test_lidar_disabled_never_pushes_and_logs_it(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False), lidar_enabled=False)
        async with serve(ctl) as client:
            ws = await collecting_ws(client)
            ok = await until(lambda: [m for m in of(ws, "status") if m.get("lidar")], 2.0)
            await asyncio.sleep(0.8)
            lidar = of(ws, "lidar")
            st = [m for m in of(ws, "status") if m.get("lidar")]
            await ws.close()
            return ok, lidar, st

    ok, lidar, st = run(go())
    assert ok and st[-1]["lidar"]["enabled"] is False
    assert lidar == []
    conn = [e for e in log_events(tmp_path) if e["event"] == "connection" and e.get("action") == "connected"]
    assert conn and conn[0]["lidar_enabled"] is False


def test_connect_log_records_lidar_enabled_true(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl):
            pass

    run(go())
    conn = [e for e in log_events(tmp_path) if e["event"] == "connection" and e.get("action") == "connected"]
    assert conn and conn[0]["lidar_enabled"] is True


def test_no_lidar_flag_sets_config_fake_and_real(tmp_path):
    import argparse
    import json

    from patrol.dog import joystick

    fake = joystick._make_factory(argparse.Namespace(fake=True, no_lidar=True, out=str(tmp_path)))[0]()
    assert fake.lidar_enabled is False
    fake = joystick._make_factory(argparse.Namespace(fake=True, no_lidar=False, out=str(tmp_path)))[0]()
    assert fake.lidar_enabled is True
    cfg = tmp_path / "dog.json"
    cfg.write_text(json.dumps({"interface": "192.168.123.161"}))
    real = joystick._make_factory(argparse.Namespace(fake=False, config=str(cfg), no_lidar=True,
                                                     out=str(tmp_path)))[0]()
    assert real.lidar_enabled is False
    real = joystick._make_factory(argparse.Namespace(fake=False, config=str(cfg), no_lidar=False,
                                                     out=str(tmp_path)))[0]()
    assert real.lidar_enabled is True


def test_slow_tab_gets_at_most_one_pending_lidar_send(tmp_path):
    async def go():
        ctl = make_ctl(tmp_path, SimConn(camera=False))
        async with serve(ctl) as client:
            ctl.dog.lidar_view = lambda: dict(VIEW)
            ws1 = await collecting_ws(client)      # the slow tab
            slow = next(iter(ctl.clients))
            ws2 = await collecting_ws(client)      # a healthy tab
            release = asyncio.Event()
            attempts = []
            real_send = ctl._send

            async def send(ws, data):
                if ws is slow and isinstance(data, str):      # a lidar frame to the slow tab hangs
                    attempts.append(1)
                    await release.wait()
                    return
                await real_send(ws, data)
            ctl._send = send
            n_status = len(of(ws2, "status"))
            await asyncio.sleep(1.2)
            lidar2 = len(of(ws2, "lidar"))
            status2 = len(of(ws2, "status")) - n_status
            pending = len(ctl._lidar_inflight)
            blocked = len(attempts)
            release.set()
            await asyncio.sleep(0.4)
            resumed = len(attempts)
            await ws1.close()
            await ws2.close()
            return blocked, lidar2, status2, pending, resumed

    attempts, lidar2, status2, pending, resumed = run(go())
    assert attempts <= 1                    # the blocked tab never queues a second lidar frame
    assert lidar2 >= 3                      # the healthy tab keeps getting frames
    assert status2 >= 3                     # status is not stuck behind lidar frames
    assert pending == 1
    assert resumed > attempts               # once the tab drains, it gets frames again
