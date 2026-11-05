"""Typed payload, ticket, and import boundaries."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

from patrol.ground.extensions.g09.implementation import create
from patrol.ground.extensions.g09.synthetic import StageScript
from patrol.ground.kernel.contracts import FeatureRequest, IncidentInput
from patrol.ground.kernel.jpeg import tiny_jpeg_bytes
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import build_test_services
from tests.ground.g09.helpers import TARGET, admit, calls, run_mission, services_for, wait_until


def test_malformed_and_mistyped_results_do_not_move(tmp_path: Path) -> None:
    async def body() -> None:
        malformed_services, malformed = await run_mission(
            tmp_path / "malformed",
            script=StageScript(malformed_slot="feature.dispatch"),
        )
        typed_services, typed = await run_mission(
            tmp_path / "typed",
            script=StageScript(bad_continuation=True),
        )
        forged_services, forged = await run_mission(
            tmp_path / "forged",
            script=StageScript(forged_ticket=True),
        )
        bool_services, bad_bool = await run_mission(
            tmp_path / "bool",
            script=StageScript(prepare_bad_bool=True),
        )
        assert malformed.failure_code == "validation_failed"
        assert typed.failure_code == "validation_failed"
        assert forged.failure_code == "stale_ticket"
        assert bad_bool.failure_code == "invalid_input"
        for services in (malformed_services, typed_services, forged_services, bool_services):
            assert "dog.run_route" not in calls(services)
            assert "drone.inspect" not in calls(services)
        assert "dog.prepare" not in calls(bool_services)
        assert forged.snapshot().phase != "MOVE_DOG"

    asyncio.run(body())


def test_admission_after_an_epoch_change_does_not_open_a_session(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = services_for(
            tmp_path,
            script=StageScript(hold_slot="feature.incident_input"),
        )
        services.kernel.barriers.arm("feature.incident_input")
        image = tmp_path / "phone.jpg"
        services.kernel.io.write_bytes(image, tiny_jpeg_bytes())
        task = asyncio.create_task(
            workflow.load(IncidentInput(str(image.resolve()), "room_2", TARGET, None, True))
        )
        await wait_until(lambda: "holding:feature.incident_input" in calls(services))
        services.kernel.authority.latch_cancel("halt")
        services.kernel.barriers.release("feature.incident_input")
        admitted = await task
        assert admitted.accepted is False
        assert admitted.error is not None
        assert admitted.error.code == "stale_ticket"
        state_trace = getattr(services.state, "trace", [])
        assert "state.open" not in state_trace

    asyncio.run(body())


def test_empty_target_is_rejected_before_open(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = services_for(tmp_path)
        image = tmp_path / "phone.jpg"
        services.kernel.io.write_bytes(image, tiny_jpeg_bytes())
        admitted = await workflow.load(
            IncidentInput(str(image.resolve()), "room_2", "  ", None, True)
        )
        assert admitted.accepted is False
        assert "state.open" not in getattr(services.state, "trace", [])
        assert calls(services) == []

    asyncio.run(body())


def test_import_boundary_stays_inside_g09() -> None:
    root = repo_root()
    files = list((root / "patrol" / "ground" / "extensions" / "g09").rglob("*.py"))
    files.extend((root / "tests" / "ground" / "g09").rglob("*.py"))
    own = "patrol.ground.extensions.g09"
    banned_roots = {"djitellopy", "unitree_webrtc_connect", "xai", "xai_sdk", "requests"}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                if module.startswith("patrol.ground.extensions.g") and not module.startswith(own):
                    raise AssertionError(module)
                if module.startswith(("patrol.dog", "patrol.drone", "patrol.grok")):
                    raise AssertionError(module)
                if module.split(".", 1)[0] in banned_roots:
                    raise AssertionError(module)


def test_fixed_seed_traces_match_and_tasks_are_collected(tmp_path: Path) -> None:
    async def once(root: Path) -> tuple[object, ...]:
        services = build_test_services(output_dir=root, seed=0)
        workflow = create(services)
        result = await workflow.execute(
            FeatureRequest("diagnostic", "blocked_resolved", None, freeze_map({"seed": 0}))
        )
        assert services.kernel.tasks.pending() == ()
        assert workflow.input_ran is True
        assert workflow.health_ran is True
        trace = result.data.get("trace")
        assert isinstance(trace, tuple)
        return trace

    async def body() -> None:
        first = await once(tmp_path / "a")
        second = await once(tmp_path / "b")
        assert first == second
        assert "inspect" in first

    asyncio.run(body())


def test_admission_helper_is_used(tmp_path: Path) -> None:
    async def body() -> None:
        services, workflow = services_for(tmp_path)
        admitted = await admit(services, workflow, tmp_path)
        assert admitted.accepted is True

    asyncio.run(body())
