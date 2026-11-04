"""Halt, fault, and same-turn races at device boundaries."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.ground.extensions.g09.synthetic import StageScript
from tests.ground.g09.helpers import admit, calls, services_for, wait_until


def test_halt_during_route_starts_no_later_stage(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = services_for(tmp_path)
        services.kernel.barriers.arm("dog.run_route")
        admitted = await admit(services, workflow, tmp_path)
        assert admitted.incident is not None
        handle = workflow.start(admitted.incident)
        await wait_until(lambda: "dog.run_route" in services.kernel.tasks.pending())
        workflow.request_halt("operator halt")
        assert services.kernel.authority.cancelled is True
        services.kernel.barriers.release("dog.run_route")
        await workflow.join(handle)
        assert workflow.outcome == "aborted"
        assert workflow.snapshot().phase == "FAULT"
        assert workflow.snapshot().recovery_required is True
        assert "dog.capture_frame" not in calls(services)
        assert "drone.inspect" not in calls(services)
        assert "reasoner.assess_ground_view" not in calls(services)
        assert getattr(services.journal, "published", None) is None
        assert services.kernel.tasks.pending() == ()

    asyncio.run(body())


def test_halt_and_release_in_either_order_block_the_next_stage(tmp_path: Path) -> None:
    async def once(root: Path, halt_first: bool) -> None:
        services, workflow = services_for(root)
        services.kernel.barriers.arm("dog.run_route")
        admitted = await admit(services, workflow, root)
        assert admitted.incident is not None
        handle = workflow.start(admitted.incident)
        await wait_until(lambda: "dog.run_route" in services.kernel.tasks.pending())
        if halt_first:
            workflow.request_halt("operator halt")
            services.kernel.barriers.release("dog.run_route")
        else:
            services.kernel.barriers.release("dog.run_route")
            workflow.request_halt("operator halt")
        await workflow.join(handle)
        assert "dog.capture_frame" not in calls(services)
        assert "drone.inspect" not in calls(services)

    async def body() -> None:
        await once(tmp_path / "halt-first", True)
        await once(tmp_path / "release-first", False)

    asyncio.run(body())


def test_persistence_and_link_loss_request_safety_while_a_stage_is_pending(tmp_path: Path) -> None:
    async def once(root: Path, link: bool) -> None:
        services, workflow = services_for(root)
        services.kernel.barriers.arm("dog.run_route")
        admitted = await admit(services, workflow, root)
        assert admitted.incident is not None
        handle = workflow.start(admitted.incident)
        await wait_until(lambda: "dog.run_route" in services.kernel.tasks.pending())
        if link:
            workflow.notify_link_lost("radio")
        else:
            workflow.notify_persistence_fault("disk")
        assert services.kernel.authority.cancelled is True
        safety = getattr(services.safety, "trace", [])
        assert "safety.request" in safety
        services.kernel.barriers.release("dog.run_route")
        await workflow.join(handle)
        assert "drone.inspect" not in calls(services)
        assert services.kernel.tasks.pending() == ()

    async def body() -> None:
        await once(tmp_path / "disk", False)
        await once(tmp_path / "radio", True)

    asyncio.run(body())


def test_late_feature_result_after_halt_does_not_prepare_the_dog(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = services_for(
            tmp_path,
            script=StageScript(hold_slot="feature.dispatch"),
        )
        services.kernel.barriers.arm("feature.dispatch")
        admitted = await admit(services, workflow, tmp_path)
        assert admitted.incident is not None
        handle = workflow.start(admitted.incident)
        await wait_until(lambda: "holding:feature.dispatch" in calls(services))
        workflow.request_halt("operator halt")
        services.kernel.barriers.release("feature.dispatch")
        await workflow.join(handle)
        assert "dog.prepare" not in calls(services)
        assert "dog.run_route" not in calls(services)
        assert workflow.outcome == "aborted"

    asyncio.run(body())
