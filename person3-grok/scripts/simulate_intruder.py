"""Offline intruder simulation: drone search -> potential intruder -> confirmed -> dog called.

Runs the scripted FakeReasoner and the real presence helpers over a fixed timeline of
drone and dog observations. No robot, no xAI key, no network. Every step is written to a
JSONL record that the demo video replays line for line.

    PYTHONPATH=. python scripts/simulate_intruder.py
    PYTHONPATH=. python scripts/simulate_intruder.py --out artifacts/sim/intruder_run.jsonl --quiet
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from patrol.contract import Frame, Incident, RunContext
from patrol.grok.fake import FakeReasoner
from patrol.grok.presence import (
    DOG_STAGE,
    image_direction,
    presence_state,
    suggested_action,
)

DRONE_SEARCH = "drone_search"
MISSION_ID = "sim-intruder-001"


@dataclass(frozen=True)
class Observation:
    """One scripted camera read. `t` is seconds into the patrol (the video timeline)."""

    t: float
    stage: str
    scene: str
    presence: str | None = None          # fake presence scenario, None = no person in frame
    box: tuple[float, float, float, float] | None = None


# Timeline is synced to the live-run footage in the submission video.
TIMELINE: tuple[Observation, ...] = (
    Observation(7.8, DRONE_SEARCH, "Hallway: workbench, open door. Nothing of interest."),
    Observation(13.6, DRONE_SEARCH, "Main hall: people at desks. Bystanders, not the target."),
    Observation(18.6, DRONE_SEARCH, "No match yet. Continuing sweep, turning 45°."),
    Observation(28.0, DRONE_SEARCH, "Person near the stairs, partly hidden. Holding.",
                presence="unsure", box=(0.62, 0.45, 0.74, 0.88)),
    Observation(32.6, DRONE_SEARCH, "Same person, clear view.",
                presence="still_there", box=(0.40, 0.30, 0.58, 0.95)),
    Observation(41.8, DOG_STAGE, "Dog front camera on target.",
                presence="still_there", box=(0.35, 0.15, 0.65, 0.98)),
)


def _record(log: list[dict], t: float, level: str, chip: str, text: str, **extra: object) -> None:
    log.append({"t": round(t, 2), "level": level, "chip": chip, "text": text, **extra})


async def run(timeline: tuple[Observation, ...] = TIMELINE) -> list[dict]:
    reasoner = FakeReasoner({"scenario": "blocked_resolved", "model": "fake"}, Path("."))
    ctx = RunContext(MISSION_ID, time.monotonic() + 120.0, Event())
    log: list[dict] = []
    suspicion = False
    dog_called = False

    for obs in timeline:
        if obs.presence is None:
            _record(log, obs.t, "info", "", obs.scene, stage=obs.stage)
            continue

        state = reasoner.read_presence(obs.presence)
        action = suggested_action(obs.stage, state)
        direction = image_direction(obs.box)

        if obs.stage == DRONE_SEARCH and state == "uncertain":
            _record(log, obs.t - 2.6, "info", "", obs.scene, stage=obs.stage,
                    presence=state, action=action, direction=direction)
            _record(log, obs.t, "warn", "POSSIBLE", "Seeing potential intruder. Investigating.",
                    stage=obs.stage, presence=state, action=action, direction=direction)
            suspicion = True
        elif obs.stage == DRONE_SEARCH and state == "person_visible" and suspicion:
            frame = Frame(path=f"/sim/{MISSION_ID}/drone_{obs.t:.1f}.jpg", source="drone",
                          zone="room_2", captured_at=None, simulated=True)
            incident = Incident(MISSION_ID, "room_2", "intruder", frame)
            decision = await reasoner.assess_incident(incident, ctx)
            if decision.action == "dispatch":
                _record(log, obs.t, "alert", "CONFIRMED", "Intruder confirmed. Calling dog.",
                        stage=obs.stage, presence=state, action=action, direction=direction,
                        decision=decision.action)
                _record(log, obs.t + 3.2, "sys", "GROUND", "Go2 dispatched to target. Lease granted.",
                        stage="ground", decision=decision.action)
                dog_called = True
        elif obs.stage == DOG_STAGE and dog_called:
            if action == "approach":
                _record(log, obs.t, "sys", "GO2", "On scene. Confirming at ground level.",
                        stage=obs.stage, presence=state, action=action, direction=direction)
            else:
                _record(log, obs.t, "warn", "GO2", f"Dog view: {state}. Holding for review.",
                        stage=obs.stage, presence=state, action=action)

    await reasoner.close()
    log.sort(key=lambda r: r["t"])
    return log


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="artifacts/sim/intruder_run.jsonl")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    log = asyncio.run(run())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in log), encoding="utf-8")
    if not args.quiet:
        for r in log:
            chip = f"[{r['chip']}] " if r["chip"] else ""
            print(f"T+{r['t']:6.2f}s  {r['level']:<5}  {chip}{r['text']}")
        print(f"\n{len(log)} events -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
