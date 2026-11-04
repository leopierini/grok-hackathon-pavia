"""Reset stays locked until workers, status, and cleanup all check out."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from patrol.contract import DogStatus, DroneStatus
from patrol.ground.extensions.g10.implementation import SafetyService
from patrol.ground.kernel.contracts import BaseServices, WaitSpec
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.paths import repo_root
from tests.ground.g10.conftest import calls_of, install, run, settle, ticket_for


def _recovery() -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g10" / "recovery.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["verified"] is True
    assert loaded["replay_route"] is False
    assert loaded["replay_takeoff"] is False
    return loaded


def test_cancel_resistant_worker_blocks_recreation(
    opened: tuple[BaseServices, SafetyService],
) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        barriers = services.kernel.barriers
        barriers.arm("resistant")
        barriers.arm("resistant-done")
        ignored = {"value": False}

        async def worker() -> None:
            try:
                await barriers.wait("resistant")
            except asyncio.CancelledError:
                ignored["value"] = True
            await barriers.wait("resistant-done")

        task = asyncio.create_task(worker())
        services.kernel.tasks.retain("old-route", task)
        try:
            service.request("operator halt", ticket_for(services))
            await settle(service)
            task.cancel()
            for _ in range(20):
                if ignored["value"]:
                    break
                await asyncio.sleep(0)
            assert ignored["value"] is True
            with pytest.raises(GroundFault) as caught:
                await service.reset(_recovery())
            assert caught.value.error.code == "unsafe_state"
            assert "adapters.build" not in calls
            assert service.motion_locked
            assert service.recovery_required
        finally:
            barriers.release("resistant-done")
            await task

    run(body)


def test_unknown_landing_and_late_grounded_stay_locked(
    opened: tuple[BaseServices, SafetyService],
) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        devices = services.adapters.devices
        state = {"flight": "unknown", "stationary": None}

        async def dog_status() -> DogStatus:
            calls.append("dog.get_status")
            if state["stationary"] is True:
                return DogStatus(True, True, True, True)
            return DogStatus(True, True, None, True)

        async def drone_status() -> DroneStatus:
            calls.append("drone.get_status")
            if state["flight"] == "grounded":
                return DroneStatus(True, "grounded", 80)
            return DroneStatus(True, "unknown", 80)

        install(devices.dog, "get_status", dog_status)
        install(devices.drone, "get_status", drone_status)
        handle = service.request("operator halt", ticket_for(services))
        await settle(service)
        with pytest.raises(GroundFault) as caught:
            await service.reset({"verified": True})
        assert caught.value.error.code == "unsafe_state"
        state["flight"] = "grounded"
        state["stationary"] = True
        snapshot = await service.observe(handle, deadline=1)
        assert snapshot.recovery_required
        assert service.motion_locked
        assert services.kernel.authority.cancelled
        assert "adapters.build" not in calls
        assert "dog.run_route" not in calls

    run(body)


def test_airborne_drone_blocks_reset(opened: tuple[BaseServices, SafetyService]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        devices = services.adapters.devices

        async def drone_status() -> DroneStatus:
            calls.append("drone.get_status")
            return DroneStatus(True, "airborne", 80)

        install(devices.drone, "get_status", drone_status)
        service.request("operator halt", ticket_for(services))
        await settle(service)
        with pytest.raises(GroundFault) as caught:
            await service.reset({"verified": True})
        assert caught.value.error.code == "unsafe_state"
        assert service.drone_posture == "airborne"
        assert "adapters.build" not in calls

    run(body)


def test_unstopped_dog_blocks_reset(opened: tuple[BaseServices, SafetyService]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        devices = services.adapters.devices

        async def dog_status() -> DogStatus:
            calls.append("dog.get_status")
            return DogStatus(True, True, False, True)

        install(devices.dog, "get_status", dog_status)
        service.request("operator halt", ticket_for(services))
        await settle(service)
        with pytest.raises(GroundFault) as caught:
            await service.reset({"verified": True})
        assert caught.value.error.code == "unsafe_state"
        assert service.dog_posture == "not_stopped"
        assert "adapters.build" not in calls

    run(body)


def test_string_verified_does_not_reset(opened: tuple[BaseServices, SafetyService]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        authority = services.kernel.authority
        service.request("operator halt", ticket_for(services))
        await settle(service)
        epoch = authority.epoch
        for payload in (
            {"verified": "true"},
            {"verified": "false"},
            {"verified": 1},
            {},
            {"verified": True, "replay_route": True},
            {"verified": True, "replay_takeoff": True},
        ):
            with pytest.raises(GroundFault) as caught:
                await service.reset(payload)
            assert caught.value.error.code == "invalid_input"
        assert authority.epoch == epoch
        assert authority.cancelled
        assert service.motion_locked
        assert "adapters.build" not in calls

    run(body)


def test_cleanup_errors_keep_the_original_failure(
    opened: tuple[BaseServices, SafetyService],
) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        devices = services.adapters.devices
        authority = services.kernel.authority
        service.note_mission_failure("route failed")
        service.request("operator halt", ticket_for(services))
        await settle(service)

        async def dog_close() -> None:
            calls.append("dog.close")
            raise RuntimeError("dog close failed")

        async def drone_close() -> None:
            calls.append("drone.close")
            raise RuntimeError("drone close failed")

        install(devices.dog, "close", dog_close)
        install(devices.drone, "close", drone_close)
        epoch = authority.epoch
        with pytest.raises(GroundFault) as caught:
            await service.reset({"verified": True})
        assert caught.value.error.code == "unsafe_state"
        assert "cleanup failed" in caught.value.error.detail
        assert service.mission_failure == "route failed"
        assert any(item.startswith("dog.close:") for item in service.cleanup_errors)
        assert any(item.startswith("drone.close:") for item in service.cleanup_errors)
        assert "reasoner.close" in calls
        assert "adapters.build" not in calls
        assert authority.epoch == epoch
        assert authority.cancelled

    run(body)


def test_verified_reset_is_disarmed_and_does_not_replay(
    opened: tuple[BaseServices, SafetyService],
) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        authority = services.kernel.authority
        ticket = ticket_for(services)
        service.request("operator halt", ticket)
        await settle(service)
        assert service.recovery_required
        assert service.motion_locked
        old_event = authority.cancel_event
        old_epoch = authority.epoch
        old_generation = service.confirmation_generation
        spec = WaitSpec("arrival", "room_2", "arrival", services.kernel.clock.monotonic() + 5)
        before = await services.console.confirm(spec)
        await service.reset(_recovery())
        after = await services.console.confirm(spec)
        with pytest.raises(GroundFault) as stale:
            authority.require_current(ticket)
        assert stale.value.error.code == "stale_ticket"
        fresh = authority.issue("mission-10", "next")
        authority.require_current(fresh)
        assert authority.epoch == old_epoch + 1
        assert authority.cancel_event is not old_event
        assert authority.cancelled is False
        assert before.accepted is False
        assert after.accepted is True
        assert service.confirmation_generation == old_generation + 1
        assert service.reconnected
        assert service.armed is False
        assert service.motion_locked is False
        assert service.recovery_required is False
        assert "dog.run_route" not in calls
        assert "drone.inspect" not in calls
        assert "takeoff_attempt" not in calls
        assert "adapters.build" in calls
        assert "adapters.connect:dog" in calls
        assert "adapters.connect:drone" in calls
        messages = [str(item) for item in getattr(services.console, "messages", [])]
        assert "reconnected disarmed" in messages

    run(body)


def test_shutdown_closes_once_without_a_second_landing(
    opened: tuple[BaseServices, SafetyService],
) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        await service.shutdown("operator quit")
        await service.shutdown("operator quit")
        assert calls.count("dog.halt") == 1
        assert calls.count("drone.land") == 1
        assert "dog.close" in calls
        assert "drone.close" in calls
        assert "reasoner.close" in calls
        assert "shutdown:duplicate" in service.trace
        assert service.recovery_required
        assert service.reconnected is False
        assert "emergency" not in calls
        assert "dog.run_route" not in calls

    run(body)


def test_reconnect_failure_keeps_the_latch(opened: tuple[BaseServices, SafetyService]) -> None:
    services, service = opened

    async def body() -> None:
        calls = calls_of(services)
        devices = services.adapters.devices
        authority = services.kernel.authority
        service.request("operator halt", ticket_for(services))
        await settle(service)

        async def dog_connect() -> DogStatus:
            calls.append("dog.connect")
            raise RuntimeError("dog reconnect failed")

        install(devices.dog, "connect", dog_connect)
        epoch = authority.epoch
        with pytest.raises(GroundFault) as caught:
            await service.reset({"verified": True})
        assert caught.value.error.code == "unsafe_state"
        assert authority.cancelled
        assert authority.epoch == epoch
        assert service.recovery_required
        assert service.reconnected is False
        assert "dog.run_route" not in calls
        assert any(item.startswith("reconnect:") for item in service.cleanup_errors)

    run(body)


def test_fixture_path_is_owned() -> None:
    path = Path(repo_root() / "fixtures" / "ground" / "g10" / "recovery.json")
    assert path.is_file()
