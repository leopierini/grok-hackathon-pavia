"""Goal completion stays independent of landing recovery."""

from __future__ import annotations

import json
from collections.abc import Mapping

from patrol.ground.extensions.g27.implementation import RecoveryFeature
from patrol.ground.extensions.g27.policy import load_fixture
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.kernel.paths import repo_root
from tests.ground.g27.conftest import calls_of, evaluate, journal_count, record


def test_manifest_uses_the_v2_recovery_slot() -> None:
    path = (
        repo_root()
        / "patrol"
        / "ground"
        / "extensions"
        / "g27"
        / "manifest.json"
    )
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body == {
        "schema_version": "ground-task-v2",
        "task_id": "GROUND-27",
        "slot": "feature.v2_recovery",
        "factory": "patrol.ground.extensions.g27.implementation:create",
        "scenario_factory": "patrol.ground.extensions.g27.scenarios:cases",
    }


def test_discovery_admits_v2_without_adding_a_v1_slot() -> None:
    from patrol.ground.kernel.catalog import SLOT_BY_NAME
    from patrol.ground.kernel.loader import discover

    root = repo_root() / "patrol" / "ground" / "extensions"
    found = discover(root, only_task="27")
    assert len(found) == 1
    assert found[0].slot == "feature.v2_recovery"
    assert found[0].schema_version == "ground-task-v2"
    assert "feature.v2_recovery" not in SLOT_BY_NAME
    discovered = discover(root)
    assert any(item.task_id == "GROUND-27" for item in discovered)


def test_goal_and_verified_landing_are_both_successes(
    feature: RecoveryFeature,
    services: BaseServices,
) -> None:
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert result.status == "ok"
    assert result.error is None
    assert result.data["goal_status"] == "reached"
    assert result.data["landing_status"] == "verified"
    assert result.data["recovery_required"] is False
    assert result.data["next_mission_blocked"] is False
    assert result.data["dog_recommendation"] == "hold_stop"
    assert result.data["issued_commands"] == ()
    assert result.data["search_commands"] == ()
    saved = record(result)
    assert saved["goal_event_id"] == "msg-event-demo_goal_reached"
    assert saved["land_command_id"] == "cmd-drone-land-001"
    assert saved["command_id"] == "cmd-drone-land-001"
    assert saved["physical_retrieval"] == "operator_step"
    assert saved["software_retrieved"] is False
    assert saved["goal_status"] == "reached"
    assert saved["landing_status"] == "verified"
    kinds = [event.kind for event in result.events]
    assert "state_changed" in kinds
    assert "operation_completed" in kinds
    assert "recovery_required" not in kinds
    assert calls_of(services) == []
    assert journal_count(services) == 0


def test_unknown_landing_survives_the_goal(
    feature: RecoveryFeature,
    services: BaseServices,
) -> None:
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("drone-landing-unknown.json"),
        observation=load_fixture("drone-observation.json"),
    )
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "recovery_required"
    assert result.error.recovery_required is True
    assert result.data["goal_status"] == "reached"
    assert result.data["landing_status"] == "unverified"
    assert result.data["device_recovery_required"] is True
    assert result.data["next_mission_blocked"] is True
    assert result.data["picture_ignored"] is True
    assert result.data["goal_timestamp_ignored"] is True
    assert result.data["goal_invented"] is False
    landing = result.data["landing_event"]
    assert isinstance(landing, Mapping)
    payload = landing["payload"]
    assert isinstance(payload, Mapping)
    assert payload["event"] == "landing_unverified"
    assert payload["device_recovery_required"] is True
    assert payload["phase"] == "recover"
    assert payload["outcome"] == "failed"
    example = _example("event-landing_unverified.json")
    example_payload = example["payload"]
    assert isinstance(example_payload, dict)
    assert payload["event"] == example_payload["event"]
    assert payload["device_recovery_required"] is example_payload["device_recovery_required"]
    saved = record(result)
    assert saved["goal_status"] == "reached"
    assert saved["landing_status"] == "unverified"
    assert "recovery_cleared" not in [event.kind for event in result.events]
    assert calls_of(services) == []


