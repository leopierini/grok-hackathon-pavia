"""One offline pass of the museum story.

Ground is the only author of dog and drone commands. YOLO dispatch does not
call Grok. Presence calls Grok only after the dog has been sent.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from patrol.ground.museum.endpoint import motion_required_message
from patrol.ground.museum.peers import ConfigError, DogPeer, DronePeer, open_dog, open_drone
from patrol.ground.museum.policy import MuseumPolicy, _plus
from patrol.ground.museum.safety import decision_motor_phrase
from patrol.ground.museum.vision import (
    PROMPT,
    RealGrok,
    ScriptedGrok,
    build_request,
    summarize_decision,
)
from patrol.ground.signal.errors import SignalError

SCENARIOS = (
    "happy_path",
    "intruder_stays",
    "gone_land_home",
    "uncertain",
    "timeout",
    "halt",
    "dog_dropout",
    "drone_dropout",
)
_SCENE = frozenset({"approach", "hold", "stop", "review"})
_DRONE_FRAME = "drone-downward-001"
Json = dict[str, object]

# Drone link dies on the land attempt. The dog stop before it still delivers.
_DROP_ON_ACTION = {"drone_dropout": "land_on_dog"}

_STEPS: dict[str, tuple[object, ...]] = {
    "happy_path": (
        "patrol",
        "intruder",
        "dispatch",
        ("presence", "dog_approach", "person_visible"),
        ("presence", "dog_approach", "not_visible"),
    ),
    "intruder_stays": (
        "patrol",
        "intruder",
        "dispatch",
        ("presence", "dog_approach", "person_visible"),
        ("presence", "dog_approach", "person_visible"),
    ),
    "gone_land_home": (
        "patrol",
        "intruder",
        "dispatch",
        ("presence", "dog_approach", "person_visible"),
        ("presence", "dog_approach", "person_visible"),
        ("presence", "dog_approach", "not_visible"),
    ),
    "uncertain": (
        "patrol",
        "intruder",
        "dispatch",
        ("presence", "dog_approach", "uncertain"),
    ),
    "timeout": (
        "patrol",
        "intruder",
        "dispatch",
        ("presence", "dog_approach", "timeout"),
    ),
    "halt": (
        "patrol",
        "intruder",
        "dispatch",
        ("presence", "dog_approach", "person_visible"),
        "halt",
        ("presence", "dog_approach", "person_visible"),
        ("presence", "dog_approach", "not_visible"),
    ),
    "dog_dropout": (
        "patrol",
        "intruder",
        "dispatch",
        ("presence", "dog_approach", "person_visible"),
        ("drop", "dog"),
        ("presence", "dog_approach", "person_visible"),
    ),
    "drone_dropout": (
        "patrol",
        "intruder",
        "dispatch",
        ("presence", "dog_approach", "person_visible"),
        ("presence", "dog_approach", "not_visible"),
    ),
}

_EXPECTED: dict[str, tuple[tuple[str, ...], tuple[str, ...], int]] = {
    "happy_path": (
        ("hover", "follow", "play_warning", "stop", "land_on_dog", "return_home"),
        ("go away",),
        2,
    ),
    "intruder_stays": (
        ("hover", "follow", "play_warning", "follow", "play_warning"),
        ("go away", "go away"),
        2,
    ),
    "gone_land_home": (
        (
            "hover",
            "follow",
            "play_warning",
            "follow",
            "play_warning",
            "stop",
            "land_on_dog",
            "return_home",
        ),
        ("go away", "go away"),
        3,
    ),
    "uncertain": (("hover", "follow"), (), 1),
    "timeout": (("hover", "follow"), (), 1),
    "halt": (("hover", "follow", "play_warning", "halt"), ("go away",), 1),
    "dog_dropout": (("hover", "follow", "play_warning"), ("go away",), 1),
    "drone_dropout": (
        ("hover", "follow", "play_warning", "stop", "halt"),
        ("go away",),
        2,
    ),
}


@dataclass
class StoryReport:
    scenario: str
    grok: str
    ok: bool = False
    detail: str = ""
    delivered: list[Json] = field(default_factory=list)
    undelivered: list[Json] = field(default_factory=list)
    spoken: list[str] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)
    decisions: list[Json] = field(default_factory=list)
    grok_calls: int = 0
    halted: bool = False
    rejections: list[str] = field(default_factory=list)
    dog_trace: list[str] = field(default_factory=list)
    drone_trace: list[str] = field(default_factory=list)
    dog_effects: list[Json] = field(default_factory=list)
    drone_effects: list[Json] = field(default_factory=list)
    fake_drone_flight_state: str | None = None
    patrol_frame: str | None = None
    dog_mode: str = "fake"
    drone_mode: str = "fake"
    motion_authorized: bool = False
    gaps: list[Json] = field(default_factory=list)
    drone_commands: list[str] = field(default_factory=list)

    def as_dict(self) -> Json:
        return {
            "scenario": self.scenario,
            "grok": self.grok,
            "ok": self.ok,
            "detail": self.detail,
            "delivered": self.delivered,
            "undelivered": self.undelivered,
            "spoken": self.spoken,
            "timeline": self.timeline,
            "decisions": self.decisions,
            "grok_calls": self.grok_calls,
            "halted": self.halted,
            "rejections": self.rejections,
            "dog_trace": self.dog_trace,
            "drone_trace": self.drone_trace,
            "dog_effects": self.dog_effects,
            "drone_effects": self.drone_effects,
            "fake_drone_flight_state": self.fake_drone_flight_state,
            "patrol_frame": self.patrol_frame,
            "dog_mode": self.dog_mode,
            "drone_mode": self.drone_mode,
            "motion_authorized": self.motion_authorized,
            "gaps": self.gaps,
            "drone_commands": self.drone_commands,
        }


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 4, 13, 0, 10, tzinfo=UTC)

    def iso(self) -> str:
        millis = self.now.microsecond // 1000
        return self.now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"

    def push(self, milliseconds: int = 200) -> str:
        self.now += timedelta(milliseconds=milliseconds)
        return self.iso()


def run_story(
    output: Path,
    *,
    scenario: str,
    dog: str = "fake",
    drone: str = "fake",
    grok: str = "fake",
    environ: Mapping[str, str] | None = None,
    file_config: Mapping[str, object] | None = None,
    motion_authorized: bool = False,
    dog_conn_factory: Any = None,
    drone_sdk_factory: Any = None,
    drone_frame: Any = None,
    drone_timing: Mapping[str, float] | None = None,
    grok_client: Any = None,
) -> StoryReport:
    """Run one scenario.

    Real dog or drone mode requires ``motion_authorized``. Missing host or port
    raises ``ConfigError`` before a socket is opened.
    """

    if scenario not in SCENARIOS:
        raise ConfigError(f"unknown scenario {scenario!r}")
    if grok not in {"fake", "real"}:
        raise ConfigError("grok mode must be fake or real")
    if (dog == "real" or drone == "real") and not motion_authorized:
        raise ConfigError(motion_required_message())
    env = dict(environ) if environ is not None else {}
    report = StoryReport(
        scenario=scenario,
        grok=grok,
        dog_mode=dog,
        drone_mode=drone,
        motion_authorized=motion_authorized,
    )
    dog_peer = open_dog(
        dog,
        output / "dog",
        env,
        file_config,
        conn_factory=dog_conn_factory,
    )
    drone_peer = open_drone(
        drone,
        output / "drone",
        env,
        file_config,
        motion_authorized=motion_authorized,
        sdk_factory=drone_sdk_factory,
        frame_source=drone_frame,
        timing=drone_timing,
    )
    source = grok_client
    if source is None:
        source = ScriptedGrok() if grok == "fake" else RealGrok()
    asyncio.run(_run(report, dog_peer, drone_peer, source))
    problem = invariant_problem(report)
    if dog == "fake" and drone == "fake" and grok == "fake" and grok_client is None:
        problem = problem or script_problem(report)
    else:
        problem = problem or hardware_problem(report)
        if grok == "fake":
            problem = problem or real_story_problem(report)
    report.ok = problem is None
    report.detail = _detail(problem, report)
    return report


async def _run(report: StoryReport, dog: DogPeer, drone: DronePeer, source: Any) -> None:
    policy = MuseumPolicy()
    clock = _Clock()
    intruder = False
    seq = 0
    try:
        for step in _STEPS[report.scenario]:
            if step == "patrol":
                await drone.patrol()
                await dog.connect()
                policy.arm()
                report.timeline.append("patrol")
                continue
            if step == "intruder":
                intruder = True
                report.timeline.append("intruder")
                continue
            if step == "dispatch":
                count = 1 if intruder else 0
                report.timeline.append(f"yolo:{count}")
                if count == 1:
                    policy.bind_track("target-001")
                    commands = policy.authorize_dispatch(clock.push(), _DRONE_FRAME)
                    await _deliver(report, policy, dog, drone, clock, commands)
                continue
            if step == "halt":
                commands = policy.halt_command(clock.push(), "Operator halt.")
                report.timeline.append("operator_halt")
                await _deliver(report, policy, dog, drone, clock, commands)
                continue
            if isinstance(step, tuple) and step[0] == "drop":
                peer_name = str(step[1])
                if peer_name == "dog":
                    dog.drop()
                else:
                    drone.drop()
                commands = policy.halt_command(clock.push(), f"{peer_name} link lost.")
                report.timeline.append(f"drop:{peer_name}")
                await _deliver(report, policy, dog, drone, clock, commands)
                continue
            if isinstance(step, tuple) and step[0] == "presence":
                if policy.halted:
                    report.timeline.append("presence_skipped")
                    continue
                stage = str(step[1])
                state = str(step[2])
                seq += 1
                sent = clock.push()
                answered = clock.push(100)
                request = build_request(
                    stage=stage,
                    sent_at=sent,
                    expires_at=_plus(sent, 5000),
                    track_id=policy.track_id or "target-001",
                    seq=seq,
                )
                try:
                    decision = source.answer(request, state, answered)
                except SignalError as exc:
                    if exc.code == "timeout":
                        report.timeline.append("grok:timeout")
                        continue
                    raise
                if decision is None:
                    report.timeline.append("grok:timeout")
                    continue
                summary = summarize_decision(decision)
                report.decisions.append(summary)
                report.timeline.append(
                    f"grok:{summary.get('target_state')}:{summary.get('suggested_action')}"
                )
                commands = policy.authorize_presence(decision, request, answered)
                await _deliver(report, policy, dog, drone, clock, commands)
    finally:
        report.grok_calls = source.calls
        report.halted = policy.halted
        report.rejections = list(policy.rejections)
        report.spoken = dog.spoken
        report.dog_trace = dog.trace
        report.drone_trace = drone.trace
        report.dog_effects = list(dog.effects)
        report.drone_effects = list(drone.effects)
        report.fake_drone_flight_state = drone.flight_state
        report.patrol_frame = drone.patrol_frame
        close_dog = getattr(dog.dog, "close", None)
        if close_dog is not None:
            await close_dog()
        await drone.close()
        report.drone_commands = [
            str(item) for item in getattr(drone.drone, "commands", []) if isinstance(item, str)
        ]


async def _deliver(
    report: StoryReport,
    policy: MuseumPolicy,
    dog: DogPeer,
    drone: DronePeer,
    clock: _Clock,
    commands: list[Json],
) -> None:
    for command in commands:
        summary = _summary(command)
        action = str(summary.get("action"))
        drop_action = _DROP_ON_ACTION.get(report.scenario)
        if drop_action == action and drone.up:
            drone.drop()
            report.timeline.append("drop:drone")
        peer: DogPeer | DronePeer = dog if command.get("destination") == "dog" else drone
        applied = await peer.apply(command)
        if applied:
            report.delivered.append(summary)
            report.timeline.append(f"cmd:{action}")
            if action == "halt":
                await drone.halt()
            continue
        if peer.outcome == "gap" and peer.last_gap is not None:
            report.gaps.append(dict(peer.last_gap))
            report.timeline.append(f"gap:{action}")
            continue
        report.undelivered.append(summary)
        report.timeline.append(f"undelivered:{action}")
        await drone.halt()
        if not policy.halted:
            halt = policy.halt_command(clock.push(), "Link lost. Halt.")
            for item in halt:
                halt_summary = _summary(item)
                if await dog.apply(item):
                    report.delivered.append(halt_summary)
                    report.timeline.append("cmd:halt")
                else:
                    report.undelivered.append(halt_summary)
                    report.timeline.append("undelivered:halt")
        break


def _summary(command: Mapping[str, object]) -> Json:
    payload = command.get("payload")
    body = payload if isinstance(payload, Mapping) else {}
    return {
        "action": body.get("action"),
        "kind": command.get("kind"),
        "source": command.get("source"),
        "destination": command.get("destination"),
        "text": body.get("text"),
        "warning_id": body.get("warning_id"),
        "standoff_m": body.get("standoff_m"),
        "primitive_id": body.get("primitive_id"),
        "beacon_epoch": body.get("beacon_epoch"),
    }


def invariant_problem(report: StoryReport) -> str | None:
    """Safety checks that do not depend on the scripted intruder timeline."""

    for item in report.delivered:
        if item.get("source") != "ground":
            return "a delivered command did not come from ground"
        if item.get("kind") not in {"dog.command", "drone.command"}:
            return "a delivered command is not a dog or drone command"
        action = item.get("action")
        if action in {"move_local", "approach", "takeoff", "land", "dispatch_dog"}:
            return f"delivered a forbidden action {action}"
    for spoken in report.spoken:
        if spoken != "go away":
            return "the dog said something other than the warning"
    for decision in report.decisions:
        if decision.get("source") != "vision" or decision.get("kind") != "vision.decision":
            return "presence reply was not a vision.decision"
        if decision.get("prompt_version") != PROMPT:
            return "presence prompt was not patrol-presence-v1"
        action = decision.get("suggested_action")
        if action not in _SCENE:
            return f"grok suggested a non-scene action {action}"
        reason = decision.get("reason")
        if not isinstance(reason, str) or decision_motor_phrase(
            {"payload": {"reason": reason}}
        ):
            return "grok reason contained a motor phrase"
    grok_at = [index for index, item in enumerate(report.timeline) if item.startswith("grok:")]
    yolo_at = [index for index, item in enumerate(report.timeline) if item.startswith("yolo:")]
    if grok_at and yolo_at and min(grok_at) < min(yolo_at):
        return "grok ran before YOLO dispatch"
    if any(item.startswith("grok:") for item in report.timeline[:1]):
        return "grok ran before patrol"
    return None


def script_problem(report: StoryReport) -> str | None:
    expected = _EXPECTED[report.scenario]
    actions = tuple(str(item.get("action")) for item in report.delivered)
    spoken = tuple(report.spoken)
    if actions != expected[0]:
        return f"delivered {actions}, expected {expected[0]}"
    if spoken != expected[1]:
        return f"spoken {spoken}, expected {expected[1]}"
    if report.grok_calls != expected[2]:
        return f"grok calls {report.grok_calls}, expected {expected[2]}"
    if report.scenario == "uncertain":
        if not report.decisions or report.decisions[0].get("target_state") != "uncertain":
            return "uncertain scenario did not record an uncertain decision"
        if report.decisions[0].get("suggested_action") != "review":
            return "uncertain decision was not review"
    if report.scenario == "timeout" and report.decisions:
        return "timeout produced a decision"
    if report.scenario in {"halt", "dog_dropout", "drone_dropout"} and not report.halted:
        return "halt did not latch"
    if report.scenario == "happy_path":
        lands = [item for item in report.delivered if item.get("action") == "land_on_dog"]
        if not lands or lands[0].get("primitive_id") != "land-on-dog-v1":
            return "land_on_dog did not use primitive land-on-dog-v1"
        if lands[0].get("beacon_epoch") is not None:
            return "land_on_dog carried a beacon epoch"
    follows = [item for item in report.delivered if item.get("action") == "follow"]
    if any(item.get("standoff_m") != 2.0 for item in follows):
        return "follow standoff was not 2.0"
    warnings = [item for item in report.delivered if item.get("action") == "play_warning"]
    bad_warning = any(
        item.get("text") != "go away" or item.get("warning_id") != "go-away" for item in warnings
    )
    if bad_warning:
        return "warning text was not go away"
    if "inspect" not in report.drone_trace or "connect" not in report.dog_trace:
        return "fake dog or fake drone was not used"
    return None


def hardware_problem(report: StoryReport) -> str | None:
    """Motor log checks for a run that touched a real adapter or a stand-in SDK."""

    commands = report.drone_commands
    if commands.count("takeoff") > 1:
        return "more than one takeoff"
    if commands.count("land") > commands.count("takeoff"):
        return "a land was sent without a matching takeoff"
    for command in commands:
        head = command.split(" ", 1)[0]
        if head in {"forward", "back", "left", "right", "up", "down", "go", "curve", "flip"}:
            return f"translation command {command}"
        if command.startswith("rc ") and command != "rc 0 0 0 0":
            return "nonzero rc"
    for item in report.gaps:
        if not item.get("owner") or not item.get("issues") or not item.get("action"):
            return "gap missing owner or issue"
    halted = report.scenario in {"halt", "dog_dropout", "drone_dropout"}
    if not halted and "emergency" in commands:
        return "emergency on a scenario that did not halt"
    return None


def real_story_problem(report: StoryReport) -> str | None:
    """Scripted Grok with at least one real peer: same story, gaps allowed."""

    expected_actions, _expected_spoken, expected_grok = _EXPECTED[report.scenario]
    if report.grok_calls != expected_grok:
        return f"grok calls {report.grok_calls}, expected {expected_grok}"
    relevant: list[str] = []
    for item in report.timeline:
        if item.startswith(("cmd:", "gap:")):
            action = item.split(":", 1)[1]
            if action not in expected_actions:
                if report.scenario == "dog_dropout" and action == "halt":
                    relevant.append(action)
                    continue
                return f"unexpected {action}"
            relevant.append(action)
        elif item.startswith("undelivered:"):
            action = item.split(":", 1)[1]
            if action in expected_actions:
                relevant.append(action)
    expected = tuple(expected_actions)
    actual = tuple(relevant)
    optional_halt = report.scenario == "dog_dropout" and actual == expected + ("halt",)
    if actual != expected and not optional_halt:
        return f"actions {actual}, expected {expected}"
    delivered_warnings = sum(
        1 for item in report.delivered if item.get("action") == "play_warning"
    )
    gap_warnings = sum(1 for item in report.gaps if item.get("action") == "play_warning")
    if delivered_warnings + gap_warnings != expected_actions.count("play_warning"):
        return "warning count"
    if tuple(report.spoken) != ("go away",) * delivered_warnings:
        return f"spoken {tuple(report.spoken)}"
    follows = [item for item in report.delivered if item.get("action") == "follow"]
    if any(item.get("standoff_m") != 2.0 for item in follows):
        return "follow standoff was not 2.0"
    lands = [item for item in report.delivered if item.get("action") == "land_on_dog"]
    if lands and lands[0].get("primitive_id") != "land-on-dog-v1":
        return "land_on_dog did not use primitive land-on-dog-v1"
    if lands and lands[0].get("beacon_epoch") is not None:
        return "land_on_dog carried a beacon epoch"
    if report.scenario in {"halt", "dog_dropout", "drone_dropout"} and not report.halted:
        return "halt did not latch"
    if report.scenario in {"uncertain", "timeout"}:
        banned = {"play_warning", "stop", "land_on_dog", "return_home", "halt"}
        if any(item.get("action") in banned for item in report.delivered):
            return "uncertain or timeout delivered a presence command"
    halt_at = [
        index
        for index, item in enumerate(report.timeline)
        if item in {"cmd:halt", "gap:halt"}
    ]
    if halt_at:
        later = report.timeline[max(halt_at) + 1 :]
        if any(item.startswith("cmd:") for item in later):
            return "a command was delivered after halt"
    return None


def _detail(problem: str | None, report: StoryReport) -> str:
    if problem is not None:
        return problem
    if not report.gaps:
        return "passed"
    parts: list[str] = []
    for item in report.gaps:
        issues = item.get("issues")
        numbers = ""
        if isinstance(issues, list):
            numbers = " ".join(f"#{issue}" for issue in issues)
        parts.append(f"{item.get('action')} ({item.get('owner')} {numbers})".strip())
    return "passed with known gaps: " + "; ".join(parts)


def write_report(report: StoryReport, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
