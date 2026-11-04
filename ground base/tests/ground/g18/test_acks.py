"""Ordered drone acknowledgements, timeout, and unknown landing."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.extensions.g18.implementation import DroneAckFeature
from patrol.ground.extensions.g18.names import SCHEMA, SLOT, TASK_ID
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest
from tests.ground.g18.conftest import (
    apply_request,
    call,
    clock_of,
    device_calls,
    kinds,
    land,
    load,
    observation,
    rewrite,
    track,
)


def test_manifest_names_the_v2_slot() -> None:
    path = Path("patrol/ground/extensions/g18/manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": SCHEMA,
        "task_id": TASK_ID,
        "slot": SLOT,
        "factory": "patrol.ground.extensions.g18.implementation:create",
        "scenario_factory": "patrol.ground.extensions.g18.scenarios:cases",
    }


def test_contract_examples_are_accepted(feature: DroneAckFeature) -> None:
    seen = observation()
    command = track()
    for name in (
        "drone-ack-accepted.json",
        "drone-ack-running.json",
        "drone-ack-completed.json",
    ):
        result = call(feature, apply_request(load(name), command, seen=seen))
        assert result.error is None
    landing = call(
        feature,
        apply_request(load("drone-landing-unknown.json"), land(), seen=seen),
    )
    assert landing.status == "blocked"
    assert landing.error is not None
    assert landing.error.code == "recovery_required"
    assert landing.data["command_id"] == "cmd-drone-land-001"


def test_ordered_acks_keep_one_airborne_lifecycle(
    feature: DroneAckFeature,
    services: BaseServices,
) -> None:
    command = track()
    seen = observation()
    results = [
        call(feature, apply_request(load(name), command, seen=seen))
        for name in (
            "drone-ack-accepted.json",
            "drone-ack-running.json",
            "drone-ack-completed.json",
        )
    ]
    last = results[-1]
    assert last.status == "ok"
    assert last.data["history"] == ("accepted", "running", "completed")
    assert last.data["issued_command_ids"] == ("cmd-drone-001",)
    assert last.data["state"] == "completed"
    assert last.data["terminal"] is True
    assert last.data["flight_state"] == "airborne"
    assert last.data["observed_motion"] == "airborne"
    assert last.data["verified"] is True
    assert last.data["verified_completion"] is True
    assert last.data["grounded"] is False
    assert last.data["landing_proof"] is False
    assert last.data["completed"] is True
    assert last.data["completion_events"] == 1
    assert last.data["proposed_commands"] == ()
    assert last.data["demo_goal_cleared"] is False
    assert last.data["command_message_id"] == "msg-ground-to-drone-command"
    assert last.data["ack_message_id"] == "msg-drone-ack-completed"
    assert last.data["correlation_id"] == "msg-ground-to-drone-command"
    completed = [
        event
        for result in results
        for event in result.events
        if event.kind == "operation_completed"
    ]
    assert len(completed) == 1
    assert completed[0].payload["command_message_id"] == "msg-ground-to-drone-command"
    assert completed[0].payload["ack_message_id"] == "msg-drone-ack-completed"
    assert completed[0].payload["grounded"] is False
    assert device_calls(services) == []


def test_accepted_is_not_completed(feature: DroneAckFeature) -> None:
    result = call(
        feature,
        apply_request(load("drone-ack-accepted.json"), track(), seen=observation()),
    )
    assert result.status == "ok"
    assert result.data["state"] == "accepted"
    assert result.data["terminal"] is False
    assert result.data["completed"] is False
    assert result.data["verified"] is False
    assert result.data["verified_completion"] is False
    assert result.data["observed_motion"] == "unknown"
    assert result.data["completion_events"] == 0
    assert kinds(result) == ["state_changed"]


def test_running_is_not_completion(feature: DroneAckFeature) -> None:
    command = track()
    seen = observation()
    call(feature, apply_request(load("drone-ack-accepted.json"), command, seen=seen))
    running = call(feature, apply_request(load("drone-ack-running.json"), command, seen=seen))
    assert running.status == "ok"
    assert running.data["state"] == "running"
    assert running.data["terminal"] is False
    assert running.data["completed"] is False
    assert running.data["verified"] is False
    assert running.data["observed_motion"] == "airborne"
    assert running.data["flight_state"] == "airborne"
    assert running.data["grounded"] is False
    assert running.data["completion_events"] == 0


def test_timeout_queries_the_original_command_and_does_not_reissue(
    feature: DroneAckFeature,
    services: BaseServices,
) -> None:
    command = track()
    registered = call(
        feature,
        FeatureRequest(
            "command",
            "register",
            None,
            {"command": command, "reply_deadline_monotonic": 0.4},
        ),
    )
    accepted = call(
        feature,
        apply_request(load("drone-ack-accepted.json"), command, deadline=0.4),
    )
    clock_of(services).advance(0.4)
    expired = call(
        feature,
        FeatureRequest("guard", "expire", None, {"command_id": "cmd-drone-001"}),
    )
    assert registered.status == "ok"
    assert accepted.data["terminal"] is False
    assert expired.status == "ok"
    assert expired.error is None
    assert expired.data["query_required"] is True
    assert expired.data["query_command"] == "cmd-drone-001"
    assert expired.data["query_count"] == 1
    assert expired.data["unresolved"] is True
    assert expired.data["state"] == "accepted"
    assert expired.data["issued_command_ids"] == ("cmd-drone-001",)
    assert expired.data["proposed_commands"] == ()
    assert expired.data["completion_events"] == 0
    assert kinds(expired) == ["state_changed"]
    assert expired.events[0].payload["query_command"] == "cmd-drone-001"
    assert device_calls(services) == []


def test_open_deadline_does_not_query(feature: DroneAckFeature, services: BaseServices) -> None:
    command = track()
    call(
        feature,
        FeatureRequest(
            "command",
            "register",
            None,
            {"command": command, "reply_deadline_monotonic": 5},
        ),
    )
    clock_of(services).advance(1)
    early = call(feature, FeatureRequest("guard", "expire", None, {"command_id": "cmd-drone-001"}))
    assert early.status == "ok"
    assert early.data["query_required"] is False
    assert early.data["query_command"] is None
    assert early.events == ()


def test_second_timeout_does_not_emit_another_query(
    feature: DroneAckFeature,
    services: BaseServices,
) -> None:
    command = track()
    call(
        feature,
        FeatureRequest(
            "command",
            "register",
            None,
            {"command": command, "reply_deadline_monotonic": 0.2},
        ),
    )
    clock_of(services).advance(0.2)
    first = call(feature, FeatureRequest("guard", "expire", None, {"command_id": "cmd-drone-001"}))
    second = call(feature, FeatureRequest("guard", "expire", None, {"command_id": "cmd-drone-001"}))
    assert first.data["query_count"] == 1
    assert second.status == "ok"
    assert second.data["duplicate"] is True
    assert second.data["query_count"] == 1
    assert second.data["query_command"] == "cmd-drone-001"
    assert second.events == ()
    assert second.data["issued_command_ids"] == ("cmd-drone-001",)


def test_unknown_landing_requires_recovery_and_blocks_the_next_mission(
    feature: DroneAckFeature,
    services: BaseServices,
) -> None:
    result = call(
        feature,
        apply_request(load("drone-landing-unknown.json"), land(), seen=observation()),
    )
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "recovery_required"
    assert result.error.recovery_required is True
    assert result.data["state"] == "unknown"
    assert result.data["verified"] is False
    assert result.data["observed_motion"] == "unknown"
    assert result.data["reason_code"] == "landing_not_verified"
    assert result.data["recovery_required"] is True
    assert result.data["blocks_next_mission"] is True
    assert result.data["grounded"] is False
    assert result.data["landing_proof"] is False
    assert result.data["flight_state"] == "unknown"
    assert result.data["terminal"] is True
    assert result.data["completed"] is False
    assert result.data["demo_goal_cleared"] is False
    assert result.data["proposed_commands"] == ()
    assert "recovery_required" in kinds(result)
    assert device_calls(services) == []


def test_duplicate_final_ack_does_not_complete_twice(feature: DroneAckFeature) -> None:
    command = track()
    seen = observation()
    names = (
        "drone-ack-accepted.json",
        "drone-ack-running.json",
        "drone-ack-completed.json",
    )
    results = [call(feature, apply_request(load(name), command, seen=seen)) for name in names]
    replay = call(feature, apply_request(load("drone-ack-completed.json"), command, seen=seen))
    completions = [
        event
        for result in [*results, replay]
        for event in result.events
        if event.kind == "operation_completed"
    ]
    assert replay.status == "ok"
    assert replay.data["duplicate"] is True
    assert replay.events == ()
    assert replay.data["completion_events"] == 1
    assert replay.data["history"] == ("accepted", "running", "completed")
    assert len(completions) == 1


def test_same_final_payload_with_a_new_message_is_idempotent(feature: DroneAckFeature) -> None:
    command = track()
    seen = observation()
    for name in (
        "drone-ack-accepted.json",
        "drone-ack-running.json",
        "drone-ack-completed.json",
    ):
        call(feature, apply_request(load(name), command, seen=seen))
    replay = rewrite(load("drone-ack-completed.json"))
    replay["message_id"] = "msg-drone-ack-completed-again"
    replay["seq"] = 8
    result = call(feature, apply_request(replay, command, seen=seen))
    assert result.status == "ok"
    assert result.data["duplicate"] is True
    assert result.events == ()
    assert result.data["completion_events"] == 1
    assert result.data["ack_message_ids"] == (
        "msg-drone-ack-accepted",
        "msg-drone-ack-running",
        "msg-drone-ack-completed",
        "msg-drone-ack-completed-again",
    )
