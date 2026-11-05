"""Offline check of the flight rules on labelled photos. No radio, no motors.

Each labelled photo goes through the reflex and through Jev (local or remote),
then through the navigator as if it were the newest frame in flight. A
photo labelled blocked that would still be flown into is a failure; the
run exits 1 if there is any. Clear photos that make the drone stop are
reported too, because a drone that never moves is not a patrol.

    .venv/bin/python -m patrol.drone.bench                 # local models
    .venv/bin/python -m patrol.drone.bench --brain jev     # OpenRouter
    .venv/bin/python -m patrol.drone.bench --no-jev        # reflex only
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from patrol.drone.navigator import Limits, Navigator, Seen, View, choose_heading

ROOT = Path(__file__).resolve().parents[2]
LABELS = Path(__file__).with_name("bench_labels.json")
RECON = ROOT / "artifacts" / "drone" / "recon"


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def main(argv: list[str] | None = None) -> int:
    from PIL import Image

    from patrol.drone import jev
    from patrol.drone.reflex import Reflex

    parser = argparse.ArgumentParser(description="Replay labelled photos through the flight rules.")
    parser.add_argument("--brain", default="local", choices=("local", "jev", "reflex-only"))
    parser.add_argument("--vlm", default=None, help="local judge model, e.g. qwen3-vl-2b or smolvlm-500m")
    parser.add_argument("--no-jev", action="store_true", help="same as --brain reflex-only")
    parser.add_argument("--brake", type=float, default=Limits.brake_m, help="brake distance in meters")
    args = parser.parse_args(argv)

    labels = json.loads(LABELS.read_text())["photos"]
    brain = "reflex-only" if args.no_jev else args.brain
    client = None
    if brain == "jev":
        key = jev.api_key()
        if key:
            client = jev.JevClient(key)
        else:
            print("no OPENROUTER_API_KEY; running reflex only")
            brain = "reflex-only"
    elif brain == "local":
        from patrol.drone.local import DEFAULT_VLM, LocalBrain

        client = LocalBrain(args.vlm or DEFAULT_VLM)
        client.guide(jev.encode_frame(Image.open(RECON / labels[0]["run"] / labels[0]["file"])))
    limits = Limits(brake_m=args.brake)
    reflex = Reflex()
    reflex_ms: list[float] = []
    jev_ms: list[float] = []
    unsafe = 0
    stuck = 0
    laps: dict[tuple[str, int], dict[int, tuple[View, dict]]] = {}
    print(f"brain {brain}, brake {limits.brake_m:.1f} m, reflex on {reflex.device}")
    print(f"{'photo':38} {'label':>9} {'reflex':>7} {'jev':>16}  decision")
    for label in labels:
        path = RECON / label["run"] / label["file"]
        if not path.is_file():
            print(f"{label['run']}/{label['file']}: missing, skipped")
            continue
        image = Image.open(path)
        reflex.measure(image)
        now = time.monotonic()
        reading = reflex.measure(image, at=now)
        reflex_ms.append(reading.seconds * 1000)
        seen = None
        jev_text = "-"
        if client is not None:
            try:
                guide = client.guide(jev.encode_frame(image), label.get("height_cm"))
                jev_ms.append(guide.latency_s * 1000)
                seen = Seen(guide.blocked, guide.steer, guide.steer_confidence, guide.person, now)
                jev_text = f"blk {guide.blocked:.2f} {guide.steer[:1]} p{guide.person:.1f}"
            except jev.JevError as exc:
                jev_text = "error"
                print(f"  jev failed: {exc}")
        nav = Navigator(limits, brain, started_at=now)
        if seen is not None:
            nav.note(seen)
        command = nav.step(now + 0.05, reading, seen)
        moving = command.mode == "cruise" and command.fb_mps > 0
        verdict = ""
        if label["blocked"] and moving:
            unsafe += 1
            verdict = "  UNSAFE"
        elif not label["blocked"] and not moving:
            stuck += 1
            verdict = "  stops on a clear view"
        decision = f"{command.mode} {command.fb_mps:.2f} m/s ({command.reason})"
        name = f"{label['run'][11:17]}/{label['file']}"
        truth = ("blk " if label["blocked"] else "") + f"{label['meters']:.1f}m"
        print(f"{name:38} {truth:>9} {reading.center_m:6.2f}m {jev_text:>16}  {decision}{verdict}")
        step = int(label["file"][4])
        heading = int(label["file"].split("-h")[1][:3])
        view = View(
            reading.center_m,
            None if seen is None else seen.blocked,
            None,
            None if seen is None else seen.person,
        )
        laps.setdefault((label["run"], step), {})[heading] = (view, label)
    if client is not None:
        client.close()

    print()
    print("scan picks per lap (labelled photos only)")
    from patrol.drone.navigator import Pose

    for (run, step), entries in sorted(laps.items()):
        if len(entries) < 2:
            continue
        views = {heading: view for heading, (view, _label) in entries.items()}
        chosen, why = choose_heading(views, None, Pose(), limits)
        if chosen is None:
            print(f"  {run[11:17]} lap {step + 1}: stay")
            continue
        picked = entries[chosen][1]
        bad = "  UNSAFE" if picked["blocked"] else ""
        if picked["blocked"]:
            unsafe += 1
        refused = ", ".join(f"{h}° {r}" for h, r in sorted(why.items()) if r)
        print(f"  {run[11:17]} lap {step + 1}: {chosen}°{bad}" + (f"  (refused {refused})" if refused else ""))

    print()
    if reflex_ms:
        print(f"reflex {statistics.mean(reflex_ms):.0f} ms mean, {_p95(reflex_ms):.0f} ms p95")
    if jev_ms:
        print(f"jev guide {statistics.mean(jev_ms):.0f} ms mean, {_p95(jev_ms):.0f} ms p95")
    print(f"unsafe {unsafe}, stops on a clear view {stuck}")
    return 1 if unsafe else 0


if __name__ == "__main__":
    sys.exit(main())
