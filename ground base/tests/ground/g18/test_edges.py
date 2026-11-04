"""Conflicts, stale identity, and landing claims that are not proof."""

from __future__ import annotations

from patrol.ground.extensions.g18.implementation import DroneAckFeature
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, Ticket
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g18.conftest import (
    apply_request,
    call,
    clock_of,
    device_calls,
    kinds,
    land,
    load,
    observation,
    payload_of,
    rewrite,
    track,
)


def _play(feature: DroneAckFeature) -> None:
    command = track()
    seen = observation()
    for name in (
        "drone-ack-accepted.json",
        "drone-ack-running.json",
        "drone-ack-completed.json",
    ):
        call(feature, apply_request(load(name), command, seen=seen))


def test_completed_then_failed_is_a_conflict(feature: DroneAckFeature) -> None:
    _play(feature)
    command = track()
    failed = rewrite(
        load("drone-ack-completed.json"),
        state="failed",
        verified=False,
        reason_code="conflict",
        detail="Conflicting final state.",
    )
    failed["message_id"] = "msg-drone-ack-conflict"
    failed["seq"] = 6
    result = call(feature, apply_request(failed, command, seen=observation()))
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "unsafe_state"
    assert result.error.recovery_required is True
    assert result.data["conflict"] is True
    assert result.data["state"] == "completed"
    assert result.data["history"] == ("accepted", "running", "completed")
    assert result.data["completion_events"] == 1
    assert result.data["flight_state"] == "airborne"
    assert result.data["grounded"] is False
    assert result.data["proposed_commands"] == ()
    assert kinds(result) == ["operation_failed"]


def test_track_completion_is_not_landing_proof(feature: DroneAckFeature) -> None:
    claimed = rewrite(load("drone-ack-completed.json"), observed_motion="grounded")
    result = call(feature, apply_request(claimed, track(), seen=observation()))
    assert result.status == "ok"
    assert result.data["action"] == "track_step"
    assert result.data["completed"] is True
    assert result.data["observed_motion"] == "grounded"
    assert result.data["grounded"] is False
    assert result.data["landing_proof"] is False
    assert result.data["flight_state"] == "unknown"


def test_verified_false_is_not_verified_completion(feature: DroneAckFeature) -> None:
    ack = rewrite(load("drone-ack-completed.json"), verified=False)
    result = call(feature, apply_request(ack, track(), seen=observation()))
    assert result.status == "ok"
    assert result.data["state"] == "completed"
    assert result.data["verified"] is False
    assert result.data["completed"] is True
    assert result.data["verified_completion"] is False
    assert result.data["grounded"] is False
    assert result.events[1].payload["verified_completion"] is False


def test_is_flying_in_the_detail_does_not_count_as_grounded(feature: DroneAckFeature) -> None:
    ack = rewrite(load("drone-ack-completed.json"), detail="is_flying=false")
    result = call(feature, apply_request(ack, track(), seen=observation()))
    assert result.data["ignored_local_flag"] is True
    assert result.data["reported_detail"] == "is_flying=false"
    assert result.data["grounded"] is False
    assert result.data["flight_state"] == "airborne"
    assert result.data["landing_proof"] is False


def test_observation_flags_do_not_ground_an_airborne_track(feature: DroneAckFeature) -> None:
    seen = observation()
    body = payload_of(seen)
    body["flight_state"] = "grounded"
    body["is_flying"] = False
    seen["payload"] = body
    result = call(feature, apply_request(load("drone-ack-completed.json"), track(), seen=seen))
    assert result.data["ignored_local_flag"] is True
    assert result.data["observation_flight_state"] == "grounded"
    assert result.data["observation_stale"] is False
    assert result.data["flight_state"] == "airborne"
    assert result.data["grounded"] is False


