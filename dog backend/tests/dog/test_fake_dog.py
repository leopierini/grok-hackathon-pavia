"""FakeDog / create_dog tests. Plain sync tests driving coroutines with asyncio.run."""
from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from patrol.contract import AdapterError, RunContext
from patrol.dog import FakeDog, create_dog

REPO = Path(__file__).resolve().parents[2]


def ctx(mission_id: str = "m-1", deadline_s: float = 10.0) -> RunContext:
    return RunContext(mission_id=mission_id, cancel=threading.Event(),
                      deadline_monotonic=time.monotonic() + deadline_s)


def make(tmp_path: Path, **config) -> FakeDog:
    return create_dog(mode="fake", config=config, output_dir=tmp_path)


async def ready(dog: FakeDog, c: RunContext) -> None:
    await dog.connect()
    await dog.prepare(c)


def code_of(coro) -> str:
    with pytest.raises(AdapterError) as info:
        asyncio.run(coro)
    return info.value.code


# -- factory / config --------------------------------------------------------

def test_factory_fake_and_empty_config_defaults(tmp_path):
    dog = create_dog(mode="fake", config={}, output_dir=tmp_path)
    assert isinstance(dog, FakeDog)
    assert dog.scenario == "blocked_resolved"
    assert dog.trace == []
    assert list(tmp_path.iterdir()) == []  # factory does no I/O


@pytest.mark.parametrize("mode", ["sim", "", None])
def test_factory_unknown_mode(tmp_path, mode):
    with pytest.raises(AdapterError) as info:
        create_dog(mode=mode, config={}, output_dir=tmp_path)
    assert info.value.code == "invalid_input"


@pytest.mark.parametrize("config", [{"scenario": "nonsense"}, ["scenario"], None,
                                    {"fake_routes": ["kitchen"]}, {"fake_route_s": 0}])
def test_factory_invalid_config(tmp_path, config):
    with pytest.raises(AdapterError) as info:
        create_dog(mode="fake", config=config, output_dir=tmp_path)
    assert info.value.code == "invalid_input"


def test_factory_real_unavailable_is_unsupported(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "patrol.dog.real", None)  # force ImportError
    with pytest.raises(AdapterError) as info:
        create_dog(mode="real", config={}, output_dir=tmp_path)
    assert info.value.code == "unsupported"


def test_import_does_not_load_vendor_library():
    script = ("import sys, patrol.dog; from pathlib import Path;"
              "patrol.dog.create_dog(mode='fake', config={}, output_dir=Path('.'));"
              "print(any(m.startswith('unitree_webrtc_connect') for m in sys.modules),"
              " 'patrol.dog.real' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", script], cwd=REPO, check=True,
                         capture_output=True, text=True).stdout.split()
    assert out == ["False", "False"]


# -- lifecycle ----------------------------------------------------------------

def test_not_connected_before_connect(tmp_path):
    dog, c = make(tmp_path), ctx()
    for coro in (dog.get_status(), dog.prepare(c), dog.run_route("room_2", c),
                 dog.capture_frame("room_2", c)):
        assert code_of(coro) == "not_connected"
    asyncio.run(dog.halt())  # safe without a connection
    asyncio.run(dog.close())


def test_connect_does_not_stand(tmp_path):
    dog = make(tmp_path)
    status = asyncio.run(dog.connect())
    assert status.connected and status.standing is False
    assert asyncio.run(dog.get_status()).standing is False


def test_route_requires_prepare(tmp_path):
    dog = make(tmp_path)
    asyncio.run(dog.connect())
    assert code_of(dog.run_route("room_2", ctx())) == "unsafe_state"


def test_happy_path_trace_order(tmp_path):
    dog, c = make(tmp_path), ctx()

    async def run():
        await dog.connect()
        await dog.get_status()
        prepared = await dog.prepare(c)
        assert prepared.standing and prepared.stationary and prepared.avoidance_enabled
        result = await dog.run_route("room_2", c)
        assert (result.completed, result.stopped) == (True, True)
        frame = await dog.capture_frame("room_2", c)
        assert frame.simulated and frame.source == "dog" and frame.zone == "room_2"
        await dog.halt()
        await dog.close()

    asyncio.run(run())
    assert dog.trace == ["connect", "get_status", "prepare", "run_route",
                         "capture_frame", "halt", "close"]


def test_close_idempotent_and_blocks_ops(tmp_path):
    dog = make(tmp_path)

    async def run():
        await dog.connect()
        await dog.close()
        await dog.close()
        await dog.halt()

    asyncio.run(run())
    assert code_of(dog.get_status()) == "not_connected"
    assert code_of(dog.connect()) == "not_connected"


# -- scenarios ----------------------------------------------------------------

@pytest.mark.parametrize("scenario", ["dismiss", "ground_clear", "slow_model",
                                      "takeoff_timeout", "landing_unknown"])
def test_irrelevant_scenarios_behave_normally(tmp_path, scenario):
    dog, c = make(tmp_path, scenario=scenario), ctx()

    async def run():
        await ready(dog, c)
        return await dog.run_route("room_2", c)

    assert asyncio.run(run()).completed


