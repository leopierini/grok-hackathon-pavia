"""Run the owned cases through Task 01's simulator."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g27.implementation import create
from patrol.ground.extensions.g27.scenarios import cases
from patrol.ground.kernel.contracts import SimulationReport
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_str_map
from patrol.ground.sim import _jsonable
from patrol.ground.testing.builders import build_test_services


def test_kernel_simulator_covers_every_recovery_case(tmp_path: Path) -> None:
    rows: list[Mapping[str, object]] = []
    failures: list[str] = []
    assertions = 0
    trace: list[str] = []
    live_calls = 0
    for case in cases(seed=0):
        services = build_test_services(
            clock_mode="manual",
            seed=0,
            output_dir=tmp_path / case.case_id,
        )
        feature = create(services)
        report = asyncio.run(
            services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
        )
        rows.extend(report.cases)
        failures.extend(report.failures)
        assertions += report.assertion_count
        trace.extend(report.trace)
        live_calls += report.live_call_count
    combined = SimulationReport(
        task_id="GROUND-27",
        seed=0,
        clock_mode="manual",
        cases=tuple(rows),
        failures=tuple(dict.fromkeys(failures)),
        assertion_count=assertions,
        modes=freeze_str_map({"dog": "fake", "drone": "fake", "grok": "fake"}),
        trace=tuple(trace),
        artifact_paths=(),
        live_call_count=live_calls,
        skipped=0,
    )
    destination = repo_root() / "artifacts" / "task-27" / "simulation.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _jsonable(combined)
    payload["artifact_paths"] = [str(destination)]
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    assert failures == []
    assert len(rows) == 10
    assert live_calls == 0
