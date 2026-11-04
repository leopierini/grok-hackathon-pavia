"""One request in flight, and the newest fresh frame wins."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g15.support import call, frame, manual, opened, payload, payload_of, run, settings


def test_a_frame_200ms_later_is_held_while_the_first_request_is_in_flight(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        first = await call(port, payload(built, "a"))
        manual(built).advance(0.2)
        second = await call(port, payload(built, "b"))
        assert first.data["outcome"] == "emitted"
        assert second.data["outcome"] == "held"
        assert second.data["message"] is None
        assert second.data["held_frame_id"] == "b"
        assert second.data["request_id"] == first.data["request_id"]
        assert second.data["in_flight"] is True

    run(body)


def test_interval_elapsed_still_holds_while_a_request_is_in_flight(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        first = await call(port, payload(built, "a"))
        manual(built).advance(1.5)
        second = await call(port, payload(built, "b"))
        assert second.data["outcome"] == "held"
        assert second.data["message"] is None
        assert second.data["request_id"] == first.data["request_id"]

    run(body)


def test_three_frames_in_flight_keep_only_the_newest(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        clock = manual(built)
        await call(port, payload(built, "a"))
        clock.advance(0.2)
        await call(port, payload(built, "b"))
        clock.advance(0.2)
        await call(port, payload(built, "c"))
        clock.advance(0.4)
        held = await call(port, payload(built, "d"))
        clock.advance(0.2)
        follow = await call(port, {"settings": settings(), "settle": True, "sample": True})
        assert held.data["held_frame_id"] == "d"
        assert held.data["dropped_frame_count"] == 2
        assert follow.data["outcome"] == "emitted"
        follow_frame = payload_of(follow)["frame"]
        assert isinstance(follow_frame, dict)
        assert follow_frame["frame_id"] == "d"

    run(body)


def test_a_burst_emits_one_request_for_the_newest_frame(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        clock = manual(built)
        older = frame(built, "older")
        clock.advance(0.1)
        mid = frame(built, "mid")
        clock.advance(0.1)
        newest = frame(built, "newest")
        result = await call(
            port,
            {
                "stage": "drone_search",
                "target_description": "A person in the operator-marked closed demo area.",
                "settings": settings(),
                "active_track_id": None,
                "frames": [older, mid, newest],
            },
        )
        assert result.data["outcome"] == "emitted"
        assert result.data["dropped_frame_count"] == 2
        assert result.data["frame_id"] == "newest"
        assert payload_of(result)["request_id"] == "vision-001"

    run(body)


def test_sample_interval_holds_the_next_frame_until_1000ms(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        clock = manual(built)
        await call(port, payload(built, "first"))
        settled = await call(port, {"settings": settings(), "settle": True})
        clock.advance(0.2)
        held = await call(port, payload(built, "second"))
        clock.advance(0.8)
        follow = await call(port, {"settings": settings(), "sample": True})
        assert settled.data["message"] is None
        assert held.data["outcome"] == "held"
        assert follow.data["outcome"] == "emitted"
        assert follow.data["frame_id"] == "second"

    run(body)


def test_an_older_frame_does_not_replace_the_held_frame(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        clock = manual(built)
        await call(port, payload(built, "a"))
        clock.advance(0.2)
        older = frame(built, "older")
        clock.advance(0.2)
        newer = frame(built, "newer")
        await call(port, payload(built, "newer", frame=newer))
        replaced = await call(port, payload(built, "older", frame=older))
        assert replaced.data["held_frame_id"] == "newer"
        assert replaced.data["dropped_on_call"] == 1

    run(body)
