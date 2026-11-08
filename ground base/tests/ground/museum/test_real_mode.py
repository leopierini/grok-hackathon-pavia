"""Real dog and drone paths with mocked sockets. No hardware and no API key."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from patrol.ground.museum.__main__ import main
from patrol.ground.museum.peers import ConfigError, open_dog, open_drone
from patrol.ground.museum.preflight import run_preflight
from patrol.ground.museum.runner import SCENARIOS, run_story
from patrol.ground.signal.errors import SignalError

HOST = "192.0.2.10"
DRONE_HOST = "192.0.2.20"
JPEG = Path(__file__).resolve().parents[4] / "patrol" / "drone" / "assets" / "simulated.jpg"


class FakePubSub:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self.subs: dict[str, object] = {}

    def subscribe(self, topic: str, cb: object = None) -> None:
        self.subs[topic] = cb

    async def publish_request_new(
        self, topic: str, options: dict[str, object]
    ) -> dict[str, object]:
        api = options["api_id"]
        self.conn.sent.append((topic, api, options.get("parameter")))
        return {"data": {"header": {"status": {"code": 0}}}}


class FakeVideo:
    def add_track_callback(self, cb: object) -> None:
        return None

    def switchVideoChannel(self, on: bool) -> None:
        return None


class _PC:
    def __init__(self) -> None:
        self.connectionState = "connected"

    def getTransceivers(self) -> list[object]:
        return []


class FakeConn:
    """Stand-in WebRTC session. connect() publishes state and never leaves the process."""

    def __init__(self) -> None:
        self.sent: list[tuple[object, object, object]] = []
        self.datachannel = type("DC", (), {})()
        self.datachannel.pub_sub = FakePubSub(self)
        self.video = FakeVideo()
        self.pc = _PC()
        self._task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._stream())

    async def disconnect(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _stream(self) -> None:
        subs = self.datachannel.pub_sub.subs
        while True:
            sport = subs.get("LF_SPORT_MOD_STATE")
            if callable(sport):
                sport(
                    {
                        "data": {
                            "mode": 5,
                            "body_height": 0.1,
                            "velocity": [0.0, 0.0, 0.0],
                            "yaw_speed": 0.0,
                            "position": [0.0, 0.0, 0.1],
                            "imu_state": {"rpy": [0.0, 0.0, 0.0]},
                        }
                    }
                )
            low = subs.get("LOW_STATE")
            if callable(low):
                low({"data": {"bms_state": {"soc": 80}}})
            multi = subs.get("MULTIPLE_STATE")
            if callable(multi):
                multi({"data": json.dumps({"obstaclesAvoidSwitch": True, "volume": 5})})
            await asyncio.sleep(0.02)

    def apis(self) -> list[object]:
        return [item[1] for item in self.sent if item[0] == "SPORT_MOD"]


class FakeSDK:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.state = {"bat": 80, "h": 0}
        self.battery = 80
        self.alive = True

    def query(self, command: str, timeout: float = 5) -> str:
        del timeout
        if not self.alive:
            raise OSError("link down")
        self.sent.append(command)
        if command == "battery?":
            return str(self.battery)
        if command == "takeoff":
            self.state["h"] = 30
            return "ok"
        if command == "land":
            self.state["h"] = 0
            return "ok"
        return "ok"

    def send(self, command: str) -> None:
        if not self.alive:
            raise OSError("link down")
        self.sent.append(command)
        if command == "emergency":
            self.state["h"] = 0

    def snapshot(self) -> dict[str, object]:
        return dict(self.state)

    def close(self) -> None:
        self.alive = False


def _dog_factory(box: list[FakeConn]):
    def factory(ip: str) -> FakeConn:
        assert ip == HOST
        conn = FakeConn()
        box.append(conn)
        return conn

    return factory


def _drone_factory(box: list[FakeSDK], seen: list[tuple[str, int]]):
    def factory(host: str, port: int) -> FakeSDK:
        seen.append((host, port))
        sdk = FakeSDK()
        box.append(sdk)
        return sdk

    return factory


def _env(**extra: str) -> dict[str, str]:
    base = {
        "PATROL_DOG_HOST": HOST,
        "PATROL_DOG_PORT": "1",
        "PATROL_DRONE_HOST": DRONE_HOST,
        "PATROL_DRONE_PORT": "4242",
    }
    base.update(extra)
    return base


def _jpeg() -> bytes:
    data = JPEG.read_bytes()
    assert data.startswith(b"\xff\xd8\xff")
    return data


def _run_real(
    tmp: Path,
    scenario: str,
    *,
    dog: str = "real",
    drone: str = "real",
    conns: list[FakeConn] | None = None,
    sdks: list[FakeSDK] | None = None,
    seen: list[tuple[str, int]] | None = None,
    grok: str = "fake",
    grok_client: object | None = None,
    motion: bool = True,
) -> object:
    return run_story(
        tmp / scenario,
        scenario=scenario,
        dog=dog,
        drone=drone,
        grok=grok,
        environ=_env(),
        motion_authorized=motion,
        dog_conn_factory=_dog_factory(conns if conns is not None else []),
        drone_sdk_factory=_drone_factory(
            sdks if sdks is not None else [],
            seen if seen is not None else [],
        ),
        drone_frame=_jpeg,
        drone_timing={"settle_s": 0, "hold_s": 0, "max_flight_s": 8},
        grok_client=grok_client,
    )


def test_motion_flag_opens_no_socket(tmp_path: Path) -> None:
    seen: list[tuple[str, int]] = []
    with pytest.raises(ConfigError, match="i-understand-this-moves-hardware"):
        _run_real(tmp_path, "happy_path", seen=seen, motion=False)
    assert seen == []


def test_main_names_the_missing_variable_and_hides_the_host(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        [
            "--dog",
            "real",
            "--drone",
            "fake",
            "--grok",
            "fake",
            "--scenario",
            "halt",
            "--output-dir",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "PATROL_DOG_HOST" in captured.err
    assert HOST not in captured.err
    code = main(
        [
            "--dog",
            "fake",
            "--drone",
            "real",
            "--grok",
            "fake",
            "--scenario",
            "halt",
            "--config",
            str(_write_config(tmp_path)),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "PATROL_DRONE_HOST" in captured.err or "i-understand" in captured.err
    assert DRONE_HOST not in captured.err + captured.out


def _write_config(tmp: Path) -> Path:
    path = tmp / "museum.json"
    path.write_text(
        json.dumps(
            {"drone": {"host": DRONE_HOST, "port": 4242}, "dog": {"host": None, "port": None}}
        ),
        encoding="utf-8",
    )
    return path


def test_real_dog_stays_down_until_ground_says_stop(tmp_path: Path) -> None:
    conns: list[FakeConn] = []
    report = _run_real(tmp_path, "happy_path", dog="real", drone="fake", conns=conns)
    assert report.ok, report.detail
    assert conns, "RealDog never built a session"
    apis = conns[0].apis()
    assert 1003 in apis
    assert 1008 not in apis
    assert 1004 not in apis
    assert report.dog_mode == "real"
    assert any(item["action"] == "follow" for item in report.gaps)
    assert any(item["action"] == "return_home" for item in report.gaps)
    assert "192.0.2.10" not in json.dumps(report.as_dict())
    blob = json.dumps(report.gaps)
    assert "Leo" in blob
    assert "28" in blob


def test_real_drone_flies_the_floor_profile_once(tmp_path: Path) -> None:
    sdks: list[FakeSDK] = []
    seen: list[tuple[str, int]] = []
    report = _run_real(tmp_path, "happy_path", dog="fake", drone="real", sdks=sdks, seen=seen)
    assert report.ok, report.detail
    assert seen == [(DRONE_HOST, 4242)]
    assert sdks[0].sent.count("takeoff") == 1
    assert sdks[0].sent.count("land") == 1
    assert "emergency" not in sdks[0].sent
    assert all(not item.startswith("rc ") or item == "rc 0 0 0 0" for item in sdks[0].sent)
    assert any(item["action"] == "land_on_dog" and "72" in item["issues"] for item in report.gaps)
    assert DRONE_HOST not in json.dumps(report.as_dict())


def test_inspect_without_the_flag_does_not_take_off(tmp_path: Path) -> None:
    sdks: list[FakeSDK] = []

    async def body() -> None:
        peer = open_drone(
            "real",
            tmp_path / "drone",
            _env(),
            None,
            motion_authorized=False,
            sdk_factory=_drone_factory(sdks, []),
            frame_source=_jpeg,
            timing={"settle_s": 0, "hold_s": 0},
        )
        await peer.drone.connect()
        with pytest.raises(Exception, match="no takeoff"):
            await peer.patrol()

    asyncio.run(body())
    assert sdks
    assert "takeoff" not in sdks[0].sent


def test_link_loss_and_halt_stop_motion(tmp_path: Path) -> None:
    conns: list[FakeConn] = []
    sdks: list[FakeSDK] = []
    halted = _run_real(tmp_path / "halt", "halt", conns=conns, sdks=sdks)
    assert halted.ok, halted.detail
    assert halted.halted
    assert 1008 not in conns[0].apis()
    assert "emergency" not in sdks[0].sent
    assert "rc 0 0 0 0" in sdks[0].sent
    dropout = _run_real(tmp_path / "drop", "dog_dropout", conns=conns, sdks=sdks)
    assert dropout.ok, dropout.detail
    assert dropout.halted
    assert "cmd:halt" in dropout.timeline or "undelivered:halt" in dropout.timeline


def test_uncertain_and_timeout_add_no_presence_motion(tmp_path: Path) -> None:
    class TimeoutGrok:
        def __init__(self) -> None:
            self.calls = 0

        def answer(self, request: object, state: str, sent_at: str) -> None:
            del request, state, sent_at
            self.calls += 1
            raise SignalError("timeout", "xAI request timed out; no decision was returned")

    uncertain = _run_real(tmp_path / "uncertain", "uncertain", dog="fake", drone="real")
    assert uncertain.ok, uncertain.detail
    assert [item["action"] for item in uncertain.delivered] == ["hover", "follow"]
    assert uncertain.spoken == []
    timed = _run_real(
        tmp_path / "timeout",
        "timeout",
        dog="fake",
        drone="fake",
        grok_client=TimeoutGrok(),
    )
    assert timed.ok, timed.detail
    assert [item["action"] for item in timed.delivered] == ["hover", "follow"]
    assert timed.decisions == []


def test_mixed_and_both_real_stories(tmp_path: Path) -> None:
    for scenario in SCENARIOS:
        mixed = _run_real(tmp_path / "mix" / scenario, scenario, dog="fake", drone="real")
        assert mixed.ok, (scenario, mixed.detail, mixed.timeline, mixed.gaps)
        both = _run_real(tmp_path / "both" / scenario, scenario, dog="real", drone="real")
        assert both.ok, (scenario, both.detail, both.timeline, both.gaps)
        assert "super-secret-value" not in json.dumps(both.as_dict())


def test_low_battery_does_not_take_off(tmp_path: Path) -> None:
    class LowSDK(FakeSDK):
        def __init__(self) -> None:
            super().__init__()
            self.battery = 10

    seen: list[tuple[str, int]] = []
    held: list[LowSDK] = []

    def factory(host: str, port: int) -> LowSDK:
        seen.append((host, port))
        sdk = LowSDK()
        held.append(sdk)
        return sdk

    with pytest.raises(Exception, match="battery"):
        run_story(
            tmp_path / "low",
            scenario="halt",
            dog="fake",
            drone="real",
            environ=_env(),
            motion_authorized=True,
            drone_sdk_factory=factory,
            drone_frame=_jpeg,
            drone_timing={"settle_s": 0, "hold_s": 0},
        )
    assert seen
    assert held
    assert "takeoff" not in held[0].sent


def test_preflight_fake_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--preflight", "--output-dir", str(tmp_path / "pre")])
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "PASS" in captured.out
    assert "FAIL" not in captured.out
    assert "sha256" in captured.out
    saved = json.loads((tmp_path / "pre" / "preflight.json").read_text(encoding="utf-8"))
    assert saved["motion_sent"] is False
    assert saved["ok"] is True


def test_preflight_real_is_read_only(tmp_path: Path) -> None:
    conns: list[FakeConn] = []
    sdks: list[FakeSDK] = []
    code, table = run_preflight(
        tmp_path / "pre",
        dog="real",
        drone="real",
        grok="real",
        environ=_env(XAI_API_KEY="super-secret-value"),
        dog_conn_factory=_dog_factory(conns),
        drone_sdk_factory=_drone_factory(sdks, []),
        frames={"dog": _jpeg(), "drone": _jpeg()},
    )
    assert code == 0, table
    assert "FAIL" not in table
    assert "super-secret-value" not in table
    assert HOST not in table
    assert DRONE_HOST not in table
    assert "sha256" in table
    digest = hashlib.sha256(_jpeg()).hexdigest()
    assert digest in table
    assert conns and sdks
    assert 1004 not in conns[0].apis()
    assert 1008 not in conns[0].apis()
    assert 1003 not in conns[0].apis()
    assert "takeoff" not in sdks[0].sent
    assert "land" not in sdks[0].sent
    assert "emergency" not in sdks[0].sent
    blob = (tmp_path / "pre" / "preflight.json").read_text(encoding="utf-8")
    assert "super-secret-value" not in blob
    assert HOST not in blob


def test_preflight_names_a_missing_key(tmp_path: Path) -> None:
    code, table = run_preflight(
        tmp_path / "pre",
        dog="fake",
        drone="fake",
        grok="real",
        environ={},
    )
    assert code == 2
    assert "XAI_API_KEY is unset" in table


def test_open_drone_does_not_import_the_vendor_sdk(tmp_path: Path) -> None:
    import sys

    sys.modules.pop("djitellopy", None)
    sys.modules.pop("unitree_webrtc_connect", None)
    peer = open_dog(
        "real",
        tmp_path / "dog",
        _env(),
        None,
        conn_factory=_dog_factory([]),
    )
    assert peer.dog._fence_r == 1.5
    assert peer.dog._max_speed == 0.25
    assert peer.dog._max_route_s == 8.0
    assert "unitree_webrtc_connect" not in sys.modules
    assert "djitellopy" not in sys.modules
