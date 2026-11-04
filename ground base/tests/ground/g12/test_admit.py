"""Capability admission against the copied contract examples."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

import pytest
from patrol.ground.extensions.g12.admit import (
    copy_envelope,
    demo_settings,
    demo_snapshot,
    load_envelopes,
    with_features,
    with_payload,
)
from patrol.ground.extensions.g12.implementation import create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import build_test_services


def test_create_rejects_a_non_service() -> None:
    with pytest.raises(GroundFault) as caught:
        create(object())  # type: ignore[arg-type]
    assert caught.value.error.code == "invalid_input"


def test_examples_arm_only_reported_validated_features(tmp_path: Path) -> None:
    services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()

    async def body() -> None:
        result = await _admit(feature, (drone, dog, pi))
        assert result.status == "ok"
        assert result.error is None
        assert result.data["motion_permission"] is False
        assert result.data["session_armed"] is False
        assert result.data["continuation"] == "admitted"
        assert result.data["autonomous_search"] == "armed"
        assert result.data["navigation_mode"] == "slam_eligible"
        assert result.data["features"] == {
            "controlled_motion": True,
            "downward_video": True,
            "rssi_receiver": True,
            "lidar": True,
            "slam": True,
            "target_range": True,
        }
        assert result.data["dog_controlled_motion"] is True
        drone_peer = _peer(result, "drone")
        dog_peer = _peer(result, "dog")
        pi_peer = _peer(result, "pi")
        assert drone_peer["model"] == "Tello EDU"
        assert drone_peer["software_version"] == "synthetic-test-v1"
        assert drone_peer["supported_commands"] == (
            "takeoff",
            "search_step",
            "track_step",
            "hover",
            "land",
        )
        assert drone_peer["acceptance_evidence_ref"] == "artifact://synthetic-only/capability-test"
        assert dog_peer["model"] == "Unitree Go2 PRO"
        assert pi_peer["device_id"] == "pi-01"
        router = result.data["router"]
        assert router["device_id"] == "router-back"
        assert router["networking"] == "failed"
        assert router["peer"] is False
        assert [event.kind for event in result.events] == ["state_changed"] * 3
        assert "password" not in repr(result.events).lower()
        assert _calls(services) == []

    _run(body)


def test_false_motion_stays_false_and_blocks_autonomous_search(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()
    reported = with_features(drone, controlled_motion=False, downward_video=False)

    async def body() -> None:
        supervised = demo_settings(flight_intent="supervised")
        honest = await _admit(feature, (reported, dog, pi), supervised)
        assert honest.status == "ok"
        assert honest.data["features"]["controlled_motion"] is False
        assert honest.data["features"]["downward_video"] is False
        assert _peer(honest, "drone")["reported_features"]["controlled_motion"] is False
        assert honest.data["continuation"] == "supervised"
        assert "motion_plan" not in honest.data

    _run(body)

    services, blocked_feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()

    async def blocked() -> None:
        changed = with_features(drone, controlled_motion=False)
        result = await _admit(blocked_feature, (changed, dog, pi))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.detail == "controlled_motion_reported_false"
        assert result.data["autonomous_search"] == "blocked"
        assert result.data["motion_permission"] is False
        assert "motion_plan" not in result.data
        assert _calls(services) == []

    _run(blocked)


def test_lidar_without_slam_stays_unresolved(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()

    async def body() -> None:
        result = await _admit(feature, (drone, with_features(dog, slam=False), pi))
        assert result.status == "ok"
        assert result.data["features"]["lidar"] is True
        assert result.data["features"]["slam"] is False
        assert result.data["reactive_avoidance_eligible"] is True
        assert result.data["slam_eligible"] is False
        assert result.data["navigation_mode"] == "unresolved"

    _run(body)


def test_false_rssi_blocks_homing_and_leaves_vision(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()

    async def body() -> None:
        result = await _admit(feature, (drone, dog, with_features(pi, rssi_receiver=False)))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.detail == "rssi_receiver_reported_false"
        assert result.data["rssi_homing"] == "blocked"
        assert result.data["vision_only_dog_approach"] == "available"
        assert result.data["features"]["rssi_receiver"] is False

    _run(body)


def test_missing_pi_disarms_rssi(tmp_path: Path) -> None:
    services, feature = _open(tmp_path)
    drone, dog, _pi = load_envelopes()

    async def body() -> None:
        result = await _admit(feature, (drone, dog))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "unavailable"
        assert result.error.detail == "pi_report_missing"
        assert result.data["features"]["rssi_receiver"] is False
        assert "pi" not in result.data["peers"]
        assert _calls(services) == []

    _run(body)


def test_unvalidated_and_null_evidence_do_not_arm(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()
    settings = demo_settings(flight_intent="supervised")

    async def body() -> None:
        unvalidated = await _admit(
            feature,
            (drone, with_payload(dog, validated=False), pi),
            settings,
        )
        assert unvalidated.status == "ok"
        assert unvalidated.data["dog_controlled_motion"] is False
        dog_peer = _peer(unvalidated, "dog")
        assert dog_peer["reported_features"]["controlled_motion"] is True
        assert dog_peer["features"]["controlled_motion"] is False
        assert "validated_false" in dog_peer["disarm_reasons"]

    _run(body)

    _services, other = _open(tmp_path)
    drone, dog, pi = load_envelopes()

    async def missing_evidence() -> None:
        result = await _admit(
            other,
            (with_payload(drone, acceptance_evidence_ref=None), dog, pi),
            settings,
        )
        assert result.status == "ok"
        assert result.data["features"]["controlled_motion"] is False
        assert result.data["features"]["downward_video"] is False
        assert "acceptance_evidence_missing" in _peer(result, "drone")["disarm_reasons"]

    _run(missing_evidence)


def test_string_boolean_is_not_coerced(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, _dog, _pi = load_envelopes()

    async def body() -> None:
        result = await _admit(feature, (with_payload(drone, validated="true"),))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert result.data["armed_record_count"] == 0
        assert result.data["motion_permission"] is False

    _run(body)


def test_command_allowlist_and_downward_camera(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()

    async def missing_command() -> None:
        changed = with_payload(drone, supported_commands=["takeoff", "hover", "land"])
        result = await _admit(feature, (changed,))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "forbidden_command"
        assert result.error.detail == "missing_command:search_step,track_step"
        assert result.data["armed_record_count"] == 0

    _run(missing_command)

    _services, other = _open(tmp_path)

    async def camera() -> None:
        changed = with_payload(drone, camera_ids=["front"])
        result = await _admit(other, (changed, dog, pi))
        assert result.status == "ok"
        assert result.data["features"]["downward_video"] is False
        assert result.data["features"]["controlled_motion"] is True
        peer = _peer(result, "drone")
        assert peer["reported_features"]["downward_video"] is True
        assert "downward_camera_id_missing" in peer["disarm_reasons"]

    _run(camera)


def test_identity_replay_conflict_and_second_owner(tmp_path: Path) -> None:
    services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()

    async def body() -> None:
        first = await _admit(feature, (drone, dog, pi))
        assert first.data["armed_record_count"] == 3
        assert len(first.events) == 3
        replay = await _admit(feature, (drone, drone))
        assert replay.status == "ok"
        assert replay.data["armed_record_count"] == 3
        assert replay.data["replayed"] == ("msg-drone-capabilities", "msg-drone-capabilities")
        assert replay.events == ()
        conflict = copy_envelope(drone)
        conflict["payload"]["model"] = "Tello EDU revised"
        rejected = await _admit(feature, (conflict,))
        assert rejected.status == "failed"
        assert rejected.error is not None
        assert rejected.error.detail == "report_id_conflict"
        assert rejected.data["armed_record_count"] == 3
        other = copy_envelope(drone)
        other["message_id"] = "msg-drone-capabilities-2"
        second = await _admit(feature, (other,))
        assert second.status == "failed"
        assert second.error is not None
        assert second.error.code == "owner_mismatch"
        assert _peer(second, "drone")["message_id"] == "msg-drone-capabilities"
        mismatch = await _admit(feature, (with_payload(copy_envelope(dog), device_id="drone-01"),))
        assert mismatch.status == "failed"
        assert mismatch.error is not None
        assert mismatch.error.detail == "role_device_mismatch"
        assert _calls(services) == []

    _run(body)


def test_router_failure_does_not_change_the_pi(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()
    router = with_payload(pi, device_id="router-back", role="pi")
    router["source"] = "pi"

    async def body() -> None:
        rejected = await _admit(feature, (router,))
        assert rejected.status == "failed"
        assert rejected.error is not None
        assert rejected.error.detail == "router_is_not_a_peer"
        assert rejected.data["router"]["networking"] == "failed"
        assert "pi" not in rejected.data["peers"]
        admitted = await _admit(feature, (drone, dog, pi))
        assert admitted.status == "ok"
        assert admitted.data["features"]["rssi_receiver"] is True
        assert _peer(admitted, "pi")["device_id"] == "pi-01"
        assert admitted.data["router"]["device_id"] == "router-back"
        assert admitted.data["router"]["networking"] == "failed"
        assert admitted.data["armed_record_count"] == 3

    _run(body)


def test_stale_epoch_does_not_enter_the_next_session(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()
    settings = demo_settings()

    async def body() -> None:
        current = await _admit(feature, (drone, dog, pi), settings, demo_snapshot(settings))
        assert current.status == "ok"
        later = demo_snapshot(settings, epoch=2)
        stale = await _admit(feature, (drone,), settings, later)
        assert stale.status == "blocked"
        assert stale.error is not None
        assert stale.error.code == "epoch_mismatch"
        assert stale.data["armed_record_count"] == 0
        assert stale.events == ()

    _run(body)


def test_credentials_synthetic_live_flag_and_partial_batch(tmp_path: Path) -> None:
    services, feature = _open(tmp_path)
    drone, dog, _pi = load_envelopes()
    secret = copy_envelope(drone)
    secret["payload"]["password"] = "super-secret-radio"

    async def body() -> None:
        hidden = await _admit(feature, (secret,))
        assert hidden.status == "failed"
        assert hidden.error is not None
        assert hidden.error.detail == "credential field is not stored"
        blob = repr(hidden)
        assert "super-secret-radio" not in blob
        live = copy_envelope(drone)
        live["simulated"] = False
        marked = await _admit(feature, (live,))
        assert marked.status == "failed"
        assert marked.error is not None
        assert marked.error.detail == "synthetic_evidence_marked_live"
        partial = await _admit(feature, (dog, with_payload(drone, validated="false")))
        assert partial.status == "failed"
        assert partial.data["armed_record_count"] == 0
        assert _calls(services) == []

    _run(body)


def test_refuses_an_armed_or_cancelled_session(tmp_path: Path) -> None:
    services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()
    settings = demo_settings()

    async def body() -> None:
        armed = await _admit(
            feature,
            (drone, dog, pi),
            settings,
            demo_snapshot(settings, armed=True),
        )
        assert armed.status == "failed"
        assert armed.error is not None
        assert armed.error.code == "unsafe_state"
        assert armed.data["motion_permission"] is False
        services.kernel.authority.latch_cancel("operator halt")
        cancelled = await _admit(feature, (drone, dog, pi), settings)
        assert cancelled.status == "blocked"
        assert cancelled.error is not None
        assert cancelled.error.code == "cancelled"
        assert _calls(services) == []

    _run(body)


def test_vision_role_recovery_and_duplicate_in_one_batch(tmp_path: Path) -> None:
    services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()
    settings = demo_settings()
    vision = with_payload(drone, role="vision")
    vision["source"] = "vision"

    async def body() -> None:
        rejected = await _admit(feature, (vision,))
        assert rejected.status == "failed"
        assert rejected.error is not None
        assert rejected.error.detail == "role_not_admitted"
        held = await _admit(
            feature,
            (drone, dog, pi),
            settings,
            demo_snapshot(settings, halt_latched=True),
        )
        assert held.status == "blocked"
        assert held.error is not None
        assert held.error.code == "recovery_required"
        assert held.data["armed_record_count"] == 0
        fresh = create(services)
        once = await _admit(fresh, (drone, drone, dog, pi))
        assert once.status == "ok"
        assert once.data["armed_record_count"] == 3
        assert once.data["replayed"] == ("msg-drone-capabilities",)
        assert len(once.events) == 3
        assert _calls(services) == []

    _run(body)


def test_transport_contradiction_blocks_without_a_motion_plan(tmp_path: Path) -> None:
    _services, feature = _open(tmp_path)
    drone, dog, pi = load_envelopes()
    settings = demo_settings(profile_transport="wifi")

    async def body() -> None:
        result = await _admit(feature, (drone, dog, pi), settings)
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.detail == "transport_profile_conflict"
        assert result.data["motion_permission"] is False
        assert "motion_plan" not in result.data

    _run(body)


def _open(tmp_path: Path) -> tuple[BaseServices, object]:
    services = build_test_services(output_dir=tmp_path)
    return services, create(services)


def _admit(
    feature: object,
    reports: tuple[Mapping[str, object], ...],
    settings: object | None = None,
    snapshot: object | None = None,
) -> Awaitable[FeatureResult]:
    chosen = demo_settings() if settings is None else settings
    session = demo_snapshot(chosen) if snapshot is None else snapshot
    request = FeatureRequest(
        "stage",
        "admit",
        None,
        freeze_map({"reports": reports, "settings": chosen, "snapshot": session}),
    )
    execute = getattr(feature, "execute", None)
    if not callable(execute):
        raise AssertionError("feature has no execute method")
    return execute(request)


def _peer(result: FeatureResult, role: str) -> Mapping[str, object]:
    peers = result.data["peers"]
    assert isinstance(peers, Mapping)
    peer = peers[role]
    assert isinstance(peer, Mapping)
    return peer


def _calls(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    calls = getattr(devices, "calls", None)
    assert isinstance(calls, list)
    return calls


def _run(test: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(test())
