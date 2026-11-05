"""Obstacle clearance stays out of any target-range field."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g20.support import (
    as_object,
    calls_of,
    candidates,
    feature,
    first_candidate,
    forbid_target_range,
    ids_of,
    observation,
    payload,
    readiness_of,
    request,
    run,
)


def test_clearance_is_stored_and_not_a_target_range(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        result = await port.execute(request(payload()))
        assert readiness_of(result)["minimum_clearance_m"] == 0.8
        assert "target_range" not in result.data
        assert "range_m" not in result.data
        forbid_target_range(result.data)
        for event in result.events:
            forbid_target_range(event.payload)
            assert event.payload["commands"] == ()
        assert calls_of(built) == []

    run(body)


def test_candidate_target_range_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        first_candidate(message)["target_range_m"] = 1.2
        built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert ids_of(result) == ()
        assert readiness_of(result)["minimum_clearance_m"] == 0.8
        forbid_target_range(result.data)
        assert result.data["commands"] == ()
        assert calls_of(built) == []

    run(body)


def test_observation_target_range_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["target_range_m"] = 1.5
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert ids_of(result) == ()
        forbid_target_range(result.data)

    run(body)


def test_missing_lidar_measurement_rejects_a_candidate_list(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["lidar_observed_at"] = None
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert ids_of(result) == ()
        assert readiness_of(result)["minimum_clearance_m"] == 0.8

    run(body)


def test_null_clearance_rejects_a_candidate_list(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["minimum_clearance_m"] = None
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "validation_failed"
        assert ids_of(result) == ()

    run(body)


def test_capability_target_range_flag_is_not_a_distance(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload()))
        assert result.status == "ok"
        forbid_target_range(result.data)
        assert readiness_of(result)["minimum_clearance_m"] == 0.8

    run(body)
