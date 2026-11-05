"""Shared flight helpers, the old floor-fit scoring for replays, and a CLI for the explorer.

`--arm` flies the continuous explorer (see `patrol.drone.explore`): reflex
depth brakes, Jev steers, rc at 10 Hz. `--replay` and `--image` re-score
saved photos with the old relative-depth floor fit. That score no longer
moves the drone: a fit can lock onto a cabinet front and read 6 m.

    .venv/bin/python -m patrol.drone.recon --arm --seconds 60 --height 100
    .venv/bin/python -m patrol.drone.recon --replay artifacts/drone/recon/<run> --height 130

Join TELLO-62A593 before --arm. Stand clear of the circle. Ctrl-C lands.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

STICK = 25
HEADINGS = 8
STEP_DEG = 45
OPEN_ENOUGH = 1.05
STRAIGHT_WEIGHT = 0.85
BACK_WEIGHT = 0.35
NEAR_BACK_WEIGHT = 0.7
CLEARANCE_M = 0.3
SHORTEST_HOP_S = 0.3
# The fallback when the stick loop in `pad_land` cannot run. `go` to 20 cm
# answers "Run timeout" on the real drone, and repeated `go` at one height
# stops at the same offset, so the steps end at 30 cm.
PAD_CENTER_CM = 4
PAD_LOW_CM = 30
PAD_HIGH_CM = 70
PAD_APPROACH = ((PAD_HIGH_CM, 20, 1), (40, 10, 3), (PAD_LOW_CM, 10, 3))


def sweep_plan(angles: int) -> tuple[int, int]:
    """How many stops, and the yaw between them.

    Four is a full turn in 90° steps. Twelve is the finest step that still
    finishes a circle before the battery cares. The step is 360° divided by
    the count, rounded to a whole degree the Tello can yaw.
    """
    if not 4 <= int(angles) <= 12:
        raise ValueError(angles)
    count = int(angles)
    return count, max(1, round(360 / count))


def heading_weight(heading: int, back_heading: int | None) -> float:
    """How much a heading is worth before looking at the photo.

    The way the drone came is always open, because it just flew through it,
    so it is heavily discounted; headings within 90° of it a little less.
    Straight ahead is discounted too, so the path bends instead of running
    one corridor every lap.
    """
    weight = 1.0
    if heading % 360 == 0:
        weight *= STRAIGHT_WEIGHT
    if back_heading is not None:
        diff = abs((heading - back_heading + 180) % 360 - 180)
        if diff == 0:
            weight *= BACK_WEIGHT
        elif diff < 90:
            weight *= NEAR_BACK_WEIGHT
    return weight


def rank_score(heading: int, value: float, back_heading: int | None = None) -> float:
    """Score used to pick a direction: free meters (or openness) times the heading weight."""
    return value * heading_weight(heading, back_heading)


def will_move(openness: float) -> bool:
    """The center of this frame is farther than its sides."""
    return openness >= OPEN_ENOUGH


def hop_seconds(free_m: float, margin_m: float, speed_mps: float, hop_cap: float) -> float | None:
    """Fly until `margin_m` short of the nearest thing ahead, capped at `hop_cap`.

    None when there is not even the margin plus a little room, or the hop
    would be too short to get past the position hold.
    """
    if free_m <= margin_m + CLEARANCE_M or speed_mps <= 0:
        return None
    seconds = min(hop_cap, (free_m - margin_m) / speed_mps)
    if seconds < SHORTEST_HOP_S:
        return None
    return seconds


def assess(
    closer,
    camera_cm: int | None,
    margin_m: float,
    speed_mps: float,
    hop_cap: float,
    tilt_deg: float | None = None,
) -> dict:
    """Read one depth map: meters ahead if the floor fits. Without a fit there is no hop.

    The openness ratio alone once allowed a hop; it read 9.36 over a car roof.
    """
    from patrol.drone.depth_look import (
        CAMERA_TILT_DEG,
        LENS_ABOVE_TOF_M,
        floor_fit,
        free_distance_m,
        openness,
    )

    ratio = openness(closer)
    tilt = CAMERA_TILT_DEG if tilt_deg is None else tilt_deg
    fit = floor_fit(closer, camera_cm / 100 + LENS_ABOVE_TOF_M, tilt) if camera_cm else None
    if fit is None:
        return {
            "metric": False,
            "free_m": None,
            "openness": ratio,
            "residual": None,
            "hop": None,
            "value": ratio,
        }
    free = free_distance_m(closer, fit)
    reach = margin_m + hop_cap * speed_mps
    return {
        "metric": True,
        "free_m": free,
        "openness": ratio,
        "residual": fit.residual,
        "hop": hop_seconds(free, margin_m, speed_mps, hop_cap),
        "value": min(free, reach),
    }


def describe(heading: int, view: dict, back_heading: int | None) -> str:
    hop = "stay" if view["hop"] is None else f"hop {view['hop']:.2f}s"
    if view["metric"]:
        seen = f"{view['free_m']:.2f} m free"
    else:
        seen = f"floor fit failed, openness {view['openness']:.2f}"
    weight = heading_weight(heading, back_heading)
    note = "" if weight == 1.0 else f"  x{weight:.2f}"
    if back_heading is not None and heading == back_heading:
        note += " way back"
    return f"  {heading:3d}°  {seen}  {hop}{note}"


def pick(views: dict[int, dict], back_heading: int | None) -> int | None:
    """Best heading that may hop. Measured views outrank ratio-only views."""
    movable = {heading: view for heading, view in views.items() if view["hop"] is not None}
    measured = {heading: view for heading, view in movable.items() if view["metric"]}
    pool = measured or movable
    if not pool:
        return None
    return max(pool, key=lambda heading: rank_score(heading, pool[heading]["value"], back_heading))


def yaw_command(current_deg: int, target_deg: int) -> str | None:
    delta = (target_deg - current_deg) % 360
    if delta == 0:
        return None
    if delta <= 180:
        return f"cw {delta}"
    return f"ccw {360 - delta}"


def parse_height_cm(reply: str) -> int | None:
    """`height?` answers in decimeters, for example `7dm`."""
    text = reply.strip().lower()
    if text.endswith("dm"):
        number = text[:-2]
        scale = 10
    elif text.endswith("cm"):
        number = text[:-2]
        scale = 1
    else:
        number = text
        scale = 1
    try:
        return int(float(number) * scale)
    except ValueError:
        return None


def height_commands(current_cm: int | None, target_cm: int) -> list[str]:
    """`up` / `down` steps that reach `target_cm`. Empty when already close.

    The SDK ignores a step under 20 cm. Each command is at most 100 cm.
    """
    if current_cm is None:
        return []
    delta = target_cm - current_cm
    commands: list[str] = []
    while abs(delta) >= 20:
        step = max(-100, min(100, delta))
        if abs(step) < 20:
            break
        if step > 0:
            commands.append(f"up {step}")
        else:
            commands.append(f"down {-step}")
        delta -= step
    return commands


def pad_centered(x: int | None, y: int | None, tolerance: int = PAD_CENTER_CM) -> bool:
    """True when the drone is within `tolerance` cm of the pad center."""
    if x is None or y is None:
        return False
    return abs(int(x)) <= tolerance and abs(int(y)) <= tolerance


def pad_go_command(
    mid: int | None,
    wanted: int | None,
    z_cm: int = PAD_LOW_CM,
    speed: int = 10,
) -> str | None:
    """Hover at `z_cm` over a mission pad, or None when none is in sight.

    `wanted` is a pad number 1-8, or None to accept whichever pad is seen.
    `mid` of -1, 0, or anything outside 1-8 means the downward camera
    does not see a pad. z must be at least 20 cm and speed 10 to 100.
    """
    if mid is None or not 1 <= int(mid) <= 8:
        return None
    if wanted is not None and int(mid) != int(wanted):
        return None
    z_cm, speed = int(z_cm), int(speed)
    if not 20 <= z_cm <= 500 or not 10 <= speed <= 100:
        return None
    return f"go 0 0 {z_cm} {speed} m{int(mid)}"


def parse_pad_id(value: str) -> int | None:
    """`any` accepts every pad. `m1` through `m8` accept one pad."""
    text = value.strip().lower()
    if text == "any":
        return None
    if len(text) == 2 and text[0] == "m" and text[1] in "12345678":
        return int(text[1])
    raise ValueError(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recon explorer, and replays of saved photos.")
    parser.add_argument("--arm", action="store_true", help="actually take off")
    parser.add_argument("--seconds", type=int, default=60, help="explore this long, 10 to 300 s")
    parser.add_argument("--cruise", type=float, default=0.2, help="top forward speed, 0.1 to 0.8 m/s")
    parser.add_argument("--brake", type=float, default=1.0, help="brake and scan this close, 0.6 to 2.5 m")
    parser.add_argument("--geofence", type=float, default=4.0, help="stay within this many meters of takeoff")
    parser.add_argument("--brain", default="local", help="local, jev (OpenRouter), or reflex-only")
    parser.add_argument("--hop", type=float, default=1.2, help="replay only: longest forward stick, 0.3 to 8 s")
    parser.add_argument("--margin", type=int, default=50, help="stop this far from the obstacle, 20 to 200 cm")
    parser.add_argument("--speed", type=float, default=0.4, help="forward speed at stick 25, 0.1 to 1.5 m/s")
    parser.add_argument("--replay", type=Path, help="re-score the photos of a saved run and do not fly")
    parser.add_argument("--tilt", type=float, help="camera tilt down in degrees, for --replay and --image")
    parser.add_argument("--distance", type=float, help="with --image: measured meters to the thing ahead; prints the tilt")
    parser.add_argument("--height", type=int, default=100, help="cruise height, 40 to 300 cm")
    parser.add_argument("--pad", action="store_true", help="land on a mission pad when one is in sight")
    parser.add_argument("--pad-id", default="any", help="any, or m1 through m8")
    parser.add_argument("--image", type=Path, help="score one saved photo and do not fly")
    parser.add_argument("--output", type=Path, default=Path("artifacts/drone/recon"))
    args = parser.parse_args(argv)
    if not 0.3 <= args.hop <= 8:
        print("--hop must be between 0.3 and 8 seconds")
        return 2
    if not 20 <= args.margin <= 200:
        print("--margin must be between 20 and 200 cm")
        return 2
    if not 0.1 <= args.speed <= 1.5:
        print("--speed must be between 0.1 and 1.5 m/s")
        return 2
    if not 40 <= args.height <= 300:
        print("--height must be between 40 and 300 cm")
        return 2
    try:
        parse_pad_id(args.pad_id)
    except ValueError:
        print("--pad-id must be any or m1 through m8")
        return 2
    if args.image:
        return _score_file(args.image, args)
    if args.replay:
        return _replay(args.replay, args)
    pad = f", pad {args.pad_id}" if args.pad else ""
    print(
        f"explore: takeoff to {args.height} cm, {args.seconds}s at up to {args.cruise} m/s, "
        f"brake at {args.brake} m, brain {args.brain}, then hover{pad}"
    )
    if not args.arm:
        print("not armed; no motors")
        return 0
    from patrol.drone.pilot import Pilot

    pilot = Pilot(args.output)
    error = pilot.update_settings(
        {
            "speed_mps": args.speed,
            "height_cm": args.height,
            "explore_s": args.seconds,
            "cruise_mps": args.cruise,
            "brake_m": args.brake,
            "geofence_m": args.geofence,
            "brain": args.brain,
            "pad": args.pad,
            "pad_id": args.pad_id,
        }
    )
    if error:
        print(error)
        return 2
    pilot.start()
    try:
        code = pilot.run_patrol()
    except KeyboardInterrupt:
        print("interrupted")
        pilot.submit({"action": "land"})
        code = 1
    try:
        if pilot.airborne:
            print("hovering; ctrl-c lands")
            while pilot.airborne:
                time.sleep(0.3)
    except KeyboardInterrupt:
        print("interrupted")
        pilot.submit({"action": "land"})
        deadline = time.monotonic() + 20
        while pilot.airborne and time.monotonic() < deadline:
            time.sleep(0.1)
    return code


def _load_model():
    from patrol.drone.depth_look import MODEL_DIR

    if not MODEL_DIR.is_dir():
        print(f"missing weights: {MODEL_DIR}")
        return None
    import torch
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    processor = AutoImageProcessor.from_pretrained(MODEL_DIR)
    model = AutoModelForDepthEstimation.from_pretrained(MODEL_DIR).to(device).eval()
    return model, processor, device


def _score_file(path: Path, args) -> int:
    from patrol.drone.depth_look import _predict

    loaded = _load_model()
    if loaded is None:
        return 1
    closer = _predict(*loaded[:2], path, loaded[2])
    if args.distance is not None:
        return _calibrate(closer, args.height, args.distance)
    view = assess(closer, args.height, args.margin / 100, args.speed, args.hop, args.tilt)
    print(describe(0, view, None))
    return 0


def _calibrate(closer, camera_cm: int, distance_m: float) -> int:
    """Find the camera tilt that makes the floor read a measured distance.

    A flat floor fixes the model's scale for any tilt, but not its offset,
    so the tilt has to come from one distance measured by hand.
    """
    from patrol.drone.depth_look import floor_fit, free_distance_m

    best = None
    for tenth in range(-100, 301, 5):
        tilt = tenth / 10
        fit = floor_fit(closer, camera_cm / 100, tilt)
        if fit is None:
            continue
        free = free_distance_m(closer, fit)
        if best is None or abs(free - distance_m) < abs(best[1] - distance_m):
            best = (tilt, free)
    if best is None:
        print("floor fit failed; pick a photo with clear floor in the lower part")
        return 1
    print(f"tilt {best[0]:.1f}° reads {best[1]:.2f} m (measured {distance_m:.2f} m)")
    print("set CAMERA_TILT_DEG in patrol/drone/depth_look.py to that value")
    return 0


def _replay(folder: Path, args) -> int:
    """Re-score a saved run. No radio, no motors."""
    import json

    from patrol.drone.depth_look import CAMERA_TILT_DEG, _predict, _save

    state_file = folder / "state.json"
    frames = []
    if state_file.is_file():
        for frame in json.loads(state_file.read_text()).get("frames", []):
            path = folder / frame["file"]
            if path.is_file():
                frames.append((frame["step"], frame["heading"], path, frame.get("height_cm") or args.height))
    if not frames:
        print(f"no photos in {folder}")
        return 1
    loaded = _load_model()
    if loaded is None:
        return 1
    model, processor, device = loaded
    maps = []
    for step, heading, path, camera_cm in frames:
        closer = _predict(model, processor, path, device)
        _save(path, closer)
        maps.append((step, heading, camera_cm, closer))
    tilt = args.tilt if args.tilt is not None else CAMERA_TILT_DEG
    print(f"scoring with tilt {tilt}°, margin {args.margin} cm, speed {args.speed} m/s, hop max {args.hop}s")
    steps = sorted({step for step, *_rest in maps})
    for step in steps:
        lap = [(heading, cm, closer) for s, heading, cm, closer in maps if s == step]
        headings = [heading for heading, _cm, _closer in lap]
        back = None if step == steps[0] else min(headings, key=lambda h: abs(h - 180))
        print(f"lap {step + 1}")
        views = {}
        for heading, cm, closer in lap:
            views[heading] = assess(closer, cm, args.margin / 100, args.speed, args.hop, tilt)
            print(describe(heading, views[heading], back) + f"  at {cm} cm")
        chosen = pick(views, back)
        if chosen is None:
            print("  -> stay")
        else:
            print(f"  -> {chosen}° for {views[chosen]['hop']:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
