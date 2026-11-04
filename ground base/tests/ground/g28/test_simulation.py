"""Task 01 harness cases for the safety latch. No live device calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g28.implementation import create
from patrol.ground.extensions.g28.scenarios import cases
from patrol.ground.kernel.contracts import SimulationReport
from patrol.ground.testing.builders import build_test_services


def test_harness_runs_every_safety_case(tmp_path: Path) -> None:
    async def body() -> list[SimulationReport]:
        reports: list[SimulationReport] = []
        for case in cases(seed=0):
            services = build_test_services(
                clock_mode="manual",
                seed=0,
                output_dir=tmp_path / case.case_id,
            )
            feature = create(services)
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            reports.append(report)
        return reports

    reports = asyncio.run(body())
    failures = [report.failures for report in reports if report.failures]
    details = [dict(report.cases[0]) for report in reports if report.failures]
    assert failures == [], details
    assert len(reports) == len(cases(seed=0))
    assert sum(report.assertion_count for report in reports) > 0
    assert all(report.live_call_count == 0 for report in reports)


def test_harness_report_matches_the_cli_shape(tmp_path: Path) -> None:
    destination = tmp_path / "simulation.json"

    async def body() -> None:
        rows: list[object] = []
        failures: list[str] = []
        assertions = 0
        trace: list[str] = []
        for case in cases(seed=0):
            services = build_test_services(
                clock_mode="manual",
                seed=0,
                output_dir=tmp_path / case.case_id,
            )
            feature = create(services)
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            rows.extend(report.cases)
            failures.extend(report.failures)
            assertions += report.assertion_count
            trace.extend(report.trace)
        payload = {
            "task_id": "GROUND-28",
            "seed": 0,
            "clock_mode": "manual",
            "cases": [dict(row) for row in rows],
            "failures": failures,
            "assertion_count": assertions,
            "modes": {"dog": "fake", "drone": "fake", "grok": "fake"},
            "trace": trace,
            "artifact_paths": [str(destination)],
            "live_call_count": 0,
            "skipped": 0,
            "evidence": "simulated",
        }
        destination.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

    asyncio.run(body())
    saved = json.loads(destination.read_text(encoding="utf-8"))
    assert saved["failures"] == []
    assert saved["evidence"] == "simulated"
    assert saved["live_call_count"] == 0
    assert {row["case_id"] for row in saved["cases"]} >= {
        "halt_during_vision_timeout",
        "late_decision",
        "expired_lease",
        "link_loss",
        "obstacle_block",
        "noisy_rssi",
        "replay_halt",
        "reset_without_token",
        "superseded_ids",
    }
