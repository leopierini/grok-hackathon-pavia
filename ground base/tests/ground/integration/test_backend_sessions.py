from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from patrol.ground import demo
from patrol.ground.backend import start_demo, step_catalog
from patrol.ground.kernel.contracts import FeatureRequest, FeatureResult
from patrol.ground.selftest import main as selftest
from patrol.ground.steps import StepControlError


async def until(handle: Any, status: str) -> dict[str, Any]:
    for _ in range(1000):
        snapshot = handle.controls.get_snapshot()
        if any(row["status"] == status for row in snapshot["steps"]):
            return snapshot
        if handle.task.done():
            await handle.task
            raise AssertionError("demo ended before the injected stage")
        await asyncio.sleep(0.001)
    raise AssertionError("stage never reached its expected state")


def test_frontend_catalog_has_explicit_defaults_and_locked_safety() -> None:
    catalog = step_catalog()
    assert [row["task"] for row in catalog] == list(range(11, 33))
    assert [row["task"] for row in catalog if not row["operator_timing"]] == [28, 29, 31, 32]
    json.dumps(catalog, allow_nan=False)


def test_documented_selftest_entrypoint_runs_composed_stub_demo(tmp_path: Path) -> None:
    assert (
        selftest(
            ["--stubs", "--scenario", "drone_first", "--output-dir", str(tmp_path / "selftest")]
        )
        == 0
    )


@pytest.mark.parametrize("transport", ["ethernet", "wifi"])
def test_backend_real_composition_completes_and_persists_control_audit(
    tmp_path: Path,
    transport: str,
) -> None:
    async def scenario() -> None:
        handle = start_demo(
            tmp_path / "session",
            transport=transport,
            budgets=[
                {"task": 16, "wait_s": 5, "hard_limit_s": 20},
            ],
        )
        report = await handle.task
        assert report["outcome"] == "completed"
        snapshot: Any = handle.snapshot()
        assert snapshot["finished"] is True
        controls = snapshot["controls"]
        assert controls["closed"] is True
        assert controls["halted"] is False
        assert len(controls["completed_steps"]) > 50
        vision = [row for row in controls["steps"] if row["step_id"].startswith("g16.")]
        assert len(vision) == 3
        assert all(row["wait_s"] == 5 and row["hard_limit_s"] == 20 for row in vision)
        events = json.loads((handle.output / "step-events.json").read_text())
        assert any(row["event"] == "attempt_started" for row in events)
        assert all(row["status"] == "succeeded" for row in controls["steps"])
        assert (await handle.close())["outcome"] == "completed"

    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["wait_more", "retry", "halt"])
def test_controlled_demo_recovers_current_stage_without_replaying_earlier_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    original_loader = demo.load_callable
    release = asyncio.Event()
    calls: list[int] = []

    def load_with_fault(manifest: Any, which: str) -> Any:
        factory = original_loader(manifest, which)
        if manifest.task_id != "GROUND-20" or which != "factory":
            return factory

        def create(services: Any) -> Any:
            provider = factory(services)
            original = provider.execute

            async def slow_or_failed(request: FeatureRequest) -> FeatureResult:
                calls.append(1)
                if len(calls) == 1:
                    if action == "retry":
                        raise ConnectionError("synthetic stage failure")
                    await release.wait()
                return await original(request)

            provider.execute = slow_or_failed
            return provider

        return create

    monkeypatch.setattr(demo, "load_callable", load_with_fault)

    async def scenario() -> None:
        handle = start_demo(
            tmp_path / "session",
            budgets=[
                {"task": 20, "wait_s": 3.0 if action == "retry" else 0.05, "hard_limit_s": 10},
            ],
        )
        snapshot = await until(handle, "failed" if action == "retry" else "awaiting_operator")
        current = next(
            row for row in snapshot["steps"] if row["step_id"] == snapshot["active_step_id"]
        )
        completed_before = list(snapshot["completed_steps"])
        request: dict[str, object] = {
            "action": action,
            "request_id": f"operator-{action}",
            "expected_revision": snapshot["revision"],
        }
        if action == "halt":
            request["reason"] = "operator demo halt"
        else:
            request.update(
                step_id=current["step_id"], attempt_id=current["attempts"][-1]["attempt_id"]
            )
            if action == "wait_more":
                request["seconds"] = 5
        response = await handle.command(request)
        assert response["ok"] is True
        release.set()
        report = await asyncio.wait_for(handle.task, timeout=10)
        assert report["outcome"] == ("unresolved" if action == "halt" else "completed")
        assert len(calls) == (2 if action == "retry" else 1)
        assert all(key in report["step_control"]["completed_steps"] for key in completed_before)
        commands = report["commands"]
        assert len({row["payload"]["command_id"] for row in commands}) == len(commands)
        assert not any(row["payload"]["action"] == "takeoff" for row in commands)
        if action == "halt":
            assert report["step_control"]["halted"] is True
            assert report["recovery_required"] is True
        await handle.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "budgets",
    [
        [{"task": 28, "wait_s": 10, "hard_limit_s": 20}],
        [{"task": 16, "wait_s": 30, "hard_limit_s": 5}],
        [{"task": True, "wait_s": 1, "hard_limit_s": 5}],
        [{"task": 16, "wait_s": 3, "hard_limit_s": 10, "safe_to_retry": True}],
    ],
)
def test_invalid_budgets_do_not_start_or_create_run_directory(tmp_path: Path, budgets: Any) -> None:
    with pytest.raises(StepControlError):
        start_demo(tmp_path / "must-not-exist", budgets=budgets)
    assert not (tmp_path / "must-not-exist").exists()
