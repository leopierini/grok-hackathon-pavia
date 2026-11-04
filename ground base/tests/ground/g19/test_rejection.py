"""Rejections, dispatch gating, and the absence of a dog command."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g19.support import (
    beacon_of,
    calls_of,
    feature,
    fixture,
    observation,
    payload,
    request,
    run,
)


def test_bssid_mismatch_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        result = await port.execute(request(payload(armed_bssid="02:00:00:00:00:02")))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.recovery_required is False
        assert "BSSID" in result.error.detail
        assert result.data["dog_motion_allowed"] is False
        assert result.data["reason"] == "bssid_mismatch"
        assert calls_of(built) == []
        assert "dog_command" not in result.data

    run(body)


def test_bssid_comparison_ignores_hex_case(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = observation()
        beacon_of(message)["bssid"] = "02:00:00:00:00:0A"
        result = await port.execute(
            request(
                payload(
                    observation=message,
                    armed_bssid="02:00:00:00:00:0a",
                    windows=[
                        {
                            "window_id": "pi-window-1",
                            "beacon_epoch": 3,
                            "bssid": "02:00:00:00:00:0A",
                        }
                    ],
                )
            )
        )
        assert result.status == "ok"
        assert result.data["dog_motion_allowed"] is True
        assert result.data["bssid"] == "02:00:00:00:00:0a"

    run(body)


def test_ssid_difference_does_not_reject_a_matching_bssid(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = observation()
        beacon_of(message)["ssid"] = "TELLO-OTHER"
        result = await port.execute(request(payload(observation=message)))
        assert result.data["dog_motion_allowed"] is True

    run(body)


def test_string_booleans_and_bool_epochs_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        running = await port.execute(request(payload(drone_command_running="false")))
        assert running.status == "blocked"
        assert running.error is not None
        assert running.error.code == "invalid_input"
        assert "boolean" in running.error.detail
        message = observation()
        beacon_of(message)["beacon_epoch"] = True
        epoch = await port.execute(request(payload(observation=message)))
        assert epoch.status == "blocked"
        assert epoch.error is not None
        assert epoch.error.code == "invalid_input"
        labeled = observation()
        beacon_of(labeled)["hold_state"] = "STABLE"
        hold = await port.execute(request(payload(observation=labeled)))
        assert hold.error is not None
        assert hold.error.code == "invalid_input"

    run(body)


def test_inverted_hold_window_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = observation()
        beacon = beacon_of(message)
        beacon["verified_at"] = "2026-11-04T13:00:12.000Z"
        beacon["hold_valid_until"] = "2026-11-04T13:00:10.000Z"
        result = await port.execute(request(payload(observation=message)))
        assert result.status == "blocked"
        assert result.error is not None
        assert "hold window" in result.error.detail

    run(body)


def test_missing_armed_bssid_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        body_payload = payload()
        del body_payload["armed_bssid"]
        result = await port.execute(request(body_payload))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert result.data["dog_motion_allowed"] is False

    run(body)


def test_dog_motion_action_is_not_a_drone_command(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        command = fixture("ground-to-drone-command.json")
        inner = command["payload"]
        assert isinstance(inner, dict)
        inner["action"] = "move_local"
        result = await port.execute(
            request(payload(drone_command=command, drone_command_status="completed"))
        )
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert calls_of(built) == []
        assert result.events[0].payload["dog_motion_allowed"] is False

    run(body)


def test_dispatch_example_is_legal_only_while_the_hold_allows_motion(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        dispatched = fixture("event-dog_dispatched.json")
        inner = dispatched["payload"]
        assert isinstance(inner, dict)
        assert inner["event"] == "dog_dispatched"
        allowed = await port.execute(request(payload()))
        message = observation()
        beacon_of(message)["hold_state"] = "moving"
        blocked = await port.execute(request(payload(observation=message)))
        assert allowed.data["dispatch_allowed"] is True
        assert blocked.data["dispatch_allowed"] is False
        assert allowed.events[0].payload["event"] == "beacon_hold"
        assert "dog_dispatched" not in allowed.events[0].payload.values()

    run(body)


def test_active_command_without_a_description_blocks(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = observation()
        inner = message["payload"]
        assert isinstance(inner, dict)
        inner["active_command_id"] = "cmd-drone-001"
        result = await port.execute(request(payload(observation=message)))
        assert result.data["dog_motion_allowed"] is False
        assert result.data["hold_state"] == "unknown"
        assert result.data["reason"] == "command_unspecified"

    run(body)


def test_explicit_not_running_overrides_a_stale_active_id(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = observation()
        inner = message["payload"]
        assert isinstance(inner, dict)
        inner["active_command_id"] = "cmd-drone-001"
        body_payload = payload(observation=message, drone_command_running=False)
        result = await port.execute(request(body_payload))
        assert result.data["dog_motion_allowed"] is True

    run(body)


def test_contradictory_running_flag_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(
                payload(
                    drone_command=fixture("ground-to-drone-command.json"),
                    drone_command_status="completed",
                    drone_command_running=True,
                )
            )
        )
        assert result.status == "blocked"
        assert result.error is not None
        assert "not running" in result.error.detail

    run(body)


def test_unknown_request_key_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        body_payload = payload()
        body_payload["dog_command"] = {"action": "move_local"}
        result = await port.execute(request(body_payload))
        assert result.status == "blocked"
        assert result.error is not None
        assert "unknown beacon input" in result.error.detail

    run(body)


def test_running_land_blocks_without_advancing_the_epoch(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        command = fixture("ground-to-drone-command.json")
        inner = command["payload"]
        assert isinstance(inner, dict)
        inner["action"] = "land"
        result = await port.execute(
            request(
                payload(
                    drone_command=command,
                    drone_command_status="running",
                    previous_beacon_epoch=3,
                )
            )
        )
        assert result.data["dog_motion_allowed"] is False
        assert result.data["hold_state"] == "unknown"
        assert result.data["reason"] == "aircraft_transition"
        assert result.data["epoch_required"] is None
        assert result.data["beacon_epoch"] == 3

    run(body)
