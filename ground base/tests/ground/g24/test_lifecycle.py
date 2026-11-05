"""Lifecycle of the contract dog acknowledgements."""

from __future__ import annotations

from patrol.ground.extensions.g24.implementation import DogAckFeature
from patrol.ground.kernel.contracts import BaseServices, GroundEvent
from tests.ground.g24.conftest import (
    calls_of,
    command,
    execute,
    expired_command,
    halt_command,
    load,
    run,
)


def test_success_sequence_reaches_verified_stop() -> None:
    async def body(opened: tuple[BaseServices, DogAckFeature]) -> None:
        services, feature = opened
        accepted = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-accepted.json")},
        )
        running = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-running.json")},
        )
        completed = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-completed.json")},
        )
        assert accepted.status == "ok"
        assert accepted.data["stopped"] is False
        assert accepted.data["state"] == "accepted"
        assert accepted.data["block_next_step"] is True
        assert running.data["state"] == "running"
        assert running.data["stopped"] is False
        assert running.data["block_next_step"] is True
        assert running.data["motion_occurred"] is True
        assert completed.status == "ok"
        assert completed.data["stopped"] is True
        assert completed.data["verified"] is True
        assert completed.data["observed_motion"] == "stationary"
        assert completed.data["active_command"] is False
        assert completed.data["stop_cause"] == "verified_stationary"
        assert completed.data["demo_goal_reached"] is False
        assert completed.data["target_arrival"] is False
        assert _no_command(completed)
        assert [item.kind for item in completed.events] == ["operation_completed"]
        assert _correlation(completed.events[0]) == "msg-ground-to-dog-command"
        assert calls_of(services) == []

    run(lambda: body(_open()))


def test_accepted_and_unverified_are_not_stopped() -> None:
    async def body(feature: DogAckFeature) -> None:
        accepted = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-accepted.json")},
        )
        unverified = load("dog-ack-completed.json")
        payload = unverified["payload"]
        assert isinstance(payload, dict)
        payload["verified"] = False
        unverified["message_id"] = "msg-dog-ack-completed-unverified"
        completed = await execute(feature, "track", {"command": command(), "ack": unverified})
        assert accepted.data["stopped"] is False
        assert completed.status == "ok"
        assert completed.data["state"] == "completed"
        assert completed.data["stopped"] is False
        assert completed.data["stop_cause"] == "unverified"
        assert completed.data["active_command"] is True
        assert _no_command(completed)

    run(lambda: body(_feature()))


def test_expired_rejection_records_no_motion() -> None:
    async def body(feature: DogAckFeature) -> None:
        result = await execute(
            feature,
            "track",
            {"command": expired_command(), "ack": load("dog-command-rejected.json")},
        )
        assert result.status == "ok"
        assert result.data["state"] == "rejected"
        assert result.data["reason_code"] == "expired_command"
        assert result.data["motion_occurred"] is False
        assert result.data["active_command"] is False
        assert result.data["stopped"] is False
        assert result.data["observed_motion"] == "stationary"
        assert _no_command(result)

    run(lambda: body(_feature()))


def test_timeout_queries_without_a_new_command() -> None:
    async def body(opened: tuple[BaseServices, DogAckFeature]) -> None:
        services, feature = opened
        early = await execute(feature, "timeout", {"command": command()})
        assert early.data["timed_out"] is False
        assert early.data["query_command"] is None
        clock = services.kernel.clock
        assert hasattr(clock, "advance")
        clock.advance(0.3)
        result = await execute(feature, "timeout", {"command": command()})
        again = await execute(feature, "timeout", {"command": command()})
        assert result.status == "ok"
        assert result.data["query_command"] == "cmd-dog-001"
        assert result.data["timed_out"] is True
        assert result.data["state"] == "pending"
        assert result.data["motion_occurred"] is False
        assert result.data["stopped"] is False
        assert _no_command(result)
        assert "cmd-dog-002" not in str(result.data)
        assert again.data["idempotent"] is True
        assert again.events == ()
        assert calls_of(services) == []

    run(lambda: body(_open()))


