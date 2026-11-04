"""Shared doubles for safety tests. Construction does not call devices."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from patrol.ground.extensions.g10.implementation import SafetyService, create
from patrol.ground.kernel.contracts import BaseServices, Ticket
from patrol.ground.testing.builders import build_test_services, service_ports


@pytest.fixture
def opened(tmp_path: Path) -> tuple[BaseServices, SafetyService]:
    services = build_test_services(output_dir=tmp_path)
    created = create(services.kernel, service_ports(services))
    if not isinstance(created, SafetyService):
        raise AssertionError("factory did not return the safety service")
    return services, created


def calls_of(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found


def ticket_for(services: BaseServices, stage: str = "halt") -> Ticket:
    return services.kernel.authority.issue("mission-10", stage)


def install(device: object, name: str, method: Callable[..., Awaitable[object]]) -> None:
    setattr(device, name, method)


async def settle(service: SafetyService) -> None:
    task = service.supervisor_task
    if task is None:
        return
    for _ in range(50):
        if task.done():
            break
        await asyncio.sleep(0)
    assert task.done()
    if not task.cancelled():
        await task


def run(test: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(test())