def test_stale_observation_cannot_clear_unknown_landing(feature: DroneAckFeature) -> None:
    seen = observation()
    body = payload_of(seen)
    body["flight_state"] = "grounded"
    body["is_flying"] = False
    seen["payload"] = body
    seen["epoch"] = 9
    result = call(feature, apply_request(load("drone-landing-unknown.json"), land(), seen=seen))
    assert result.data["observation_stale"] is True
    assert result.data["observation_flight_state"] is None
    assert result.data["ignored_local_flag"] is False
    assert result.data["grounded"] is False
    assert result.data["recovery_required"] is True
    assert result.data["blocks_next_mission"] is True


def test_foreign_epoch_is_stale_and_does_not_replace_the_record(
    feature: DroneAckFeature,
) -> None:
    command = track()
    call(feature, apply_request(load("drone-ack-accepted.json"), command))
    stale = load("drone-ack-running.json")
    stale["epoch"] = 4
    stale["message_id"] = "msg-drone-ack-foreign-epoch"
    result = call(feature, apply_request(stale, command))
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "epoch_mismatch"
    assert result.data["state"] == "accepted"
    assert result.data["history"] == ("accepted",)
    projected = call(
        feature,
        FeatureRequest("projection", "project", None, {"command_id": "cmd-drone-001"}),
    )
    assert projected.data["state"] == "accepted"


def test_unknown_command_id_is_rejected(feature: DroneAckFeature) -> None:
    ack = rewrite(load("drone-ack-accepted.json"), command_id="cmd-not-issued")
    ack["message_id"] = "msg-drone-ack-foreign"
    result = call(feature, apply_request(ack, track()))
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert result.error.detail == "unknown command_id"
    assert result.data["issued_command_ids"] == ()
    assert result.data["proposed_commands"] == ()


def test_dog_ack_is_left_to_its_own_task(feature: DroneAckFeature) -> None:
    result = call(feature, apply_request(load("dog-ack-accepted.json"), track()))
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert result.error.detail == "dog acknowledgements are tracked by task 24"
    assert result.data["issued_command_ids"] == ()
    assert result.events == ()


def test_correlation_and_mission_must_match_the_command(feature: DroneAckFeature) -> None:
    command = track()
    mismatched = load("drone-ack-accepted.json")
    mismatched["correlation_id"] = "msg-some-other-command"
    correlation = call(feature, apply_request(mismatched, command))
    assert correlation.status == "blocked"
    assert correlation.error is not None
    assert correlation.error.code == "contract_mismatch"
    other_mission = load("drone-ack-accepted.json")
    other_mission["mission_id"] = "demo-other"
    mission = call(feature, apply_request(other_mission, command))
    assert mission.status == "blocked"
    assert mission.error is not None
    assert mission.error.code == "contract_mismatch"
    assert mission.data["issued_command_ids"] == ()


def test_lower_sequence_does_not_rewrite_the_state(feature: DroneAckFeature) -> None:
    command = track()
    call(feature, apply_request(load("drone-ack-accepted.json"), command))
    older = load("drone-ack-running.json")
    older["seq"] = 1
    older["message_id"] = "msg-drone-ack-old"
    result = call(feature, apply_request(older, command))
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "stale_ticket"
    assert result.data["state"] == "accepted"
    assert result.data["history"] == ("accepted",)


def test_reused_message_id_with_a_different_payload_conflicts(feature: DroneAckFeature) -> None:
    command = track()
    call(feature, apply_request(load("drone-ack-accepted.json"), command))
    changed = rewrite(load("drone-ack-accepted.json"), state="running", observed_motion="airborne")
    changed["seq"] = 9
    result = call(feature, apply_request(changed, command))
    assert result.status == "failed"
    assert result.data["conflict"] is True
    assert result.data["state"] == "accepted"
    assert result.data["history"] == ("accepted",)


