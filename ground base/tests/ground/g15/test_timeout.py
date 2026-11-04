"""A timeout retires the request id and does not send it again."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g15.support import call, frame, manual, opened, payload, run, settings


def test_default_timeout_does_not_resend_and_the_old_frame_is_stale(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        original = frame(built, "same")
        first = await call(port, payload(built, "same", frame=original))
        first_id = first.data["request_id"]
        manual(built).advance(5.001)
        quiet = await call(port, {"settings": settings(), "sample": True})
        retry = await call(port, payload(built, "same", frame=original))
        assert first_id == "vision-001"
        assert quiet.data["outcome"] == "expired"
        assert quiet.data["message"] is None
        assert quiet.data["expired_request_id"] == first_id
        assert retry.data["outcome"] == "dropped"
        assert retry.data["message"] is None
        assert retry.data["request_id"] is None
        assert first_id in retry.data["unusable_request_ids"]

    run(body)


def test_retry_after_a_shorter_timeout_uses_a_new_id_for_the_same_frame(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        original = frame(built, "same")
        short = settings(timeout_ms=1000)
        first = await call(port, payload(built, "same", frame=original, settings=short))
        assert first.data["request_id"] == "vision-001"
        manual(built).advance(1.001)
        quiet = await call(port, {"settings": short, "sample": True})
        retry = await call(port, payload(built, "same", frame=original, settings=short))
        assert quiet.data["message"] is None
        assert quiet.data["expired_request_id"] == "vision-001"
        assert retry.data["outcome"] == "emitted"
        assert retry.data["request_id"] == "vision-002"
        assert retry.data["frame_id"] == "same"
        assert "vision-001" in retry.data["unusable_request_ids"]
        assert retry.data["message"] is not None

    run(body)


def test_request_ids_stay_unique_across_epochs(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        first = await call(port, payload(built, "one"))
        manual(built).advance(1)
        second = await call(port, payload(built, "two", settings=settings(epoch=2), settle=True))
        assert first.data["request_id"] == "vision-001"
        assert second.data["request_id"] == "vision-002"
        assert "vision-001" in second.data["unusable_request_ids"]

    run(body)
