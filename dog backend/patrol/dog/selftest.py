"""Dog adapter self-test.

    python -m patrol.dog.selftest --mode fake [--scenario NAME] [--out DIR]
    python -m patrol.dog.selftest --mode real --config PATH --arm   (delegates)
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
import threading
import time
from pathlib import Path

from patrol.contract import AdapterError, RunContext

from . import create_dog
from .fake import DEFAULT_SCENARIO

ZONE = "room_2"


def _parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m patrol.dog.selftest")
    p.add_argument("--mode", choices=["fake", "real"], default="fake")
    p.add_argument("--scenario", default=DEFAULT_SCENARIO, help="fake scenario name")
    p.add_argument("--out", type=Path, default=Path("artifacts/dog-selftest"))
    p.add_argument("--config", type=Path, help="real mode: dog config JSON")
    p.add_argument("--arm", action="store_true", help="real mode: allow motion")
    return p.parse_args(argv)


async def _run_fake(scenario: str, out: Path) -> bool:
    ok = True

    def step(name: str, value: object, passed: bool = True) -> None:
        nonlocal ok
        ok = ok and passed
        print(f"[{'ok' if passed else 'FAIL'}] {name}: {value}")

    dog = create_dog(mode="fake", config={"scenario": scenario}, output_dir=out)
    ctx = RunContext(mission_id=f"selftest-{int(time.time())}",
                     deadline_monotonic=time.monotonic() + 30.0, cancel=threading.Event())
    try:
        status = await dog.connect()
        step("connect", status, status.connected and not status.standing)
        step("get_status", await dog.get_status())
        status = await dog.prepare(ctx)
        step("prepare", status, bool(status.standing and status.avoidance_enabled))
        route = await dog.run_route(ZONE, ctx)
        expect_complete = scenario != "route_blocked"
        step("run_route", route, route.stopped and route.completed == expect_complete)
        frame = await dog.capture_frame(ZONE, ctx)
        path = Path(frame.path)
        good = path.is_absolute() and path.read_bytes()[:2] == b"\xff\xd8" and frame.simulated
        step("capture_frame", frame, good)
        await dog.halt()
        step("halt", "ok")
        try:
            await dog.run_route(ZONE, ctx)
            step("route after halt", "accepted (should be refused)", False)
        except AdapterError as exc:
            step("route after halt", f"refused ({exc.code})", exc.code == "unsafe_state")
    finally:
        await dog.close()
        step("close", "ok")
    return ok


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    if args.mode == "real":
        name = f"{__package__}.real_selftest"
        try:
            real_selftest = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            print("real selftest not implemented yet")
            return 2
        if not hasattr(real_selftest, "main"):
            print("real selftest not implemented yet")
            return 2
        return int(real_selftest.main(args) or 0)

    print(f"dog selftest: mode=fake scenario={args.scenario} out={args.out.resolve()}")
    try:
        ok = asyncio.run(_run_fake(args.scenario, args.out))
    except AdapterError as exc:
        print(f"[FAIL] {exc}")
        ok = False
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
