"""Direct timings from the task 31 provider."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g31.implementation import create
from patrol.ground.extensions.g31.metrics import METRIC_NAMES
from patrol.ground.extensions.g31.samples import (
    ACTIVATION_MS,
    DOG_CAMERA_MS,
    GOAL_MS,
    HOLD_MS,
    LANDING_MS,
    PROXIMITY_MS,
    TARGET_MS,
    empty_journal,
    evaluation_manifest,
    full_journal,
    load_example,
    request_payload,
    without_dog_camera,
    without_landing,
)
from patrol.ground.kernel.contracts import FeatureRequest, FeatureResult
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import build_test_services


def test_full_journal_fills_every_interval(tmp_path: Path) -> None:
    result = _run(tmp_path, request_payload(full_journal()))
    assert result.status == "ok"
    assert result.error is None
    assert result.data["run_id"] == "demo-20261104-001"
    assert result.data["evidence"] == "simulated"
    assert result.data["metric_names"] == list(METRIC_NAMES)
    assert _seconds(result, "mission_start_to_drone_target_s") == _gap(0, TARGET_MS)
    assert _seconds(result, "detection_to_stable_hold_s") == _gap(TARGET_MS, HOLD_MS)
    assert _seconds(result, "stable_hold_to_dog_activation_s") == _gap(HOLD_MS, ACTIVATION_MS)
    assert _seconds(result, "dog_activation_to_dog_camera_s") == _gap(ACTIVATION_MS, DOG_CAMERA_MS)
    assert _seconds(result, "mission_start_to_proximity_s") == _gap(0, PROXIMITY_MS)
    assert _seconds(result, "dog_activation_to_proximity_s") == _gap(ACTIVATION_MS, PROXIMITY_MS)
    assert _seconds(result, "goal_to_verified_landing_s") == _gap(GOAL_MS, LANDING_MS)
    assert _count(result, "dropped_stale_frame_count") == 1
    assert _count(result, "beacon_epoch_resets") == 1
    assert _count(result, "no_progress_stops") == 1
    assert _count(result, "blocked_candidate_events") == 1
    accuracy = _metric(result, "model_accuracy")
    assert accuracy["accuracy"] is None
    assert accuracy["unavailable_reason"] == "no_labeled_evaluation"
    denominators = result.data["denominators"]
    assert isinstance(denominators, dict)
    assert denominators["journal_records"] == len(full_journal())
    assert denominators["labeled_images"] is None
    assert denominators["commands"] >= 1


def test_missing_landing_is_null_and_named(tmp_path: Path) -> None:
    result = _run(tmp_path, request_payload(without_landing()))
    row = _metric(result, "goal_to_verified_landing_s")
    assert row["seconds"] is None
    assert row["unavailable_reason"] == "landing_unverified"
    assert _seconds(result, "mission_start_to_drone_target_s") == _gap(0, TARGET_MS)
    assert _seconds(result, "goal_to_verified_landing_s") is None


def test_missing_dog_acquisition_keeps_detection(tmp_path: Path) -> None:
    result = _run(tmp_path, request_payload(without_dog_camera()))
    row = _metric(result, "dog_activation_to_dog_camera_s")
    assert row["seconds"] is None
    assert row["unavailable_reason"] == "dog_camera_acquisition_missing"
    assert _seconds(result, "mission_start_to_drone_target_s") == _gap(0, TARGET_MS)
    assert _seconds(result, "detection_to_stable_hold_s") == _gap(TARGET_MS, HOLD_MS)


def test_empty_journal_is_null_not_zero(tmp_path: Path) -> None:
    result = _run(tmp_path, request_payload(empty_journal()))
    encoded = json.dumps(result.data["metrics"])
    assert ": 0" not in encoded
    assert "0.0" not in encoded
    for name in (
        "mission_start_to_drone_target_s",
        "goal_to_verified_landing_s",
        "dog_activation_to_dog_camera_s",
    ):
        row = _metric(result, name)
        assert row["seconds"] is None
        assert row["unavailable_reason"] == "empty_journal"
    drops = _metric(result, "dropped_stale_frame_count")
    assert drops["count"] is None


def test_recompute_is_deterministic(tmp_path: Path) -> None:
    payload = request_payload(full_journal())
    first = _run(tmp_path, payload)
    second = _run(tmp_path, payload)
    assert first.data == second.data


def test_contract_examples_drive_vision_and_rssi(tmp_path: Path) -> None:
    request = load_example("drone-vision-request.json")
    decision = load_example("drone-vision-decision.json")
    window = load_example("pi-rssi-window.json")
    acquired = load_example("event-drone_target_acquired.json")
    dispatched = load_example("event-dog_dispatched.json")
    goal = load_example("event-demo_goal_reached.json")
    unverified = load_example("event-landing_unverified.json")
    for record in (request, decision, window, acquired, dispatched, goal, unverified):
        record["clock_domain"] = "ground"
    result = _run(
        tmp_path,
        request_payload([request, decision, window, acquired, dispatched, goal, unverified]),
    )
    assert result.status == "ok"
    pairs = _metric(result, "vision_latency_s")["pairs"]
    assert isinstance(pairs, list)
    drone = next(
        row for row in pairs if isinstance(row, dict) and row["request_id"] == "vision-drone-001"
    )
    assert drone["seconds"] == 0.1
    assert drone["clock"] == "utc_sent_at"
    counts = _metric(result, "rssi_windows_by_quality")["counts"]
    assert counts == {"valid": 1}
    assert (
        _metric(result, "goal_to_verified_landing_s")["unavailable_reason"] == "landing_unverified"
    )


def test_labeled_evaluation_is_not_orchestration_success(tmp_path: Path) -> None:
    payload = request_payload(full_journal(), evaluation=evaluation_manifest())
    result = _run(tmp_path, payload)
    accuracy = _metric(result, "model_accuracy")
    assert accuracy["accuracy"] == 0.5
    assert accuracy["precision"] == 0.5
    assert accuracy["recall"] == 0.5
    assert accuracy["tp"] == 1
    assert accuracy["fp"] == 1
    assert accuracy["tn"] == 1
    assert accuracy["fn"] == 0
    assert accuracy["reviews"] == 1
    assert accuracy["unavailable_reason"] is None
    plain = _run(tmp_path, request_payload(full_journal()))
    assert _metric(plain, "model_accuracy")["unavailable_reason"] == "no_labeled_evaluation"


def _run(tmp_path: Path, payload: dict[str, object]) -> FeatureResult:
    services = build_test_services(output_dir=tmp_path)

    async def invoke() -> FeatureResult:
        feature = create(services)
        result = await feature.execute(
            FeatureRequest("projection", "feature.v2_metrics", None, freeze_map(payload))
        )
        assert services.state.trace == []  # type: ignore[attr-defined]
        return result

    return asyncio.run(invoke())


def _metric(result: FeatureResult, name: str) -> dict[str, object]:
    metrics = result.data["metrics"]
    assert isinstance(metrics, dict)
    row = metrics[name]
    assert isinstance(row, dict)
    return row


def _seconds(result: FeatureResult, name: str) -> object:
    return _metric(result, name)["seconds"]


def _count(result: FeatureResult, name: str) -> object:
    return _metric(result, name)["count"]


def _gap(start_ms: int, end_ms: int) -> float:
    return (end_ms - start_ms) / 1000
