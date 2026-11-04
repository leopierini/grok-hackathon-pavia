"""Explicit private-stub rehearsal entry point from the v2 Ground guide."""

from __future__ import annotations

import argparse
from pathlib import Path

from patrol.ground.__main__ import main as run_ground


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m patrol.ground.selftest")
    parser.add_argument("--stubs", action="store_true", required=True)
    parser.add_argument("--scenario", choices=("drone_first",), default="drone_first")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    flags = [
        "--dog",
        "fake",
        "--drone",
        "fake",
        "--pi",
        "fake",
        "--vision",
        "fake",
        "--scenario",
        args.scenario,
    ]
    if args.output_dir is not None:
        flags.extend(("--output-dir", str(args.output_dir)))
    return run_ground(flags)


if __name__ == "__main__":
    raise SystemExit(main())
