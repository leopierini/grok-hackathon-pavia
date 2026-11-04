"""message_id is immutable and command_id conflict does not repeat an action."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from tests.ground.g11.support import calls, load, request_for, run, services
from tests.ground.g11.test_accept import create_port


def test_duplicate_message_returns_the_stored_result(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        port = create_port(built)
        message = load("ground-to-dog-command.json")
        first = await run(port, request_for(message))
        second = await run(port, request_for(message))
        records = getattr(built.journal, "records", [])
        assert first is second
        assert first.status == "ok"
        assert len([record for record in records if record.event == "decision_received"]) == 1
        assert calls(built) == []

    asyncio.run(body())


def test_same_message_id_with_a_different_body_conflicts(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        port = create_port(built)
        original = load("ground-to-dog-command.json")
        changed = load("ground-to-dog-command.json")
        changed["seq"] = 99
        first = await run(port, request_for(original))
        second = await run(port, request_for(changed))
        assert first.status == "ok"
        assert second.error is not None
        assert second.error.detail == "message_immutable"
        assert calls(built) == []

    asyncio.run(body())


def test_same_command_id_is_idempotent_until_the_payload_changes(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        port = create_port(built)
        original = load("ground-to-dog-command.json")
        replay = load("ground-to-dog-command.json")
        replay["message_id"] = "msg-ground-to-dog-command-replay"
        replay["seq"] = 8
        conflict = load("ground-to-dog-command.json")
        conflict["message_id"] = "msg-ground-to-dog-command-conflict"
        conflict["seq"] = 9
        motion = conflict["payload"]
        assert isinstance(motion, dict)
        step = motion["motion"]
        assert isinstance(step, dict)
        step["linear_x_m_s"] = 0.2
        stored = await run(port, request_for(original))
        again = await run(port, request_for(replay))
        rejected = await run(port, request_for(conflict))
        assert stored is again
        assert rejected.error is not None
        assert rejected.error.detail == "command_conflict"
        records = getattr(built.journal, "records", [])
        assert len([record for record in records if record.event == "decision_received"]) == 1
        assert calls(built) == []

    asyncio.run(body())


def test_replay_does_not_refresh_expiry(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        port = create_port(built)
        message = load("ground-to-dog-command.json")
        first = await run(port, request_for(message))
        clock = built.kernel.clock
        advance = getattr(clock, "advance", None)
        assert callable(advance)
        expires = datetime(2026, 11, 4, 13, 0, 11, tzinfo=UTC)
        now = clock.utc_now()
        advance((expires - now).total_seconds())
        second = await run(port, request_for(message))
        assert second is first
        assert second.data["expires_at"] == "2026-11-04T13:00:10.510Z"
        fresh = load("ground-to-drone-command.json")
        rejected = await run(port, request_for(fresh))
        assert rejected.error is not None
        assert rejected.error.detail == "expired"
        assert calls(built) == []

    asyncio.run(body())


def test_secret_text_in_a_reason_stays_out_of_the_journal(tmp_path: Path) -> None:
    async def body() -> None:
        built = services(tmp_path)
        message = load("ground-to-dog-command.json")
        payload = message["payload"]
        assert isinstance(payload, dict)
        payload["reason"] = "bearer sk-live-secret token"
        result = await run(create_port(built), request_for(message))
        rendered = str(getattr(built.journal, "records", []))
        event = str(result.events)
        assert result.status == "ok"
        assert "sk-live-secret" not in rendered
        assert "sk-live-secret" not in event
        assert calls(built) == []

    asyncio.run(body())
