"""Fake-drone selftest. No Tello and no network.

    python -m patrol.drone.selftest --mode fake
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import time
from pathlib import Path
from threading import Event

from patrol.contract import AdapterError, InspectionRequest, RunContext
from patrol.drone import create_drone


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drone adapter selftest.")
    parser.add_argument("--mode", default="fake", choices=["fake"])
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args.mode))
    except (AssertionError, AdapterError) as exc:
        print(f"selftest failed: {exc}")
        return 1
    print("fake drone selftest ok")
    return 0


async def _run(mode: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        await _happy(mode, Path(tmp))
        await _unavailable(mode, Path(tmp) / "unavailable")
        await _takeoff_timeout(mode, Path(tmp) / "timeout")
        await _landing_unknown(mode, Path(tmp) / "landing")


async def _happy(mode: str, output: Path) -> None:
    drone = create_drone(mode=mode, config={}, output_dir=output)
    status = await drone.connect()
    assert status.connected and status.flight_state == "grounded"
    assert status.battery_percent == 90
    result = await drone.inspect(_request(), _ctx("happy"))
    assert result.outcome == "captured"
    assert result.flight_state == "grounded"
    assert result.frame is not None and result.frame.simulated
    assert Path(result.frame.path).is_file()
    await drone.land()
    await drone.land()
    await drone.close()
    await drone.close()
    assert drone.trace.count("takeoff_attempt") == 1
    assert "abort_attempt" not in drone.trace


async def _unavailable(mode: str, output: Path) -> None:
    drone = create_drone(
        mode=mode, config={"scenario": "drone_unavailable"}, output_dir=output
    )
    await drone.connect()
    result = await drone.inspect(_request(), _ctx("unavailable"))
    assert result.outcome == "unavailable"
    assert result.frame is None
    assert result.flight_state == "grounded"
    assert "takeoff_attempt" not in drone.trace
    await drone.close()


async def _takeoff_timeout(mode: str, output: Path) -> None:
    drone = create_drone(
        mode=mode, config={"scenario": "takeoff_timeout"}, output_dir=output
    )
    await drone.connect()
    result = await drone.inspect(_request(), _ctx("timeout"))
    assert result.outcome == "failed"
    assert result.frame is None
    assert result.flight_state == "unknown"
    assert drone.trace.count("takeoff_attempt") == 1
    assert drone.trace.count("abort_attempt") == 1
    try:
        await drone.inspect(_request(), _ctx("timeout-again"))
    except AdapterError as exc:
        assert exc.code == "unsafe_state"
    else:
        raise AssertionError("a timed-out takeoff must not be retried")
    assert drone.trace.count("takeoff_attempt") == 1
    try:
        await drone.land()
    except AdapterError as exc:
        assert exc.code == "unsafe_state"
    else:
        raise AssertionError("unknown landing must not look grounded")
    await drone.close()


async def _landing_unknown(mode: str, output: Path) -> None:
    drone = create_drone(
        mode=mode, config={"scenario": "landing_unknown"}, output_dir=output
    )
    await drone.connect()
    result = await drone.inspect(_request(), _ctx("landing"))
    assert result.outcome == "failed"
    assert result.flight_state == "unknown"
    assert result.frame is not None and Path(result.frame.path).is_file()
    await drone.close()


def _request() -> InspectionRequest:
    return InspectionRequest("room_2", "room_2_view_v1", "floor")


def _ctx(mission_id: str) -> RunContext:
    return RunContext(mission_id, time.monotonic() + 30, Event())


if __name__ == "__main__":
    sys.exit(main())
