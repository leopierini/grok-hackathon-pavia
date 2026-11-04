"""The same selection returns the original command id and does not call the dog."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g23.support import (
    approve,
    calls_of,
    command_of,
    move_payload,
    opened,
    payload_of,
    run,
)


def test_replay_returns_the_same_command_id(tmp_path: Path) -> None:
    async def body() -> None:
        services, feature = opened(tmp_path)
        payload = move_payload()
        first = await approve(feature, payload)
        second = await approve(feature, payload)
        first_command = command_of(first)
        second_command = command_of(second)
        assert payload_of(first_command)["command_id"] == "cmd-dog-001"
        assert payload_of(second_command)["command_id"] == "cmd-dog-001"
        assert first_command["message_id"] == second_command["message_id"]
        assert second.data["replayed"] is True
        assert second.events == ()
        assert len(first.events) == 1
        assert calls_of(services) == []
        other = move_payload(selection={
            "selection_id": "sel-other",
            "action": "move_local",
            "candidate_id": "candidate-forward-01",
            "track_id": "target-001",
            "beacon_epoch": 3,
            "safety_snapshot_id": "safety-001",
            "lease_ms": 300,
            "duration_ms": 300,
            "linear_x_m_s": 0.1,
            "linear_y_m_s": 0.0,
            "angular_z_rad_s": 0.0,
        })
        del other["proposal"]
        third = command_of(await approve(feature, other))
        assert payload_of(third)["command_id"] == "cmd-dog-002"
        assert calls_of(services) == []

    run(body)


def test_raw_proposal_is_not_the_emitted_command(tmp_path: Path) -> None:
    async def body() -> None:
        _services, feature = opened(tmp_path)
        payload = move_payload()
        proposal = payload["proposal"]
        command = command_of(await approve(feature, payload))
        assert command != proposal
        assert command["kind"] == "dog.command"
        assert isinstance(proposal, dict)
        assert proposal["kind"] == "motion.proposal"
        assert "evidence_frame_id" not in payload_of(command)

    run(body)
