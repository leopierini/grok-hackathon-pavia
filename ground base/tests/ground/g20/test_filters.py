"""Expiry, map epoch, frame, and mode mismatches do not become steps."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from patrol.ground.kernel.clock import ManualClock
from tests.ground.g20.support import (
    CANDIDATE,
    as_object,
    candidates,
    capabilities,
    feature,
    first_candidate,
    ids_of,
    observation,
    payload,
    request,
    run,
)

_DEADLINE = datetime(2026, 11, 4, 13, 0, 10, 500000, tzinfo=UTC)


def test_expired_candidate_is_dropped(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        clock = built.kernel.clock
        assert isinstance(clock, ManualClock)
        clock.advance((_DEADLINE - clock.utc_now()).total_seconds())
        result = await port.execute(request(payload()))
        assert result.status == "ok"
        assert ids_of(result) == ()
        assert result.data["ready"] is False
        assert result.data["dropped"] == "expired"
        assert result.data["commands"] == ()

    run(body)


def test_valid_until_equal_to_now_is_not_in_the_future(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        clock = built.kernel.clock
        assert isinstance(clock, ManualClock)
        delta = (_DEADLINE - clock.utc_now()).total_seconds()
        clock.advance(delta)
        result = await port.execute(request(payload()))
        assert ids_of(result) == ()
        assert result.data["dropped"] == "expired"

    run(body)


def test_other_map_epoch_is_dropped(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(map_epoch=2)))
        assert result.status == "ok"
        assert ids_of(result) == ()
        assert result.data["dropped"] == "map_epoch"
        assert result.data["pose_map_epoch"] == 1
        assert result.data["map_epoch"] == 2
        assert result.data["ready"] is False

    run(body)


def test_candidate_epoch_disagreement_is_dropped(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        first_candidate(message)["map_epoch"] = 9
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert ids_of(result) == ()
        assert result.data["dropped"] == "map_epoch"

    run(body)


def test_wrong_body_frame_is_dropped(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        first_candidate(message)["frame_id"] = "museum/map"
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "ok"
        assert ids_of(result) == ()
        assert result.data["dropped"] == "frame"

    run(body)


def test_unsafe_candidate_is_dropped(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        first_candidate(message)["safe"] = False
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert ids_of(result) == ()
        assert result.data["dropped"] == "unsafe"

    run(body)


def test_slam_mode_without_capability_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        message = capabilities()
        features = as_object(as_object(message["payload"], "payload")["features"], "features")
        features["slam"] = False
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(capability_message=message)))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert ids_of(result) == ()
        assert result.data["ready"] is False

    run(body)


def test_mode_mismatch_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        as_object(message["payload"], "payload")["navigation_mode"] = "reactive_avoidance"
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert ids_of(result) == ()

    run(body)


def test_safe_ids_keep_dog_order(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        body_map = as_object(message["payload"], "payload")
        first = first_candidate(message)
        unsafe = dict(first)
        unsafe["candidate_id"] = "candidate-side"
        unsafe["safe"] = False
        later = dict(first)
        later["candidate_id"] = "candidate-yaw"
        later["delta_yaw_rad"] = 0.2
        body_map["candidates"] = [unsafe, first, later]
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "ok"
        assert ids_of(result) == (CANDIDATE, "candidate-yaw")

    run(body)


def test_string_safe_flag_is_not_coerced(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        first_candidate(message)["safe"] = "true"
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert ids_of(result) == ()

    run(body)


def test_duplicate_candidate_ids_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        first = first_candidate(message)
        as_object(message["payload"], "payload")["candidates"] = [first, dict(first)]
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"

    run(body)


def test_reactive_mode_does_not_require_slam(tmp_path: Path) -> None:
    async def body() -> None:
        observed = observation()
        nav = candidates()
        armed = capabilities()
        as_object(observed["payload"], "payload")["navigation_mode"] = "reactive_avoidance"
        as_object(observed["payload"], "payload")["slam_state"] = "not_available"
        as_object(nav["payload"], "payload")["navigation_mode"] = "reactive_avoidance"
        features = as_object(as_object(armed["payload"], "payload")["features"], "features")
        features["slam"] = False
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(
                payload(
                    observation_message=observed,
                    candidate_message=nav,
                    capability_message=armed,
                )
            )
        )
        assert result.status == "ok"
        assert ids_of(result) == (CANDIDATE,)
        assert result.data["ready"] is True

    run(body)
