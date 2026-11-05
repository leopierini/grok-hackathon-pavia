"""Dog-camera handoff: two fresh matches switch the mode, and nothing else moves."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.contract import Frame, Incident
from patrol.ground.extensions.g25.implementation import DogAcquire, create
from patrol.ground.extensions.g25.samples import build, fixture
from patrol.ground.extensions.g25.scenarios import cases
from patrol.ground.kernel.contracts import FeatureRequest, FeatureResult, Ticket
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings
from patrol.ground.testing.builders import build_test_services


def test_scenario_names_match_payloads() -> None:
    assert [case.case_id for case in cases(0)] == [
        "two_fresh_hits",
        "one_hit",
        "not_visible_resets",
        "drone_frame",
        "second_track",
        "stale_frame",
        "empty_detections",
        "multiple_strangers",
        "unlabeled_person",
        "epoch_mismatch",
        "suggestion_ignored",
        "threshold_three",
        "drone_between_hits",
        "homing_disabled",
        "example_contract",
        "rssi_records_kept",
        "no_goal_no_command",
        "cancelled",
    ]


def test_contract_example_is_one_hit_and_does_not_switch() -> None:
    services = build_test_services(output_dir=Path("artifacts") / "g25-example")
    result = asyncio.run(_run(create(services), build("example_contract")))
    decision = fixture("dog-vision-decision.json")
    assert result.status == "ok"
    assert result.data["mode"] == "rssi"
    assert result.data["phase"] == "acquiring"
    assert result.data["hit_count"] == 1
    assert result.data["frame_ids"] == ("dog-front-001",)
    assert result.data["handoff"] is False
    assert result.events == ()
    payload = decision["payload"]
    assert isinstance(payload, dict)
    assert payload["suggested_action"] == "switch_to_dog_vision"
    _assert_no_motion(result, services)


def test_two_fresh_hits_hand_off_and_keep_rssi() -> None:
    services = build_test_services(output_dir=Path("artifacts") / "g25-visual")
    calls = _calls(services)
    result = asyncio.run(_run(create(services), build("two_fresh_hits")))
    assert result.status == "ok"
    assert result.data["mode"] == "visual"
    assert result.data["phase"] == "handed_off"
    assert result.data["rssi_role"] == "supporting"
    assert result.data["hit_count"] == 2
    assert result.data["frame_ids"] == ("dog-front-001", "dog-front-002")
    assert result.data["handoff"] is True
    assert result.data["command"] is None
    assert result.data["goal_reached"] is False
    assert result.data["arrival_confirmed"] is False
    assert result.data["rssi_selection"] is None
    records = result.data["rssi_records"]
    assert isinstance(records, tuple) and len(records) == 1
    window = records[0]
    assert isinstance(window, Mapping)
    assert window["message_id"] == "msg-pi-rssi-window"
    body = window["payload"]
    assert isinstance(body, Mapping)
    assert body["median_rssi_dbm"] == -60
    assert isinstance(body["samples"], list) and len(body["samples"]) == 3
    assert result.events[0].kind == "decision_received"
    assert result.events[0].payload["event"] == "dog_vision_handoff"
    assert result.events[0].payload["frame_ids"] == ("dog-front-001", "dog-front-002")
    journal = result.data["journal"]
    expected = json.loads(
        (repo_root() / "fixtures" / "ground" / "g25" / "handoff-event.json").read_text(
            encoding="utf-8"
        )
    )
    assert journal == expected
    assert calls == _calls(services)
    _assert_no_motion(result, services)


def test_history_starts_with_the_contract_decision() -> None:
    history = fixture("history.json")
    example = fixture("dog-vision-decision.json")
    decisions = history["decisions"]
    assert isinstance(decisions, list)
    assert decisions[0] == example


def test_one_hit_stays_acquiring_even_when_the_model_says_switch() -> None:
    result = asyncio.run(_stage("suggestion_ignored"))
    assert result.data["mode"] == "rssi"
    assert result.data["phase"] == "acquiring"
    assert result.data["rssi_role"] == "primary"
    assert result.data["handoff"] is False


def test_not_visible_between_hits_prevents_the_switch() -> None:
    result = asyncio.run(_stage("not_visible_resets"))
    assert result.data["mode"] == "rssi"
    assert result.data["phase"] == "acquiring"
    assert result.data["hit_count"] == 1
    assert result.data["frame_ids"] == ("dog-front-002",)
    assert result.data["resets"] == ("not_visible",)
    assert result.data["handoff"] is False


def test_drone_camera_is_rejected() -> None:
    result = asyncio.run(_stage("drone_frame"))
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert result.data["mode"] == "rssi"
    assert result.data["handoff"] is False
    assert result.data["frame_ids"] == ()


def test_wrong_track_multiple_and_unlabeled_force_review() -> None:
    mismatched = asyncio.run(_stage("second_track"))
    strangers = asyncio.run(_stage("multiple_strangers"))
    unlabeled = asyncio.run(_stage("unlabeled_person"))
    for result in (mismatched, strangers, unlabeled):
        assert result.status == "ok"
        assert result.data["mode"] == "review"
        assert result.data["handoff"] is False
        assert result.data["rssi_role"] == "primary"
        assert result.events == ()


def test_stale_frame_and_empty_detections_do_not_switch() -> None:
    stale = asyncio.run(_stage("stale_frame"))
    empty = asyncio.run(_stage("empty_detections"))
    assert stale.data["mode"] == "rssi"
    assert stale.data["hit_count"] == 0
    assert stale.data["resets"] == ("stale",)
    assert empty.data["resets"] == ("empty",)
    assert empty.data["handoff"] is False


def test_wrong_epoch_rejects_the_handoff() -> None:
    result = asyncio.run(_stage("epoch_mismatch"))
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.detail == "rejected:camera_epoch"
    assert result.data["handoff"] is False


def test_threshold_three_keeps_two_hits_on_rssi() -> None:
    result = asyncio.run(_stage("threshold_three"))
    assert result.data["phase"] == "acquiring"
    assert result.data["hit_count"] == 2
    assert result.data["rssi_role"] == "primary"
    assert result.data["handoff"] is False


def test_drone_frame_between_dog_hits_does_not_reset() -> None:
    result = asyncio.run(_stage("drone_between_hits"))
    assert result.data["mode"] == "visual"
    assert result.data["frame_ids"] == ("dog-front-001", "dog-front-002")
    assert result.data["rssi_selection"] is None


def test_homing_disabled_on_a_miss_does_not_stay_on_rssi() -> None:
    result = asyncio.run(_stage("homing_disabled"))
    assert result.data["mode"] == "review"
    assert result.data["resets"] == ("not_visible",)


def test_string_boolean_and_bad_box_are_rejected() -> None:
    payload = build("one_hit")
    payload["homing_allowed"] = "true"
    bool_result = asyncio.run(_stage_payload(payload))
    assert bool_result.status == "failed"
    assert bool_result.error is not None
    assert bool_result.error.code == "invalid_input"

    broken = build("one_hit")
    decisions = broken["decisions"]
    assert isinstance(decisions, list)
    body = decisions[0]["payload"]
    assert isinstance(body, dict)
    detections = body["detections"]
    assert isinstance(detections, list)
    box = detections[0]["box_xyxy_norm"]
    assert isinstance(box, list)
    box[0] = 0.9
    box_result = asyncio.run(_stage_payload(broken))
    assert box_result.status == "failed"
    assert box_result.error is not None
    assert box_result.error.code == "validation_failed"


def test_cancelled_ticket_does_not_hand_off() -> None:
    services = build_test_services(output_dir=Path("artifacts") / "g25-cancel")
    ticket = services.kernel.authority.issue("demo-20261104-001", "dog_acquire")
    services.kernel.authority.latch_cancel("operator halt")
    feature = create(services)
    request = FeatureRequest("stage", "dog_acquire", ticket, build("two_fresh_hits"))

    async def body() -> FeatureResult:
        assert isinstance(feature, DogAcquire)
        return await feature.execute(request)

    result = asyncio.run(body())
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "cancelled"
    assert result.data["handoff"] is False
    assert result.events == ()


def test_stale_ticket_is_not_a_handoff() -> None:
    services = build_test_services(output_dir=Path("artifacts") / "g25-stale-ticket")
    ticket = services.kernel.authority.issue("demo-20261104-001", "dog_acquire")
    services.kernel.authority.reset_generation("verified recovery")
    feature = create(services)
    request = FeatureRequest("stage", "dog_acquire", ticket, build("two_fresh_hits"))

    async def body() -> FeatureResult:
        assert isinstance(feature, DogAcquire)
        return await feature.execute(request)

    result = asyncio.run(body())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "stale_ticket"
    assert result.data["goal_reached"] is False


def test_default_threshold_is_two() -> None:
    payload = build("two_fresh_hits")
    del payload["consecutive_hit_threshold"]
    result = asyncio.run(_stage_payload(payload))
    assert result.data["mode"] == "visual"
    assert result.data["hit_count"] == 2


def test_dog_approach_stage_counts_as_a_dog_hit() -> None:
    payload = build("example_contract")
    requests = payload["requests"]
    assert isinstance(requests, list)
    request = requests[0]
    assert isinstance(request, dict)
    body = request["payload"]
    assert isinstance(body, dict)
    body["stage"] = "dog_approach"
    result = asyncio.run(_stage_payload(payload))
    assert result.status == "ok"
    assert result.data["phase"] == "acquiring"
    assert result.data["hit_count"] == 1
    assert result.data["handoff"] is False


def test_repeating_one_frame_is_not_a_second_hit() -> None:
    payload = build("two_fresh_hits")
    decisions = payload["decisions"]
    frames = payload["frames"]
    assert isinstance(decisions, list) and isinstance(frames, list)
    second = decisions[1]
    assert isinstance(second, dict)
    body = second["payload"]
    assert isinstance(body, dict)
    first = frames[0]
    assert isinstance(first, dict)
    body["frame_id"] = first["frame_id"]
    body["frame_captured_at"] = first["captured_at"]
    payload["frames"] = [first]
    result = asyncio.run(_stage_payload(payload))
    assert result.data["mode"] == "rssi"
    assert result.data["phase"] == "acquiring"
    assert result.data["hit_count"] == 1
    assert result.data["frame_ids"] == ("dog-front-001",)
    assert result.data["handoff"] is False


def test_uncertain_resets_the_streak() -> None:
    payload = build("not_visible_resets")
    decisions = payload["decisions"]
    assert isinstance(decisions, list)
    gap = decisions[1]
    assert isinstance(gap, dict)
    body = gap["payload"]
    assert isinstance(body, dict)
    body["target_state"] = "uncertain"
    result = asyncio.run(_stage_payload(payload))
    assert result.data["mode"] == "rssi"
    assert result.data["hit_count"] == 1
    assert result.data["resets"] == ("uncertain",)
    assert result.data["handoff"] is False


def test_handoff_event_can_be_applied_by_state() -> None:
    services = build_test_services(output_dir=Path("artifacts") / "g25-apply")
    ticket = services.kernel.authority.issue("demo-20261104-001", "dog_acquire")
    feature = create(services)
    request = FeatureRequest("stage", "dog_acquire", ticket, build("two_fresh_hits"))

    async def body() -> FeatureResult:
        assert isinstance(feature, DogAcquire)
        return await feature.execute(request)

    result = asyncio.run(body())
    assert result.events[0].kind == "decision_received"
    frame = Frame("phone.jpg", "phone", "room_2", "2026-11-04T13:00:00Z", True)
    incident = Incident("demo-20261104-001", "room_2", "staged person", frame)
    services.state.open(incident, make_settings())
    snapshot = services.state.apply(result.events[0], expected_ticket=ticket)
    assert snapshot.arrival_confirmed is None
    assert snapshot.phase == "ASSESS"


def test_owned_cases_pass_the_kernel_simulator() -> None:
    services = build_test_services(output_dir=Path("artifacts") / "g25-sim")
    feature = create(services)

    async def body() -> tuple[str, ...]:
        failures: list[str] = []
        for case in cases(0):
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            failures.extend(report.failures)
        return tuple(failures)

    assert asyncio.run(body()) == ()


def test_factory_rejects_a_non_service() -> None:
    try:
        create(Ticket("demo", 0, "dog_acquire"))  # type: ignore[arg-type]
    except Exception as exc:
        assert getattr(getattr(exc, "error", None), "code", "") == "invalid_input"
    else:
        raise AssertionError("factory accepted a ticket")


async def _stage(case_id: str) -> FeatureResult:
    return await _stage_payload(build(case_id))


async def _stage_payload(payload: dict[str, object]) -> FeatureResult:
    services = build_test_services(output_dir=Path("artifacts") / "g25-stage")
    return await _run(create(services), payload)


async def _run(feature: object, payload: Mapping[str, object]) -> FeatureResult:
    execute = feature.execute  # type: ignore[attr-defined]
    result = await execute(FeatureRequest("stage", "dog_acquire", None, payload))
    assert isinstance(result, FeatureResult)
    return result


def _calls(services: object) -> list[str]:
    adapters = services.adapters  # type: ignore[attr-defined]
    devices = adapters.devices  # type: ignore[attr-defined]
    calls = devices.calls  # type: ignore[attr-defined]
    assert isinstance(calls, list)
    return list(calls)


def _assert_no_motion(result: FeatureResult, services: object) -> None:
    assert result.data["command"] is None
    assert result.data["goal_reached"] is False
    assert result.data["arrival_confirmed"] is False
    assert _calls(services) == []
