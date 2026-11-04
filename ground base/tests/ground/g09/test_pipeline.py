"""Normal stage order and the branches that must skip later actions."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from patrol.ground.extensions.g09.implementation import create
from patrol.ground.extensions.g09.scenarios import BLOCKED_TRACE, CLEAR_TRACE, DISMISS_TRACE
from patrol.ground.extensions.g09.synthetic import StageScript
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.settings import make_settings
from tests.ground.g09.helpers import calls, run_mission, services_for


def test_dismiss_skips_motion_and_publishes_once(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = await run_mission(
            tmp_path,
            script=StageScript(dispatch_continuation="ignored"),
        )
        assert workflow.outcome == "ignored"
        assert tuple(workflow.stage_trace) == DISMISS_TRACE
        assert "dog.prepare" not in calls(services)
        assert "dog.run_route" not in calls(services)
        assert "drone.inspect" not in calls(services)
        assert calls(services).count("reasoner.compose_alert") == 0
        assert workflow.wording_source == "template"
        published = getattr(services.journal, "published", None)
        assert published is not None
        await workflow._terminal("ignored", workflow._ticket)  # type: ignore[arg-type]
        assert getattr(services.journal, "published", None) is published
        assert calls(services).count("reasoner.compose_alert") == 0

    asyncio.run(body())


def test_ground_clear_and_confirmed_do_not_fly(tmp_path: Path) -> None:
    async def body() -> None:
        clear_services, cleared = await run_mission(
            tmp_path / "clear",
            script=StageScript(ground_continuation="resolve", resolution_outcome="cleared"),
        )
        confirmed_services, confirmed = await run_mission(
            tmp_path / "confirmed",
            script=StageScript(ground_continuation="resolve", resolution_outcome="confirmed"),
        )
        assert cleared.outcome == "cleared"
        assert confirmed.outcome == "alerted"
        assert tuple(cleared.stage_trace) == CLEAR_TRACE
        assert tuple(confirmed.stage_trace) == CLEAR_TRACE
        assert "drone.inspect" not in calls(clear_services)
        assert "drone.inspect" not in calls(confirmed_services)
        assert calls(confirmed_services).count("reasoner.compose_alert") == 1
        assert cleared.snapshot().flight_lock is False

    asyncio.run(body())


def test_blocked_resolved_inspects_once_and_keeps_the_flight_lock(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = await run_mission(tmp_path)
        assert workflow.outcome == "alerted"
        assert workflow.snapshot().phase == "DONE"
        assert workflow.snapshot().flight_lock is True
        assert workflow.snapshot().recovery_required is False
        assert tuple(workflow.stage_trace) == BLOCKED_TRACE
        assert calls(services).count("drone.inspect") == 1
        assert calls(services).count("dog.run_route") == 1
        assert calls(services).count("reasoner.compose_alert") == 1
        assert services.kernel.tasks.pending() == ()

    asyncio.run(body())


def test_route_blocked_fails_without_flight(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = await run_mission(tmp_path, scenario="route_blocked")
        assert workflow.outcome == "failed"
        assert workflow.snapshot().recovery_required is False
        assert "drone.inspect" not in calls(services)
        assert "dog.capture_frame" not in calls(services)

    asyncio.run(body())


def test_unknown_landing_keeps_recovery_after_the_report(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = await run_mission(
            tmp_path,
            scenario="landing_unknown",
            script=StageScript(ground_continuation="preflight"),
        )
        assert workflow.outcome == "failed"
        assert workflow.snapshot().phase == "FAULT"
        assert workflow.snapshot().flight_lock is True
        assert workflow.snapshot().recovery_required is True
        assert services.state.snapshot().phase == "FAULT"
        assert services.state.snapshot().recovery_required is True
        names = [record.event for record in services.journal.records]
        assert "recovery_cleared" not in names
        assert calls(services).count("reasoner.resolve_incident") == 0
        assert calls(services).count("reasoner.compose_alert") == 0
        assert getattr(services.journal, "published", None) is not None

    asyncio.run(body())


def test_missing_dispatch_and_preflight_block_their_stages(tmp_path: Path) -> None:
    async def body() -> None:
        dispatch_services, dispatch_run = await run_mission(
            tmp_path / "dispatch",
            script=StageScript(omit=frozenset({"feature.dispatch"})),
        )
        preflight_services, preflight_run = await run_mission(
            tmp_path / "preflight",
            script=StageScript(omit=frozenset({"feature.preflight"})),
        )
        assert dispatch_run.failure_code == "missing_provider"
        assert "dog.run_route" not in calls(dispatch_services)
        assert preflight_run.failure_code == "missing_provider"
        assert "drone.inspect" not in calls(preflight_services)
        assert "dog.run_route" in calls(preflight_services)

    asyncio.run(body())


def test_missing_optional_providers_do_not_block_flight(tmp_path: Path) -> None:
    async def body() -> None:
        script = StageScript(
            omit=frozenset(
                {
                    "feature.transport",
                    "feature.metrics",
                    "feature.status",
                }
            )
        )
        services, workflow = await run_mission(tmp_path, script=script)
        assert workflow.outcome == "alerted"
        assert calls(services).count("drone.inspect") == 1
        assert "feature.network_diagnostics" not in services.kernel.features.installed()
        assert "feature.adapter_probe" not in services.kernel.features.installed()

    asyncio.run(body())


def test_missing_restart_and_unarmed_real_dog_do_not_route(tmp_path: Path) -> None:
    async def body() -> None:
        restart_services, restart_run = await run_mission(
            tmp_path / "restart",
            script=StageScript(omit=frozenset({"feature.restart"})),
        )
        real = make_settings(
            output_root=str(tmp_path / "real"),
            modes={"dog": "real", "drone": "fake", "grok": "fake"},
        )
        real_services, real_run = await run_mission(tmp_path / "real", settings=real)
        assert restart_run.outcome == "unresolved"
        assert "dog.run_route" not in calls(restart_services)
        assert real_run.outcome == "unresolved"
        assert "dog.prepare" not in calls(real_services)
        assert "dog.run_route" not in calls(real_services)

    asyncio.run(body())


def test_armed_real_dog_on_a_manual_clock_does_not_route(tmp_path: Path) -> None:
    async def body() -> None:
        settings = make_settings(
            output_root=str(tmp_path),
            modes={"dog": "real", "drone": "fake", "grok": "fake"},
        )

        async def arm(workflow, _services) -> None:
            from patrol.ground.kernel.commands import parse_command

            await workflow.route_command(parse_command("arm"))

        services, workflow = await run_mission(tmp_path, settings=settings, before_start=arm)
        assert "arm:accepted" in workflow.command_log
        assert "dog.run_route" not in calls(services)
        assert workflow.failure_code == "invalid_input"

    asyncio.run(body())


def test_fake_dog_cannot_authorize_a_real_pad_launch(tmp_path: Path) -> None:
    async def body() -> None:
        settings = make_settings(
            output_root=str(tmp_path),
            launch_tier="carried_pad",
            modes={"dog": "fake", "drone": "real", "grok": "fake"},
        )

        async def arm(workflow, _services) -> None:
            from patrol.ground.kernel.commands import parse_command

            await workflow.route_command(parse_command("arm"))

        services, workflow = await run_mission(tmp_path, settings=settings, before_start=arm)
        assert workflow.outcome == "unresolved"
        assert workflow.snapshot().flight_lock is True
        assert "drone.inspect" not in calls(services)
        assert "dog.run_route" in calls(services)

    asyncio.run(body())


def test_initial_preflight_cannot_grant_inspect(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = await run_mission(
            tmp_path,
            script=StageScript(initial_may_inspect=True),
        )
        assert workflow.outcome == "unresolved"
        assert workflow.snapshot().flight_lock is True
        assert "drone.inspect" not in calls(services)
        assert "flight_ready" not in workflow.stage_trace

    asyncio.run(body())


def test_double_start_and_second_load_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        from patrol.ground.kernel.contracts import IncidentInput
        from tests.ground.g09.helpers import TARGET, admit

        services, workflow = services_for(tmp_path)
        admitted = await admit(services, workflow, tmp_path)
        assert admitted.incident is not None
        again = await workflow.load(
            IncidentInput(str((tmp_path / "phone.jpg").resolve()), "room_2", TARGET, None, True)
        )
        assert again.accepted is False
        assert calls_open(services) == 1
        handle = workflow.start(admitted.incident)
        with pytest.raises(GroundFault) as caught:
            workflow.start(admitted.incident)
        assert caught.value.error.code == "rejected"
        await workflow.join(handle)
        assert calls(services).count("dog.run_route") == 1

    asyncio.run(body())


def test_create_does_not_install_a_synthetic_pack(tmp_path: Path) -> None:
    from patrol.ground.testing.builders import build_test_services

    bare = create(build_test_services(output_dir=tmp_path / "bare"))
    assert "feature.dispatch" not in bare.kernel.features.installed()


def calls_open(services: object) -> int:
    state = getattr(services, "state", None)
    trace = getattr(state, "trace", [])
    return sum(1 for item in trace if item == "state.open")