def test_halt_ack_leaves_the_move_incomplete() -> None:
    async def body(feature: DogAckFeature) -> None:
        await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-accepted.json")},
        )
        await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-running.json")},
        )
        halt = halt_command()
        ack = {
            "protocol_version": "2.0-draft",
            "message_id": "msg-dog-ack-halt-completed",
            "mission_id": halt["mission_id"],
            "epoch": 1,
            "seq": 8,
            "sent_at": "2026-11-04T13:00:11.200Z",
            "source": "dog",
            "destination": "ground",
            "kind": "command.ack",
            "correlation_id": halt["message_id"],
            "expires_at": None,
            "simulated": True,
            "payload": {
                "command_id": "cmd-dog-halt-001",
                "state": "completed",
                "reason_code": "ok",
                "observed_at": "2026-11-04T13:00:11.200Z",
                "verified": True,
                "observed_motion": "stationary",
                "detail": "Halt settled. The earlier move is not complete.",
            },
        }
        result = await execute(feature, "track", {"command": halt, "ack": ack})
        move = feature.tracker.view("cmd-dog-001")
        assert move is not None
        assert move["state"] == "running"
        assert move["stopped"] is False
        assert result.data["command_id"] == "cmd-dog-halt-001"
        assert result.data["state"] == "completed"
        assert result.data["stopped"] is True
        assert result.data["halt_cleared"] is False
        assert result.data["block_next_step"] is True
        assert result.data["demo_goal_reached"] is False
        assert _no_command(result)

    run(lambda: body(_feature()))


def test_replay_of_the_final_ack_adds_no_event() -> None:
    async def body(feature: DogAckFeature) -> None:
        await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-accepted.json")},
        )
        await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-running.json")},
        )
        first = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-completed.json")},
        )
        replay = await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-completed.json")},
        )
        assert len(first.events) == 1
        assert first.data["terminal_events"] == 1
        assert replay.status == "ok"
        assert replay.events == ()
        assert replay.data["idempotent"] is True
        assert replay.data["event_count"] == 3
        assert replay.data["terminal_events"] == 1
        assert replay.data["stopped"] is True

    run(lambda: body(_feature()))


def test_conflicting_terminal_acks_fault() -> None:
    async def body(feature: DogAckFeature) -> None:
        await execute(
            feature,
            "track",
            {"command": command(), "ack": load("dog-ack-completed.json")},
        )
        failed = load("dog-ack-completed.json")
        failed["message_id"] = "msg-dog-ack-failed"
        failed["seq"] = 8
        payload = failed["payload"]
        assert isinstance(payload, dict)
        payload["state"] = "failed"
        payload["reason_code"] = "execution_failed"
        payload["verified"] = False
        result = await execute(feature, "track", {"command": command(), "ack": failed})
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "unsafe_state"
        assert result.error.recovery_required is True
        assert result.data["faulted"] is True
        assert result.data["stopped"] is False
        assert result.data["block_next_step"] is True
        assert result.data["halt_cleared"] is False
        assert _no_command(result)
        assert result.events[0].kind == "operation_failed"

    run(lambda: body(_feature()))


def _open() -> tuple[BaseServices, DogAckFeature]:
    import tempfile
    from pathlib import Path

    root = Path(tempfile.mkdtemp(prefix="ground-g24-"))
    services = __import__(
        "patrol.ground.testing.builders",
        fromlist=["build_test_services"],
    ).build_test_services(output_dir=root)
    feature = __import__(
        "patrol.ground.extensions.g24.implementation",
        fromlist=["create"],
    ).create(services)
    assert isinstance(feature, DogAckFeature)
    return services, feature


def _feature() -> DogAckFeature:
    return _open()[1]


def _no_command(result: object) -> bool:
    data = getattr(result, "data", None)
    if not isinstance(data, dict) and not hasattr(data, "get"):
        return False
    return (
        data.get("commands_issued") == 0
        and data.get("proposed_command") is None
        and data.get("replacement_command_id") is None
        and data.get("motion_allowed") is False
        and data.get("demo_goal_reached") is False
    )


def _correlation(event: GroundEvent) -> object:
    return event.payload["correlation_id"]