def test_running_then_accepted_conflicts(feature: DroneAckFeature) -> None:
    command = track()
    seen = observation()
    call(feature, apply_request(load("drone-ack-accepted.json"), command, seen=seen))
    call(feature, apply_request(load("drone-ack-running.json"), command, seen=seen))
    backwards = rewrite(
        load("drone-ack-accepted.json"),
        observed_motion="stationary",
    )
    backwards["message_id"] = "msg-drone-ack-backwards"
    backwards["seq"] = 9
    result = call(feature, apply_request(backwards, command, seen=seen))
    assert result.status == "failed"
    assert result.data["state"] == "running"
    assert result.data["history"] == ("accepted", "running")
    assert result.data["proposed_commands"] == ()


def test_rejected_cancelled_and_failed_are_terminal_but_not_completed(
    feature: DroneAckFeature,
) -> None:
    command = track()
    for state, seq in (("rejected", 3), ("cancelled", 4), ("failed", 5)):
        separate = DroneAckFeature(feature.services)
        ack = rewrite(
            load("drone-ack-accepted.json"),
            state=state,
            reason_code=state,
            observed_motion="stationary",
        )
        ack["message_id"] = f"msg-drone-ack-{state}"
        ack["seq"] = seq
        rebound = dict(command)
        body = payload_of(command)
        body["command_id"] = f"cmd-{state}"
        rebound["message_id"] = f"msg-command-{state}"
        rebound["payload"] = body
        ack["correlation_id"] = rebound["message_id"]
        ack_body = payload_of(ack)
        ack_body["command_id"] = f"cmd-{state}"
        ack["payload"] = ack_body
        result = call(separate, apply_request(ack, rebound))
        assert result.status == "ok"
        assert result.data["state"] == state
        assert result.data["terminal"] is True
        assert result.data["completed"] is False
        assert result.data["verified_completion"] is False
        assert result.data["grounded"] is False
        assert result.data["proposed_commands"] == ()


def test_only_a_verified_grounded_landing_is_grounded(feature: DroneAckFeature) -> None:
    landed = rewrite(
        load("drone-ack-completed.json"),
        command_id="cmd-drone-land-001",
        observed_motion="grounded",
        detail="Gear on the floor.",
    )
    landed["message_id"] = "msg-drone-ack-landed"
    landed["correlation_id"] = "msg-ground-to-drone-land"
    result = call(feature, apply_request(landed, land(), seen=observation()))
    assert result.status == "ok"
    assert result.data["grounded"] is True
    assert result.data["landing_proof"] is True
    assert result.data["flight_state"] == "grounded"
    assert result.data["verified_completion"] is True
    assert result.data["proposed_commands"] == ()
    assert result.data["demo_goal_cleared"] is False


def test_stationary_or_unverified_landing_is_not_grounded(feature: DroneAckFeature) -> None:
    stationary = rewrite(
        load("drone-ack-completed.json"),
        command_id="cmd-drone-land-001",
        observed_motion="stationary",
    )
    stationary["correlation_id"] = "msg-ground-to-drone-land"
    stationary["message_id"] = "msg-land-stationary"
    hovering = call(feature, apply_request(stationary, land()))
    assert hovering.data["grounded"] is False
    assert hovering.data["flight_state"] == "unknown"
    other = DroneAckFeature(feature.services)
    unverified = rewrite(
        load("drone-ack-completed.json"),
        command_id="cmd-drone-land-001",
        observed_motion="grounded",
        verified=False,
    )
    unverified["correlation_id"] = "msg-ground-to-drone-land"
    unverified["message_id"] = "msg-land-unverified"
    result = call(other, apply_request(unverified, land()))
    assert result.data["verified_completion"] is False
    assert result.data["grounded"] is False


def test_string_boolean_is_rejected(feature: DroneAckFeature) -> None:
    ack = rewrite(load("drone-ack-accepted.json"), verified="true")
    result = call(feature, apply_request(ack, track()))
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"
    assert result.data["proposed_commands"] == ()
    assert result.data["grounded"] is False


