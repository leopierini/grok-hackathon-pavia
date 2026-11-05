"""Museum simulation: Ground authorizes, fakes move, Grok does not."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from patrol.ground.museum.__main__ import main
from patrol.ground.museum.peers import ConfigError, open_dog, open_drone
from patrol.ground.museum.policy import MuseumPolicy
from patrol.ground.museum.runner import SCENARIOS, run_story
from patrol.ground.museum.vision import build_request, scripted_decision


def test_fake_scenarios_match_the_story(tmp_path: Path) -> None:
    for scenario in SCENARIOS:
        report = run_story(tmp_path / scenario, scenario=scenario, environ={})
        assert report.ok, (scenario, report.detail, report.rejections, report.timeline)
        assert report.grok == "fake"
        assert "inspect" in report.drone_trace
        assert report.patrol_frame


def test_grok_decision_does_not_move_the_dog(tmp_path: Path) -> None:
    peer = open_dog("fake", tmp_path / "dog", {}, None)

    async def body() -> None:
        await peer.connect()
        request = build_request(
            stage="dog_approach",
            sent_at="2026-11-04T13:00:10.100Z",
            expires_at="2026-11-04T13:00:15.100Z",
            track_id="target-001",
            seq=1,
        )
        decision = scripted_decision(request, "person_visible", "2026-11-04T13:00:10.200Z")
        applied = await peer.apply(decision)
        assert applied is False
        assert peer.spoken == []
        assert peer.effects == []
        move = {
            "source": "ground",
            "destination": "dog",
            "kind": "dog.command",
            "payload": {"action": "move_local", "text": "go away"},
        }
        assert await peer.apply(move) is False
        assert peer.spoken == []
        floor = {
            "source": "ground",
            "destination": "drone",
            "kind": "drone.command",
            "payload": {"action": "land"},
        }
        drone = open_drone("fake", tmp_path / "drone", {}, None)
        await drone.patrol()
        assert await drone.apply(floor) is False
        assert drone.effects == []

    asyncio.run(body())


def test_ground_rejects_messages_outside_the_contract() -> None:
    policy = MuseumPolicy()
    policy.arm()
    policy.bind_track("target-001")
    gallop = {
        "protocol_version": "2.0-draft",
        "message_id": "msg-gallop",
        "mission_id": "demo-20261104-001",
        "epoch": 1,
        "seq": 1,
        "sent_at": "2026-11-04T13:00:10.400Z",
        "source": "ground",
        "destination": "dog",
        "kind": "dog.command",
        "correlation_id": None,
        "expires_at": "2026-11-04T13:00:15.400Z",
        "simulated": True,
        "payload": {
            "command_id": "cmd-gallop",
            "proposal_id": None,
            "action": "gallop",
            "lease_ms": 500,
            "motion": None,
            "track_id": "target-001",
            "beacon_epoch": None,
            "safety_snapshot_id": "safety-presence-001",
            "reason": "not a contract action",
        },
    }
    assert policy.rejection_of(gallop) is not None

    request = build_request(
        stage="dog_approach",
        sent_at="2026-11-04T13:00:10.100Z",
        expires_at="2026-11-04T13:00:15.100Z",
        track_id="target-001",
        seq=1,
    )
    decision = scripted_decision(request, "person_visible", "2026-11-04T13:00:10.200Z")
    payload = decision["payload"]
    assert isinstance(payload, dict)
    payload["reason"] = "takeoff"
    assert policy.authorize_presence(decision, request, "2026-11-04T13:00:10.200Z") == []
    assert any("sdk" in item for item in policy.rejections)

    approach = {
        "protocol_version": "2.0-draft",
        "message_id": "msg-approach",
        "mission_id": "demo-20261104-001",
        "epoch": 1,
        "seq": 1,
        "sent_at": "2026-11-04T13:00:10.400Z",
        "source": "vision",
        "destination": "ground",
        "kind": "motion.proposal",
        "correlation_id": None,
        "expires_at": "2026-11-04T13:00:15.400Z",
        "simulated": True,
        "payload": {
            "proposal_id": "proposal-approach",
            "target_component": "dog",
            "action": "approach",
            "direction_hint": "center",
            "track_id": "target-001",
            "evidence_frame_id": "dog-front-001",
            "candidate_id": None,
            "beacon_epoch": None,
            "reason": "Image-space approach. Not a gait command.",
            "sdk": "Move",
        },
    }
    assert policy.rejection_of(approach) is not None
    assert policy.seal_proposal(approach, "2026-11-04T13:00:10.400Z") is None


def test_uncertain_and_timeout_add_no_motion(tmp_path: Path) -> None:
    for scenario in ("uncertain", "timeout"):
        report = run_story(tmp_path / scenario, scenario=scenario, environ={})
        assert report.ok, report.detail
        assert [item["action"] for item in report.delivered] == ["hover", "follow"]
        assert report.spoken == []


def test_real_peers_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATROL_DOG_HOST", raising=False)
    monkeypatch.delenv("PATROL_DOG_PORT", raising=False)
    monkeypatch.delenv("PATROL_DRONE_HOST", raising=False)
    monkeypatch.delenv("PATROL_DRONE_PORT", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="PATROL_DOG_HOST"):
        open_dog("real", tmp_path / "dog", {}, None)
    with pytest.raises(ConfigError, match="PATROL_DRONE_HOST"):
        open_drone("real", tmp_path / "drone", {}, None)
    dog_real = main(
        ["--dog", "real", "--drone", "fake", "--grok", "fake", "--scenario", "happy_path"]
    )
    assert dog_real == 2
    assert main(["--dog", "fake", "--drone", "real", "--grok", "fake", "--scenario", "halt"]) == 2
    configured = {"PATROL_DOG_HOST": "192.0.2.10", "PATROL_DOG_PORT": "9"}
    peer = open_dog("real", tmp_path / "dog-set", configured, None, conn_factory=lambda _ip: None)
    assert peer.real is True
    assert peer.dog._connected is False
    assert peer.endpoint_port == 9
    file_peer = open_dog(
        "real",
        tmp_path / "dog-file",
        {},
        {"dog": {"host": "192.0.2.10", "port": 9}},
        conn_factory=lambda _ip: None,
    )
    assert file_peer.endpoint_port == 9
    with pytest.raises(ConfigError, match="i-understand-this-moves-hardware"):
        run_story(
            tmp_path / "needs-flag",
            scenario="halt",
            dog="real",
            environ=configured,
        )
    code = main(
        ["--dog", "fake", "--drone", "fake", "--grok", "real", "--scenario", "happy_path"]
    )
    assert code == 2


def test_fake_run_does_not_record_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "super-secret-value")
    report = run_story(
        tmp_path / "happy",
        scenario="happy_path",
        environ={"XAI_API_KEY": "super-secret-value"},
    )
    assert report.ok, report.detail
    blob = json.dumps(report.as_dict())
    assert "super-secret-value" not in blob


def test_cli_all_fake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    code = main(
        [
            "--dog",
            "fake",
            "--drone",
            "fake",
            "--grok",
            "fake",
            "--scenario",
            "all",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "happy_path" in captured.out
    assert "super-secret" not in captured.out
    assert (tmp_path / "out" / "halt" / "report.json").is_file()
