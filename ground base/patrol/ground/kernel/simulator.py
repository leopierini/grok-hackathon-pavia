"""One-case simulation runner used by the task harness."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    SimulationCase,
    SimulationReport,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map, freeze_str_map


class KernelSimulator:
    def __init__(self) -> None:
        self._bound = False

    def bind(self, _context: object) -> None:
        self._bound = True

    async def run(
        self,
        case: SimulationCase,
        *,
        providers: Mapping[str, object],
        clock_mode: str,
    ) -> SimulationReport:
        feature = providers.get("feature")
        services = providers.get("services")
        if not isinstance(services, BaseServices) or not hasattr(feature, "execute"):
            raise fault("invalid_input", "simulation providers are incomplete")
        if clock_mode not in {"manual", "real"}:
            raise fault("invalid_input", "clock mode must be manual or real")
        failures: list[str] = []
        assertions = 0
        status = "failed"
        error_code = ""
        trace: tuple[str, ...] = ()
        live_calls = 0
        try:
            request = FeatureRequest(
                kind="diagnostic",
                name=case.case_id,
                ticket=None,
                payload=freeze_map({"seed": case.seed}),
            )
            checked = services.kernel.result_validation.feature_request(
                "kernel.foundation",
                request,
            )
            raw = await _execute(feature, checked)
            result = services.kernel.result_validation.feature_result(
                "kernel.foundation",
                raw,
            )
            status = result.status
            if result.error is not None:
                error_code = result.error.code
            compared, compare_failures = _compare(case, result)
            assertions += compared
            failures.extend(compare_failures)
            device_trace = _device_trace(services)
            for name in case.forbidden_calls:
                assertions += 1
                if name in device_trace:
                    failures.append(f"forbidden call {name}")
            live_value = result.data.get("live_call_count", 0)
            if isinstance(live_value, int) and not isinstance(live_value, bool):
                live_calls = live_value
            trace_value = result.data.get("trace", ())
            if isinstance(trace_value, tuple):
                trace = tuple(str(item) for item in trace_value)
        except Exception as exc:  # noqa: BLE001 - harness must record, not skip
            failures.append(f"{type(exc).__name__}: {exc}")
            assertions += 1
        teardown_failures, teardown_assertions = await _teardown(case, services, feature)
        failures.extend(teardown_failures)
        assertions += teardown_assertions
        passed = not failures
        case_row = freeze_map(
            {
                "case_id": case.case_id,
                "passed": passed,
                "status": status,
                "error_code": error_code,
                "clock_mode": "real" if case.case_id == "responsiveness" else clock_mode,
                "live_call_count": live_calls,
                "trace": trace,
                "failures": tuple(failures),
            }
        )
        return SimulationReport(
            task_id=case.task_id,
            seed=case.seed,
            clock_mode=clock_mode,
            cases=(case_row,),
            failures=() if passed else (case.case_id,),
            assertion_count=assertions,
            modes=freeze_str_map({"dog": "fake", "drone": "fake", "grok": "fake"}),
            trace=trace,
            artifact_paths=(),
            live_call_count=live_calls,
            skipped=0,
        )


async def _execute(feature: object, request: FeatureRequest) -> FeatureResult:
    method_name = "execute"
    execute = getattr(feature, method_name, None)
    if not callable(execute):
        raise fault("invalid_input", "provider has no execute method")
    result: object = await execute(request)
    if not isinstance(result, FeatureResult):
        raise fault("validation_failed", "provider did not return a FeatureResult")
    return result


def _compare(case: SimulationCase, result: FeatureResult) -> tuple[int, list[str]]:
    assertions = 0
    failures: list[str] = []
    for key, expected in case.expected.items():
        assertions += 1
        if key == "status":
            actual: object = result.status
        elif key == "error_code":
            actual = None if result.error is None else result.error.code
        elif key == "error_detail":
            actual = None if result.error is None else result.error.detail
        else:
            actual = result.data.get(key)
        if actual != expected:
            failures.append(f"{key}: expected {expected!r} got {actual!r}")
    return assertions, failures


def _device_trace(services: BaseServices) -> tuple[str, ...]:
    devices = getattr(services.adapters, "devices", None)
    calls = getattr(devices, "calls", ())
    if isinstance(calls, list):
        return tuple(str(item) for item in calls)
    return ()


async def _teardown(
    case: SimulationCase,
    services: BaseServices,
    feature: object,
) -> tuple[list[str], int]:
    failures: list[str] = []
    assertions = 0
    services.kernel.barriers.release_all()
    try:
        await services.kernel.tasks.collect(deadline=2)
    except GroundFault as exc:
        failures.append(exc.error.detail)
    assertions += 1
    if services.kernel.tasks.pending():
        failures.append("retained task still pending after teardown")
    if "assert_released" in case.teardown:
        observations = getattr(feature, "observations", {})
        flag = observations.get("released") if isinstance(observations, dict) else None
        assertions += 1
        released = isinstance(flag, dict) and flag.get("released") is True
        cancelled = isinstance(flag, dict) and flag.get("cancelled") is True
        if not released or cancelled:
            failures.append("barrier worker was not released cleanly")
    result_cleanup = getattr(feature, "cleanup_paths", ())
    if isinstance(result_cleanup, tuple):
        cleanup = result_cleanup
    for item in cleanup:
        assertions += 1
        try:
            _remove_owned(Path(str(item)))
        except GroundFault as exc:
            failures.append(exc.error.detail)
    return failures, assertions


def _remove_owned(path: Path) -> None:
    if not path.exists():
        return
    resolved = path.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        resolved.relative_to(temp_root)
    except ValueError as exc:
        raise fault("path_escape", "refusing to delete a path outside the temp directory") from exc
    if resolved.is_dir():
        import shutil

        shutil.rmtree(resolved)
    else:
        resolved.unlink()
