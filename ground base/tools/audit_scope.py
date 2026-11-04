"""Build a portable evidence index; task reviews remain explicit human-readable notes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NOTES = {
    11: (
        "Strict envelopes/directions/identity; command ACKs share the issued ID; sequence "
        "replay and old-epoch cached replay rejected."
    ),
    12: (
        "Per-peer validated capabilities and real/fake separation; no invented controlled "
        "motion, Pi link, height, or radio."
    ),
    13: (
        "Observation identity, camera, pose and missing measurements; frame bytes and "
        "beacon hold delegated to their owners."
    ),
    14: (
        "Actual JPEG bytes, hash, dimensions, artifact containment and frame identity; "
        "immutable evidence cannot establish hardware freshness."
    ),
    15: (
        "One in-flight vision request, newest pending frame, expiry and "
        "clock-error-plus-age budget; capture precision preserved."
    ),
    16: (
        "Real stage entry wired; exact request/frame/track/camera/model/prompt "
        "correlation and local expiry/authority checks; no motor calls."
    ),
    17: (
        "Allowlisted bounded drone command approval; current safety rechecked before "
        "cache replay; conflicting request IDs and mutable cache results rejected."
    ),
    18: (
        "ACK lifecycle, duplicate/terminal conflict handling, unknown result queries, and "
        "no automatic second takeoff."
    ),
    19: (
        "Moving/expired beacon blocks dog permission; fresh hold and beacon epoch "
        "required; authoritative halt wins."
    ),
    20: (
        "Accept only peer-reported safe candidate IDs with frame/map/expiry/tether "
        "constraints; no SLAM implementation or invented detour."
    ),
    21: (
        "Pi RSSI window BSSID/epoch/time/pose/quality validation, null no-signal "
        "handling; no dBm-to-meters conversion."
    ),
    22: (
        "Comparable RSSI windows, bounded exploration/hysteresis/no-progress stops; "
        "actual selection result exposed to composition."
    ),
    23: (
        "Leased dog commands require current authority, stationary/standing/avoidance and "
        "cable bounds; changed motion under one selection ID rejected."
    ),
    24: (
        "ACK accepted/running/completed are separate; active/uncertain commands block "
        "another step; verified stationary and faulted replay checked."
    ),
    25: (
        "Two fresh same-track dog front-camera hits; ambiguous/wrong track goes to "
        "review; approach and goal remain separate."
    ),
    26: (
        "Separate dog range and drone horizontal offset, thresholds/freshness/sources; no "
        "goal from RSSI, obstacle clearance or one 3D distance."
    ),
    27: (
        "Goal and aircraft recovery independent; unknown landing stays latched until new "
        "verified recovery evidence; prior legitimate trace allowed."
    ),
    28: (
        "Immediate halt/link-loss/lease-expiry latch and independent stop requests; "
        "pending work and reset gates preserved."
    ),
    29: (
        "Correlation-preserving redacted v2 journal composed with the real G04 disk "
        "writer; open binding, modes, ticket and clock metadata repaired."
    ),
    30: (
        "Ethernet/Wi-Fi/Pi/internet topology validation, cable acceptance and "
        "missing-path refusal; no radio fallback or OS route mutation."
    ),
    31: (
        "Metrics from actual composed journal records with one clock domain; missing "
        "values/accuracy stay null with reasons."
    ),
    32: (
        "Owned isolated rehearsal stays independent; separate composed runner exercises "
        "real G11–31 providers and all Ground base services."
    ),
}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def build(evidence: Path, output: Path) -> None:
    simulations = read(evidence / "release-simulations/index.json")
    composed = read(evidence / "release-composed/index.json")
    quality = read(evidence / "quality.json")
    coverage = read(evidence / "coverage.json")
    suites = ET.parse(evidence / "tests.xml").getroot()
    test_rows = list(suites.iter("testcase"))
    if not all((simulations["passed"], composed["passed"], quality["passed"])):
        raise SystemExit("verification evidence contains a failed gate")
    if any(list(row) for row in test_rows):
        raise SystemExit("test evidence contains skipped/failed/error cases")
    output.mkdir(parents=True, exist_ok=True)
    lines = (ROOT / "ground task.md").read_text(encoding="utf-8").splitlines()
    cards: dict[int, dict[str, Any]] = {}
    requirements: list[dict[str, object]] = []
    task = 0
    section = ""
    for lineno, line in enumerate(lines, 1):
        match = re.match(r"## Task (\d+): (.+)", line)
        if match:
            task = int(match[1])
            if task >= 11:
                cards[task] = {"task": task, "title": match[2], "spec_line": lineno}
        if line.startswith("### "):
            section = line[4:]
        if task in range(11, 33) and line.startswith("- [ ] "):
            requirements.append(
                {
                    "task": task,
                    "spec_line": lineno,
                    "section": section,
                    "requirement": line[6:],
                    "evidence_directory": f"tests/ground/g{task:02}",
                    "review_status": "indexed_for_scope_review",
                }
            )
    if set(cards) != set(range(11, 33)):
        raise SystemExit("active task cards were not all found")
    for number, card in cards.items():
        runs = [row for row in simulations["runs"] if row["task"] == number]
        if len(runs) != 3 or not all(row["verified"] for row in runs):
            raise SystemExit(f"task {number} needs three verified simulations")
        branch = f"codex/ground-{number:02}"
        card.update(
            branch=branch,
            branch_tip=git("rev-parse", branch),
            merged=subprocess.run(
                ["git", "merge-base", "--is-ancestor", branch, "HEAD"],
                cwd=ROOT,
                capture_output=True,
            ).returncode
            == 0,
            owned_tests=sum(f".g{number:02}." in row.get("classname", "") for row in test_rows),
            test_files=sorted(
                str(p.relative_to(ROOT)).replace("\\", "/")
                for p in (ROOT / f"tests/ground/g{number:02}").glob("test_*.py")
            ),
            simulation_runs=len(runs),
            cases_per_run=runs[0]["cases"],
            assertions_all_seeds=sum(row["assertions"] for row in runs),
            scope_review="software verified; external acceptance remains separate",
            notes=NOTES[number],
        )
    if not all(card["merged"] and card["owned_tests"] for card in cards.values()):
        raise SystemExit("unmerged branch or missing task-specific tests")
    functions = []
    for path, record in coverage["files"].items():
        for name, result in record.get("functions", {}).items():
            summary = result["summary"]
            if name and summary["num_statements"] > 1:
                functions.append(
                    {
                        "file": path.replace("\\", "/"),
                        "function": name,
                        "entered_in_coverage_run": summary["covered_lines"] > 0,
                        "covered_lines": summary["covered_lines"],
                        "statements": summary["num_statements"],
                    }
                )
    totals = coverage["totals"]
    summary = {
        "evidence": "simulated",
        "python": "3.12.10",
        "os": "Windows",
        "tests_passed": len(test_rows),
        "failures": 0,
        "skipped": 0,
        "task_simulations": len(simulations["runs"]),
        "simulation_case_executions": simulations["case_executions"],
        "simulation_assertions": simulations["assertions"],
        "composed_runs": len(composed["runs"]),
        "quality_tasks": len(quality["tasks"]),
        "live_calls": 0,
        "line_coverage_percent": round(100 * totals["covered_lines"] / totals["num_statements"], 2),
        "branch_coverage_percent": round(
            100 * totals["covered_branches"] / totals["num_branches"], 2
        ),
        "nontrivial_functions": len(functions),
        "functions_entered": sum(row["entered_in_coverage_run"] for row in functions),
        "physical_acceptance": "not performed",
        "linear": "sync pending",
    }
    write(output / "summary.json", summary)
    write(output / "task-scope.json", list(cards.values()))
    write(output / "task-requirements.json", requirements)
    write(output / "function-coverage.json", functions)
    write(
        output / "simulations.json",
        {
            **simulations,
            "runs": [{**row, "report": Path(row["report"]).name} for row in simulations["runs"]],
        },
    )
    write(
        output / "composed.json",
        {
            **composed,
            "runs": [
                {**row, "report": Path(row["report"]).parent.name + "/report.json"}
                for row in composed["runs"]
            ],
        },
    )
    write(output / "quality.json", quality)
    table = [
        "| Task | Owned tests | Cases × seeds | Scope evidence |",
        "| --- | ---: | ---: | --- |",
    ]
    for number, card in cards.items():
        table.append(
            f"| {number}: {card['title']} | {card['owned_tests']} | "
            f"{card['cases_per_run']} × 3 | {card['notes']} |"
        )
    (output / "task-table.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=ROOT / "artifacts/integration")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/ground/verification")
    args = parser.parse_args()
    build(args.evidence, args.output)


if __name__ == "__main__":
    main()
