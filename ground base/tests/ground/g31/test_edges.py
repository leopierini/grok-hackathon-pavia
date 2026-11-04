"""Edge cases that the scripted mission does not already cover."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g31.implementation import create
from patrol.ground.extensions.g31.samples import (
    TARGET_MS,
    full_journal,
    load_example,
    request_payload,
    with_extra_drop,
)
from patrol.ground.kernel.contracts import FeatureRequest, FeatureResult, Ticket
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import build_test_services


def test_extra_drops_do_not_shrink_vision_latency(tmp_path: Path) -> None:
    result = _run(tmp_path, request_payload(with_extra_drop()))
    assert _count(result) == 2
    pairs = _metric(result, "vision_latency_s")["pairs"]
    assert isinstance(pairs, list)
    drone = next(
        row for row in pairs if isinstance(row, dict) and row["request_id"] == "vision-drone-001"
    )
    assert drone["seconds"] == 0.2
    assert drone["unavailable_reason"] is None


def test_cross_clock_subtraction_is_rejected(tmp_path: Path) -> None:
    rows = full_journal()
    for row in rows:
        if row.get("message_id") == "msg-event-drone_target_acquired":
            row["clock_domain"] = "drone_monotonic"
    result = _run(tmp_path, request_payload(rows))
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert "ground" in result.error.detail
    assert "drone_monotonic" in result.error.detail
    assert "metrics" not in result.data


def test_peer_monotonic_is_not_subtracted(tmp_path: Path) -> None:
    rows = full_journal()
    for row in rows:
        if row.get("message_id") == "msg-event-drone_target_acquired":
            row["peer_monotonic_ms"] = 50
    result = _run(tmp_path, request_payload(rows))
    assert _metric(result, "mission_start_to_drone_target_s")["seconds"] == TARGET_MS / 1000


def test_duplicate_message_keeps_the_first_target(tmp_path: Path) -> None:
    rows = full_journal()
    duplicate = dict(
        next(row for row in rows if row["message_id"] == "msg-event-drone_target_acquired")
    )
    duplicate["monotonic_ms"] = 9000
    rows.append(duplicate)
    result = _run(tmp_path, request_payload(rows))
    assert _metric(result, "mission_start_to_drone_target_s")["seconds"] == TARGET_MS / 1000
    denominators = result.data["denominators"]
    assert isinstance(denominators, dict)
    assert denominators["journal_records"] == denominators["records_used"] + 1


def test_track_mismatch_does_not_count_as_acquisition(tmp_path: Path) -> None:
    rows = full_journal()
    decision = next(row for row in rows if row["message_id"] == "msg-dog-vision-decision")
    payload = decision["payload"]
    assert isinstance(payload, dict)
    detections = payload["detections"]
    assert isinstance(detections, list)
    first = detections[0]
    assert isinstance(first, dict)
    first["track_id"] = "other-person"
    result = _run(tmp_path, request_payload(rows))
    row = _metric(result, "dog_activation_to_dog_camera_s")
    assert row["seconds"] is None
    assert row["unavailable_reason"] == "track_mismatch"
    assert _metric(result, "mission_start_to_drone_target_s")["seconds"] == TARGET_MS / 1000


def test_clear_candidate_list_is_not_a_block(tmp_path: Path) -> None:
    sample = load_example("dog-navigation-candidates.json")
    sample["monotonic_ms"] = 1000
    sample["clock_domain"] = "ground"
    result = _run(tmp_path, request_payload([sample]))
    assert _count(result, "blocked_candidate_events") == 0


def test_secret_field_is_not_copied(tmp_path: Path) -> None:
    rows = full_journal()
    rows[0]["api_key"] = "sk-test-not-real"
    result = _run(tmp_path, request_payload(rows))
    assert "sk-test-not-real" not in json.dumps(result.data, default=str)
    assert result.data["rejected_fields"] == ["api_key"]


def test_string_boolean_is_rejected(tmp_path: Path) -> None:
    payload = request_payload(full_journal())
    clock = dict(payload["clock"])  # type: ignore[arg-type]
    clock["utc_pairs_allowed"] = "true"
    payload["clock"] = clock
    result = _run(tmp_path, payload)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"


def test_journal_string_is_rejected(tmp_path: Path) -> None:
    payload = request_payload([])
    payload["journal"] = "not-a-list"
    result = _run(tmp_path, payload)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"


def test_events_alias_matches_journal(tmp_path: Path) -> None:
    payload = request_payload(full_journal())
    journal = payload.pop("journal")
    payload["events"] = journal
    result = _run(tmp_path, payload)
    assert result.status == "ok"
    assert _metric(result, "mission_start_to_drone_target_s")["seconds"] == TARGET_MS / 1000


def test_cancelled_ticket_is_rejected(tmp_path: Path) -> None:
    services = build_test_services(output_dir=tmp_path)
    ticket = services.kernel.authority.issue("demo-20261104-001", "metrics")
    services.kernel.authority.latch_cancel("operator halt")

    async def invoke() -> FeatureResult:
        feature = create(services)
        return await feature.execute(
            FeatureRequest(
                "projection",
                "feature.v2_metrics",
                ticket,
                freeze_map(request_payload(full_journal())),
            )
        )

    result = asyncio.run(invoke())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "cancelled"
    assert isinstance(ticket, Ticket)


def test_stale_frame_that_was_used_is_not_a_fast_latency(tmp_path: Path) -> None:
    rows = full_journal()
    rows.append(
        {
            "message_id": "msg-frame-dropped-used",
            "mission_id": "demo-20261104-001",
            "kind": "scheduler.note",
            "event": "frame_dropped",
            "reason": "stale",
            "frame_id": "drone-downward-001",
            "simulated": True,
            "monotonic_ms": 1100,
            "clock_domain": "ground",
        }
    )
    result = _run(tmp_path, request_payload(rows))
    pairs = _metric(result, "vision_latency_s")["pairs"]
    assert isinstance(pairs, list)
    drone = next(
        row for row in pairs if isinstance(row, dict) and row["request_id"] == "vision-drone-001"
    )
    assert drone["seconds"] is None
    assert drone["unavailable_reason"] == "stale_frame_dropped"
    assert _count(result) == 2


def test_raw_completed_airborne_ack_is_not_a_landing(tmp_path: Path) -> None:
    goal = load_example("event-demo_goal_reached.json")
    land = load_example("ground-to-drone-land.json")
    done = load_example("drone-ack-completed.json")
    for index, record in enumerate((goal, land, done), start=1):
        record["monotonic_ms"] = 8000 + index * 100
        record["clock_domain"] = "ground"
    result = _run(tmp_path, request_payload([goal, land, done]))
    row = _metric(result, "goal_to_verified_landing_s")
    assert row["seconds"] is None
    assert row["unavailable_reason"] == "verified_landing_missing"


def _run(tmp_path: Path, payload: dict[str, object]) -> FeatureResult:
    services = build_test_services(output_dir=tmp_path)

    async def invoke() -> FeatureResult:
        feature = create(services)
        return await feature.execute(
            FeatureRequest("projection", "feature.v2_metrics", None, freeze_map(payload))
        )

    return asyncio.run(invoke())


def _metric(result: FeatureResult, name: str) -> dict[str, object]:
    metrics = result.data["metrics"]
    assert isinstance(metrics, dict)
    row = metrics[name]
    assert isinstance(row, dict)
    return row


def _count(result: FeatureResult, name: str = "dropped_stale_frame_count") -> object:
    return _metric(result, name)["count"]
