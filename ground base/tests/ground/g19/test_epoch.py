"""Beacon epoch advance, retained windows, and hover."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g19.support import beacon_of, data_of, feature, fixture, payload, request, run


def _command() -> dict[str, object]:
    return fixture("ground-to-drone-command.json")


def _hover() -> dict[str, object]:
    return fixture("ground-to-drone-hover.json")


def _windows() -> list[dict[str, object]]:
    return [
        {
            "window_id": "pi-window-old",
            "beacon_epoch": 3,
            "bssid": "02:00:00:00:00:01",
            "rssi_dbm": -62,
        },
        {
            "window_id": "pi-window-new",
            "beacon_epoch": 4,
            "bssid": "02:00:00:00:00:01",
            "rssi_dbm": -40,
        },
    ]


def test_completed_track_makes_the_old_epoch_unusable(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(
                payload(
                    drone_command=_command(),
                    drone_command_status="completed",
                    drone_command_running=False,
                    previous_beacon_epoch=3,
                    windows=_windows(),
                )
            )
        )
        found = data_of(result)
        assert found["dog_motion_allowed"] is False
        assert found["comparisons_allowed"] is False
        assert found["reason"] == "epoch_pending"
        assert found["beacon_epoch"] == 3
        assert found["epoch_required"] == 4
        assert found["comparable_epoch"] is None
        windows = found["windows"]
        assert isinstance(windows, tuple)
        assert len(windows) == 2
        assert windows[0]["label"] == "invalid"
        assert windows[0]["retained"] is True
        assert windows[0]["comparable"] is False
        assert windows[1]["label"] == "withheld"
        assert windows[1]["retained"] is True
        assert result.events[0].payload["command_id"] == "cmd-drone-001"
        assert result.events[0].payload["beacon_epoch"] == 3

    run(body)


def test_next_epoch_allows_comparison_again(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = fixture("drone-observation.json")
        beacon_of(message)["beacon_epoch"] = 4
        result = await port.execute(
            request(
                payload(
                    observation=message,
                    drone_command=_command(),
                    drone_command_status="completed",
                    drone_command_running=False,
                    previous_beacon_epoch=3,
                    windows=_windows(),
                )
            )
        )
        found = data_of(result)
        assert found["dog_motion_allowed"] is True
        assert found["comparisons_allowed"] is True
        assert found["beacon_epoch"] == 4
        assert found["comparable_epoch"] == 4
        assert found["prior_epoch"] == 3
        assert found["epoch_required"] is None
        windows = found["windows"]
        assert isinstance(windows, tuple)
        assert windows[0]["window_id"] == "pi-window-old"
        assert windows[0]["label"] == "invalid"
        assert windows[0]["retained"] is True
        assert windows[1]["label"] == "current"
        assert windows[1]["comparable"] is True

    run(body)


def test_same_epoch_after_reposition_stays_blocked(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        first = await port.execute(
            request(
                payload(
                    drone_command=_command(),
                    drone_command_status="completed",
                    previous_beacon_epoch=3,
                )
            )
        )
        second = await port.execute(
            request(
                payload(
                    drone_command=_command(),
                    drone_command_status="completed",
                    previous_beacon_epoch=3,
                )
            )
        )
        assert first.data == second.data
        assert second.data["epoch_required"] == 4
        assert second.data["dog_motion_allowed"] is False

    run(body)


def test_hover_without_motion_keeps_the_epoch(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(
                payload(
                    drone_command=_hover(),
                    drone_command_status="completed",
                    drone_command_running=False,
                    previous_beacon_epoch=3,
                    beacon_moved=False,
                )
            )
        )
        found = data_of(result)
        assert found["dog_motion_allowed"] is True
        assert found["beacon_epoch"] == 3
        assert found["commanded_epoch"] == 4
        assert found["epoch_required"] is None
        assert found["comparable_epoch"] == 3
        assert found["reason"] == "stable_hold"

    run(body)


def test_hover_that_the_fixture_says_moved_requires_a_new_epoch(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(
                payload(
                    drone_command=_hover(),
                    drone_command_status="completed",
                    previous_beacon_epoch=3,
                    beacon_moved=True,
                )
            )
        )
        assert result.data["dog_motion_allowed"] is False
        assert result.data["reason"] == "epoch_pending"
        assert result.data["epoch_required"] == 4

    run(body)


def test_running_hover_does_not_force_moving(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(
                payload(
                    drone_command=_hover(),
                    drone_command_status="running",
                    drone_command_running=True,
                    beacon_moved=False,
                    previous_beacon_epoch=3,
                )
            )
        )
        assert result.data["hold_state"] == "stable"
        assert result.data["dog_motion_allowed"] is True
        assert result.data["beacon_epoch"] == 3

    run(body)


def test_lower_epoch_than_required_stays_incomparable(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        message = fixture("drone-observation.json")
        beacon_of(message)["beacon_epoch"] = 2
        result = await port.execute(
            request(
                payload(
                    observation=message,
                    drone_command=_command(),
                    drone_command_status="completed",
                    previous_beacon_epoch=3,
                    windows=[
                        {
                            "window_id": "pi-window-older",
                            "beacon_epoch": 2,
                            "bssid": "02:00:00:00:00:01",
                        }
                    ],
                )
            )
        )
        assert result.data["dog_motion_allowed"] is False
        windows = result.data["windows"]
        assert isinstance(windows, tuple)
        assert windows[0]["label"] == "invalid"
        assert windows[0]["retained"] is True

    run(body)
