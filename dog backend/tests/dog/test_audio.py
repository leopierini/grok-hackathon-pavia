"""Speaker + mic: audio helpers and RealDog audio extras, on the simulated connection."""

import asyncio
import shutil
import time
import wave

import numpy as np
import pytest

from patrol.contract import AdapterError
from patrol.dog import audio as A
from patrol.dog.real import RealDog
from patrol.dog.sim_conn import SimConn


def run(coro):
    return asyncio.run(coro)


def make_dog(tmp_path, sim, **cfg):
    config = {"interface": "simulated", "command_timeout_s": 0.3, **cfg}
    return RealDog(config=config, output_dir=tmp_path, _conn_factory=lambda ip: sim)


# ---------------------------------------------------------------- helpers

def test_converter_rates_and_channels():
    one_s_16k_stereo = np.zeros(16000 * 2, dtype="<i2").tobytes()
    assert abs(len(A.to_mono48(one_s_16k_stereo, 16000, 2)) / 2 / 48000 - 1.0) < 0.01
    c = A.PcmConverter(48000, 1, out_rate=16000)
    n = sum(len(c.convert(A.tone_pcm(440, 0.02))) for _ in range(50)) + len(c.flush())
    assert abs(n / 2 / 16000 - 1.0) < 0.01
    odd = A.PcmConverter(48000, 1)
    assert odd.convert(b"\x01\x02\x03") == b"\x01\x02"     # half sample kept for the next chunk
    assert odd.convert(b"\x04") == b"\x03\x04"
    with pytest.raises(ValueError):
        A.PcmConverter(100, 1)
    with pytest.raises(ValueError):
        A.PcmConverter(48000, 3)


def test_wav_roundtrip_and_decode(tmp_path):
    pcm = A.chime_pcm()
    path = A.write_wav(tmp_path / "c.wav", pcm)
    assert A.decode_file(path) == pcm
    with wave.open(path) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 48000, 2)
    with pytest.raises(FileNotFoundError):
        A.decode_file(tmp_path / "missing.wav")
    with pytest.raises(ValueError):
        A.decode_file(path, max_s=0.1)


def test_speaker_track_paces_in_real_time_with_continuous_pts():
    async def go():
        t = A.SpeakerTrack()
        t.enqueue(A.tone_pcm(440, 0.1))
        t0 = time.monotonic()
        frames = [await t.recv() for _ in range(15)]           # 0.3 s
        took = time.monotonic() - t0
        assert 0.25 <= took <= 0.45
        assert [f.pts for f in frames] == [i * 960 for i in range(15)]
        assert t.audio_frames_sent == 5 and not t.active        # 0.1 s of audio, then silence
        assert not np.any(np.frombuffer(bytes(frames[-1].planes[0]), dtype="<i2"))
        t.stop()
    run(go())