def test_query_then_completion_uses_the_same_command(
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
            {"command": command, "reply_deadline_monotonic": 0.3},
        ),
    )
    clock_of(services).advance(0.3)
    expired = call(
        feature,
        FeatureRequest("guard", "expire", None, {"command_id": "cmd-drone-001"}),
    )
    done = call(
        feature,
        apply_request(load("drone-ack-completed.json"), command, seen=observation()),
    )
    assert expired.data["query_command"] == "cmd-drone-001"
    assert done.status == "ok"
    assert done.data["state"] == "completed"
    assert done.data["query_required"] is False
    assert done.data["query_count"] == 1
    assert done.data["unresolved"] is False
    assert done.data["issued_command_ids"] == ("cmd-drone-001",)
    assert done.data["proposed_commands"] == ()
    assert done.data["grounded"] is False


def test_timeout_of_one_command_does_not_query_another(
    feature: DroneAckFeature,
    services: BaseServices,
) -> None:
    call(
        feature,
        FeatureRequest(
            "command",
            "register",
            None,
            {"command": track(), "reply_deadline_monotonic": 0.2},
        ),
    )
    call(
        feature,
        FeatureRequest(
            "command",
            "register",
            None,
            {"command": land(), "reply_deadline_monotonic": 10},
        ),
    )
    clock_of(services).advance(0.2)
    expired = call(
        feature,
        FeatureRequest("guard", "expire", None, {"command_id": "cmd-drone-001"}),
    )
    other = call(
        feature,
        FeatureRequest("projection", "project", None, {"command_id": "cmd-drone-land-001"}),
    )
    assert expired.data["query_command"] == "cmd-drone-001"
    assert other.data["query_count"] == 0
    assert other.data["query_required"] is False
    assert expired.data["issued_command_ids"] == ("cmd-drone-001", "cmd-drone-land-001")


def test_later_completion_does_not_clear_unknown_landing(feature: DroneAckFeature) -> None:
    command = land()
    unknown = call(feature, apply_request(load("drone-landing-unknown.json"), command))
    later = rewrite(
        load("drone-ack-completed.json"),
        command_id="cmd-drone-land-001",
        observed_motion="grounded",
    )
    later["message_id"] = "msg-land-after-unknown"
    later["seq"] = 9
    later["correlation_id"] = "msg-ground-to-drone-land"
    conflict = call(feature, apply_request(later, command))
    assert unknown.data["blocks_next_mission"] is True
    assert conflict.status == "failed"
    assert conflict.data["state"] == "unknown"
    assert conflict.data["recovery_required"] is True
    assert conflict.data["blocks_next_mission"] is True
    assert conflict.data["grounded"] is False
    assert conflict.data["demo_goal_cleared"] is False


def test_unknown_track_execution_recovers_without_a_new_takeoff(feature: DroneAckFeature) -> None:
    ack = rewrite(
        load("drone-ack-accepted.json"),
        state="unknown",
        reason_code="execution_unknown",
        observed_motion="unknown",
        verified=False,
    )
    ack["message_id"] = "msg-track-unknown"
    result = call(feature, apply_request(ack, track()))
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "recovery_required"
    assert result.data["recovery_required"] is True
    assert result.data["blocks_next_mission"] is False
    assert result.data["grounded"] is False
    assert result.data["proposed_commands"] == ()
    assert result.data["issued_command_ids"] == ("cmd-drone-001",)


def test_stale_ticket_is_rejected(feature: DroneAckFeature, services: BaseServices) -> None:
    ticket = Ticket("demo-20261104-001", 4, "ack")
    try:
        services.kernel.authority.require_current(ticket)
    except GroundFault as exc:
        assert exc.error.code == "stale_ticket"
    request = apply_request(load("drone-ack-accepted.json"), track())
    stale = FeatureRequest(request.kind, request.name, ticket, request.payload)
    result = call(feature, stale)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "stale_ticket"
    assert result.data["proposed_commands"] == ()
    assert device_calls(services) == []


def test_boolean_deadline_is_rejected(feature: DroneAckFeature) -> None:
    request = FeatureRequest(
        "command",
        "register",
        None,
        {"command": track(), "reply_deadline_monotonic": True},
    )
    result = call(feature, request)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"
