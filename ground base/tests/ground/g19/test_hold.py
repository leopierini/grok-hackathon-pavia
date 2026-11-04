"""Stable, moving, expired, and unknown holds."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from patrol.ground.extensions.g19.policy import SLOT
from tests.ground.g19.support import (
    HOLD_UNTIL,
    advance_to,
    beacon_of,
    calls_of,
    data_of,
    feature,
    observation,
    payload,
    request,
    run,
)


def test_manifest_names_the_v2_beacon_slot() -> None:
    import json

    from patrol.ground.kernel.paths import repo_root

    text = (repo_root() / "patrol" / "ground" / "extensions" / "g19" / "manifest.json").read_text(
        encoding="utf-8"
    )
    manifest = json.loads(text)
    assert manifest["schema_version"] == "ground-task-v2"
    assert manifest["task_id"] == "GROUND-19"
    assert manifest["slot"] == SLOT


def test_fresh_stable_hold_allows_dog_motion(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        result = await port.execute(request(payload()))
        found = data_of(result)
        assert result.status == "ok"
        assert result.error is None
        assert found["dog_motion_allowed"] is True
        assert found["dispatch_allowed"] is True
        assert found["hold_state"] == "stable"
        assert found["flight_state"] == "airborne"
        assert found["beacon_epoch"] == 3
        assert found["comparable_epoch"] == 3
        assert found["comparisons_allowed"] is True
        assert calls_of(built) == []
        records = getattr(built.journal, "records", None)
        assert records == []
        assert result.events[0].kind == "state_changed"
        assert result.events[0].payload["event"] == "beacon_hold"
        assert result.events[0].payload["message_id"] == "msg-drone-observation"
        assert result.events[0].payload["mission_id"] == "demo-20261104-001"
        assert result.events[0].payload["frame_id"] == "drone-downward-001"
        assert result.events[0].payload["camera_epoch"] == 1
        assert "rssi_dbm" not in found
        assert "dog_command" not in found

    run(body)


def test_duplicate_stable_hold_is_idempotent(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        first = await port.execute(request(payload()))
        second = await port.execute(request(payload()))
        assert first.status == second.status
        assert first.data == second.data
        assert first.events[0].payload == second.events[0].payload
        assert second.data["beacon_epoch"] == 3

    run(body)


def test_moving_hold_blocks_the_dog(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = observation()
        beacon_of(message)["hold_state"] = "moving"
        result = await port.execute(request(payload(observation=message)))
        assert result.status == "ok"
        assert result.data["hold_state"] == "moving"
        assert result.data["dog_motion_allowed"] is False
        assert result.data["dispatch_allowed"] is False
        assert result.data["comparisons_allowed"] is False
        assert result.data["reason"] == "moving"

    run(body)


def test_unknown_hold_blocks_the_dog(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = observation()
        beacon_of(message)["hold_state"] = "unknown"
        result = await port.execute(request(payload(observation=message)))
        assert result.data["dog_motion_allowed"] is False
        assert result.data["reason"] == "hold_unknown"
        assert result.data["hold_state"] == "unknown"

    run(body)


def test_expired_hold_blocks_even_when_labeled_stable(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        advance_to(built, HOLD_UNTIL + timedelta(seconds=1))
        result = await port.execute(request(payload()))
        assert result.data["reported_hold_state"] == "stable"
        assert result.data["dog_motion_allowed"] is False
        assert result.data["reason"] == "expired"

    run(body)


def test_hold_is_valid_at_the_exact_deadline(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        advance_to(built, HOLD_UNTIL)
        result = await port.execute(request(payload()))
        assert result.data["dog_motion_allowed"] is True
        assert result.data["reason"] == "stable_hold"

    run(body)


def test_unknown_flight_blocks_a_stable_hold(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(flight_state="unknown")))
        assert result.data["reported_hold_state"] == "stable"
        assert result.data["flight_state"] == "unknown"
        assert result.data["dog_motion_allowed"] is False
        assert result.data["reason"] == "flight_unknown"

    run(body)


def test_grounded_aircraft_blocks_a_stable_hold(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(flight_state="grounded")))
        assert result.data["dog_motion_allowed"] is False
        assert result.data["reason"] == "grounded"

    run(body)


def test_running_track_step_forces_moving(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(
                payload(
                    drone_command=observation_command(),
                    drone_command_status="running",
                    drone_command_running=True,
                    previous_beacon_epoch=3,
                )
            )
        )
        assert result.data["hold_state"] == "moving"
        assert result.data["reported_hold_state"] == "stable"
        assert result.data["dog_motion_allowed"] is False
        assert result.data["reason"] == "running_reposition"
        windows = result.data["windows"]
        assert isinstance(windows, tuple)
        assert windows[0]["label"] == "suspended"
        assert windows[0]["retained"] is True

    run(body)


def test_running_search_step_also_blocks(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        command = observation_command()
        inner = command["payload"]
        assert isinstance(inner, dict)
        inner["action"] = "search_step"
        result = await port.execute(
            request(
                payload(
                    drone_command=command,
                    drone_command_status="accepted",
                    previous_beacon_epoch=3,
                )
            )
        )
        assert result.data["reason"] == "running_reposition"
        assert result.data["dog_motion_allowed"] is False

    run(body)


def test_rssi_values_do_not_change_the_decision(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        loud = payload()
        quiet = payload(
            windows=[
                {
                    "window_id": "pi-window-1",
                    "beacon_epoch": 3,
                    "bssid": "02:00:00:00:00:01",
                    "rssi_dbm": -95,
                }
            ]
        )
        first = await port.execute(request(loud))
        second = await port.execute(request(quiet))
        assert first.data["dog_motion_allowed"] is True
        assert second.data["dog_motion_allowed"] is True
        assert first.data["reason"] == second.data["reason"]
        assert "rssi" not in str(first.data["reason"])

    run(body)


def observation_command() -> dict[str, object]:
    from tests.ground.g19.support import fixture

    return fixture("ground-to-drone-command.json")
