"""Fly the one floor profile. Motors stay off unless --arm is passed.

    python -m patrol.drone.room2
    python -m patrol.drone.room2 --arm

Join TELLO-62A593 first. Put the drone on the floor mark, nose toward the
subject, with the dog behind it. It hovers, takes one photo, and lands on
that same mark. It does not translate: the distance command cannot track
this floor.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from patrol.contract import AdapterError
from patrol.drone.profile import allow

VIDEO_URL = "udp://0.0.0.0:11111"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fly room_2_view_v1 from the floor.")
    parser.add_argument("--arm", action="store_true", help="actually take off")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/drone"),
        help="directory for the viewpoint JPEG",
    )
    args = parser.parse_args(argv)
    try:
        profile = allow("room_2_view_v1", "room_2", "floor")
    except AdapterError as exc:
        print(f"{exc.code}: {exc.detail}")
        return 2
    settle = int(profile["settle_s"])
    print(f"room_2_view_v1: takeoff, hold {settle}s, photo, land on the same mark")
    if not args.arm:
        print("not armed; no motors")
        return 0
    try:
        return fly(profile, args.output)
    except KeyboardInterrupt:
        print("interrupted")
        return 1


def fly(profile: dict, output_dir: Path) -> int:
    from patrol.drone.tello_sdk import TelloSDK

    sdk = TelloSDK()
    takeoff_sent = False
    forward_sent = False
    outbound_ok = False
    back_attempted = False
    back_ok = False
    grounded = False
    streaming = False
    frame: Path | None = None
    code = 1
    forward = int(profile["viewpoint"]["forward_cm"])
    move_timeout = float(profile["command_timeout_s"])
    deadline = 0.0
    try:
        if sdk.query("command") != "ok":
            print("sdk did not enter command mode")
        else:
            battery = int(sdk.query("battery?"))
            print(f"battery {battery}%")
            reserve = int(profile["battery_min_percent"])
            if battery < reserve:
                print(f"refusing to fly below {reserve}%")
            else:
                _query_optional(sdk, "downvision 0")
                print("taking off")
                takeoff_sent = True
                if sdk.query("takeoff", timeout=float(profile["takeoff_timeout_s"])) != "ok":
                    print("takeoff was not confirmed; no second attempt")
                else:
                    deadline = time.monotonic() + float(profile["max_flight_s"])
                    _settle(sdk, float(profile["settle_s"]), deadline)
                    if forward == 0:
                        print("holding; no translation on this floor")
                        streaming = True
                        frame = _photo(sdk, output_dir)
                        code = 0 if frame is not None else 1
                    else:
                        _query_optional(sdk, f"speed {int(profile['speed_cm_s'])}")
                        _expire(deadline)
                        print(f"forward {forward} cm")
                        forward_sent = True
                        if sdk.query(f"forward {forward}", timeout=move_timeout) != "ok":
                            print("forward was not confirmed; landing here, no retry")
                        else:
                            outbound_ok = True
                            streaming = True
                            frame = _photo(sdk, output_dir)
                            _expire(deadline)
                            print(f"back {forward} cm")
                            back_attempted = True
                            if sdk.query(f"back {forward}", timeout=move_timeout) == "ok":
                                back_ok = True
                                code = 0 if frame is not None else 1
                            else:
                                print("return was not confirmed")
    except Exception as exc:
        print(f"profile failed: {exc}")
        code = 1
    finally:
        if takeoff_sent and outbound_ok and not back_attempted:
            try:
                print(f"abort return {forward} cm")
                if sdk.query(f"back {forward}", timeout=move_timeout) == "ok":
                    back_ok = True
            except Exception as exc:
                print(f"abort return failed: {exc}")
        if takeoff_sent:
            on_patch = back_ok or not forward_sent
            grounded = _land(sdk, on_patch)
            if not grounded:
                code = 1
                print("flight state unknown; do not take off again")
        if streaming:
            try:
                sdk.query("streamoff", timeout=2)
            except Exception:
                pass
        sdk.close()
    return code


def _photo(sdk, output_dir: Path) -> Path | None:
    """Video stays off during takeoff. It comes on only to grab the still."""
    print(sdk.query("streamon"))
    time.sleep(0.8)
    sdk.query("command", timeout=3)
    return _capture(output_dir, timeout=4)


def _land(sdk, on_patch: bool) -> bool:
    try:
        print("landing")
        reply = sdk.query("land", timeout=15)
        height = sdk.query("height?", timeout=3)
    except Exception as exc:
        print(f"land failed: {exc}")
        return False
    print(f"land {reply}, height {height} cm")
    on_ground = reply == "ok" and height == "0"
    if on_ground and on_patch:
        print("grounded on the landing mark")
        return True
    if on_ground:
        print("on the ground, landing mark not confirmed")
    return False


def _settle(sdk, seconds: float, deadline: float) -> None:
    """Hover until the body is level. A move during the climb comes out short and curved."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        _expire(deadline)
        height = sdk.query("height?", timeout=3)
        print(f"settling, height {height} cm")
        pause = min(0.5, end - time.monotonic())
        if pause > 0:
            time.sleep(pause)


def _query_optional(sdk, command: str) -> None:
    try:
        print(f"{command}: {sdk.query(command, timeout=3)}")
    except Exception as exc:
        print(f"{command} skipped: {exc}")


def _expire(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise TimeoutError("profile time is up")


def _capture(output_dir: Path, timeout: float) -> Path | None:
    import av

    container = None
    try:
        container = av.open(
            VIDEO_URL,
            timeout=(timeout, None),
            options={"overrun_nonfatal": "1", "fifo_size": "5000000", "reuse": "1"},
        )
        for frame in container.decode(video=0):
            image = frame.to_image()
            if image.size[0] < 16:
                continue
            output_dir.mkdir(parents=True, exist_ok=True)
            captured = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            path = output_dir / f"room_2_view_v1-{captured.replace(':', '')}.jpg"
            image.save(path)
            print(f"saved {path} size={image.size} captured_at={captured}")
            return path
    except Exception as exc:
        print(f"capture failed: {exc}")
        return None
    finally:
        if container is not None:
            container.close()
    return None


if __name__ == "__main__":
    sys.exit(main())
