"""Per-task simulation command.

Run with ``python -m patrol.ground.sim --task NN --case all --seed 0 --report PATH``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import socket
import sys
import tempfile
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from patrol.ground.kernel.contracts import SimulationReport
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.loader import discover, load_callable, normalize_task
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_str_map
from patrol.ground.testing.builders import build_test_services


class _SocketGuard:
    """Count socket construction without replacing the socket type.

    Asyncio on Windows checks ``isinstance(conn, socket.socket)``. Replacing the
    class with a function breaks that check, so only ``__init__`` is wrapped.
    """

    def __init__(self) -> None:
        self.count = 0
        self._original_init = socket.socket.__init__

    def install(self) -> None:
        guard = self

        def guarded(sock: socket.socket, *args: object, **kwargs: object) -> None:
            frames = traceback.extract_stack()[:-1]
            caller = frames[-1].filename.replace("\\", "/") if frames else ""
            if "/patrol/" in caller and "/asyncio/" not in caller:
                guard.count += 1
                raise RuntimeError("simulation opened a socket")
            original = cast(Callable[..., None], guard._original_init)
            original(sock, *args, **kwargs)

        socket.socket.__init__ = guarded  # type: ignore[method-assign, assignment]

    def close(self) -> None:
        socket.socket.__init__ = self._original_init  # type: ignore[method-assign]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m patrol.ground.sim")
    parser.add_argument("--task", required=True)
    parser.add_argument("--case", default="all")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(
            _run(task=args.task, case_name=args.case, seed=args.seed, report_path=Path(args.report))
        )
    except GroundFault as exc:
        print(f"{exc.error.code}: {exc.error.detail}", file=sys.stderr)
        return 1
    destination = Path(args.report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(_jsonable(report), indent=2) + "\n", encoding="utf-8")
    if report.failures or report.skipped:
        print(f"simulation failed: {', '.join(report.failures)}", file=sys.stderr)
        return 1
    print(f"simulation passed: {len(report.cases)} case(s), {report.assertion_count} assertion(s)")
    return 0


async def _run(*, task: str, case_name: str, seed: int, report_path: Path) -> SimulationReport:
    number = normalize_task(task)
    root = repo_root()
    manifests = discover(root / "patrol" / "ground" / "extensions", only_task=number)
    manifest = manifests[0]
    scenario_factory = load_callable(manifest, "scenario_factory")
    provider_factory = load_callable(manifest, "factory")
    produced = scenario_factory(seed=seed)
    if not isinstance(produced, tuple):
        raise fault("invalid_input", "scenario factory must return cases")
    selected = [
        case
        for case in produced
        if case_name == "all" or case.case_id == case_name
    ]
    if not selected:
        raise fault("invalid_input", f"unknown case {case_name}")
    guard = _SocketGuard()
    guard.install()
    rows: list[Mapping[str, object]] = []
    failures: list[str] = []
    assertions = 0
    live_calls = 0
    trace: list[str] = []
    try:
        for case in selected:
            stack = Path(tempfile.mkdtemp(prefix=f"ground-task-{number}-"))
            try:
                services = build_test_services(
                    clock_mode="manual",
                    seed=seed,
                    output_dir=stack / "out",
                )
                feature = provider_factory(services)
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
                if guard.count:
                    failures.append(case.case_id)
                    assertions += 1
            finally:
                shutil.rmtree(stack, ignore_errors=True)
    finally:
        guard.close()
    if not (root / "patrol" / "contract.py").is_file():
        failures.append("contract")
    return SimulationReport(
        task_id=manifest.task_id,
        seed=seed,
        clock_mode="manual",
        cases=tuple(rows),
        failures=tuple(dict.fromkeys(failures)),
        assertion_count=assertions,
        modes=freeze_str_map({"dog": "fake", "drone": "fake", "grok": "fake"}),
        trace=tuple(trace),
        artifact_paths=(str(report_path),),
        live_call_count=live_calls,
        skipped=0,
    )


def _jsonable(report: SimulationReport) -> dict[str, object]:
    return {
        "task_id": report.task_id,
        "seed": report.seed,
        "clock_mode": report.clock_mode,
        "cases": [_jsonable_value(case) for case in report.cases],
        "failures": list(report.failures),
        "assertion_count": report.assertion_count,
        "modes": dict(report.modes),
        "trace": list(report.trace),
        "artifact_paths": list(report.artifact_paths),
        "live_call_count": report.live_call_count,
        "skipped": report.skipped,
        "evidence": "simulated",
    }


def _jsonable_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _jsonable_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, (str, int, float)):
        return value
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
