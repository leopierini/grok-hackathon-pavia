"""Success, errors, expired budgets, and lazy factory invocation."""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

import pytest
from patrol.contract import AdapterError, RunContext
from patrol.ground.extensions.g05.implementation import ACCEPTANCE_PRECEDENCE, create
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import service_ports
from tests.ground.g05.helpers import finished, make_executor, manual


def test_precedence_fixture_matches_the_executor() -> None:
    path = repo_root() / "fixtures" / "ground" / "g05" / "precedence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["acceptance_precedence"] == ACCEPTANCE_PRECEDENCE
    assert payload["exact_deadline"] == "timeout"
    assert payload["retries"] == "never"
    assert payload["cancellation_does_not_prove_device_stop"] is True
    assert payload["recovery_reuses_cancelled_context"] is False


def test_completed_operation_records_ticket_timing_and_events(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        executor.bind_mission("mission", 30)
        ticket = services.kernel.authority.issue("mission", "prepare")
        result = await executor.run("dog.prepare", ticket, finished, limit_s=5)
        assert result.status == "completed"
        assert result.value == "done"
        assert result.error is None
        assert result.pending is False
        assert result.ticket is ticket
        assert result.started_monotonic == 0
        assert result.ended_monotonic == 0
        assert result.started_utc.startswith("2026-01-01")
        assert executor.authorizes_next(result) is True
        assert executor.factory_calls == ["dog.prepare"]
        assert [event.kind for event in executor.events] == [
            "operation_started",
            "operation_completed",
        ]
        assert executor.events[0].ticket == ticket
        assert executor.events[1].payload["status"] == "completed"
        assert services.kernel.tasks.pending() == ()

    asyncio.run(body())


def test_factory_is_lazy_for_cancel_zero_and_garbage_limits(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        ticket = services.kernel.authority.issue("mission", "route")
        services.kernel.authority.latch_cancel("halt")
        cancelled = await executor.run("dog.run_route", ticket, finished, limit_s=5)
        assert cancelled.status == "cancelled"
        assert cancelled.error is not None
        assert cancelled.error.code == "cancelled"
        assert executor.factory_calls == []

        executor, services = make_executor(tmp_path)
        ticket = services.kernel.authority.issue("mission", "route")
        zero = await executor.run("dog.run_route", ticket, finished, limit_s=0)
        assert zero.status == "timeout"
        assert zero.error is not None
        assert zero.error.code == "expired_deadline"
        negative = await executor.run("dog.run_route", ticket, finished, limit_s=-1)
        assert negative.status == "failed"
        assert negative.error is not None
        assert negative.error.code == "invalid_input"
        boolean = await executor.run("dog.run_route", ticket, finished, limit_s=True)  # type: ignore[arg-type]
        assert boolean.error is not None
        assert boolean.error.code == "invalid_input"
        missing = await executor.run("dog.run_route", ticket, finished, limit_s=math.nan)
        assert missing.error is not None
        assert missing.error.code == "invalid_input"
        assert executor.factory_calls == []

    asyncio.run(body())


def test_none_result_is_success_and_adapter_errors_are_not(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        ticket = services.kernel.authority.issue("mission", "capture")

        async def empty(_context: RunContext) -> None:
            return None

        result = await executor.run("dog.capture_frame", ticket, empty, limit_s=5)
        assert result.status == "completed"
        assert result.value is None

        async def broken(_context: RunContext) -> str:
            raise AdapterError("device_error", "link dropped")

        failed = await executor.run("dog.capture_frame", ticket, broken, limit_s=5)
        assert failed.status == "failed"
        assert failed.value is None
        assert failed.error is not None
        assert failed.error.code == "unavailable"
        assert failed.error.detail == "link dropped"
        assert executor.factory_calls == ["dog.capture_frame", "dog.capture_frame"]

    asyncio.run(body())


def test_non_awaitable_factory_fails_once_and_peers_stay_idle(tmp_path: Path) -> None:
    async def body() -> None:
        executor, services = make_executor(tmp_path)
        ticket = services.kernel.authority.issue("mission", "model")

        def factory(_context: RunContext) -> str:
            return "not-awaitable"

        result = await executor.run(
            "reasoner.assess_incident",
            ticket,
            factory,  # type: ignore[arg-type]
            limit_s=5,
        )
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert executor.factory_calls == ["reasoner.assess_incident"]
        assert services.safety.trace == []  # type: ignore[attr-defined]
        assert services.workflow.trace == []  # type: ignore[attr-defined]
        assert services.executor.trace == []  # type: ignore[attr-defined]

    asyncio.run(body())


def test_harness_can_construct_from_services(tmp_path: Path) -> None:
    async def body() -> None:
        _executor, services = make_executor(tmp_path)
        built = create(services)
        ticket = services.kernel.authority.issue("mission", "prepare")
        result = await built.run("dog.prepare", ticket, finished, limit_s=2)
        assert result.status == "completed"
        with pytest.raises(GroundFault):
            create(services.kernel)  # type: ignore[arg-type]

    asyncio.run(body())


def test_create_peers_match_the_service_ports(tmp_path: Path) -> None:
    executor, services = make_executor(tmp_path)
    ports = service_ports(services)
    assert executor.peers.safety is ports.safety
    assert executor.peers.workflow is ports.workflow
    manual(services).advance(0)
