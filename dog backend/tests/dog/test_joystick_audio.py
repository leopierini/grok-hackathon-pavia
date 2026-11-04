"""Joystick audio: volume, chime, say, hold-to-talk, listen, record, meters (simulated dog)."""

import asyncio
import json
import shutil

import aiohttp
import numpy as np
import pytest

from patrol.dog.sim_conn import SimConn
from tests.dog.test_joystick import log_events, make_ctl, run, serve, ws_open


async def raw_ws(client):
    """WS that we read ourselves (to see binary + meter messages)."""
    ws = await client.ws_connect("/ws")
    hello = await ws.receive_json()
    return ws, hello


async def until(pred, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if pred():
            return True
        await asyncio.sleep(0.02)
    return pred()


def test_volume_read_on_connect_set_and_metered(tmp_path):
    async def go():
        sim = SimConn(volume=2)
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            assert ctl.volume == 2
            ws, _ = await raw_ws(client)
            await ws.send_json({"t": "volume", "level": 99})
            assert await until(lambda: sim.volume == 10)
            meter = None
            for _ in range(60):                               # meter is pushed at 10 Hz
                m = await ws.receive()
                if m.type == aiohttp.WSMsgType.TEXT and json.loads(m.data)["t"] == "meter":
                    meter = json.loads(m.data)
                    if meter["volume"] == 10:
                        break
            assert meter is not None and meter["volume"] == 10 and meter["volume_set"] == 10
            assert "mic_dbfs" in meter and "spk_dbfs" in meter
            await ws.close()
        assert any(e["event"] == "volume" and e["new"] == 10 for e in log_events(tmp_path))
    run(go())


def test_chime_plays_and_stop_cuts_audio_and_rests(tmp_path):
    async def go():
        sim = SimConn(volume=5)
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await ws.send_json({"t": "chime"})
            assert await until(lambda: sim.audio_played_s > 0.1)
            await ws.send_json({"t": "stop"})
            assert await until(lambda: 1005 in sim.apis())     # soft lie-down as always
            assert not ctl.dog.speaker_status()["playing"]
            assert sim.audio_played_s < 0.55                    # cut before the 0.6 s chime ended
            await ws.close()
    run(go())


def test_view_only_tab_cannot_use_speaker_but_can_listen(tmp_path):
    async def go():
        sim = SimConn(volume=5)
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ctl_ws = await ws_open(client)
            view, hello = await raw_ws(client)
            assert hello["role"] == "view"
            await view.send_json({"t": "chime"})
            await view.send_json({"t": "volume", "level": 9})
            await view.send_json({"t": "talk", "on": True, "rate": 48000})
            await view.send_bytes(np.full(4800, 9000, dtype="<i2").tobytes())
            await view.send_json({"t": "listen", "on": True})
            got = None
            for _ in range(80):
                m = await view.receive()
                if m.type == aiohttp.WSMsgType.BINARY:
                    got = m.data
                    break
            assert got is not None and len(got) % 2 == 0            # 16 kHz mono s16
            assert sim.volume == 5 and sim.audio_played_s == 0
            assert sim.audio_switches == [True]
            await view.send_json({"t": "listen", "on": False})
            assert await until(lambda: sim.audio_switches[-1] is False)
            await view.close()
            await ctl_ws.close()
    run(go())


def test_hold_to_talk_reaches_dog_with_bounded_lag(tmp_path):
    async def go():
        sim = SimConn(volume=5)
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            chunk = (np.sin(np.arange(1920) / 4) * 8000).astype("<i2").tobytes()   # 40 ms at 48 kHz
            await ws.send_bytes(chunk)                        # before talk: ignored
            await asyncio.sleep(0.1)
            assert not ctl.dog.speaker_status()["attached"]
            await ws.send_json({"t": "talk", "on": True, "rate": 48000})
            for _ in range(40):                               # 1.6 s sent in a burst
                await ws.send_bytes(chunk)
            await asyncio.sleep(0.15)
            assert ctl.dog.speaker_status()["queued_s"] <= 0.45  # old audio dropped, lag bounded
            await ws.send_json({"t": "talk", "on": False})
            await ws.send_bytes(chunk * 10)                   # after release: ignored
            assert await until(lambda: not ctl.dog.speaker_status()["playing"], 2.0)
            assert 0.1 < sim.audio_played_s < 0.6
            await ws.close()
        ev = [e for e in log_events(tmp_path) if e["event"] == "talk"]
        assert [e["action"] for e in ev] == ["start", "stop"]
    run(go())


def test_record_button_saves_wav(tmp_path):
    async def go():
        sim = SimConn()
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await ws.send_json({"t": "record", "seconds": 1})
            assert await until(lambda: ctl.last_recording is not None, 4.0)
            assert ctl.last_recording["path"].endswith(".wav") and ctl.last_recording["seconds"] == 1.0
            assert sim.audio_switches == [True, False]        # mic off again afterwards
            await ws.close()
        assert sim.apis("SPORT_MOD") == []                    # audio never moves the dog
    run(go())


@pytest.mark.skipif(shutil.which("say") is None, reason="macOS say only")
def test_say_italian(tmp_path):
    async def go():
        sim = SimConn(volume=5)
        ctl = make_ctl(tmp_path, sim)
        async with serve(ctl) as client:
            ws = await ws_open(client)
            await ws.send_json({"t": "say", "text": "Buonasera", "lang": "it"})
            assert await until(lambda: sim.audio_played_s > 0.2, 6.0)
            await ws.send_json({"t": "audio_stop"})
            await ws.close()
        ev = [e for e in log_events(tmp_path) if e["event"] == "say"]
        assert ev and ev[0]["voice"] == "Alice"
    run(go())
