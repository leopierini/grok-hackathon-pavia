"""Null readiness booleans fail closed and do not publish a step."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from patrol.ground.kernel.contracts import Ticket
from tests.ground.g20.support import as_object, feature, ids_of, observation, payload, request, run


def test_standing_null_is_not_ready(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["standing"] = None
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.status == "ok"
        assert result.error is None
        readiness = result.data["readiness"]
        assert isinstance(readiness, Mapping)
        assert readiness["standing"] is None
        assert result.data["ready"] is False
        assert result.data["ready_to_wait"] is False
        assert ids_of(result) == ()
        assert result.data["withheld"] == "standing"

    run(body)


def test_standing_false_is_not_ready(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["standing"] = False
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.data["ready"] is False
        assert ids_of(result) == ()
        assert result.data["withheld"] == "standing"

    run(body)


def test_standing_string_is_not_true(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["standing"] = "true"
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert ids_of(result) == ()
        assert result.data["ready"] is False

    run(body)


def test_avoidance_null_is_not_ready(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["avoidance_enabled"] = None
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.status == "ok"
        readiness = result.data["readiness"]
        assert isinstance(readiness, Mapping)
        assert readiness["avoidance"] is None
        assert result.data["ready"] is False
        assert ids_of(result) == ()

    run(body)


def test_stationary_false_is_not_ready(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["stationary"] = False
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.data["ready"] is False
        assert result.data["withheld"] == "stationary"
        assert ids_of(result) == ()

    run(body)


def test_lost_slam_is_not_route_ready(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["slam_state"] = "lost"
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(observation_message=message)))
        assert result.status == "ok"
        assert result.data["ready"] is False
        assert ids_of(result) == ()
        assert result.data["withheld"] == "slam_state"

    run(body)


def test_null_standing_blocks_ready_to_wait(tmp_path: Path) -> None:
    async def body() -> None:
        observed = observation()
        as_object(observed["payload"], "payload")["standing"] = None
        from tests.ground.g20.support import candidates

        nav = candidates()
        body_map = as_object(nav["payload"], "payload")
        body_map["candidates"] = []
        body_map["blocked"] = True
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(payload(observation_message=observed, candidate_message=nav))
        )
        assert result.data["ready_to_wait"] is False
        assert result.data["ready"] is False

    run(body)


def test_cancelled_ticket_publishes_no_candidate(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        ticket = built.kernel.authority.issue("demo-20261104-001", "navigate")
        built.kernel.authority.latch_cancel("halt")
        result = await port.execute(request(payload(), ticket))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "cancelled"
        assert ids_of(result) == ()

    run(body)


def test_stale_ticket_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        ticket: Ticket = built.kernel.authority.issue("demo-20261104-001", "navigate")
        built.kernel.authority.reset_generation("recovered")
        result = await port.execute(request(payload(), ticket))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "stale_ticket"
        assert ids_of(result) == ()

    run(body)


def test_unvalidated_capabilities_disarm_slam(tmp_path: Path) -> None:
    async def body() -> None:
        from tests.ground.g20.support import capabilities

        message = capabilities()
        as_object(message["payload"], "payload")["validated"] = False
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(capability_message=message)))
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert ids_of(result) == ()

    run(body)
