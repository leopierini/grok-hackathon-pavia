"""Backend sessions for a future frontend. No HTTP server or live robot bridge."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from patrol.ground.demo import SCENARIOS, run_demo
from patrol.ground.kernel.v2_catalog import V2_SLOTS
from patrol.ground.steps import StepControlError, StepSession, StepSpec, _validate


def step_catalog() -> list[dict[str, object]]:
    """All v2 provider groups, including stages with mandatory fixed safety timing."""
    return [
        {
            "task": int(owner),
            "slot": slot,
            "wait_s": 3.0,
            "hard_limit_s": 30.0,
            "operator_timing": int(owner) not in {28, 29, 31, 32},
            "retry_mode": "idempotent" if int(owner) in {20, 30} else "never",
        }
        for slot, owner in V2_SLOTS.items()
    ]


@dataclass
class DemoHandle:
    controls: StepSession
    task: asyncio.Task[dict[str, Any]]
    output: Path

    def snapshot(self) -> dict[str, object]:
        result: dict[str, object] = {
            "controls": self.controls.get_snapshot(),
            "finished": self.task.done(),
            "outcome": None,
        }
        if self.task.done():
            if self.task.cancelled():
                result["outcome"] = "cancelled"
            elif self.task.exception() is not None:
                result["outcome"] = "failed"
                result["error"] = type(self.task.exception()).__name__
            else:
                report = self.task.result()
                result.update(
                    outcome=report["outcome"],
                    goal_reached=report["goal_reached"],
                    landing_verified=report["landing_verified"],
                )
        return result

    async def command(self, request: Mapping[str, object]) -> dict[str, object]:
        return await self.controls.command(request)

    async def close(self) -> dict[str, object]:
        await self.controls.close()
        if not self.task.done():
            # The runner observes the halt signal and performs existing safety cleanup.
            await asyncio.wait((self.task,), timeout=3.0)
        return self.snapshot()


def start_demo(
    output: Path,
    *,
    scenario: str = "happy_path",
    seed: int = 0,
    transport: str = "ethernet",
    mission_limit_s: float = 180.0,
    budgets: Sequence[Mapping[str, object]] = (),
) -> DemoHandle:
    """Start in the current event loop and immediately return a controllable handle.

    Budget rows are {task: int, wait_s: number, hard_limit_s: number}. They are
    validated atomically before any task starts. Each loop iteration gets its own
    step ID/attempt history; group budgets apply to future iterations as well.
    """
    if scenario not in SCENARIOS or transport not in {"ethernet", "wifi"}:
        raise StepControlError("invalid_input", "unknown scenario or transport")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise StepControlError("invalid_input", "seed must be an integer")
    if len(budgets) > 22:
        raise StepControlError("invalid_input", "too many budget rows")
    timing: dict[int, tuple[float, float]] = {}
    for row in budgets:
        if set(row) != {"task", "wait_s", "hard_limit_s"}:
            raise StepControlError("invalid_input", "budget needs task, wait_s, hard_limit_s")
        task = row["task"]
        if isinstance(task, bool) or not isinstance(task, int) or task not in range(11, 33):
            raise StepControlError("invalid_input", "task must identify a v2 provider")
        if task in {28, 29, 31, 32} or task in timing:
            raise StepControlError("budget_locked", "duplicate task or fixed safety/cleanup timing")
        spec = StepSpec(f"g{task}", f"Task {task}", row["wait_s"], row["hard_limit_s"])  # type: ignore[arg-type]
        _validate(spec)
        timing[task] = (float(spec.wait_s), float(spec.hard_limit_s))
    controls = StepSession([], mission_limit_s=mission_limit_s)
    task = asyncio.create_task(
        run_demo(
            output,
            scenario=scenario,
            seed=seed,
            transport=transport,
            controls=controls,
            budgets=timing,
        )
    )
    return DemoHandle(controls, task, output)
