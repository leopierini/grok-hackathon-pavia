"""Operator commands stay on their fixed policy bindings."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.ground.extensions.g09.synthetic import StageScript
from patrol.ground.kernel.commands import parse_command
from tests.ground.g09.helpers import admit, calls, run_mission, services_for, wait_until


def test_commands_reject_the_wrong_phase_and_zone(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = services_for(
            tmp_path,
            script=StageScript(hold_slot="feature.arrival"),
        )
        services.kernel.barriers.arm("feature.arrival")
        admitted = await admit(services, workflow, tmp_path)
        assert admitted.incident is not None
        await workflow.route_command(parse_command("flight-ready"))
        assert "flight-ready:rejected" in workflow.command_log
        handle = workflow.start(admitted.incident)
        await wait_until(lambda: "holding:feature.arrival" in calls(services))
        await workflow.route_command(parse_command("arrived display"))
        await workflow.route_command(parse_command("arrived room_2"))
        assert "arrival:rejected" in workflow.command_log
        assert "arrival:accepted" in workflow.command_log
        services.kernel.barriers.release("feature.arrival")
        await workflow.join(handle)

    asyncio.run(body())


def test_halt_command_latches_without_a_journal_write(tmp_path: Path) -> None:
    async def body() -> None:
        _services, workflow = services_for(tmp_path)
        before = len(getattr(workflow.journal, "records", []))
        await workflow.route_command(parse_command("halt"))
        assert workflow.kernel.authority.cancelled is True
        assert "halt:latched" in workflow.command_log
        assert len(getattr(workflow.journal, "records", [])) == before
        assert "safety.request" in getattr(workflow.safety, "trace", [])

    asyncio.run(body())


def test_quit_requests_shutdown_without_motion(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = services_for(tmp_path)
        await workflow.route_command(parse_command("quit"))
        assert "quit" in workflow.command_log
        assert "safety.shutdown" in getattr(services.safety, "trace", [])
        assert "drone.inspect" not in calls(services)
        assert "dog.run_route" not in calls(services)

    asyncio.run(body())


def test_status_without_the_optional_provider_stays_local(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = services_for(
            tmp_path,
            script=StageScript(omit=frozenset({"feature.status"})),
        )
        await workflow.route_command(parse_command("status"))
        assert "status:builtin" in workflow.command_log
        assert services.console.messages[-1] == workflow.snapshot().phase

    asyncio.run(body())


def test_reset_without_verified_recovery_keeps_the_lock(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = await run_mission(
            tmp_path,
            scenario="landing_unknown",
            script=StageScript(ground_continuation="preflight"),
        )
        epoch = services.kernel.authority.epoch
        await workflow.route_command(parse_command("reset"))
        assert "reset:rejected" in workflow.command_log
        assert workflow.snapshot().flight_lock is True
        assert workflow.snapshot().recovery_required is True
        assert services.kernel.authority.epoch == epoch
        workflow.note_physical_recovery()
        await workflow.route_command(parse_command("reset"))
        assert "reset:accepted" in workflow.command_log
        assert workflow.snapshot().flight_lock is False
        assert services.kernel.authority.epoch != epoch

    asyncio.run(body())
