"""Evidence age and clock uncertainty."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g15.support import call, frame, manual, opened, payload, run, settings


def test_a_frame_older_than_3000ms_is_dropped(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        stale = frame(built, "stale")
        manual(built).advance(3.001)
        result = await call(port, payload(built, "stale", frame=stale))
        assert result.status == "ok"
        assert result.data["outcome"] == "dropped"
        assert result.data["drop_reason"] == "stale"
        assert result.data["message"] is None
        assert result.data["dropped_frame_count"] == 1
        assert result.data["request_id"] is None

    run(body)


def test_a_frame_aged_exactly_3000ms_is_still_fresh(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        fresh = frame(built, "exact")
        manual(built).advance(3)
        result = await call(port, payload(built, "exact", frame=fresh))
        assert result.data["outcome"] == "emitted"
        assert result.data["frame_id"] == "exact"

    run(body)


def test_age_plus_clock_error_cannot_exceed_budget(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        captured = frame(built, "uncertain-age")
        manual(built).advance(2)
        result = await call(
            port, payload(built, "uncertain-age", frame=captured, clock_error_ms=2000)
        )
        assert result.data["outcome"] == "dropped"
        assert result.data["message"] is None

    run(body)


def test_capture_timestamp_precision_is_preserved(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        manual(built).advance(0.1)
        exact = "2026-01-01T00:00:00.012345Z"
        captured = frame(built, "precise", captured_at=exact)
        result = await call(port, payload(built, "precise", frame=captured))
        assert result.data["message"]["payload"]["frame"]["captured_at"] == exact

    run(body)


def test_clock_uncertainty_above_the_age_budget_blocks_emission(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        blocked = await call(port, payload(built, "fresh", clock_error_ms=3001))
        assert blocked.status == "blocked"
        assert blocked.error is not None
        assert blocked.error.code == "rejected"
        assert blocked.data["message"] is None
        assert blocked.data["drop_reason"] == "clock_uncertainty"

    run(body)


def test_clock_error_equal_to_the_budget_still_allows_a_fresh_frame(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        result = await call(port, payload(built, "fresh", clock_error_ms=3000))
        assert result.status == "ok"
        assert result.data["outcome"] == "emitted"

    run(body)


def test_a_future_frame_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        future = frame(built, "future", captured_at="2026-01-01T00:00:02.000Z")
        result = await call(port, payload(built, "future", frame=future))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.data["message"] is None

    run(body)


def test_a_held_frame_is_dropped_when_it_ages_out(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        await call(port, payload(built, "a", in_flight=True))
        manual(built).advance(3.001)
        result = await call(port, {"settings": settings(), "sample": True})
        assert result.data["outcome"] == "dropped"
        assert result.data["drop_reason"] == "stale"
        assert result.data["message"] is None

    run(body)
