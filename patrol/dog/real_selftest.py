"""Supervised real-dog session (HAC-3), one step per run.

    python -m patrol.dog.real_selftest --config config/dog.local.json --step read
    python -m patrol.dog.real_selftest --config config/dog.local.json --step prepare --arm
    python -m patrol.dog.real_selftest --config config/dog.local.json --step halt --arm
    python -m patrol.dog.real_selftest --config config/dog.local.json --step move --arm
    python -m patrol.dog.real_selftest --config config/dog.local.json --step halt-mid-move --arm
    python -m patrol.dog.real_selftest --config config/dog.local.json --step expiry --arm
    python -m patrol.dog.real_selftest --config config/dog.local.json --step rest --arm

Before ANY --arm step: staff present holding their controller, 2 m clear in front
of the dog, Unitree phone app closed.

HARD STOPS from the keyboard (run this in your own Terminal so it can read keys):
  Q / ENTER -> STOP: stop walking, then lie down softly (StandDown).
               Top priority: works at any time. Never uses Damp (rough drop).
  Ctrl+C    -> stop walking (stay standing), then exit
After a rest, stand the dog up again with:  --step prepare --arm
The staff controller is always the primary stop; this is the backup.

Steps
  read           connect, status, motion mode, avoidance readback, one photo. No motion.
  prepare        stand up if needed + avoidance on, then read back.
  halt           StopMove while stationary; check it is accepted.
  move           0.2 m/s forward for 1.0 s via the route control path; odometry delta.
  halt-mid-move  start 0.2 m/s for 3 s, halt() after 0.8 s; time until stationary.
  expiry         ONE Move at 0.2 m/s, no repeats; watch how long it keeps walking (max 2 s), then halt.
  rest           Emergency rest on demand: stop, then lie down slowly (same as pressing Q).

Each run appends a JSON line to evidence/dog/session.jsonl and prints a summary.
Never auto-retries anything.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

from patrol.contract import AdapterError, RunContext

MOTION_STEPS = {"prepare", "halt", "move", "halt-mid-move", "expiry", "rest"}
STEPS = ["read", *sorted(MOTION_STEPS)]
EVIDENCE = Path("evidence/dog")


def _ctx(seconds: float) -> RunContext:
    return RunContext(mission_id=f"hac3-{datetime.now().strftime('%H%M%S')}",
                      deadline_monotonic=time.monotonic() + seconds, cancel=Event())


def _pos(dog) -> list[float] | None:
    s = dog.raw_state()["sport"]
    return list(s["position"]) if s and "position" in s else None


def _speed(dog) -> float | None:
    s = dog.raw_state()["sport"]
    if not s:
        return None
    return math.hypot(s["velocity"][0], s["velocity"][1])


class _Keys:
    """Single-key hard stops, read straight from the terminal (no Enter needed).

    Q or ENTER -> STOP: stop walking + lie down softly (StandDown). Top priority,
                  works any time. Never the rough drop (Damp).
    Ctrl+C     -> stop walking (stay standing), then exit.
    """

    def __init__(self, dog, rec: dict, main_task: asyncio.Task) -> None:
        self.dog, self.rec, self.main_task = dog, rec, main_task
        self.rest_task: asyncio.Task | None = None
        self.halt_task: asyncio.Task | None = None
        self.active = False
        self._old = None

    def install(self) -> bool:
        if not sys.stdin.isatty():
            return False
        import termios
        import tty

        fd = sys.stdin.fileno()
        self._old = termios.tcgetattr(fd)
        tty.setcbreak(fd)                      # keys arrive immediately; Ctrl+C still works
        asyncio.get_running_loop().add_reader(fd, self._on_key)
        self.active = True
        return True

    def restore(self) -> None:
        if not self.active:
            return
        import termios

        fd = sys.stdin.fileno()
        try:
            asyncio.get_running_loop().remove_reader(fd)
        except Exception:
            pass
        termios.tcsetattr(fd, termios.TCSADRAIN, self._old)
        self.active = False

    def _on_key(self) -> None:
        ch = os.read(sys.stdin.fileno(), 1)
        # Q and ENTER both = STOP = lie down softly (StopMove + StandDown). Never Damp.
        if ch in (b"q", b"Q", b"\n", b"\r") and self.rest_task is None:
            print("\n*** STOP: lying down softly ***", flush=True)
            self.rec["operator_hard_stop"] = "rest"
            self.rest_task = asyncio.get_running_loop().create_task(self.dog.rest())
            self.main_task.cancel()


async def _uncancellable(aw):
    """Await to completion even if the step task gets cancelled meanwhile (e.g. Q pressed)."""
    task = asyncio.ensure_future(aw)
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result() if not task.cancelled() else None
            continue


async def _run(step: str, config: dict, out: Path) -> dict:
    from patrol.dog.real import RealDog

    rec: dict = {"step": step, "utc": datetime.now(timezone.utc).isoformat()}
    dog = RealDog(config=config, output_dir=out)
    keys = _Keys(dog, rec, asyncio.current_task())
    rec["keyboard_stops_active"] = keys.install()
    if keys.active:
        print("STOP: press Q or ENTER = stop + lie down softly", flush=True)
    elif step in MOTION_STEPS:
        print("WARNING: no terminal keyboard, Q/ENTER stops are OFF (only Ctrl+C and the staff controller).",
              flush=True)
    try:
        t0 = time.monotonic()
        rec["status_after_connect"] = asdict(await dog.connect())
        rec["connect_s"] = round(time.monotonic() - t0, 2)
        rec["start_position"] = _pos(dog)

        if step == "read":
            rec["motion_mode"] = await dog.get_motion_mode()
            rec["avoidance_query"] = await dog.get_avoidance()
            s = dog.raw_state()
            low = s["low"] or {}
            rec["battery"] = (low.get("bms_state") or {}).get("soc")
            rec["sport_mode"] = (s["sport"] or {}).get("mode")
            rec["body_height"] = (s["sport"] or {}).get("body_height")
            rec["settings"] = s["multi"]
            frame = await dog.capture_frame("room_2", _ctx(5))
            rec["photo"] = frame.path
            rec["photo_captured_at"] = frame.captured_at

        elif step == "rest":
            rec["rest_report"] = await dog.rest()
            await asyncio.sleep(2.5)            # let it finish lying down before we read status

        elif step == "prepare":
            rec["status_after_prepare"] = asdict(await dog.prepare(_ctx(15)))
            rec["avoidance_query"] = await dog.get_avoidance()

        elif step == "halt":
            t = time.monotonic()
            await dog.halt()
            rec["halt_call_s"] = round(time.monotonic() - t, 3)
            await asyncio.sleep(0.5)
            rec["status_after_halt"] = asdict(await dog.get_status())

        elif step == "move":
            res = await dog.run_segments([{"vx": 0.2, "duration_s": 1.0}], _ctx(10), "hac3_move")
            await asyncio.sleep(0.3)
            rec["result"] = asdict(res)
            rec["end_position"] = _pos(dog)

        elif step == "halt-mid-move":
            route = asyncio.create_task(
                dog.run_segments([{"vx": 0.2, "duration_s": 3.0}], _ctx(10), "hac3_halt_mid"))
            await asyncio.sleep(0.8)
            rec["speed_before_halt"] = _speed(dog)
            t = time.monotonic()
            await dog.halt()
            rec["halt_call_s"] = round(time.monotonic() - t, 3)
            while time.monotonic() - t < 3.0:
                st = await dog.get_status()
                if st.stationary is True:
                    rec["stationary_after_halt_s"] = round(time.monotonic() - t, 3)
                    break
                await asyncio.sleep(0.02)
            rec["result"] = asdict(await asyncio.wait_for(route, 5.0))
            rec["end_position"] = _pos(dog)

        elif step == "expiry":
            await dog.send_single_move(0.2)
            t = time.monotonic()
            samples = []
            moving_seen = False
            while time.monotonic() - t < 2.0:
                v = _speed(dog)
                samples.append((round(time.monotonic() - t, 2), None if v is None else round(v, 3)))
                if v is not None and v > 0.05:
                    moving_seen = True
                elif moving_seen and v is not None:
                    rec["stopped_by_itself_after_s"] = round(time.monotonic() - t, 2)
                    break
                await asyncio.sleep(0.05)
            await dog.halt()
            rec["moving_seen"] = moving_seen
            rec["speed_samples"] = samples[::4]
            rec["end_position"] = _pos(dog)

        rec["status_end"] = asdict(await dog.get_status())
        rec["ok"] = True
    except (KeyboardInterrupt, asyncio.CancelledError):
        rec["ok"] = False
        how = rec.get("operator_hard_stop")
        rec["error"] = f"hard stop by operator ({how})" if how else "interrupted by operator"
        if keys.rest_task is None:
            await _uncancellable(dog.halt())
    except AdapterError as e:
        rec["ok"] = False
        rec["error"] = str(e)
        if step in MOTION_STEPS:
            await _uncancellable(dog.halt())
    except Exception as e:  # unexpected bug: record it and stop the dog, never crash silently
        rec["ok"] = False
        rec["error"] = f"unexpected {type(e).__name__}: {e}"
        await _uncancellable(dog.halt())
    finally:
        # STOP (Q/Enter) wins over everything: wait for its soft lie-down to finish.
        if keys.rest_task is not None:
            rec["rest_report"] = await _uncancellable(keys.rest_task)
            if rec.get("ok"):
                rec["ok"] = False
                rec["error"] = "hard stop by operator (rest)"
        await _uncancellable(dog.close())
        keys.restore()                      # keys stay live until the dog is closed
    sp, ep = rec.get("start_position"), rec.get("end_position")
    if sp and ep:
        rec["moved_m"] = round(math.hypot(ep[0] - sp[0], ep[1] - sp[1]), 3)
    return rec


def main(args: argparse.Namespace | None = None) -> int:
    import logging
    logging.getLogger("aiortc.codecs.h264").setLevel(logging.ERROR)  # harmless pre-keyframe noise
    if args is None or not hasattr(args, "step"):
        ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        ap.add_argument("--config", default=getattr(args, "config", None) or "config/dog.local.json")
        ap.add_argument("--step", choices=STEPS, default="read")
        ap.add_argument("--arm", action="store_true", default=bool(getattr(args, "arm", False)))
        ap.add_argument("--out", default=str(EVIDENCE))
        args = ap.parse_args(None if args is None else [])
    if args.step in MOTION_STEPS and not args.arm:
        print(f"Step {args.step!r} moves or commands the dog: re-run with --arm "
              "(staff present with controller, area clear, phone app closed).")
        return 2
    config = json.loads(Path(args.config).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        rec = asyncio.run(_run(args.step, config, out))
    except KeyboardInterrupt:
        print("Interrupted.")
        return 1
    with open(out / "session.jsonl", "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(json.dumps(rec, indent=2, default=str))
    print("PASS" if rec.get("ok") else "FAIL")
    return 0 if rec.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
