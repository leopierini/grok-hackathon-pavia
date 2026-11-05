"""Run every task simulation and retain actual outputs, including failed reports."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_one(job: tuple[int, int], output: Path) -> dict[str, object]:
    task, seed = job
    destination = output / f"task-{task:02}-seed-{seed}.json"
    command = [
        sys.executable,
        "-m",
        "patrol.ground.sim",
        "--task",
        f"{task:02}",
        "--case",
        "all",
        "--seed",
        str(seed),
        "--report",
        str(destination),
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        returncode = result.returncode
        log = result.stdout + result.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        log = str(exc)
    destination.with_suffix(".log").write_text(log, encoding="utf-8")
    report = json.loads(destination.read_text()) if destination.exists() else {}
    verified = (
        returncode == 0
        and report.get("failures") == []
        and report.get("skipped") == 0
        and report.get("live_call_count") == 0
        and report.get("evidence") == "simulated"
        and bool(report.get("cases"))
        and all(row.get("passed") is True for row in report.get("cases", []))
    )
    return {
        "task": task,
        "seed": seed,
        "returncode": returncode,
        "verified": verified,
        "cases": len(report.get("cases", [])),
        "assertions": report.get("assertion_count", 0),
        "duration_s": round(time.monotonic() - started, 3),
        "report": str(destination),
        "failures": report.get("failures", [log[-1000:]]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/integration/simulations")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 7, 29])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = [(task, seed) for task in range(1, 33) for seed in args.seeds]
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda job: run_one(job, args.output), jobs))
    report = {
        "evidence": "simulated",
        "runs": rows,
        "passed": all(row["verified"] for row in rows),
        "case_executions": sum(int(row["cases"]) for row in rows),
        "assertions": sum(int(row["assertions"]) for row in rows),
    }
    (args.output / "index.json").write_text(json.dumps(report, indent=2) + "\n")
    failed = [row for row in rows if not row["verified"]]
    print(json.dumps({**report, "runs": failed}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
