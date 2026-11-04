"""Rejections, holds, and facts that must not be inferred from a dog ack."""

from __future__ import annotations

from patrol.ground.extensions.g24.implementation import DogAckFeature
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import BaseServices
from tests.ground.g24.conftest import command, execute, load, run


def test_foreign_epoch_is_stale_and_does_not_bind() -> None:
    async def body(feature: DogAckFeature) -> None:
        ack = load("dog-ack-accepted.json")
        ack["epoch"] = 9
        stale = await execute(feature, "track", {"command": command(), "ack": ack})
        assert stale.status == "failed"
        assert stale.error is not None
        assert stale.error.code == "epoch_mismatch"
        assert stale.data["bound"] is False
        assert stale.data["motion_occurred"] is False
        fresh = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-accepted.json")},
        )
        assert fresh.status == "ok"
        assert fresh.data["state"] == "accepted"
        assert fresh.data["stopped"] is False

    run(lambda: body(_feature()))


def test_foreign_command_id_is_rejected() -> None:
    async def body(feature: DogAckFeature) -> None:
        ack = load("dog-ack-accepted.json")
        payload = ack["payload"]
        assert isinstance(payload, dict)
        payload["command_id"] = "cmd-dog-999"
        result = await execute(feature, "track", {"command": command(), "ack": ack})
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.detail == "foreign command id"
        assert result.data["bound"] is False
        assert result.data["command_id"] == "cmd-dog-999"
        assert feature.tracker.view("cmd-dog-001") is None

    run(lambda: body(_feature()))


def test_correlation_must_name_the_command_message() -> None:
    async def body(feature: DogAckFeature) -> None:
        ack = load("dog-ack-accepted.json")
        ack["correlation_id"] = "msg-some-other-command"
        result = await execute(feature, "track", {"command": command(), "ack": ack})
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert feature.tracker.records == {}

    run(lambda: body(_feature()))


def test_string_verified_is_rejected() -> None:
    async def body(feature: DogAckFeature) -> None:
        ack = load("dog-ack-completed.json")
        payload = ack["payload"]
        assert isinstance(payload, dict)
        payload["verified"] = "true"
        result = await execute(feature, "track", {"command": command(), "ack": ack})
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert result.error.detail == "verified must be a boolean"
        assert feature.tracker.view("cmd-dog-001") is None

    run(lambda: body(_feature()))


def test_lidar_stop_is_not_target_arrival() -> None:
    async def body(feature: DogAckFeature) -> None:
        ack = load("dog-ack-completed.json")
        payload = ack["payload"]
        assert isinstance(payload, dict)
        payload["reason_code"] = "lidar_stop"
        payload["detail"] = "LiDAR clearance stop. This is not target arrival."
        result = await execute(feature, "track", {"command": command(), "ack": ack})
        assert result.status == "ok"
        assert result.data["stopped"] is True
        assert result.data["stop_cause"] == "lidar"
        assert result.data["target_arrival"] is False
        assert result.data["demo_goal_reached"] is False
        assert result.events[0].payload["target_arrival"] is False

    run(lambda: body(_feature()))


def test_repeated_command_id_does_not_authorize_another_move() -> None:
    async def body(feature: DogAckFeature) -> None:
        await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-completed.json")},
        )
        repeat = command()
        repeat["message_id"] = "msg-ground-to-dog-command-repeat"
        ack = load("dog-ack-accepted.json")
        ack["message_id"] = "msg-dog-ack-repeat"
        ack["correlation_id"] = "msg-ground-to-dog-command-repeat"
        result = await execute(feature, "track", {"command": repeat, "ack": ack})
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.data["repeated_command"] is True
        assert result.data["motion_allowed"] is False
        assert result.data["stopped"] is True
        assert result.data["state"] == "completed"
        assert result.data["commands_issued"] == 0
        assert result.events == ()

    run(lambda: body(_feature()))


