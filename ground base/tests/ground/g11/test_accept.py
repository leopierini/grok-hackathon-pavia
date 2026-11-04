"""Known-good envelopes round-trip correlation fields and leave adapters idle."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.contract import CONTRACT_VERSION, Frame, Incident
from patrol.ground.kernel import tiny_jpeg_bytes
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings
from tests.ground.g11.support import calls, load, request_for, run, services


def test_v1_robot_contract_is_unchanged() -> None:
    text = (repo_root() / "patrol" / "contract.py").read_text(encoding="utf-8")
    assert CONTRACT_VERSION == "1.0"
    assert "async def run_route" in text
    assert "async def inspect" in text
    assert "class DogPort" in text
    assert "class DronePort" in text


def test_observation_keeps_null_pose_and_correlation(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        result = await run(create_port(built), request_for(load("drone-observation.json")))
        assert result.status == "ok"
        assert result.error is None
        assert result.data["kind"] == "drone.observation"
        assert result.data["pose"] is None
        assert "x_m" not in result.data
        assert result.data["frame_id"] == "drone-downward-001"
        assert result.data["camera_epoch"] == 1
        assert result.data["beacon_epoch"] == 3
        assert result.data["correlation_id"] is None
        assert calls(built) == []

    asyncio.run(body())


def test_dog_command_and_proposal_round_trip(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        port = create_port(built)
        command = await run(port, request_for(load("ground-to-dog-command.json")))
        proposal = await run(port, request_for(load("ai-to-drone-proposal.json")))
        assert command.status == "ok"
        assert command.data["correlation_id"] == "msg-ai-to-dog-proposal"
        assert command.data["track_id"] == "target-001"
        assert command.data["beacon_epoch"] == 3
        assert command.data["map_epoch"] == 1
        assert command.data["command_id"] == "cmd-dog-001"
        assert proposal.status == "ok"
        assert proposal.data["frame_id"] == "drone-downward-001"
        assert proposal.data["track_id"] == "target-001"
        assert proposal.data["correlation_id"] == "msg-drone-vision-decision"
        assert calls(built) == []

    asyncio.run(body())


def test_open_session_epoch_must_match(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        image = tmp_path / "phone.jpg"
        image.write_bytes(tiny_jpeg_bytes())
        frame = Frame(str(image), "phone", "room_2", None, True)
        incident = Incident("demo-20261104-001", "room_2", "a person", frame)
        built.state.open(incident, make_settings())
        port = create_port(built)
        accepted = await run(port, request_for(load("drone-observation.json")))
        stale = load("drone-observation.json")
        stale["message_id"] = "msg-other-epoch"
        stale["epoch"] = 2
        rejected = await run(port, request_for(stale, epoch=1))
        other = load("drone-observation.json")
        other["message_id"] = "msg-other-mission"
        other["mission_id"] = "demo-other"
        foreign = await run(port, request_for(other))
        assert accepted.status == "ok"
        assert foreign.status == "blocked"
        assert foreign.error is not None
        assert foreign.error.detail == "mission_mismatch"
        assert rejected.status == "blocked"
        assert rejected.error is not None
        assert rejected.error.detail == "epoch_mismatch"
        assert calls(built) == []

    asyncio.run(body())


def test_real_shaped_message_without_synthetic_hash_is_parsed(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        message = load("drone-observation.json")
        message["message_id"] = "msg-real-observation"
        message["simulated"] = False
        frame = message["payload"]
        assert isinstance(frame, dict)
        nested = frame["frame"]
        assert isinstance(nested, dict)
        nested["simulated"] = False
        nested["sha256"] = "a" * 64
        result = await run(create_port(built), request_for(message))
        assert result.status == "ok"
        assert result.data["simulated"] is False
        assert calls(built) == []

    asyncio.run(body())


def create_port(built: object) -> object:
    from patrol.ground.extensions.g11.implementation import create
    from patrol.ground.kernel.contracts import BaseServices

    assert isinstance(built, BaseServices)
    return create(built)


def test_fixture_text_is_utf8_json() -> None:
    text = (fixture_path("drone-observation.json")).read_text(encoding="utf-8")
    loaded = json.loads(text)
    assert loaded["protocol_version"] == "2.0-draft"


def fixture_path(name: str) -> Path:
    return repo_root() / "fixtures" / "ground" / "g11" / name
