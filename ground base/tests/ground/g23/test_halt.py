"""Halt uses the dog.command schema and still goes out when motion is blocked."""

from __future__ import annotations

import json
from pathlib import Path

from tests.ground.g23.support import (
    approve,
    calls_of,
    command_of,
    fixture,
    move_payload,
    opened,
    payload_of,
    run,
)


def _halt_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "issue_halt": True,
        "halt_latched": True,
        "track_id": "target-001",
        "beacon_epoch": 3,
        "safety_snapshot_id": "safety-stop-001",
        "lease_ms": 500,
        "simulated": True,
        "mission_id": "demo-20261104-001",
        "epoch": 1,
    }
    payload.update(overrides)
    return payload


def test_halt_matches_the_example_schema(tmp_path: Path) -> None:
    async def body() -> None:
        services, feature = opened(tmp_path)
        result = await approve(feature, _halt_payload())
        command = command_of(result)
        example = fixture("halt-example.json")
        body_payload = payload_of(command)
        example_payload = payload_of(example)
        assert set(command) == set(example)
        assert set(body_payload) == set(example_payload)
        assert command["kind"] == "dog.command"
        assert command["correlation_id"] is None
        assert command["source"] == "ground"
        assert command["destination"] == "dog"
        assert body_payload["action"] == "halt"
        assert body_payload["motion"] is None
        assert body_payload["proposal_id"] is None
        assert body_payload["lease_ms"] == 500
        assert body_payload["track_id"] == "target-001"
        assert body_payload["beacon_epoch"] == 3
        assert body_payload["safety_snapshot_id"] == "safety-stop-001"
        reason = body_payload["reason"]
        assert isinstance(reason, str)
        assert "not a lie-down" in reason
        assert "recheck" in reason
        assert "altitude" not in json.dumps(command)
        assert result.events[0].kind == "halt_requested"
        assert calls_of(services) == []

    run(body)


def test_halt_is_emitted_when_ordinary_motion_is_blocked(tmp_path: Path) -> None:
    async def body() -> None:
        services, feature = opened(tmp_path)
        readiness = fixture("readiness.json")
        readiness["standing"] = None
        readiness["avoidance_enabled"] = None
        command = command_of(
            await approve(
                feature,
                _halt_payload(
                    readiness=readiness,
                    candidate_id="candidate-missing",
                ),
            )
        )
        assert payload_of(command)["action"] == "halt"
        assert calls_of(services) == []

    run(body)


def test_halt_replay_keeps_one_command_id(tmp_path: Path) -> None:
    async def body() -> None:
        services, feature = opened(tmp_path)
        first = await approve(feature, _halt_payload())
        second = await approve(feature, _halt_payload())
        assert command_of(first)["payload"]
        assert payload_of(command_of(first))["command_id"] == "cmd-dog-halt-001"
        assert payload_of(command_of(second))["command_id"] == "cmd-dog-halt-001"
        assert second.data["replayed"] is True
        assert second.events == ()
        assert len(first.events) == 1
        assert calls_of(services) == []

    run(body)


def test_latched_halt_refuses_a_move(tmp_path: Path) -> None:
    async def body() -> None:
        services, feature = opened(tmp_path)
        result = await approve(feature, move_payload(halt_latched=True))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.detail == "ordinary motion is refused while halt is latched"
        assert "command" not in result.data
        assert calls_of(services) == []

    run(body)