def test_speaker_queue_cap_clear_and_live_lag():
    t = A.SpeakerTrack(max_buffer_s=1.0)
    t.enqueue(bytes(48000 * 2 // 2))                            # 0.5 s
    with pytest.raises(OverflowError):
        t.enqueue(bytes(48000 * 2))                             # + 1 s > cap
    t.clear()
    assert t.buffered_s == 0
    for _ in range(20):                                         # 20 x 0.1 s live chunks
        t.enqueue(bytes(4800 * 2), max_lag_s=0.3)
    assert abs(t.buffered_s - 0.3) < 0.01


def test_mic_tap_level_and_subscribers():
    import av
    tap = A.MicTap()
    q48, q16 = tap.subscribe(), tap.subscribe(16000)
    st = np.full((1, 1920), 3277, dtype="<i2")                  # stereo, -20 dBFS
    fr = av.AudioFrame.from_ndarray(st, format="s16", layout="stereo")
    fr.sample_rate = 48000
    for _ in range(10):
        tap.feed(fr)
    assert tap.frames == 10 and abs(tap.level_dbfs() + 20) < 0.5
    assert sum(len(q48.get_nowait()) for _ in range(q48.qsize())) == 10 * 960 * 2
    assert q16.qsize() > 0
    tap.unsubscribe(q48)
    assert tap.subscribers == 1


def test_mic_queue_drops_oldest_when_full():
    import av
    tap = A.MicTap()
    q = tap.subscribe(max_chunks=3)
    for i in range(5):
        fr = av.AudioFrame.from_ndarray(np.full((1, 960), i, dtype="<i2"), format="s16", layout="mono")
        fr.sample_rate = 48000
        tap.feed(fr)
    firsts = [np.frombuffer(q.get_nowait(), dtype="<i2")[0] for _ in range(3)]
    assert firsts == [2, 3, 4]


@pytest.mark.skipif(shutil.which("say") is None, reason="macOS say only")
def test_tts_macos_italian():
    pcm = A.tts_macos("Buonasera", "Alice")
    assert len(pcm) / 2 / 48000 > 0.3
    with pytest.raises(ValueError):
        A.tts_macos("x" * (A.MAX_SAY_CHARS + 1))


# ---------------------------------------------------------------- RealDog

def test_volume_get_set_clamp_and_readback(tmp_path):
    async def go():
        sim = SimConn(volume=3)
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        assert await dog.get_volume() == 3
        assert await dog.set_volume(12) == 10 and sim.volume == 10
        assert await dog.set_volume(-1) == 0
        for bad in ("x", float("nan"), None):
            with pytest.raises(AdapterError) as e:
                await dog.set_volume(bad)
            assert e.value.code == "invalid_input"
        await dog.set_volume(7)
        await asyncio.sleep(1.2)                                # multiplestate ~1 Hz
        assert dog.volume_readback() == 7
        await dog.close()
    run(go())


def test_play_reaches_the_dog_speaker_and_stop_cuts_it(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        assert dog.speaker_status()["attached"] is False         # nothing sent until first use
        secs = dog.play_chime()
        assert 0.5 < secs < 0.8
        assert dog.speaker_status()["playing"] is True
        assert await dog.wait_audio_done(3.0)
        assert 0.5 < sim.audio_played_s < 0.8 and sim.peak_played > 5000
        # long file, then stop_audio part-way
        long_path = A.write_wav(tmp_path / "long.wav", A.tone_pcm(300, 3.0))
        assert abs(await dog.play_audio_file(long_path) - 3.0) < 0.01
        await asyncio.sleep(0.3)
        dog.stop_audio()
        before = sim.audio_played_s
        await asyncio.sleep(0.3)
        assert sim.audio_played_s - before < 0.05
        assert dog.speaker_status()["playing"] is False
        with pytest.raises(AdapterError) as e:
            await dog.play_audio_file(tmp_path / "nope.mp3")
        assert e.value.code == "invalid_input"
        await dog.close()
        assert sim.pc.getTransceivers()[0].sender.track is None   # detached on close
    run(go())


def test_play_pcm_stream_any_rate(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        chunk = (np.sin(np.arange(2400) / 5) * 8000).astype("<i2").tobytes()  # 0.1 s at 24 kHz
        for _ in range(5):
            dog.play_pcm(chunk, rate=24000)
        assert abs(dog.speaker_status()["queued_s"] - 0.5) < 0.05
        with pytest.raises(AdapterError):
            dog.play_pcm(chunk, rate=5)
        assert await dog.wait_audio_done(2.0)
        assert sim.audio_played_s > 0.4
        await dog.close()
    run(go())


def test_audio_needs_connection(tmp_path):
    async def go():
        dog = make_dog(tmp_path, SimConn())
        with pytest.raises(AdapterError) as e:
            dog.play_chime()
        assert e.value.code == "not_connected"
        with pytest.raises(AdapterError):
            dog.mic_subscribe()
        dog.stop_audio()                                        # never raises
    run(go())


def test_mic_switches_on_only_while_subscribed(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        assert sim.audio_switches == [] and dog.mic_status()["on"] is False
        q1, q2 = dog.mic_subscribe(16000), dog.mic_subscribe()
        assert sim.audio_switches == [True]
        chunk = await asyncio.wait_for(q1.get(), 3.0)
        assert len(chunk) > 0
        dog.mic_unsubscribe(q1)
        assert sim.audio_switches == [True]
        dog.mic_unsubscribe(q2)
        dog.mic_unsubscribe(q2)                                 # idempotent
        assert sim.audio_switches == [True, False] and dog.mic_status()["on"] is False
        q3 = dog.mic_subscribe()
        await dog.close()                                       # close switches it off
        assert sim.audio_switches[-1] is False
        with pytest.raises(AdapterError):
            dog.mic_subscribe(rate=1)
    run(go())


def test_record_hears_the_speaker_loopback(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        rec_task = asyncio.create_task(dog.record_audio(1.5, name="loop test"))
        await asyncio.sleep(0.4)
        dog.play_chime()
        rec = await rec_task
        with wave.open(rec["path"]) as w:
            assert w.getnframes() == int(1.5 * 48000)
        lv = rec["levels_dbfs_100ms"]
        assert max(lv[:3]) < -50 and rec["peak_dbfs"] > -30      # quiet, then the chime
        assert "looptest_" in rec["path"]
        assert dog.mic_status()["on"] is False
        await dog.close()
    run(go())


def test_record_without_mic_frames_times_out(tmp_path):
    async def go():
        dog = make_dog(tmp_path, SimConn(mic=False))
        await dog.connect()
        with pytest.raises(AdapterError) as e:
            await dog.record_audio(0.5)
        assert e.value.code == "timeout"
        assert dog.mic_status()["on"] is False
        for bad in (0, 100, "x"):
            with pytest.raises(AdapterError):
                await dog.record_audio(bad)
        await dog.close()
    run(go())


def test_audio_never_touches_motion(tmp_path):
    async def go():
        sim = SimConn()
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        await dog.set_volume(5)
        dog.play_chime()
        await dog.record_audio(0.3)
        dog.stop_audio()
        await dog.close()
        assert sim.apis("SPORT_MOD") == []
    run(go())


def _noise(seconds, sigma, seed=0):
    return np.random.default_rng(seed).normal(0, sigma, round(seconds * A.RATE))


def _burst(pcm, t0, t1, sigma, seed):
    a, b = round(t0 * A.RATE), round(t1 * A.RATE)
    pcm[a:b] += np.random.default_rng(seed).normal(0, sigma, b - a)


def test_loopback_check_finds_chime_under_louder_noise():
    # Shape of the real 2026-11-04 recording: a loud noise burst *before* the chime,
    # then a chime that is quieter than the burst. Plain loudness says "not heard".
    pcm = _noise(4.0, 300)                                         # ~ -40 dBFS room
    _burst(pcm, 0.3, 0.6, 4000, seed=1)                            # ~ -18 dBFS burst
    chime = np.frombuffer(A.chime_pcm(), dtype="<i2").astype(float) * 0.1
    at = round(1.7 * A.RATE)                                       # 1.5 s + 0.2 s latency
    pcm[at:at + len(chime)] += chime
    pcm = np.clip(pcm, -32768, 32767).astype("<i2").tobytes()

    lv = A.level_series(pcm, A.RATE)
    assert max(lv[15:24]) < max(lv[:14])                           # the old check fails here

    r = A.loopback_check(pcm, A.RATE, chime_at_s=1.5)
    assert r["heard"] is True
    assert set(r["tone_rise_db"]) == {"660", "990"}
    assert min(r["tone_rise_db"].values()) > 15


def test_loopback_check_when_the_recording_starts_late():
    # The mic switches on after the test clock starts, so the chime can land *before*
    # the nominal 1.5 s in the recording (seen in the simulator: 660 Hz at 1.4 s).
    pcm = _noise(4.0, 300)
    chime = np.frombuffer(A.chime_pcm(), dtype="<i2").astype(float) * 0.1
    at = round(1.25 * A.RATE)
    pcm[at:at + len(chime)] += chime
    pcm = np.clip(pcm, -32768, 32767).astype("<i2").tobytes()
    r = A.loopback_check(pcm, A.RATE, chime_at_s=1.5)
    assert r["heard"] is True and min(r["tone_rise_db"].values()) > 15


def test_loopback_check_says_not_heard_without_chime():
    pcm = _noise(4.0, 300)
    _burst(pcm, 0.3, 0.6, 4000, seed=1)
    _burst(pcm, 1.7, 2.3, 4000, seed=2)                            # loud, but no tone
    pcm = np.clip(pcm, -32768, 32767).astype("<i2").tobytes()
    r = A.loopback_check(pcm, A.RATE, chime_at_s=1.5)
    assert r["heard"] is False


def test_loopback_check_on_digital_silence():
    r = A.loopback_check(bytes(4 * A.RATE * 2), A.RATE, chime_at_s=1.5)
    assert r["heard"] is False and all(abs(v) < 1 for v in r["tone_rise_db"].values())


def test_selftest_audio_step_loopback_and_volume_restore(tmp_path):
    from patrol.dog.real_selftest import STEPS, MOTION_STEPS, _audio_step
    assert "audio" in STEPS and "audio" not in MOTION_STEPS        # no --arm needed: never moves

    async def go():
        sim = SimConn(volume=2)
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        rec = {}
        await _audio_step(dog, rec, volume=6)
        await dog.close()
        return sim, rec
    sim, rec = run(go())
    assert rec["volume_before"] == 2 and rec["volume_set"] == 6 and rec["volume_restored"] == 2
    assert sim.volume == 2
    assert rec["loopback_heard"] is True and rec["recording"].endswith(".wav")
    assert min(rec["loopback_tone_rise_db"].values()) > 20
    assert "loopback_rise_db" not in rec                            # old loudness-only check is gone
    assert sim.apis("SPORT_MOD") == []


def test_selftest_audio_step_warns_on_zero_volume(tmp_path):
    from patrol.dog.real_selftest import _audio_step

    async def go():
        sim = SimConn(volume=0)
        dog = make_dog(tmp_path, sim)
        await dog.connect()
        rec = {}
        await _audio_step(dog, rec, volume=None)
        await dog.close()
        return sim, rec
    sim, rec = run(go())
    assert "volume is 0" in rec["note"] and "volume_restored" not in rec
    assert [a for a in sim.apis("VUI") if a == 1003] == []          # never changed the volume


# ---------------------------------------------------------------- audio step verdict (real dog 2026-11-04 17:21:
# the page ran the test at volume 0, the mic heard nothing, and it still said PASS)

def test_sim_volume_mutes_option():
    sim = SimConn(volume=0, volume_mutes=True)
    assert sim.volume_mutes is True and SimConn().volume_mutes is False


def test_audio_step_fails_when_the_mic_does_not_hear_the_chime(tmp_path):
    from patrol.dog.real_selftest import _run

    dog = make_dog(tmp_path, SimConn(volume=0, volume_mutes=True))
    rec = run(_run("audio", {}, tmp_path, None, dog=dog, keys=False))
    assert rec["loopback_heard"] is False
    assert rec["ok"] is False and "volume is 0" in rec["error"]


def test_audio_step_passes_when_heard(tmp_path):
    from patrol.dog.real_selftest import _run

    sim = SimConn(volume=0, volume_mutes=True)
    rec = run(_run("audio", {}, tmp_path, 5, dog=make_dog(tmp_path, sim), keys=False))
    assert rec["ok"] is True and rec["loopback_heard"] is True
    assert rec["volume_restored"] == 0 and sim.volume == 0
