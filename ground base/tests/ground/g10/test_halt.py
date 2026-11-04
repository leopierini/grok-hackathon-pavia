"""Halt latches immediately and starts both stops independently."""

from __future__ import annotations

import asyncio
import time

import pytest
from patrol.contract import DogStatus, DroneStatus
from patrol.ground.extensions.g10.implementation import SafetyHandle, create
from patrol.ground.kernel.build import build_kernel
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g10.conftest import calls_of, install, run, settle, ticket_for


def test_factory_requires_peers() -> None:
    kernel = build_kernel()
    with pytest.raises(GroundFault) as caught:
        create(kernel, None)
    assert caught.value.error.code == "invalid_input"


def test_latch_happens_before_device_entry_or_journal(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        records = getattr(services.journal, "records", None)
        ticket = ticket_for(services)
        service.request("operator halt", ticket)
        assert services.kernel.authority.cancelled
        assert "dog.halt" not in calls
        assert "drone.land" not in calls
        assert records == []
        messages = getattr(services.console, "messages", [])
        assert str(messages[0]).startswith("halt requested:")
        await settle(service)
        assert "dog.halt" in calls
        assert "drone.land" in calls
        assert "emergency" not in calls

    run(body)


def test_blocked_dog_does_not_delay_drone_land(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        barriers = services.kernel.barriers
        barriers.arm("safety.dog.halt")
        devices = services.adapters.devices

        async def dog_halt() -> None:
            calls.append("dog.halt")
            await barriers.wait("safety.dog.halt")

        async def drone_land() -> None:
            calls.append("drone.land")

        install(devices.dog, "halt", dog_halt)
        install(devices.drone, "land", drone_land)
        try:
            service.request("operator halt", ticket_for(services))
            for _ in range(20):
                if "drone.land" in calls and "dog.halt" in calls:
                    break
                await asyncio.sleep(0)
            assert service.dog_task is not None and not service.dog_task.done()
            assert service.drone_task is not None and service.drone_task.done()
            assert calls.count("drone.land") == 1
        finally:
            barriers.release("safety.dog.halt")
            await settle(service)

    run(body)


def test_repeated_halt_reuses_one_supervisor(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        authority = services.kernel.authority
        ticket = ticket_for(services)
        first = service.request("operator halt", ticket)
        epoch = authority.epoch
        dog_task = service.dog_task
        second = service.request("halt again", ticket)
        assert second is first
        assert service.dog_task is dog_task
        assert authority.epoch == epoch
        await settle(service)
        assert calls.count("dog.halt") == 1
        assert calls.count("drone.land") == 1
        messages = getattr(services.console, "messages", [])
        halt_lines = [str(item) for item in messages if str(item).startswith("halt requested:")]
        assert halt_lines == ["halt requested: operator halt"]

    run(body)


def test_both_stop_errors_are_kept(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        devices = services.adapters.devices

        async def dog_halt() -> None:
            calls.append("dog.halt")
            raise RuntimeError("dog halt failed")

        async def drone_land() -> None:
            calls.append("drone.land")
            raise RuntimeError("drone land failed")

        install(devices.dog, "halt", dog_halt)
        install(devices.drone, "land", drone_land)
        service.request("operator halt", ticket_for(services))
        await settle(service)
        assert "dog halt failed" in service.dog_error
        assert "drone land failed" in service.drone_error
        assert calls.count("dog.halt") == 1
        assert calls.count("drone.land") == 1
        assert service.recovery_required
        assert service.motion_locked
        snapshot = await service.observe(service.handle, deadline=1)  # type: ignore[arg-type]
        assert snapshot.recovery_required
        assert snapshot.halted

    run(body)


def test_recognition_is_separate_from_physical_stop(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        barriers = services.kernel.barriers
        barriers.arm("safety.dog.halt")
        devices = services.adapters.devices

        async def dog_halt() -> None:
            calls.append("dog.halt")
            await barriers.wait("safety.dog.halt")

        install(devices.dog, "halt", dog_halt)
        try:
            started = time.monotonic()
            service.request("operator halt", ticket_for(services))
            elapsed = time.monotonic() - started
            assert elapsed < 0.5
            assert services.kernel.authority.cancelled
            assert service.dog_task is not None and not service.dog_task.done()
        finally:
            barriers.release("safety.dog.halt")
            await settle(service)

    run(body)


def test_link_loss_does_not_claim_delivery(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        devices = services.adapters.devices

        async def dog_status() -> DogStatus:
            calls.append("dog.get_status")
            return DogStatus(False, None, None, None)

        async def drone_status() -> DroneStatus:
            calls.append("drone.get_status")
            return DroneStatus(False, "unknown", None)

        install(devices.dog, "get_status", dog_status)
        install(devices.drone, "get_status", drone_status)
        service.request("ethernet link lost", ticket_for(services))
        await settle(service)
        assert "dog.halt" in calls
        assert "drone.land" in calls
        assert "delivery_not_assumed" in service.detail
        assert "delivered" not in service.detail
        assert service.dog_posture == "disconnected"
        assert service.recovery_required

    run(body)


def test_expired_deadline_still_requests_stops(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        authority = services.kernel.authority
        clock = services.kernel.clock
        ticket = ticket_for(services, "route")
        with pytest.raises(GroundFault) as caught:
            authority.require_action(ticket, deadline_monotonic=clock.monotonic(), clock=clock)
        assert caught.value.error.code == "expired_deadline"
        service.request("operator halt", ticket)
        await settle(service)
        assert "dog.halt" in calls
        assert "drone.land" in calls

    run(body)


def test_invalid_request_does_not_latch(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        authority = services.kernel.authority
        ticket = ticket_for(services)
        epoch = authority.epoch
        with pytest.raises(GroundFault) as blank:
            service.request("  ", ticket)
        assert blank.value.error.code == "invalid_input"
        with pytest.raises(GroundFault) as bad_ticket:
            service.request("operator halt", "ticket")  # type: ignore[arg-type]
        assert bad_ticket.value.error.code == "invalid_input"
        assert authority.epoch == epoch
        assert authority.cancelled is False
        assert service.handle is None

    run(body)


def test_observe_rejects_bad_deadline_and_stale_handle(opened: tuple[object, object]) -> None:
    services, service = opened

    async def body() -> None:
        handle = service.request("operator halt", ticket_for(services))
        for deadline in (True, 0, -1, float("nan")):
            with pytest.raises(GroundFault) as caught:
                await service.observe(handle, deadline=deadline)  # type: ignore[arg-type]
            assert caught.value.error.code == "invalid_input"
        stale = SafetyHandle(handle.ticket, "other", handle.generation)
        with pytest.raises(GroundFault) as caught:
            await service.observe(stale, deadline=1)
        assert caught.value.error.code == "stale_ticket"
        await settle(service)

    run(body)
