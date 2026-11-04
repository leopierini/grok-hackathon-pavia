"""Demo timing feature. create(services) does not read logs or call devices."""

from __future__ import annotations

from collections.abc import Mapping

from patrol.ground.extensions.g31.metrics import MeasureFailure, compute_metrics
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_metrics"
SCHEMA = "ground-task-v2"


class MetricsFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest", False)
        try:
            if request.ticket is not None:
                self.services.kernel.authority.require_current(request.ticket)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, exc.error.recovery_required)
        journal = _journal(request.payload)
        if journal is None and request.kind == "diagnostic":
            from patrol.ground.extensions.g31.scenarios import CASE_IDS, run_case

            if request.name in CASE_IDS:
                report = await run_case(self.services, request.name, _seed(request.payload))
                return _harness_result(request.name, report)
        if journal is None:
            return _failed("invalid_input", "journal is required", False)
        try:
            data = compute_metrics(
                journal,
                mission_start_monotonic=request.payload.get("mission_start_monotonic"),
                clock=request.payload.get("clock"),
                evaluation=request.payload.get("evaluation"),
                run_id=request.payload.get("run_id"),
            )
        except MeasureFailure as exc:
            return _failed(exc.code, exc.detail, False)
        return FeatureResult("ok", freeze_map(data), (), None)


def create(services: BaseServices) -> MetricsFeature:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "metrics create expects base services")
    return MetricsFeature(services)


def _journal(payload: Mapping[str, object]) -> object | None:
    if "journal" in payload:
        return payload["journal"]
    if "events" in payload:
        return payload["events"]
    return None


def _seed(payload: Mapping[str, object]) -> int:
    value = payload.get("seed", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _harness_result(case_id: str, report: Mapping[str, object]) -> FeatureResult:
    passed = report.get("passed") is True
    trace = report.get("trace")
    if not isinstance(trace, tuple):
        trace = ("check_failed", case_id)
    detail = case_id if passed else _failure_text(report)
    data = freeze_map(
        {
            "simulated": True,
            "live_call_count": 0,
            "device_calls": 0,
            "authorized": False,
            "retained": False,
            "within_limit": True,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
            "detail": detail,
            "trace": trace,
        }
    )
    if passed:
        return FeatureResult("ok", data, (), None)
    return FeatureResult("failed", data, (), GroundError("validation_failed", detail, False))


def _failure_text(report: Mapping[str, object]) -> str:
    failures = report.get("failures")
    if isinstance(failures, list) and failures and isinstance(failures[0], str):
        return failures[0]
    return "timing case failed"


def _failed(code: str, detail: str, recovery_required: bool) -> FeatureResult:
    if not detail:
        detail = code
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "simulated": True,
                "live_call_count": 0,
                "slot": SLOT,
                "schema_version": SCHEMA,
                "detail": detail,
            }
        ),
        (),
        GroundError(code, detail, recovery_required),
    )
