"""Start the local operator API. Bind stays on localhost."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from patrol.ground.operator.app import create_app


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m patrol.ground.operator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runs-root", type=Path, default=Path("artifacts") / "operator-runs")
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost"}:
        print("refusing non-local bind", file=sys.stderr)
        return 2
    token = os.environ.get("GROUND_OPERATOR_TOKEN", "")
    if len(token) < 16:
        print("GROUND_OPERATOR_TOKEN must be at least 16 characters", file=sys.stderr)
        return 2
    uvicorn.run(
        create_app(token, args.runs_root),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
