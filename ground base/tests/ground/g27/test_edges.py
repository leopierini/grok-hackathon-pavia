"""Extra recovery edges that the contract examples do not spell out."""

from __future__ import annotations

from patrol.ground.extensions.g27.implementation import RecoveryFeature, create
from patrol.ground.extensions.g27.policy import load_fixture
from patrol.ground.kernel.contracts import BaseServices
from tests.ground.g27.conftest import calls_of, evaluate, record


def test_string_verified_is_rejected(
    feature: RecoveryFeature,
    services: BaseServices,
) -> None:
    ack = _copy(load_fixture("land-ack-verified.json"))
    payload = _copy(ack["payload"])
    payload["verified"] = "true"
    ack["payload"] = payload
    result = evaluate(
        feature,
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=ack,
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"
    assert calls_of(services) == []


def test_running_ack_is_not_a_verified_landing(feature: RecoveryFeature) -> None:
    ack = _copy(load_fixture("land-ack-verified.json"))
    payload = _copy(ack["payload"])
    payload["state"] = "running"
    payload["verified"] = False
    payload["observed_motion"] = "unknown"
    ack["payload"] = payload
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=ack,
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert result.status == "blocked"
    assert result.data["landing_status"] == "unverified"
    assert result.data["goal_status"] == "reached"
    assert result.data["recovery_required"] is True


def test_failed_ack_keeps_the_goal(feature: RecoveryFeature) -> None:
    ack = _copy(load_fixture("land-ack-verified.json"))
    payload = _copy(ack["payload"])
    payload["state"] = "failed"
    payload["verified"] = False
    payload["observed_motion"] = "unknown"
    ack["payload"] = payload
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=ack,
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert result.data["landing_status"] == "failed"
    assert result.data["goal_status"] == "reached"
    assert result.data["recovery_required"] is True
    assert record(result)["goal_status"] == "reached"


def test_goal_flag_and_same_picture_do_not_clear_unknown(feature: RecoveryFeature) -> None:
    goal = load_fixture("event-demo_goal_reached.json")
    assert isinstance(goal["payload"], dict)
    assert goal["payload"]["device_recovery_required"] is False
    first = evaluate(
        feature,
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("drone-landing-unknown.json"),
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert first.data["goal_status"] == "not_reached"
    assert first.data["recovery_required"] is True
    assert first.data["picture_ignored"] is True
    second = evaluate(
        feature,
        goal_event=goal,
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("drone-landing-unknown.json"),
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert second.data["goal_status"] == "reached"
    assert second.data["recovery_required"] is True
    assert second.data["landing_status"] == "unverified"
    assert second.data["recovery_record_count"] == 1
    third = evaluate(
        feature,
        goal_event=goal,
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation-grounded.json"),
        attempt_clear=True,
    )
    assert third.status == "failed"
    assert third.error is not None
    assert third.error.code == "rejected"
    assert third.data["recovery_required"] is True
    assert third.data["clear_rejected"] is True


def test_new_grounded_observation_clears_only_that_record(
    services: BaseServices,
) -> None:
    feature = create(services)
    evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("drone-landing-unknown.json"),
        observation=load_fixture("drone-observation.json"),
    )
    cleared = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation-grounded-later.json"),
        attempt_clear=True,
    )
    assert cleared.status == "ok"
    assert cleared.data["cleared"] is True
    assert cleared.data["recovery_required"] is False
    assert cleared.data["landing_status"] == "verified"
    assert cleared.data["goal_status"] == "reached"
    assert cleared.data["recovery_record_count"] == 1
    assert cleared.data["physical_retrieval"] == "operator_step"
    assert record(cleared)["software_retrieved"] is False
    assert "recovery_cleared" in [event.kind for event in cleared.events]
    assert calls_of(services) == []


def test_mismatched_missions_are_rejected(feature: RecoveryFeature) -> None:
    land = _copy(load_fixture("ground-to-drone-land.json"))
    land["mission_id"] = "other-mission"
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=land,
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"


def test_ack_for_another_command_does_not_verify(feature: RecoveryFeature) -> None:
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("drone-ack-completed.json"),
        observation=load_fixture("drone-observation-grounded.json"),
    )
    assert result.data["landing_status"] == "unverified"
    assert result.data["land_ack_accepted"] is False
    assert result.data["recovery_required"] is True
    assert result.data["goal_status"] == "reached"


def test_verified_followup_clears_without_a_separate_flag(services: BaseServices) -> None:
    feature = create(services)
    evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("drone-landing-unknown.json"),
        observation=load_fixture("drone-observation.json"),
    )
    cleared = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        land_command=load_fixture("ground-to-drone-land.json"),
        land_ack=load_fixture("land-ack-verified.json"),
        observation=load_fixture("drone-observation-grounded-later.json"),
    )
    assert cleared.status == "ok"
    assert cleared.data["cleared"] is True
    assert cleared.data["goal_status"] == "reached"
    assert cleared.data["landing_status"] == "verified"
    assert cleared.data["recovery_required"] is False
    assert cleared.data["recovery_record_count"] == 1
    assert record(cleared)["request_id"] is None
    assert record(cleared)["software_retrieved"] is False
    assert calls_of(services) == []


def test_clear_without_a_record_is_rejected(feature: RecoveryFeature) -> None:
    result = evaluate(
        feature,
        goal_event=load_fixture("event-demo_goal_reached.json"),
        attempt_clear=True,
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "rejected"


def _copy(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("expected an object")
    return {str(key): item for key, item in value.items()}
