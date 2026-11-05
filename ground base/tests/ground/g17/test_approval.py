"""Approved drone commands match the contract examples."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g17.samples import (
    armed_context,
    features_of,
    load,
    operator_context,
    payload_of,
)
from tests.ground.g17.support import calls_of, feature, payload, request, run


def test_example_track_matches_the_contract_command(tmp_path: Path) -> None:
    services, port = feature(tmp_path)
    ticket = services.kernel.authority.issue("demo-20261104-001", "drone-command")

    async def body() -> None:
        result = await port.execute(request(armed_context(), ticket))
        example = load("ground-to-drone-command.json")
        assert result.status == "ok"
        assert result.error is None
        assert result.data["command"] == example
        assert result.data["replayed"] is False
        assert result.data["deadline_ms"] == 300
        assert result.events[0].kind == "decision_received"
        assert result.events[0].ticket == ticket
        event = result.events[0].payload
        assert event["command_id"] == "cmd-drone-001"
        assert event["frame_id"] == "drone-downward-001"
        assert event["track_id"] == "target-001"
        assert event["beacon_epoch"] == 4
        assert event["message_id"] == "msg-ground-to-drone-command"
        assert calls_of(services) == []

    run(body)


def test_hover_matches_the_contract_when_tracking_is_blocked(tmp_path: Path) -> None:
    _services, port = feature(tmp_path)
    context = operator_context("hover", "operator-hover-001")
    capabilities = context["capabilities"]
    assert isinstance(capabilities, dict)
    features_of(capabilities)["controlled_motion"] = False

    async def body() -> None:
        result = await port.execute(request(context))
        assert result.status == "ok"
        assert result.data["command"] == load("ground-to-drone-hover.json")
        assert payload(result)["action"] == "hover"

    run(body)


def test_land_keeps_the_example_primitive_and_uses_the_landing_deadline(
    tmp_path: Path,
) -> None:
    _services, port = feature(tmp_path)
    context = operator_context("land", "operator-land-001")
    capabilities = context["capabilities"]
    assert isinstance(capabilities, dict)
    features_of(capabilities)["controlled_motion"] = False

    async def body() -> None:
        result = await port.execute(request(context))
        example = load("ground-to-drone-land.json")
        assert result.status == "ok"
        assert payload(result) == example["payload"]
        assert result.data["lease_ms"] == 500
        assert result.data["deadline_ms"] == 8000
        command = result.data["command"]
        assert isinstance(command, dict)
        assert command["expires_at"] == "2026-11-04T13:00:19.000Z"
        assert command["expires_at"] != example["expires_at"]

    run(body)


def test_replay_returns_the_same_command_id(tmp_path: Path) -> None:
    _services, port = feature(tmp_path)
    context = armed_context()

    async def body() -> None:
        first = await port.execute(request(context))
        poisoned = armed_context()
        proposal = poisoned["proposal"]
        assert isinstance(proposal, dict)
        payload_of(proposal)["reason"] = "send_rc_control 0 0 0 0"
        rejected = await port.execute(request(poisoned))
        assert rejected.status != "ok"
        second = await port.execute(request(armed_context()))
        other = armed_context()
        other_proposal = other["proposal"]
        assert isinstance(other_proposal, dict)
        payload_of(other_proposal)["proposal_id"] = "proposal-drone-002"
        third = await port.execute(request(other))
        assert first.data["command_id"] == "cmd-drone-001"
        assert second.data["command"] == first.data["command"]
        assert second.data["replayed"] is True
        assert third.data["command_id"] != first.data["command_id"]
        assert third.data["replayed"] is False

    run(body)


def test_search_stays_inside_the_seeded_allowlist(tmp_path: Path) -> None:
    _services, port = feature(tmp_path)

    async def body() -> None:
        seen: set[object] = set()
        for seed in range(21):
            context = armed_context()
            proposal = context["proposal"]
            assert isinstance(proposal, dict)
            body_payload = payload_of(proposal)
            body_payload["action"] = "search"
            body_payload["proposal_id"] = f"proposal-search-{seed}"
            context["seed"] = seed
            result = await port.execute(request(context))
            assert result.status == "ok"
            ident = payload(result)["primitive_id"]
            assert ident in {"verified-search-left-v1", "verified-search-right-v1"}
            seen.add(ident)
        assert seen == {"verified-search-left-v1", "verified-search-right-v1"}
        again = armed_context()
        proposal = again["proposal"]
        assert isinstance(proposal, dict)
        payload_of(proposal)["action"] = "search"
        payload_of(proposal)["proposal_id"] = "proposal-search-again"
        again["seed"] = 0
        repeat = await port.execute(request(again))
        assert payload(repeat)["primitive_id"] == "verified-search-right-v1"

    run(body)


def test_agreed_height_is_copied_and_observation_height_is_not(tmp_path: Path) -> None:
    _services, port = feature(tmp_path)
    context = operator_context("takeoff", "operator-takeoff-001")
    observation = context["observation"]
    assert isinstance(observation, dict)
    payload_of(observation)["flight_state"] = "grounded"
    context["requested_height_m"] = 4
    context["height_reference"] = "floor_agl"

    async def body() -> None:
        result = await port.execute(request(context))
        assert result.status == "ok", result.error
        assert payload(result)["requested_height_m"] == 4.0
        assert payload(result)["height_reference"] == "floor_agl"
        assert result.data["deadline_ms"] == 8000
        assert result.data["lease_ms"] == 500
        plain = await port.execute(request(armed_context()))
        assert payload(plain)["requested_height_m"] is None
        assert payload(plain)["height_reference"] == "unknown"

    run(body)
