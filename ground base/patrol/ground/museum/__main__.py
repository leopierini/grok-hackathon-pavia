"""Museum patrol through Ground.

    python -m patrol.ground.museum --dog fake --drone fake --grok fake --scenario all
    python -m patrol.ground.museum --preflight

``--grok real`` reads ``XAI_API_KEY`` and does not take a scenario named ``all``.
``--dog real`` and ``--drone real`` read ``PATROL_*_HOST`` and ``PATROL_*_PORT``.
A missing value exits 2 and opens no socket. Motion also requires
``--i-understand-this-moves-hardware``. ``--preflight`` does not move hardware.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from patrol.ground.museum.endpoint import (
    motion_required_message,
    redact,
    require_endpoint,
    secret_values,
)
from patrol.ground.museum.peers import ConfigError
from patrol.ground.museum.preflight import run_preflight
from patrol.ground.museum.runner import SCENARIOS, run_story, write_report
from patrol.ground.signal import SignalError, require_api_key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m patrol.ground.museum")
    parser.add_argument("--dog", choices=("fake", "real"), default="fake")
    parser.add_argument("--drone", choices=("fake", "real"), default="fake")
    parser.add_argument("--grok", choices=("fake", "real"), default="fake")
    parser.add_argument("--scenario", default="all")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--i-understand-this-moves-hardware", action="store_true")
    args = parser.parse_args(argv)
    file_config = _read_config(args.config)
    if isinstance(file_config, str):
        print(file_config, file=sys.stderr)
        return 2
    secrets = secret_values(os.environ, file_config)
    if args.preflight:
        code, table = run_preflight(
            args.output_dir or Path("artifacts") / "museum" / "preflight",
            dog=args.dog,
            drone=args.drone,
            grok=args.grok,
            environ=os.environ,
            file_config=file_config,
        )
        print(table)
        return code
    if args.scenario != "all" and args.scenario not in SCENARIOS:
        print(f"unknown scenario {args.scenario!r}", file=sys.stderr)
        return 2
    if args.grok == "real" and args.scenario == "all":
        print(
            "real Grok runs one named scenario, not --scenario all. "
            "CI uses --grok fake.",
            file=sys.stderr,
        )
        return 2
    if args.dog == "real" or args.drone == "real":
        try:
            if args.dog == "real":
                require_endpoint("dog", os.environ, file_config)
            if args.drone == "real":
                require_endpoint("drone", os.environ, file_config)
        except ConfigError as exc:
            print(redact(str(exc), secrets), file=sys.stderr)
            return 2
        if not args.i_understand_this_moves_hardware:
            print(motion_required_message(), file=sys.stderr)
            return 2
    if args.grok == "real":
        try:
            require_api_key()
        except SignalError as exc:
            print(f"grok signal connector refused: {exc}", file=sys.stderr)
            return 2
    scenarios = SCENARIOS if args.scenario == "all" else (args.scenario,)
    output_root = args.output_dir or Path("artifacts") / "museum"
    failed = False
    try:
        for scenario in scenarios:
            report = run_story(
                output_root / scenario,
                scenario=scenario,
                dog=args.dog,
                drone=args.drone,
                grok=args.grok,
                environ=os.environ,
                file_config=file_config,
                motion_authorized=args.i_understand_this_moves_hardware,
            )
            write_report(report, output_root / scenario)
            print(
                json.dumps(
                    {
                        "scenario": report.scenario,
                        "ok": report.ok,
                        "detail": report.detail,
                        "delivered": [item.get("action") for item in report.delivered],
                        "spoken": report.spoken,
                        "grok_calls": report.grok_calls,
                        "halted": report.halted,
                        "gaps": report.gaps,
                        "report": str((output_root / scenario / "report.json").resolve()),
                    },
                    indent=2,
                )
            )
            failed = failed or not report.ok
    except ConfigError as exc:
        print(redact(str(exc), secrets), file=sys.stderr)
        return 2
    except SignalError as exc:
        print(redact(f"grok signal connector refused: {exc}", secrets), file=sys.stderr)
        return 2
    except Exception as exc:
        if getattr(exc, "code", None):
            print(redact(str(exc), secrets), file=sys.stderr)
            return 2
        raise
    return 1 if failed else 0


def _read_config(path: Path | None) -> dict[str, object] | None | str:
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"cannot read config: {exc}"
    if "api_key" in text.lower() or "xai_api_key" in text.lower():
        return "config refused: an API key must not be in the config file"
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError:
        return "config refused: file is not JSON"
    if not isinstance(parsed, dict):
        return "config refused: file must be an object"
    return {str(key): value for key, value in parsed.items()}


if __name__ == "__main__":
    raise SystemExit(main())
