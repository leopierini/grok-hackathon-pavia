"""Run Task 01's simulator against every g23 case. The v1 loader is not edited."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.extensions.g23.scenarios import cases
from patrol.ground.kernel.contracts import SimulationReport
from tests.ground.g23.support import opened, run


def test_kernel_simulator_covers_every_case(tmp_path: Path) -> None:
    async def body() -> None:
        produced = cases(seed=0)
        assert produced
        rows: list[dict[str, object]] = []
        failures: list[str] = []
        assertions = 0
        for case in produced:
            services, feature = opened(tmp_path / case.case_id)
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            assert isinstance(report, SimulationReport)
            assertions += report.assertion_count
            if report.failures:
                failures.append(case.case_id)
            for row in report.cases:
                rows.append({str(key): value for key, value in row.items()})
        destination = Path("artifacts/task-23/simulation.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {
                    "task_id": "GROUND-23",
                    "seed": 0,
                    "clock_mode": "manual",
                    "cases": rows,
                    "failures": failures,
                    "assertion_count": assertions,
                    "modes": {"dog": "fake", "drone": "fake", "grok": "fake"},
                    "live_call_count": 0,
                    "skipped": 0,
                    "evidence": "simulated",
                    "harness": "kernel.simulator",
                },
                indent=2,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        assert failures == [], rows

    run(body)
