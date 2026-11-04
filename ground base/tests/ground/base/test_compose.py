"""Shared scenarios through the real base services and the seeded stage pack."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.ground.base import (
    ProtocolEvidence,
    ProtocolJournal,
    SessionLink,
    build_base_services,
)
from patrol.ground.extensions.g02.implementation import ConfigService
from patrol.ground.extensions.g05.implementation import OperationExecutor
from patrol.ground.extensions.g07.implementation import ConsoleService
from patrol.ground.extensions.g08.gateway import AdapterGateway
from patrol.ground.extensions.g09.implementation import Workflow
from patrol.ground.extensions.g09.synthetic import install_stage_pack
from patrol.ground.extensions.g10.implementation import SafetyService
from patrol.ground.kernel.contracts import IncidentInput
from patrol.ground.kernel.jpeg import tiny_jpeg_bytes
from patrol.ground.testing.devices import DeviceBundle

TARGET = "a person or an object left in a marked closed area"


def test_providers_are_the_base_implementations(tmp_path: Path) -> None:
    services, workflow = asyncio.run(_run(tmp_path, "dismiss"))

    assert isinstance(services.config, ConfigService)
    assert isinstance(services.state, SessionLink)
    assert isinstance(services.journal, ProtocolJournal)
    assert isinstance(services.executor, OperationExecutor)
    assert isinstance(services.evidence, ProtocolEvidence)
    assert isinstance(services.console, ConsoleService)
    assert isinstance(services.adapters, AdapterGateway)
    assert isinstance(services.workflow, Workflow)
    assert isinstance(services.safety, SafetyService)
    assert isinstance(getattr(services.adapters, "devices", None), DeviceBundle)
    assert workflow.outcome == "ignored"


def test_dismiss_does_not_move_the_dog(tmp_path: Path) -> None:
    _services, workflow = asyncio.run(_run(tmp_path, "dismiss"))

    assert workflow.outcome == "ignored"
    assert "dog.prepare" not in workflow.stage_trace
    assert _calls(workflow).count("dog.prepare") == 0
    assert _calls(workflow).count("drone.inspect") == 0


def test_invalid_model_stops_before_motion(tmp_path: Path) -> None:
    _services, workflow = asyncio.run(_run(tmp_path, "invalid_model"))

    assert workflow.outcome == "unresolved"
    names = _calls(workflow)
    assert "dog.prepare" not in names
    assert "dog.run_route" not in names
    assert "drone.inspect" not in names


def test_ground_clear_does_not_fly(tmp_path: Path) -> None:
    services, workflow = asyncio.run(_run(tmp_path, "ground_clear"))

    assert workflow.outcome == "cleared"
    assert _calls(workflow).count("drone.inspect") == 0
    assert services.state.snapshot().phase == "DONE"


def test_ground_confirmed_does_not_fly(tmp_path: Path) -> None:
    _services, workflow = asyncio.run(_run(tmp_path, "ground_confirmed"))

    assert workflow.outcome == "alerted"
    assert _calls(workflow).count("drone.inspect") == 0


def test_blocked_view_inspects_once(tmp_path: Path) -> None:
    services, workflow = asyncio.run(_run(tmp_path, "blocked_resolved"))

    assert workflow.outcome == "alerted"
    assert _calls(workflow).count("drone.inspect") == 1
    assert services.state.snapshot().phase == "DONE"


def test_blocked_route_does_not_fly(tmp_path: Path) -> None:
    _services, workflow = asyncio.run(_run(tmp_path, "route_blocked"))

    assert workflow.outcome == "failed"
    names = _calls(workflow)
    assert "dog.run_route" in names
    assert "drone.inspect" not in names


async def _run(tmp_path: Path, scenario: str):
    output = tmp_path / "out"
    services = await build_base_services(scenario=scenario, output_dir=output)
    workflow = services.workflow
    assert isinstance(workflow, Workflow)
    try:
        install_stage_pack(services)
        image = output / "phone.jpg"
        services.kernel.io.write_bytes(image, tiny_jpeg_bytes())
        admitted = await workflow.load(
            IncidentInput(str(image.resolve()), "room_2", TARGET, None, True)
        )
        assert admitted.accepted is True
        assert admitted.incident is not None
        handle = workflow.start(admitted.incident)
        await workflow.join(handle)
        return services, workflow
    finally:
        await services.journal.close()
        try:
            await services.adapters.close()
        except Exception:
            pass


def _calls(workflow: Workflow) -> list[str]:
    services = workflow.services
    if services is None:
        return []
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", [])
    return [str(item) for item in found]
