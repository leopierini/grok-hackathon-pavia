"""RealDog LiDAR subscription + simulated room + `--step lidar`, against SimConn (no robot)."""

import asyncio
import time
from pathlib import Path

import numpy as np

from patrol.dog import real as real_mod
from patrol.dog import real_selftest
from patrol.dog.real import RealDog
from patrol.dog.sim_conn import SimConn


def run(coro):
    return asyncio.run(coro)


def make_dog(tmp_path, sim, **cfg):
    config = {"interface": "simulated", "command_timeout_s": 0.3, **cfg}
    return RealDog(config=config, output_dir=tmp_path, _conn_factory=lambda ip: sim)


def switch_entries(sim):
    return [s for s in sim.sent if s[0] == "ULIDAR_SWITCH"]


def test_connect_subscribes_and_uses_native_decoder(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            assert sim.decoder_calls == ["native"]
            assert sim.traffic_saving_calls == [True]
            await asyncio.sleep(1.0)
            st = dog.lidar_status()
            assert st["msgs"] >= 1
            assert st["points"] > 1000
            assert st["frame_id"] == "odom"
            assert st["error"] is None
            assert set(st) == {"enabled", "msgs", "bad", "age_s", "points", "rate_hz", "frame_id",
                               "switch_sent", "error"}
            assert st["enabled"] is True and st["bad"] == 0
        finally:
            await dog.close()

    run(go())


def test_connect_never_sends_switch(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            await asyncio.sleep(1.0)
            assert switch_entries(sim) == []
            assert dog.lidar_status()["switch_sent"] is False
        finally:
            await dog.close()

    run(go())


def test_lidar_view_shows_room(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            await asyncio.sleep(0.8)
            v = dog.lidar_view()
            assert v["n"] > 0
            assert v["reason"] is None
            assert abs(v["nearest_ahead_m"] - 0.95) <= 0.06
        finally:
            await dog.close()

    run(go())


def test_lidar_view_without_scan_has_reason(tmp_path):
    async def go():
        sim = SimConn(lidar=False)
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            await asyncio.sleep(0.5)
            assert dog.latest_lidar() is None
            assert dog.lidar_view()["reason"] == "no scan"
            assert dog.lidar_status()["msgs"] == 0
        finally:
            await dog.close()

    run(go())


def test_lidar_switch_on_button_path(tmp_path):
    async def go():
        sim = SimConn(lidar_needs_switch=True)
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            await asyncio.sleep(1.0)
            assert dog.lidar_status()["msgs"] == 0
            res = await dog.lidar_switch_on()
            assert isinstance(res["utc"], str)
            await asyncio.sleep(1.0)
            assert dog.lidar_status()["msgs"] >= 1
            assert dog.lidar_status()["switch_sent"] is True
            assert len(switch_entries(sim)) == 1
            assert switch_entries(sim)[0][2] == "on"
        finally:
            await dog.close()

    run(go())


def test_lidar_switch_allowed_while_motion_locked(tmp_path):
    async def go():
        sim = SimConn(lidar_needs_switch=True)
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            dog.latch_lock("test lock")
            await dog.lidar_switch_on()
            assert len(switch_entries(sim)) == 1
            assert sim.moves() == []
        finally:
            await dog.close()

    run(go())


def test_lidar_switch_requires_connection(tmp_path):
    async def go():
        dog = make_dog(tmp_path, SimConn())
        try:
            await dog.lidar_switch_on()
        except Exception as e:
            assert getattr(e, "code", None) == "not_connected"
        else:
            raise AssertionError("expected not_connected")

    run(go())


def test_on_lidar_never_raises(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            await asyncio.sleep(0.5)
            before = dog.latest_lidar()
            assert before is not None
            dog._on_lidar({})
            dog._on_lidar({"data": 5})
            dog._on_lidar(None)
            assert dog.latest_lidar() is before
        finally:
            await dog.close()

    run(go())


def test_lidar_pose_none_without_fresh_state(tmp_path):
    dog = make_dog(tmp_path, SimConn())
    assert dog.lidar_pose() is None
    dog._sport = {"position": [1.0, 2.0, 0.3], "body_height": 0.3, "imu_state": {"rpy": [0, 0, 0.5]}}
    dog._sport_t = time.monotonic()
    x, y, yaw, ground = dog.lidar_pose()
    assert (x, y, yaw) == (1.0, 2.0, 0.5) and abs(ground) < 1e-9
    dog._sport = {"position": [1.0, 2.0, 0.3], "imu_state": {"rpy": [0, 0, 0.5]}}
    assert dog.lidar_pose()[3] is None
    dog._sport = {"position": [1.0, 2.0, 0.3]}
    assert dog.lidar_pose() is None


def test_traffic_saving_failure_is_not_fatal(tmp_path):
    async def go():
        sim = SimConn()

        async def boom(switch):
            raise RuntimeError("no traffic saving")
        sim.datachannel.disableTrafficSaving = boom
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            await asyncio.sleep(0.6)
            st = dog.lidar_status()
            assert st["error"].startswith("warning:") and "RuntimeError" in st["error"]
            assert st["msgs"] >= 1                      # still subscribed and receiving
        finally:
            await dog.close()

    run(go())


def test_traffic_saving_hang_does_not_block_connect(tmp_path, monkeypatch):
    monkeypatch.setattr(real_mod, "LIDAR_TRAFFIC_TIMEOUT_S", 0.2)

    async def go():
        sim = SimConn()

        async def hang(switch):
            await asyncio.sleep(60)
        sim.datachannel.disableTrafficSaving = hang
        dog = make_dog(tmp_path, sim)
        t0 = time.monotonic()
        st = await dog.connect()
        took = time.monotonic() - t0
        try:
            assert st.connected is True
            assert took < 3.0
            await asyncio.sleep(0.6)
            ls = dog.lidar_status()
            assert ls["error"].startswith("warning:") and "no reply" in ls["error"]
            assert ls["msgs"] >= 1
        finally:
            await dog.close()

    run(go())


def test_missing_set_decoder_skips_subscription(tmp_path):
    async def go():
        sim = SimConn()
        del sim.datachannel.set_decoder
        dog = make_dog(tmp_path, sim)
        st = await dog.connect()
        try:
            assert st.connected is True
            await asyncio.sleep(0.6)
            ls = dog.lidar_status()
            assert "set_decoder" in ls["error"] and ls["error"].startswith("LiDAR not subscribed")
            assert ls["msgs"] == 0 and ls["bad"] == 0
            assert sim.traffic_saving_calls == []
            assert "ULIDAR_ARRAY" not in sim.datachannel.pub_sub.subs
            assert switch_entries(sim) == []
        finally:
            await dog.close()

    run(go())


def test_set_decoder_raising_skips_subscription(tmp_path):
    async def go():
        sim = SimConn()

        def boom(decoder_type="libvoxel"):
            raise RuntimeError("no native decoder")
        sim.datachannel.set_decoder = boom
        dog = make_dog(tmp_path, sim)
        st = await dog.connect()
        try:
            assert st.connected is True
            await asyncio.sleep(0.6)
            ls = dog.lidar_status()
            assert "RuntimeError" in ls["error"] and ls["error"].startswith("LiDAR not subscribed")
            assert ls["msgs"] == 0
            assert sim.traffic_saving_calls == []
            assert "ULIDAR_ARRAY" not in sim.datachannel.pub_sub.subs
        finally:
            await dog.close()

    run(go())


def test_lidar_disabled_by_config_touches_nothing(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim, lidar_enabled=False)
        st = await dog.connect()
        try:
            assert st.connected is True
            await asyncio.sleep(0.6)
            assert sim.decoder_calls == [] and sim.traffic_saving_calls == []
            assert "ULIDAR_ARRAY" not in sim.datachannel.pub_sub.subs
            ls = dog.lidar_status()
            assert ls["enabled"] is False and ls["msgs"] == 0 and ls["error"] is None
            assert dog.lidar_enabled is False
            try:
                await dog.lidar_switch_on()
            except Exception as e:
                assert getattr(e, "code", None) == "unsupported"
            else:
                raise AssertionError("expected unsupported")
            assert switch_entries(sim) == []
        finally:
            await dog.close()

    run(go())


def test_lidar_enabled_must_be_bool(tmp_path):
    try:
        make_dog(tmp_path, SimConn(), lidar_enabled="no")
    except Exception as e:
        assert getattr(e, "code", None) == "invalid_input"
    else:
        raise AssertionError("expected invalid_input")


def test_bad_counter_counts_garbage_and_clears_on_valid_scan(tmp_path):
    async def go():
        sim = SimConn(lidar=False)
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        try:
            for junk in ({}, {"data": 5}, None):
                dog._on_lidar(junk)
            ls = dog.lidar_status()
            assert ls["bad"] == 3 and ls["msgs"] == 0
            assert "could not be decoded" in ls["error"]
            dog._on_lidar(sim._lidar_message(time.monotonic()))
            ls = dog.lidar_status()
            assert ls["msgs"] == 1 and ls["bad"] == 3
            assert ls["error"] is None                  # stream error cleared by a valid scan
        finally:
            await dog.close()

    run(go())


def test_selftest_lidar_step_saves_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(real_selftest, "LIDAR_COLLECT_S", 1.5)

    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        rec = await real_selftest._run("lidar", {"interface": "simulated"}, tmp_path, dog=dog, keys=False)
        return sim, rec

    sim, rec = run(go())
    assert rec["ok"] is True, rec
    lid = rec["lidar"]
    assert lid["ok"] is True
    assert lid["msgs"] >= 4
    assert 2.0 <= lid["rate_hz"] <= 8.0                  # exact: (end - start msgs) / elapsed
    assert "rate_hz_window" in lid
    assert rec["lidar_enabled"] is True
    assert lid["points_last"] > 1000
    assert lid["frame_id"] == "odom"
    assert len(lid["xyz_min"]) == 3 and len(lid["xyz_max"]) == 3
    assert lid["pose_start"] is not None and lid["pose_end"] is not None
    assert Path(lid["npy"]).exists() and Path(lid["npy"]).parent == tmp_path
    assert Path(lid["ply"]).exists()
    assert np.load(lid["npy"]).shape[1] == 3
    assert [s for s in sim.sent if s[0] == "SPORT_MOD" and s[1] == 1008] == []
    assert switch_entries(sim) == []


def test_selftest_lidar_step_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(real_selftest, "LIDAR_FIRST_SCAN_S", 0.6)
    monkeypatch.setattr(real_selftest, "LIDAR_COLLECT_S", 0.3)

    async def go():
        sim = SimConn(lidar_needs_switch=True)
        dog = make_dog(tmp_path, sim)
        rec = await real_selftest._run("lidar", {"interface": "simulated"}, tmp_path, dog=dog, keys=False)
        return sim, rec

    sim, rec = run(go())
    assert rec["lidar"]["ok"] is False
    assert "no LiDAR data" in rec["lidar"]["reason"]
    assert rec["ok"] is False
    assert switch_entries(sim) == []


def test_lidar_is_not_a_motion_step():
    assert "lidar" in real_selftest.STEPS
    assert "lidar" not in real_selftest.MOTION_STEPS


def test_selftest_lidar_step_disabled_by_config(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim, lidar_enabled=False)
        rec = await real_selftest._run("lidar", {"interface": "simulated"}, tmp_path, dog=dog, keys=False)
        return sim, rec

    sim, rec = run(go())
    assert rec["lidar"] == {"ok": False, "reason": "disabled by config (lidar_enabled: false)"}
    assert rec["ok"] is False
    assert rec["lidar_enabled"] is False
    assert sim.decoder_calls == [] and switch_entries(sim) == []


def test_selftest_records_lidar_enabled_on_every_step(tmp_path):
    async def go():
        dog = make_dog(tmp_path, SimConn())
        return await real_selftest._run("read", {"interface": "simulated"}, tmp_path, dog=dog, keys=False)

    assert run(go())["lidar_enabled"] is True
