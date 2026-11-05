"""Lease, candidate, avoidance, tether, and altitude failures do not move the dog."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g11.schema_check import load_schema, validate_message
from patrol.ground.extensions.g18.messages import parse_command as parse_drone_command
from patrol.ground.extensions.g24.model import parse_command as parse_dog_command
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


def _readiness(**overrides: object) -> dict[str, object]:
    readiness = fixture("readiness.json")
    readiness.update(overrides)
    return readiness


def _candidates_with(candidate: dict[str, object], *, blocked: bool = False) -> dict[str, object]:
    message = fixture("candidates.json")
    body = message["payload"]
    assert isinstance(body, dict)
    body = dict(body)
    body["candidates"] = [candidate]
    body["blocked"] = blocked
    message = dict(message)
    message["payload"] = body
    return message


async def _rejected(tmp_path: Path, payload: dict[str, object], detail: str) -> None:
    services, feature = opened(tmp_path)
    result = await approve(feature, payload)
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert result.error.detail == detail
    assert calls_of(services) == []


def test_presence_actions_are_not_rewritten_into_a_walk(tmp_path: Path) -> None:
    async def body() -> None:
        for action in ("stop", "play_warning", "follow", "return_home"):
            proposal = fixture("proposal.json")
            body_payload = proposal["payload"]
            assert isinstance(body_payload, dict)
            proposal["payload"] = {**body_payload, "action": action}
            await _rejected(
                tmp_path / action,
                move_payload(proposal=proposal),
                "proposal action is not a dog step",
            )
        services, feature = opened(tmp_path / "approach")
        command = command_of(await approve(feature, move_payload()))
        assert payload_action(command) == "move_local"
        assert calls_of(services) == []

    run(body)


def test_bridge_presence_does_not_require_a_candidate(tmp_path: Path) -> None:
    async def body() -> None:
        schema = load_schema()
        for action in ("approach", "stop", "play_warning", "follow", "return_home"):
            proposal = fixture("proposal.json")
            body_payload = proposal["payload"]
            assert isinstance(body_payload, dict)
            shaped = {
                **body_payload,
                "action": action,
                "candidate_id": None,
                "beacon_epoch": None,
            }
            if action == "play_warning":
                shaped["warning_id"] = "go-away"
                shaped["text"] = "go away"
            if action == "follow":
                shaped["standoff_m"] = 2.0
            proposal["payload"] = shaped
            services, feature = opened(tmp_path / action)
            command = command_of(await approve(feature, move_payload(proposal=proposal)))
            command_body = payload_of(command)
            assert command_body["action"] == action
            assert command_body["action"] != "move_local"
            assert command_body["motion"] is None
            assert command_body["beacon_epoch"] is None
            if action == "play_warning":
                assert command_body["warning_id"] == "go-away"
                assert command_body["text"] == "go away"
            if action == "follow":
                assert command_body["standoff_m"] == 2.0
            validate_message(command, schema)
            parse_dog_command(command)
            assert calls_of(services) == []

    run(body)


def test_land_on_dog_is_a_drone_command(tmp_path: Path) -> None:
    async def body() -> None:
        proposal = fixture("proposal.json")
        body_payload = proposal["payload"]
        assert isinstance(body_payload, dict)
        proposal["payload"] = {
            **body_payload,
            "action": "land_on_dog",
            "target_component": "drone",
            "beacon_epoch": None,
        }
        services, feature = opened(tmp_path)
        command = command_of(await approve(feature, move_payload(proposal=proposal)))
        assert command["kind"] == "drone.command"
        assert command["destination"] == "drone"
        command_body = payload_of(command)
        assert command_body["action"] == "land_on_dog"
        assert command_body["primitive_id"] == "land-on-dog-v1"
        assert command_body["beacon_epoch"] is None
        validate_message(command, load_schema())
        parsed, parsed_body = parse_drone_command(command)
        assert parsed.kind == "drone.command"
        assert parsed_body.action == "land_on_dog"
        assert calls_of(services) == []

    run(body)


def test_unknown_candidate_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        proposal = fixture("proposal.json")
        body_payload = proposal["payload"]
        assert isinstance(body_payload, dict)
        proposal["payload"] = {**body_payload, "candidate_id": "candidate-missing"}
        await _rejected(
            tmp_path,
            move_payload(proposal=proposal),
            "candidate is not in the safe list",
        )

    run(body)


def test_duration_and_lease_over_500_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        await _rejected(
            tmp_path / "duration",
            move_payload(duration_ms=2000),
            "duration_ms exceeds 500",
        )
        await _rejected(tmp_path / "lease", move_payload(lease_ms=2000), "lease_ms exceeds 500")
        services, feature = opened(tmp_path / "cap")
        command = command_of(await approve(feature, move_payload(duration_ms=500, lease_ms=500)))
        motion = command["payload"]
        assert isinstance(motion, dict)
        step = motion["motion"]
        assert isinstance(step, dict)
        assert step["duration_ms"] == 500
        assert motion["lease_ms"] == 500
        assert calls_of(services) == []

    run(body)


def test_avoidance_and_standing_null_or_string_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        await _rejected(
            tmp_path / "avoidance",
            move_payload(readiness=_readiness(avoidance_enabled=None)),
            "avoidance_enabled is not true",
        )
        await _rejected(
            tmp_path / "standing",
            move_payload(readiness=_readiness(standing=None)),
            "standing is not true",
        )
        await _rejected(
            tmp_path / "string",
            move_payload(readiness=_readiness(avoidance_enabled="true", standing="true")),
            "standing is not true",
        )

    run(body)


def test_ethernet_tether_overrun_is_rejected_and_wifi_is_not(tmp_path: Path) -> None:
    async def body() -> None:
        await _rejected(
            tmp_path / "over",
            move_payload(readiness=_readiness(step_distance_m=3.0, tether_budget_m=1.0)),
            "ethernet step exceeds tether budget",
        )
        services, feature = opened(tmp_path / "equal")
        command = command_of(
            await approve(
                feature,
                move_payload(readiness=_readiness(step_distance_m=2.0, tether_budget_m=2.0)),
            )
        )
        assert payload_action(command) == "move_local"
        assert calls_of(services) == []
        _wifi_services, wifi = opened(tmp_path / "wifi")
        wifi_command = command_of(
            await approve(
                wifi,
                move_payload(
                    readiness=_readiness(transport="wifi", step_distance_m=9.0, tether_budget_m=1.0)
                ),
            )
        )
        assert payload_action(wifi_command) == "move_local"

    run(body)


def test_altitude_field_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        await _rejected(tmp_path, move_payload(altitude_m=4), "altitude is not a dog command field")

    run(body)


def test_missing_beacon_rejects_rssi_and_allows_vision(tmp_path: Path) -> None:
    async def body() -> None:
        proposal = fixture("proposal.json")
        body_payload = proposal["payload"]
        assert isinstance(body_payload, dict)
        kept = {key: value for key, value in body_payload.items() if key != "beacon_epoch"}
        proposal["payload"] = kept
        await _rejected(
            tmp_path / "rssi",
            move_payload(proposal=proposal),
            "beacon_epoch is required for an RSSI step",
        )
        services, feature = opened(tmp_path / "vision")
        command = command_of(
            await approve(
                feature,
                move_payload(
                    proposal=proposal,
                    readiness=_readiness(vision_active=True),
                    guidance="vision",
                ),
            )
        )
        body_command = command["payload"]
        assert isinstance(body_command, dict)
        assert body_command["beacon_epoch"] is None
        assert calls_of(services) == []

    run(body)


def test_unsafe_blocked_and_expired_candidates_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        message = fixture("candidates.json")
        listed = message["payload"]
        assert isinstance(listed, dict)
        raw = listed["candidates"]
        assert isinstance(raw, list)
        candidate = dict(raw[0])
        assert isinstance(candidate, dict)
        unsafe = dict(candidate)
        unsafe["safe"] = False
        await _rejected(
            tmp_path / "unsafe",
            move_payload(candidates=_candidates_with(unsafe)),
            "candidate is not safe",
        )
        await _rejected(
            tmp_path / "blocked",
            move_payload(candidates=_candidates_with(candidate, blocked=True)),
            "candidate list is blocked",
        )
        services, feature = opened(tmp_path / "expired")
        clock = services.kernel.clock
        advance = getattr(clock, "advance", None)
        assert callable(advance)
        advance(30_000_000)
        result = await approve(feature, move_payload())
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.detail == "candidate is expired"
        assert calls_of(services) == []

    run(body)


def test_wrong_target_and_bad_frame_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        proposal = fixture("proposal.json")
        body_payload = proposal["payload"]
        assert isinstance(body_payload, dict)
        proposal["payload"] = {**body_payload, "target_component": "drone"}
        await _rejected(
            tmp_path / "target",
            move_payload(proposal=proposal),
            "proposal target_component is not dog",
        )
        message = fixture("candidates.json")
        listed = message["payload"]
        assert isinstance(listed, dict)
        raw = listed["candidates"]
        assert isinstance(raw, list)
        candidate = dict(raw[0])
        assert isinstance(candidate, dict)
        candidate["frame_id"] = "map"
        services, feature = opened(tmp_path / "frame")
        result = await approve(feature, move_payload(candidates=_candidates_with(candidate)))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.detail == "candidate frame is not dog/base_link"
        assert calls_of(services) == []

    run(body)


def test_snapshot_mismatch_and_boolean_lease_are_refused(tmp_path: Path) -> None:
    async def body() -> None:
        selection = fixture("selection.json")
        selection["snapshot_id"] = "nav-other"
        payload = move_payload(selection=selection)
        del payload["proposal"]
        services, feature = opened(tmp_path / "snapshot")
        result = await approve(feature, payload)
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.detail == "snapshot_id does not match the candidate"
        assert calls_of(services) == []
        _services, feature = opened(tmp_path / "lease")
        result = await approve(feature, move_payload(lease_ms=True))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert calls_of(_services) == []

    run(body)


def payload_action(command: dict[str, object]) -> object:
    body = command["payload"]
    assert isinstance(body, dict)
    return body["action"]