def test_missing_land_command_is_not_success(feature: RecoveryFeature) -> None:
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_ack=load_fixture("drone-ack-completed.json"),
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert result.status == "ok"
    assert result.data["goal_status"] == "reached"
    assert result.data["landing_status"] == "not_attempted"
    assert result.data["recovery_required"] is False
    assert result.data["land_ack_accepted"] is False
    assert result.data["issued_commands"] == ()


def test_airborne_flight_state_after_land_ack_is_a_fault(feature: RecoveryFeature) -> None:
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation.json"),
    )
    assert result.status == "blocked"
    assert result.data["goal_status"] == "reached"
    assert result.data["landing_status"] == "contradicted"
    assert result.data["fault_name"] == "flight_state_airborne"
    assert result.data["recovery_required"] is True
    assert result.data["search_commands"] == ()
    assert record(result)["goal_event_id"] == "msg-event-demo_goal_reached"


def test_replay_keeps_one_record(feature: RecoveryFeature) -> None:
    kwargs = {
        "goal_event": load_fixture("event-demo_goal_reached.json"),
        "land_command": load_fixture("ground-to-drone-land.json"),
        "land_ack": load_fixture("land-ack-verified.json"),
        "observation": load_fixture("drone-observation-grounded.json"),
    }
    first = evaluate(feature, **kwargs)
    second = evaluate(feature, **kwargs)
    assert first.data["replayed"] is False
    assert second.data["replayed"] is True
    assert second.data["recovery_record_count"] == 1
    assert record(second)["record_id"] == record(first)["record_id"]
    assert second.events == ()
    assert second.data["goal_status"] == "reached"
    assert second.data["landing_status"] == "verified"


def test_track_completion_is_not_a_land_ack(feature: RecoveryFeature) -> None:
    result = evaluate(
        feature,
        land_command=load_fixture("ground-to-drone-command.json"),
        land_ack=load_fixture("drone-ack-completed.json"),
        observation=load_fixture("drone-observation.json"),
    )
    assert result.data["landing_status"] == "not_attempted"
    assert result.data["land_ack_accepted"] is False
    assert result.data["foreign_command_id"] == "cmd-drone-001"
    assert result.data["goal_status"] == "not_reached"
    assert result.data["goal_invented"] is False
    assert result.data["search_commands"] == ()
    assert result.data["dog_recommendation"] == "hold_stop"


def test_search_proposal_is_not_emitted(
    feature: RecoveryFeature,
    services: BaseServices,
) -> None:
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation-grounded.json"),
        ignored_actions=("search", "track_step", "move_local"),
    )
    assert result.data["issued_commands"] == ()
    assert result.data["search_commands"] == ()
    assert calls_of(services) == []
    assert "drone.land" not in calls_of(services)
    assert "dog.run_route" not in calls_of(services)


def test_named_contract_examples_are_accepted(feature: RecoveryFeature) -> None:
    goal = load_fixture("event-demo_goal_reached.json")
    land = load_fixture("ground-to-drone-land.json")
    unknown = load_fixture("drone-landing-unknown.json")
    unverified = load_fixture("event-landing_unverified.json")
    reached = evaluate(
        feature,
        goal_event=goal,
        land_command=land,
        land_ack=unknown,
    )
    assert reached.data["goal_status"] == "reached"
    assert reached.data["landing_status"] == "unverified"
    other = RecoveryFeature(feature.services)
    not_goal = evaluate(
        other,
        goal_event=unverified,
        land_command=land,
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert not_goal.data["goal_status"] == "not_reached"
    assert not_goal.data["landing_status"] == "verified"
    assert isinstance(unverified["payload"], dict)
    assert unverified["payload"]["event"] == "landing_unverified"


def _example(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g27" / name
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return {str(key): value for key, value in loaded.items()}
