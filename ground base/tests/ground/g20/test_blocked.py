"""A blocked empty list is a stop-and-review observation, not a detour."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g20.support import (
    as_object,
    calls_of,
    candidates,
    feature,
    ids_of,
    payload,
    request,
    run,
)


def test_blocked_empty_list_stays_empty(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        body_map = as_object(message["payload"], "payload")
        body_map["candidates"] = []
        body_map["blocked"] = True
        body_map["reason"] = "No safe local step."
        built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "ok"
        assert result.error is None
        assert ids_of(result) == ()
        assert result.data["blocked"] is True
        assert result.data["ready"] is False
        assert result.data["ready_to_wait"] is True
        assert result.data["commands"] == ()
        assert result.data["reason"] == "ready_to_wait"
        assert calls_of(built) == []

    run(body)


def test_blocked_with_candidates_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        as_object(message["payload"], "payload")["blocked"] = True
        built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert ids_of(result) == ()
        assert result.data["ready_to_wait"] is False
        assert result.data["commands"] == ()
        assert calls_of(built) == []

    run(body)


def test_unblocked_empty_list_invents_nothing(tmp_path: Path) -> None:
    async def body() -> None:
        message = candidates()
        body_map = as_object(message["payload"], "payload")
        body_map["candidates"] = []
        body_map["blocked"] = False
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "ok"
        assert ids_of(result) == ()
        assert result.data["ready"] is False
        assert result.data["ready_to_wait"] is False
        assert result.data["reason"] == "no_candidate"

    run(body)
