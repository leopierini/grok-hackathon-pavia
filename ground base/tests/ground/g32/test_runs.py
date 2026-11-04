"""Run directories, failed-command exit, and barrier teardown."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g32.implementation import command_exit, create
from patrol.ground.extensions.g32.rehearsal import distinct_ids, overwrite_id
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, SimulationCase
from patrol.ground.kernel.validation import freeze_map
from tests.ground.g32.conftest import run


def test_distinct_run_ids_make_two_directories(services: BaseServices) -> None:
    _feature, result = run(services, "distinct_runs")
    assert result.status == "ok"
    assert command_exit(result) == 0
    devices = getattr(services.adapters, "devices", None)
    output = Path(str(getattr(devices, "output_dir", "")))
    left, right = distinct_ids(0)
    for name in (left, right):
        report = json.loads((output / name / "report.json").read_text(encoding="utf-8"))
        assert report["scenario"] == "happy_path"
        assert report["passed"] is True
        assert "physical acceptance" in (output / name / "script.md").read_text(encoding="utf-8")
    assert left != right


def test_second_run_does_not_overwrite(services: BaseServices) -> None:
    _feature, result = run(services, "overwrite_rejected")
    assert result.status == "failed"
    assert result.data["detail"] == "overwrite_rejected"
    assert command_exit(result) == 1
    devices = getattr(services.adapters, "devices", None)
    output = Path(str(getattr(devices, "output_dir", "")))
    report_path = output / overwrite_id(0) / "report.json"
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["scenario"] == "happy_path"
    assert saved["passed"] is True
    assert saved["detail"] == "happy_path"
    assert list(output.glob("rehearsal-overwrite-seed0*")) == [output / overwrite_id(0)]


def test_unreleased_barrier_fails_teardown(services: BaseServices) -> None:
    feature = create(services)
    case = SimulationCase(
        task_id="GROUND-32",
        case_id="barrier_cancelled",
        seed=0,
        setup=freeze_map({"seed": 0}),
        stimuli=(),
        barriers=(),
        faults=(),
        expected=freeze_map({"status": "ok", "detail": "barrier_cancelled"}),
        forbidden_calls=(),
        teardown=("assert_released",),
    )
    report = asyncio.run(
        services.kernel.simulator.run(
            case,
            providers={"feature": feature, "services": services},
            clock_mode="manual",
        )
    )
    assert report.failures == ("barrier_cancelled",)
    released = feature.observations["released"]
    assert isinstance(released, dict)
    assert released["cancelled"] is True
    assert released["released"] is False


def test_request_shape_accepts_named_scenario(services: BaseServices) -> None:
    feature = create(services)
    devices = getattr(services.adapters, "devices", None)
    output = getattr(devices, "output_dir", None)
    request = FeatureRequest(
        "diagnostic",
        "ignored-name",
        None,
        {
            "scenario": "stale_frame",
            "seed": 0,
            "simulation_mode": "simulation",
            "output_root": str(output),
        },
    )
    result = asyncio.run(feature.execute(request))
    assert result.status == "failed"
    assert result.data["detail"] == "stale_frame_dropped"
