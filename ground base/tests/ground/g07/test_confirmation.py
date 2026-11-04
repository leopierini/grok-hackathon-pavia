"""Scoped arrival and readiness confirmation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.contract import Frame, Incident
from patrol.ground.extensions.g07.implementation import ConsoleService, create
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import BaseServices, WaitSpec
from patrol.ground.kernel.settings import make_settings
from patrol.ground.testing.builders import build_test_services, service_ports


def _services(tmp_path: Path) -> BaseServices:
    return build_test_services(clock_mode="manual", seed=7, output_dir=tmp_path)


def _console(services: BaseServices) -> ConsoleService:
    return create(services.kernel, service_ports(services))


def _clock(services: BaseServices) -> ManualClock:
    clock = services.kernel.clock
    assert isinstance(clock, ManualClock)
    return clock


def test_early_confirmation_is_not_reused(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        spec = WaitSpec("arrival", "room_2", "arrive-1", 30.0)
        await console.submit_turn(("arrived room_2",))
        pending = asyncio.create_task(console.confirm(spec))
        await asyncio.sleep(0)
        assert not pending.done()
        await console.submit_turn(("arrived room_2",))
        result = await pending
        assert result.accepted is True
        assert result.zone == "room_2"
        assert result.method == "operator"
        await console.close()

    asyncio.run(body())


def test_wrong_zone_does_not_resolve_the_wait(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        pending = asyncio.create_task(
            console.confirm(WaitSpec("arrival", "room_2", "arrive-1", 30.0))
        )
        await asyncio.sleep(0)
        await console.submit_turn(("arrived entrance",))
        await asyncio.sleep(0)
        assert not pending.done()
        await console.submit_turn(("arrived room_2",))
        result = await pending
        assert result.accepted is True
        assert result.zone == "room_2"
        await console.close()

    asyncio.run(body())


def test_duplicate_confirmation_is_rejected(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        pending = asyncio.create_task(
            console.confirm(WaitSpec("arrival", "display", "arrive-1", 30.0))
        )
        await asyncio.sleep(0)
        await console.submit_turn(("arrived display",))
        first = await pending
        assert first.accepted is True
        await console.submit_turn(("arrived display",))
        assert console.trace[-1] == "confirmation:arrived:duplicate"
        await console.close()

    asyncio.run(body())


def test_expired_wait_is_not_a_later_permission(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        pending = asyncio.create_task(
            console.confirm(WaitSpec("arrival", "room_2", "expire", 4.0))
        )
        await asyncio.sleep(0)
        _clock(services).advance(4)
        result = await pending
        assert result.accepted is False
        assert result.detail == "expired"
        await console.submit_turn(("arrived room_2",))
        assert console.trace[-1] == "confirmation:arrived:early"
        await console.close()

    asyncio.run(body())


def test_stale_epoch_rejects_flight_ready(tmp_path: Path) -> None:
    services = _services(tmp_path)
    frame = Frame("C:/simulated/phone.jpg", "phone", "room_2", None, True)
    incident = Incident("m1", "room_2", "a person or an object left in a marked closed area", frame)
    services.state.open(incident, make_settings())
    services.kernel.authority.reset_generation("newer epoch")

    async def body() -> None:
        console = _console(services)
        result = await console.confirm(WaitSpec("flight_ready", "room_2", "preflight", 20.0))
        assert result.accepted is False
        assert result.detail == "stale"
        await console.close()

    asyncio.run(body())


def test_same_turn_halt_invalidates_readiness_in_both_orders(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        first = asyncio.create_task(
            console.confirm(WaitSpec("flight_ready", "room_2", "pre-a", 50.0))
        )
        await asyncio.sleep(0)
        await console.submit_turn(("halt", "flight-ready"))
        assert (await first).accepted is False
        assert services.kernel.authority.cancelled is True
        services.kernel.authority.reset_generation("recover")
        second = asyncio.create_task(
            console.confirm(WaitSpec("readiness", "room_2", "pre-b", 50.0))
        )
        await asyncio.sleep(0)
        await console.submit_turn(("flight-ready", "halt"))
        assert (await second).accepted is False
        assert services.kernel.authority.cancelled is True
        await console.close()

    asyncio.run(body())


def test_flight_ready_does_not_resolve_an_arrival_wait(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        pending = asyncio.create_task(
            console.confirm(WaitSpec("arrived", "room_2", "arrive-1", 20.0))
        )
        await asyncio.sleep(0)
        await console.submit_turn(("flight-ready",))
        await asyncio.sleep(0)
        assert not pending.done()
        await console.submit_turn(("arrived room_2",))
        result = await pending
        assert result.accepted is True
        await console.close()

    asyncio.run(body())


def test_resolved_flight_ready_stays_accepted_when_halt_is_later(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        pending = asyncio.create_task(
            console.confirm(WaitSpec("flight-ready", "display", "pre-c", 20.0))
        )
        await asyncio.sleep(0)
        await console.submit_turn(("flight-ready",))
        result = await pending
        assert result.accepted is True
        await console.submit_turn(("halt",))
        assert services.kernel.authority.cancelled is True
        follow = await console.confirm(WaitSpec("flight_ready", "display", "pre-d", 20.0))
        assert follow.accepted is False
        assert follow.detail == "cancelled"
        await console.close()

    asyncio.run(body())


def test_a_new_wait_replaces_the_previous_one(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        first = asyncio.create_task(
            console.confirm(WaitSpec("arrival", "room_2", "arrive-1", 30.0))
        )
        await asyncio.sleep(0)
        second = asyncio.create_task(
            console.confirm(WaitSpec("arrival", "display", "arrive-2", 30.0))
        )
        replaced = await first
        assert replaced.accepted is False
        assert replaced.detail == "stale"
        await asyncio.sleep(0)
        await console.submit_turn(("arrived room_2",))
        await asyncio.sleep(0)
        assert not second.done()
        await console.submit_turn(("arrived display",))
        result = await second
        assert result.accepted is True
        assert result.zone == "display"
        await console.close()

    asyncio.run(body())
