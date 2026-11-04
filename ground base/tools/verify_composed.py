"""Persist and independently check the composed scenario/transport/seed matrix."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from patrol.ground.demo import SCENARIOS, run_demo  # noqa: E402


async def verify(output: Path, seeds: list[int]) -> dict[str, object]:
    rows = []
    for seed in seeds:
        for transport in ("ethernet", "wifi"):
            for scenario in SCENARIOS:
                directory = output / f"{scenario}-{transport}-{seed}"
                report = await run_demo(
                    directory, scenario=scenario, seed=seed, transport=transport
                )
                commands = report["commands"]
                ids = [c["payload"]["command_id"] for c in commands]
                checks = {
                    "goal": report["goal_reached"]
                    == (scenario in {"happy_path", "unknown_landing"}),
                    "landing": report["landing_verified"] == (scenario == "happy_path"),
                    "outcome": report["outcome"]
                    == ("completed" if scenario == "happy_path" else "unresolved"),
                    "unique_commands": len(ids) == len(set(ids)),
                    "no_takeoff_retry": all(c["payload"]["action"] != "takeoff" for c in commands),
                    "simulated": report["live_call_count"] == 0
                    and report["evidence"] == "simulated",
                    "cleanup": report["cleanup_errors"] == [],
                    "durable_journal": (directory / "mission/events.jsonl").is_file(),
                    "durable_summary": (directory / "mission/summary.json").is_file(),
                }
                rows.append(
                    {
                        "scenario": scenario,
                        "seed": seed,
                        "transport": transport,
                        "verified": all(checks.values()),
                        "checks": checks,
                        "outcome": report["outcome"],
                        "goal_reached": report["goal_reached"],
                        "landing_verified": report["landing_verified"],
                        "reason": report["reason"],
                        "report": str(directory / "report.json"),
                    }
                )
    result = {"evidence": "simulated", "passed": all(r["verified"] for r in rows), "runs": rows}
    (output / "index.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/integration/composed")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 7, 29])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = asyncio.run(verify(args.output, args.seeds))
    print(json.dumps({"passed": result["passed"], "runs": len(result["runs"])}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