def test_readiness_after_the_window_can_remove_a_stop() -> None:
    async def body(opened: tuple[BaseServices, DogAckFeature]) -> None:
        services, feature = opened
        done = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-completed.json")},
        )
        assert done.data["stopped"] is True
        early = await execute(
            feature,
            "readiness",
            {"command": command(), "readiness": {"stationary": False}},
        )
        assert early.data["stopped"] is True
        clock = services.kernel.clock
        assert isinstance(clock, ManualClock)
        clock.advance(0.3)
        disagreed = await execute(
            feature,
            "readiness",
            {
                "command": command(),
                "readiness": {"stationary": False, "observed_after_window": True},
            },
        )
        assert disagreed.status == "ok"
        assert disagreed.data["stopped"] is False
        assert disagreed.data["stop_cause"] == "readiness_disagrees"
        assert disagreed.data["demo_goal_reached"] is False
        assert disagreed.data["commands_issued"] == 0

    run(lambda: body(_open()))


def test_drone_ack_and_bad_snapshot_are_rejected() -> None:
    async def body(feature: DogAckFeature) -> None:
        drone = load("dog-ack-accepted.json")
        drone["source"] = "drone"
        rejected = await execute(feature, "track", {"command": command(), "ack": drone})
        assert rejected.error is not None
        assert rejected.error.code == "invalid_input"
        flagged = await execute(
            feature,
            "track",
            {
                "command": command(),
                "ack": load("dog-ack-accepted.json"),
                "snapshot": {"halt_latched": "true"},
            },
        )
        assert flagged.error is not None
        assert flagged.error.code == "invalid_input"
        assert feature.tracker.view("cmd-dog-001") is None

    run(lambda: body(_feature()))


def test_lower_sequence_does_not_rewrite_a_stop() -> None:
    async def body(feature: DogAckFeature) -> None:
        await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-completed.json")},
        )
        older = load("dog-ack-running.json")
        result = await execute(feature, "track", {"command": command(), "ack": older})
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.detail == "stale sequence"
        assert result.data["stopped"] is True
        assert result.data["state"] == "completed"

    run(lambda: body(_feature()))


def test_cancelled_authority_does_not_accept_an_ack() -> None:
    async def body(opened: tuple[BaseServices, DogAckFeature]) -> None:
        services, feature = opened
        ticket = services.kernel.authority.issue("demo-20261104-001", "dog-ack")
        admitted = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-accepted.json")},
            ticket,
        )
        assert admitted.status == "ok"
        services.kernel.authority.latch_cancel("operator halt")
        blocked = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-running.json")},
            ticket,
        )
        assert blocked.status == "failed"
        assert blocked.error is not None
        assert blocked.error.code == "cancelled"
        assert blocked.error.recovery_required is True
        view = feature.tracker.view("cmd-dog-001")
        assert view is not None
        assert view["state"] == "accepted"
        assert view["halt_cleared"] is False

    run(lambda: body(_open()))


def test_expired_command_that_claims_motion_faults() -> None:
    async def body(feature: DogAckFeature) -> None:
        ack = load("dog-command-rejected.json")
        payload = ack["payload"]
        assert isinstance(payload, dict)
        payload["observed_motion"] = "moving"
        issued = load("expired-dog-command.json")
        result = await execute(feature, "track", {"command": issued, "ack": ack})
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "unsafe_state"
        assert result.data["motion_occurred"] is False
        assert result.data["commands_issued"] == 0

    run(lambda: body(_feature()))


def _open() -> tuple[BaseServices, DogAckFeature]:
    import tempfile
    from pathlib import Path

    from patrol.ground.extensions.g24.implementation import create
    from patrol.ground.testing.builders import build_test_services

    root = Path(tempfile.mkdtemp(prefix="ground-g24-"))
    services = build_test_services(output_dir=root)
    feature = create(services)
    assert isinstance(feature, DogAckFeature)
    return services, feature


def _feature() -> DogAckFeature:
    return _open()[1]
