"""Run the owned provider through Task 01's simulator."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g18.implementation import create
from patrol.ground.extensions.g18.scenarios import cases
from patrol.ground.extensions.g18.script import projection_dir
from patrol.ground.kernel.contracts import SimulationReport
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def test_harness_plays_every_ack_case(tmp_path: Path) -> None:
    report = asyncio.run(_run(tmp_path))
    assert report.failures == ()
    assert report.live_call_count == 0
    assert report.skipped == 0
    assert report.assertion_count > 0
    names = [case["case_id"] for case in report.cases]
    assert names == [
        "ordered_acks",
        "accepted_only",
        "reply_timeout",
        "landing_unknown",
        "duplicate_final",
        "conflicting_final",
        "stale_epoch",
        "unverified_completion",
        "local_flag_ignored",
        "unknown_command",
        "dog_ack",
    ]
    assert all(case["passed"] is True for case in report.cases)
    saved = projection_dir() / "ordered_acks.json"
    projection = json.loads(saved.read_text(encoding="utf-8"))
    assert projection["history"] == ["accepted", "running", "completed"]
    assert projection["flight_state"] == "airborne"
    assert projection["grounded"] is False
    assert projection["completion_events"] == 1
    assert projection["proposed_commands"] == []
    landing = json.loads((projection_dir() / "landing_unknown.json").read_text(encoding="utf-8"))
    assert landing["recovery_required"] is True
    assert landing["blocks_next_mission"] is True
    assert landing["grounded"] is False
    timeout = json.loads((projection_dir() / "reply_timeout.json").read_text(encoding="utf-8"))
    assert timeout["query_command"] == "cmd-drone-001"
    assert timeout["issued_command_ids"] == ["cmd-drone-001"]
    destination = repo_root() / "artifacts" / "task-18" / "simulation.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(_jsonable(report), indent=2) + "\n", encoding="utf-8")


async def _run(tmp_path: Path) -> SimulationReport:
    selected = cases(seed=0)
    rows: list[Mapping[str, object]] = []
    failures: list[str] = []
    assertions = 0
    live_calls = 0
    trace: list[str] = []
    for case in selected:
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
        live_calls += report.live_call_count
        trace.extend(report.trace)
    return SimulationReport(
        task_id="GROUND-18",
        seed=0,
        clock_mode="manual",
        cases=tuple(rows),
        failures=tuple(dict.fromkeys(failures)),
        assertion_count=assertions,
        modes={"dog": "fake", "drone": "fake", "grok": "fake"},
        trace=tuple(trace),
        artifact_paths=(),
        live_call_count=live_calls,
        skipped=0,
    )


def _jsonable(report: SimulationReport) -> dict[str, object]:
    return {
        "task_id": report.task_id,
        "seed": report.seed,
        "clock_mode": report.clock_mode,
        "cases": [_plain(case) for case in report.cases],
        "failures": list(report.failures),
        "assertion_count": report.assertion_count,
        "modes": dict(report.modes),
        "trace": list(report.trace),
        "artifact_paths": ["artifacts/task-18/simulation.json"],
        "live_call_count": report.live_call_count,
        "skipped": report.skipped,
        "evidence": "simulated",
    }


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    return value
