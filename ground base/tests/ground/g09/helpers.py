"""Shared setup for workflow tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from patrol.ground.extensions.g09.implementation import Workflow, create
from patrol.ground.extensions.g09.synthetic import StageScript, install_stage_pack
from patrol.ground.kernel.contracts import BaseServices, GroundSettings, IncidentInput
from patrol.ground.kernel.jpeg import tiny_jpeg_bytes
from patrol.ground.kernel.settings import make_settings
from patrol.ground.testing.builders import build_test_services

TARGET = "a person or an object left in a marked closed area"


def services_for(
    tmp_path: Path,
    *,
    scenario: str = "blocked_resolved",
    script: StageScript | None = None,
    settings: GroundSettings | None = None,
) -> tuple[BaseServices, Workflow]:
    services = build_test_services(output_dir=tmp_path, scenario=scenario)
    install_stage_pack(services, script or StageScript())
    workflow = create(services)
    workflow.bind_settings(settings or make_settings(scenario=scenario, output_root=str(tmp_path)))
    return services, workflow


async def admit(services: BaseServices, workflow: Workflow, tmp_path: Path):
    image = tmp_path / "phone.jpg"
    services.kernel.io.write_bytes(image, tiny_jpeg_bytes())
    return await workflow.load(IncidentInput(str(image.resolve()), "room_2", TARGET, None, True))


async def run_mission(
    tmp_path: Path,
    *,
    scenario: str = "blocked_resolved",
    script: StageScript | None = None,
    settings: GroundSettings | None = None,
    before_start: Callable[[Workflow, BaseServices], Awaitable[None]] | None = None,
) -> tuple[BaseServices, Workflow]:
    services, workflow = services_for(
        tmp_path,
        scenario=scenario,
        script=script,
        settings=settings,
    )
    admitted = await admit(services, workflow, tmp_path)
    assert admitted.accepted is True
    assert admitted.incident is not None
    if before_start is not None:
        await before_start(workflow, services)
    handle = workflow.start(admitted.incident)
    await workflow.join(handle)
    return services, workflow


def calls(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", [])
    return [str(item) for item in found]


async def wait_until(predicate: Callable[[], bool]) -> None:
    for _ in range(300):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")