def test_route_blocked(tmp_path):
    dog, c = make(tmp_path, scenario="route_blocked"), ctx()

    async def run():
        await ready(dog, c)
        return await dog.run_route("room_2", c)

    result = asyncio.run(run())
    assert (result.completed, result.stopped) == (False, True)
    assert "blocked" in result.detail


def test_stale_frame_is_old_and_simulated(tmp_path):
    dog, c = make(tmp_path, scenario="stale_frame"), ctx()

    async def run():
        await dog.connect()
        return await dog.capture_frame("room_2", c)

    frame = asyncio.run(run())
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(frame.captured_at)).total_seconds()
    assert age > 30 and frame.simulated


# -- halt / cancel / deadline ----------------------------------------------------

def test_halt_during_route_is_fast_and_locks(tmp_path):
    dog, c = make(tmp_path, fake_route_s=5.0), ctx()

    async def run():
        await ready(dog, c)
        route = asyncio.create_task(dog.run_route("room_2", c))
        await asyncio.sleep(0.05)
        start = time.monotonic()
        await dog.halt()
        result = await asyncio.wait_for(route, 0.5)
        elapsed = time.monotonic() - start
        await dog.halt()  # repeatable
        return result, elapsed

    result, elapsed = asyncio.run(run())
    assert elapsed < 0.5
    assert (result.completed, result.stopped) == (False, True)
    assert code_of(dog.run_route("room_2", ctx())) == "unsafe_state"
    assert code_of(dog.prepare(ctx())) == "unsafe_state"


def test_cancel_mid_route(tmp_path):
    dog, c = make(tmp_path, fake_route_s=5.0), ctx()

    async def run():
        await ready(dog, c)
        asyncio.get_running_loop().call_later(0.05, c.cancel.set)
        return await asyncio.wait_for(dog.run_route("room_2", c), 0.5)

    result = asyncio.run(run())
    assert (result.completed, result.stopped) == (False, True)
    assert "cancel" in result.detail


def test_deadline_exceeded_mid_route(tmp_path):
    dog, c = make(tmp_path, fake_route_s=5.0), ctx(deadline_s=0.1)

    async def run():
        await ready(dog, c)
        return await asyncio.wait_for(dog.run_route("room_2", c), 0.5)

    result = asyncio.run(run())
    assert (result.completed, result.stopped) == (False, True)
    assert "timeout" in result.detail


def test_capture_respects_cancel_and_deadline(tmp_path):
    dog = make(tmp_path)
    asyncio.run(dog.connect())
    cancelled = ctx()
    cancelled.cancel.set()
    assert code_of(dog.capture_frame("room_2", cancelled)) == "cancelled"
    assert code_of(dog.capture_frame("room_2", ctx(deadline_s=-1))) == "timeout"
    assert list(tmp_path.iterdir()) == []


# -- capture / zones ----------------------------------------------------------

def test_capture_writes_unique_complete_jpeg(tmp_path):
    dog, c = make(tmp_path), ctx(mission_id="mission-42")

    async def run():
        await dog.connect()
        return [await dog.capture_frame("room_2", c) for _ in range(2)]

    frames = asyncio.run(run())
    paths = [Path(f.path) for f in frames]
    assert len(set(paths)) == 2
    for p in paths:
        assert p.is_absolute() and p.is_file() and "mission-42" in p.name
        data = p.read_bytes()
        assert data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
    assert sorted(tmp_path.iterdir()) == sorted(paths)  # no temp files left


def test_unknown_and_uncalibrated_zone(tmp_path):
    dog, c = make(tmp_path), ctx()
    asyncio.run(ready(dog, c))
    assert code_of(dog.run_route("kitchen", c)) == "invalid_input"
    assert code_of(dog.capture_frame("kitchen", c)) == "invalid_input"
    assert code_of(dog.run_route("entrance", c)) == "unsupported"
    assert code_of(dog.run_route("display", c)) == "unsupported"


def test_configured_extra_route(tmp_path):
    dog, c = make(tmp_path, fake_routes=["room_2", "entrance"]), ctx()

    async def run():
        await ready(dog, c)
        return await dog.run_route("entrance", c)

    assert asyncio.run(run()).completed


def test_fake_dog_audio_extras(tmp_path):
    import asyncio
    import wave

    from patrol.dog.fake import FakeDog

    async def go():
        dog = FakeDog(config={}, output_dir=tmp_path)
        with pytest.raises(AdapterError):
            await dog.say("ciao")
        await dog.connect()
        assert await dog.set_volume(14) == 10 and await dog.get_volume() == 10
        assert await dog.say("Buonasera, quest'area è riservata.") > 0
        assert dog.play_pcm(bytes(48000), rate=24000) == 1.0
        rec = await dog.record_audio(1.0, name="answer")
        with wave.open(rec["path"]) as w:
            assert w.getnframes() == 48000
        assert rec["simulated"] is True
        assert dog.spoken[0].startswith("Buonasera")
        with pytest.raises(AdapterError):
            await dog.say("")
    asyncio.run(go())
