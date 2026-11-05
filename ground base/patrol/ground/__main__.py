"""Ground CLI: all-fake rehearsal, with a real Grok vision connector when asked."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from patrol.ground.demo import SCENARIOS, run_demo
from patrol.ground.dog_link import EthernetDogLink
from patrol.ground.kernel.catalog import ZONES
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.radio import LinkError, ethernet_now, pi4, probe_dog_ethernet
from patrol.ground.signal import SignalError, require_api_key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m patrol.ground")
    parser.add_argument("--dog", choices=("fake", "real", "ethernet"), required=True)
    parser.add_argument("--drone", choices=("fake", "real"), required=True)
    vision = parser.add_mutually_exclusive_group(required=True)
    vision.add_argument("--grok", dest="grok", choices=("fake", "real"))
    vision.add_argument("--vision", dest="grok", choices=("fake", "real"))
    parser.add_argument("--pi", choices=("fake", "real"), default="fake")
    parser.add_argument(
        "--scenario", choices=(*SCENARIOS, "blocked_resolved", "drone_first"), default="happy_path"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--dog-transport", choices=("ethernet", "wifi"), default="ethernet")
    parser.add_argument("--link", choices=("ethernet", "pi4"), default="ethernet")
    parser.add_argument("--arm", action="store_true")
    parser.add_argument(
        "--dog-sim",
        action="store_true",
        help="drive the simulated dog body instead of Ethernet",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--config")
    parser.add_argument("--image")
    parser.add_argument("--zone", choices=tuple(sorted(ZONES)))
    parser.add_argument("--target")
    parser.add_argument("--captured-at")
    args = parser.parse_args(argv)
    if "real" in (args.dog, args.drone, args.pi):
        print(
            "live operation refused: v2 teammate transport/factory bridges and physical "
            "acceptance have not been supplied; the v1 run_route/inspect API cannot "
            "execute v2 commands",
            file=sys.stderr,
        )
        return 2
    if args.grok == "real":
        try:
            require_api_key()
        except SignalError as exc:
            print(f"grok signal connector refused: {exc}", file=sys.stderr)
            return 2
    if args.link == "pi4":
        print(json.dumps(pi4(), indent=2))
        print(
            "pi4 plan: the laptop Wi-Fi joins only the ground AP. The Pi 4 Ethernet "
            "holds the dog and the Pi's USB radio is the only Tello client. That relay "
            "is not mounted, so this command does not associate a second Wi-Fi network.",
            file=sys.stderr,
        )
        return 2
    if args.dog == "ethernet":
        if args.drone != "fake" or args.grok != "fake" or args.pi != "fake":
            print("ethernet dog motion keeps the drone, vision, and Pi simulated", file=sys.stderr)
            return 2
        if not args.arm:
            print(
                "ethernet motion needs --arm, with staff holding the controller and the "
                "phone app closed. No WebRTC session was opened.",
                file=sys.stderr,
            )
            return 2
        if not args.dog_sim:
            route = probe_dog_ethernet()
            if not route["reachable"]:
                print(
                    f"dog Ethernet is not reachable at {route['dog']}:{route['port']} "
                    f"({route['detail']}). Set this machine's adapter to "
                    "192.168.123.222/24. No motion was sent.",
                    file=sys.stderr,
                )
                return 2
            if route["laptop_on_dog_subnet"] is not True:
                print(
                    f"dog answered on {route['local_address']}, which is not 192.168.123.222/24. "
                    "Refusing to open WebRTC from the wrong network.",
                    file=sys.stderr,
                )
                return 2
    if any((args.config, args.image, args.zone, args.target, args.captured_at)):
        print(
            "input refused: this offline v2 rehearsal uses bundled synthetic peer evidence; "
            "custom/live incident input requires the teammate bridges",
            file=sys.stderr,
        )
        return 2
    output = args.output_dir or Path("artifacts") / f"demo-{uuid4().hex[:12]}"
    scenario = (
        "happy_path" if args.scenario in {"blocked_resolved", "drone_first"} else args.scenario
    )
    link = None
    radio = None
    transport = args.dog_transport
    if args.dog == "ethernet":
        link = EthernetDogLink(output / "dog", armed=True, fake=args.dog_sim)
        radio = ethernet_now()
        transport = "ethernet"
    try:
        report = asyncio.run(
            run_demo(
                output,
                scenario=scenario,
                seed=args.seed,
                transport=transport,
                dog_link=link,
                radio=radio,
                grok=args.grok,
            )
        )
    except SignalError as exc:
        print(f"grok signal connector refused: {exc}", file=sys.stderr)
        return 2
    except (GroundFault, LinkError, OSError) as exc:
        print(f"rehearsal failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "evidence": (
                    "dog-ethernet" if report.get("dog_ethernet", {}).get("sent") else "simulated"
                ),
                "outcome": report["outcome"],
                "dog_sent": (report.get("dog_ethernet") or {}).get("sent"),
                "goal_reached": report["goal_reached"],
                "landing_verified": report["landing_verified"],
                "reason": report["reason"],
                "report": str(output.resolve() / "report.json"),
            },
            indent=2,
        )
    )
    return 0 if report["outcome"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
