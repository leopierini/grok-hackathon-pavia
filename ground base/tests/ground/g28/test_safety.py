"""Direct safety checks. They call create() with Task 01 doubles."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from patrol.ground.extensions.g28.implementation import create
from patrol.ground.extensions.g28.messages import accept_command, load_examples
from patrol.ground.kernel.contracts import FeatureRequest
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import build_test_services

ROOT = repo_root() / "fixtures" / "ground" / "g28"


def _run(awaitable: object) -> object:
    if not asyncio.iscoroutine(awaitable):
        raise AssertionError("expected a coroutine")
    return asyncio.run(awaitable)


def _request(name: str, **extra: object) -> FeatureRequest:
    payload: dict[str, object] = {"stimulus": name}
    payload.update(extra)
    return FeatureRequest("guard", name, None, freeze_map(payload))


def _action(result_data: Mapping[str, object], key: str) -> str:
    message = result_data[key]
    assert isinstance(message, Mapping)
    payload = message["payload"]
    assert isinstance(payload, Mapping)
    action = payload["action"]
    assert isinstance(action, str)
    return action


def test_manifest_uses_the_v2_safety_slot() -> None:
    path = ROOT.parents[2] / "patrol" / "ground" / "extensions" / "g28" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": "ground-task-v2",
        "task_id": "GROUND-28",
        "slot": "feature.v2_safety",
        "factory": "patrol.ground.extensions.g28.implementation:create",
        "scenario_factory": "patrol.ground.extensions.g28.scenarios:cases",
    }


def test_contract_examples_are_accepted_and_motor_cut_is_not() -> None:
    examples = load_examples(ROOT)
    assert _action({"dog_command": examples.dog_halt}, "dog_command") == "halt"
    assert _action({"drone_command": examples.drone_hover}, "drone_command") == "hover"
    assert _action({"drone_command": examples.drone_land}, "drone_command") == "land"
    payload_value = examples.drone_hover["payload"]
    assert isinstance(payload_value, dict)
    payload = dict(payload_value)
    payload["action"] = "emergency"
    emergency = dict(examples.drone_hover)
    emergency["payload"] = payload
    with pytest.raises(GroundFault) as caught:
        accept_command(emergency, kind="drone.command", action="hover")
    assert caught.value.error.code == "rejected"
    assert "motor cut" in caught.value.error.detail


def test_halt_does_not_wait_for_vision_or_call_a_model(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        services.kernel.barriers.arm("vision")
        start = services.kernel.clock.monotonic()
        result = await feature.execute(_request("operator_halt", vision_pending=True))
        assert services.kernel.clock.monotonic() == start
        assert services.kernel.barriers.armed("vision")
        assert result.status == "ok"
        assert result.error is None
        assert feature.model_calls == 0
        assert result.data["model_called"] is False
        assert result.data["motor_cut"] is False
        assert result.data["vision_cleared"] is False
        assert _action(result.data, "dog_command") == "halt"
        assert _action(result.data, "drone_command") == "hover"
        assert services.adapters.devices.calls == []
        assert services.kernel.authority.cancelled is True
        assert result.data["block_actions"] is True
        kinds = [event.kind for event in result.events]
        assert "halt_requested" in kinds
        assert "stop_attempted" in kinds
        assert feature.safety_calls == 1

    _run(body())


def test_late_person_visible_does_not_clear_the_latch(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        await feature.execute(_request("operator_halt"))
        first = feature.handle
        result = await feature.execute(
            _request("late_decision", decision={"label": "person_visible"})
        )
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.data["latch_set"] is True
        assert result.data["vision_cleared"] is False
        assert result.data["arrival_confirmed"] is False
        assert feature.handle is first
        assert feature.model_calls == 0
        assert services.kernel.authority.cancelled is True

    _run(body())


def test_expired_lease_refuses_an_unstarted_dog_command(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        examples = load_examples(ROOT)
        result = await feature.execute(
            _request("expired_lease", command=examples.dog_move, started=False)
        )
        assert result.status == "blocked"
        assert result.data["command_refused"] is True
        assert result.data["execution"] == "unknown"
        assert result.data["started"] is False
        assert result.data["query_path"] == "feature.v2_dog_ack"
        assert result.data["query_task"] == "24"
        assert result.data["query_command_id"] == "cmd-dog-001"
        assert _action(result.data, "dog_command") == "halt"
        assert _action(result.data, "drone_command") == "hover"

    _run(body())


def test_expired_drone_lease_asks_the_drone_ack_path(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        examples = load_examples(ROOT)
        result = await feature.execute(
            _request("expired_lease", command=examples.drone_move, started=False)
        )
        assert result.data["query_path"] == "feature.v2_drone_ack"
        assert result.data["query_task"] == "18"
        assert result.data["query_command_id"] == "cmd-drone-001"
        assert result.data["execution"] == "unknown"
        assert _action(result.data, "dog_command") == "halt"

    _run(body())


def test_link_loss_records_unknown_delivery_and_local_failsafe(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        result = await feature.execute(_request("link_loss"))
        assert result.status == "ok"
        assert result.data["delivery"] == "unknown"
        assert result.data["physical_stop_claimed"] is False
        assert result.data["local_failsafe"] is True
        assert result.data["delivery_guaranteed"] is False
        assert _action(result.data, "dog_command") == "halt"
        assert _action(result.data, "drone_command") == "hover"
        assert any(event.kind == "link_lost" for event in result.events)
        assert result.data["physical_stop_claimed"] is False

    _run(body())


def test_link_loss_land_profile_uses_the_land_example(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        examples = load_examples(ROOT)
        held = await feature.execute(
            _request("link_loss", profile="land", link_loss_action="hover")
        )
        assert _action(held.data, "drone_command") == "hover"
        feature_land = create(
            build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path / "land")
        )
        landed = await feature_land.execute(
            _request("link_loss", profile="hover", link_loss_action="land")
        )
        assert _action(landed.data, "drone_command") == "land"
        assert landed.data["drone_command"] == examples.drone_land
        explicit = create(
            build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path / "explicit")
        )
        requested = await explicit.execute(_request("explicit_land", profile="hover"))
        assert _action(requested.data, "dog_command") == "halt"
        assert requested.data["drone_command"] == examples.drone_land
        assert requested.data["motor_cut"] is False

    _run(body())


def test_obstacle_and_noisy_rssi_and_lost_track_do_not_arrive(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        obstacle = create(services)
        blocked = await obstacle.execute(_request("obstacle_block", detour=True))
        assert _action(blocked.data, "dog_command") == "halt"
        assert blocked.data["detour"] is False
        assert blocked.data["arrival_confirmed"] is False
        noisy = create(
            build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path / "noisy")
        )
        rssi = await noisy.execute(_request("noisy_rssi", goal_reached=True))
        assert rssi.data["goal_reached"] is False
        assert rssi.data["arrival_confirmed"] is False
        assert _action(rssi.data, "dog_command") == "halt"
        lost = create(
            build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path / "lost")
        )
        track = await lost.execute(_request("lost_track"))
        assert track.data["goal_reached"] is False
        assert track.data["arrival_confirmed"] is False

    _run(body())


def test_second_halt_returns_the_same_handle(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        first = await feature.execute(_request("operator_halt"))
        handle = feature.handle
        second = await feature.execute(_request("operator_halt"))
        assert second.status == "ok"
        assert second.data["same_handle"] is True
        assert feature.handle is handle
        assert first.data["handle"] == second.data["handle"]
        assert feature.safety_calls == 1
        assert feature.dog_halt_count == 1
        assert feature.drone_hover_count == 1
        assert services.safety.trace == ["safety.request"]

    _run(body())


def test_reset_requires_the_token_and_quiescent_workers(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        examples = load_examples(ROOT)
        await feature.execute(_request("operator_halt"))
        missing = await feature.execute(_request("reset"))
        assert missing.status == "failed"
        assert missing.error is not None
        assert missing.error.code == "rejected"
        assert feature.handle is not None
        wrong = await feature.execute(_request("reset", recovery_token="nope"))
        assert wrong.status == "failed"
        assert feature.handle is not None
        boolean = await feature.execute(_request("reset", recovery_token=True))
        assert boolean.status == "failed"
        assert boolean.error is not None
        assert boolean.error.code == "invalid_input"
        text = await feature.execute(
            _request(
                "reset",
                recovery_token=examples.recovery_token,
                workers_pending="false",
            )
        )
        assert text.status == "failed"
        assert text.error is not None
        assert text.error.code == "invalid_input"
        pending = await feature.execute(
            _request(
                "reset",
                recovery_token=examples.recovery_token,
                workers_pending=True,
            )
        )
        assert pending.status == "failed"
        assert pending.error is not None
        assert "quiescent" in pending.error.detail
        assert "safety.reset" not in services.safety.trace
        assert feature.handle is not None

    _run(body())


def test_reset_with_token_clears_only_when_workers_are_quiescent(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        examples = load_examples(ROOT)
        await feature.execute(_request("operator_halt"))
        services.kernel.barriers.arm("g28-stuck")

        async def hang() -> None:
            await services.kernel.barriers.wait("g28-stuck")

        task = asyncio.create_task(hang())
        services.kernel.tasks.retain("g28-stuck", task)
        await asyncio.sleep(0)
        refused = await feature.execute(
            _request("reset", recovery_token=examples.recovery_token, workers_pending=False)
        )
        assert refused.status == "failed"
        assert feature.handle is not None
        services.kernel.barriers.release("g28-stuck")
        await task
        accepted = await feature.execute(
            _request("reset", recovery_token=examples.recovery_token, workers_pending=False)
        )
        assert accepted.status == "ok"
        assert accepted.data["reset_accepted"] is True
        assert accepted.data["latch_set"] is False
        assert accepted.data["block_actions"] is False
        assert feature.handle is None
        assert services.kernel.authority.cancelled is False
        assert "safety.reset" in services.safety.trace

    _run(body())


def test_ordinary_search_track_and_homing_are_refused_while_latched(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        before = await feature.execute(_request("ordinary_proposal", proposal_action="search"))
        assert before.status == "blocked"
        assert before.data["ordinary_refused"] is False
        assert before.data["latch_set"] is False
        assert "dog_command" not in before.data
        await feature.execute(_request("operator_halt"))
        for action in ("search", "track", "homing"):
            result = await feature.execute(
                _request("ordinary_proposal", proposal_action=action)
            )
            assert result.status == "blocked"
            assert result.data["ordinary_refused"] is True
            assert result.data["latch_set"] is True
            assert "dog_command" not in result.data
        assert feature.dog_halt_count == 1

    _run(body())


def test_emergency_profile_does_not_emit_a_motor_cut(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        result = await feature.execute(_request("operator_halt", profile="emergency"))
        assert result.status == "ok"
        assert result.data["profile_rejected"] == "emergency"
        assert result.data["motor_cut"] is False
        assert _action(result.data, "dog_command") == "halt"
        assert _action(result.data, "drone_command") == "hover"
        encoded = json.dumps(result.data["drone_command"])
        assert "emergency" not in encoded
        assert "motor_cut" not in encoded

    _run(body())


def test_superseded_command_ids_are_journaled_with_the_latch(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        examples = load_examples(ROOT)
        result = await feature.execute(
            _request(
                "operator_halt",
                active_commands=[examples.dog_move, examples.drone_move],
            )
        )
        assert result.data["superseded_command_ids"] == ("cmd-dog-001", "cmd-drone-001")
        record = services.journal.records[0]
        assert record.event == "halt_requested"
        assert record.data["stimulus"] == "operator_halt"
        assert record.data["superseded_command_ids"] == ("cmd-dog-001", "cmd-drone-001")
        assert isinstance(record.data["latch_monotonic"], float)
        dog = record.data["dog"]
        assert isinstance(dog, Mapping)
        assert dog["message_id"] == "msg-ground-to-dog-halt"
        assert dog["mission_id"] == "demo-20261104-001"
        assert dog["command_id"] == "cmd-dog-halt-001"
        assert dog["track_id"] == "target-001"
        assert dog["beacon_epoch"] == 3
        assert "camera_epoch" not in dog
        await feature.execute(_request("operator_halt"))
        duplicate = services.journal.records[1]
        assert duplicate.data["duplicate"] is True
        assert duplicate.data["latch_monotonic"] == record.data["latch_monotonic"]
        assert duplicate.data["superseded_command_ids"] == ("cmd-dog-001", "cmd-drone-001")

    _run(body())


def test_stale_frame_latches_and_ignores_person_visible(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        result = await feature.execute(
            _request(
                "stale_frame",
                decision={"label": "person_visible"},
                vision_pending=True,
            )
        )
        assert result.status == "ok"
        assert result.data["latch_set"] is True
        assert result.data["vision_cleared"] is False
        assert result.data["arrival_confirmed"] is False
        assert feature.model_calls == 0
        assert _action(result.data, "dog_command") == "halt"
        assert any(event.kind == "decision_received" for event in result.events)

    _run(body())


def test_blank_stimulus_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        result = await feature.execute(_request(" "))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert feature.handle is None
        assert services.safety.trace == []

    _run(body())


def test_armed_land_profile_is_not_a_motor_cut(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        feature = create(services)
        examples = load_examples(ROOT)
        result = await feature.execute(_request("operator_halt", profile="land"))
        assert result.data["drone_command"] == examples.drone_land
        assert result.data["dog_command"] == examples.dog_halt
        assert result.data["motor_cut"] is False

    _run(body())
