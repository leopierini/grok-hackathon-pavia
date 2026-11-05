"""Live ground station for the museum demo.

    python -m patrol.ground.live --drone http://127.0.0.1:8766 --dog ethernet --grok real [--arm-dog]

Simulation, no hardware and no key:

    (repo root)  .venv/bin/python -m patrol.drone.manual --fake --port 8799
    (ground base) .venv/bin/python -m patrol.ground.live --drone http://127.0.0.1:8799 --dog sim --grok fake

Then open http://127.0.0.1:8770. Halt is the red button or the Q key.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from patrol.ground.dog_limits import clamp_limits
from patrol.ground.dog_link import EthernetDogLink
from patrol.ground.live.drone import DroneHttp
from patrol.ground.live.grok import RealGrok, ScriptedGrok
from patrol.ground.live.mission import LiveMission, Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m patrol.ground.live")
    parser.add_argument("--drone", default="http://127.0.0.1:8766", help="drone flight server URL")
    parser.add_argument("--dog", choices=("ethernet", "sim", "none"), default="ethernet")
    parser.add_argument("--dog-ip", default="192.168.123.161")
    parser.add_argument("--arm-dog", action="store_true", help="allow stand and operator steps (halt always works)")
    parser.add_argument("--grok", choices=("real", "fake"), default="fake")
    parser.add_argument("--target", default="a person in the closed demo area")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--no-track", action="store_true", help="drone does not yaw to follow the person")
    parser.add_argument("--allow-takeoff", action="store_true", help="Start patrol may send takeoff")
    parser.add_argument("--confirm-frames", type=int, default=2)
    parser.add_argument("--vision-period", type=float, default=1.2)
    args = parser.parse_args(argv)

    try:
        grok = RealGrok(args.target) if args.grok == "real" else ScriptedGrok()
    except Exception as exc:  # noqa: BLE001
        print(f"grok refused: {exc}", file=sys.stderr)
        return 2

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path("artifacts") / "live" / f"live-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    dog = None
    if args.dog != "none":
        # Operator steps only. clamp_limits keeps every axis under the dog-folder recommendation.
        limits = clamp_limits({"forward_m_s": 0.2, "side_m_s": 0.1, "yaw_rad_s": 0.4, "step_s": 1.0})
        dog = EthernetDogLink(run_dir / "dog", armed=args.arm_dog, fake=args.dog == "sim", ip=args.dog_ip,
                              limits=limits)
    settings = Settings(
        track=not args.no_track,
        allow_takeoff=args.allow_takeoff,
        confirm_frames=max(1, args.confirm_frames),
        drone_vision_period_s=max(0.5, args.vision_period),
    )
    mission = LiveMission(drone=DroneHttp(args.drone), dog=dog, grok=grok, run_dir=run_dir,
                          settings=settings, dog_mode=args.dog)

    import uvicorn

    from patrol.ground.live.server import create_app

    print(f"live console: http://127.0.0.1:{args.port}   journal: {run_dir}/events.jsonl")
    print(f"grok={grok.name} dog={args.dog} armed={args.arm_dog} drone={args.drone} track={settings.track}")
    uvicorn.run(create_app(mission, args.port), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
