"""Ordered drone-first rehearsal. Fixtures only; no adapter calls."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from patrol.ground.kernel.contracts import IOPort
from patrol.ground.kernel.paths import repo_root

SLOT = "feature.v2_rehearsal"
SCHEMA = "ground-task-v2"
EVIDENCE_AGE_S = 3.0
MISSION_ID = "demo-20261104-001"
FORBIDDEN_KEYS = frozenset(
    {
        "rssi_m",
        "meters_from_rssi",
        "range_from_rssi_m",
        "distance_from_rssi_m",
    }
)

HAPPY_TRACE = (
    "capabilities",
    "stable_hold",
    "drone_detection",
    "drone_step",
    "dog_stopped",
    "beacon_epoch",
    "pi_window",
    "dog_step",
    "dog_camera_handoff",
    "proximity_goal",
    "landing",
)
UNKNOWN_TRACE = HAPPY_TRACE[:-1] + ("landing_unverified",)
BLOCKED_TRACE = HAPPY_TRACE[:7] + ("dog_stop",)
NOISY_TRACE = HAPPY_TRACE[:6] + ("noisy_rssi", "dog_stop")
STALE_TRACE = ("capabilities", "stale_frame")
UNCONTROLLED_TRACE = ("capabilities", "supervised_stop")
SECOND_TRACE = ("takeoff_timeout", "second_takeoff_rejected")

_HAPPY_FILES = (
    ("messages", "dog-capabilities.json"),
    ("messages", "drone-capabilities.json"),
    ("messages", "pi-capabilities.json"),
    ("messages", "dog-observation.json"),
    ("messages", "drone-observation.json"),
    ("messages", "drone-vision-request.json"),
    ("messages", "drone-vision-decision.json"),
    ("messages", "ai-to-drone-proposal.json"),
    ("messages", "ground-to-drone-command.json"),
    ("messages", "drone-ack-accepted.json"),
    ("messages", "drone-ack-running.json"),
    ("messages", "drone-ack-completed.json"),
    ("messages", "pi-heartbeat.json"),
    ("ordered", "pi-rssi-window-after-motion.json"),
    ("messages", "dog-navigation-candidates.json"),
    ("messages", "ai-to-dog-proposal.json"),
    ("ordered", "ground-to-dog-command-after-motion.json"),
    ("messages", "dog-ack-accepted.json"),
    ("messages", "dog-ack-running.json"),
    ("messages", "dog-ack-completed.json"),
    ("messages", "dog-vision-request.json"),
    ("messages", "dog-vision-decision.json"),
    ("messages", "proximity-evidence.json"),
    ("messages", "event-demo_goal_reached.json"),
    ("messages", "ground-to-drone-land.json"),
    ("ordered", "drone-land-completed.json"),
)


class RehearsalError(Exception):
    def __init__(self, code: str, detail: str, *, recovery: bool = False) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.recovery = recovery


@dataclass(frozen=True)
class Play:
    trace: tuple[str, ...]
    violations: tuple[str, ...]
    goal: str
    landing: str
    journal: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class Outcome:
    status: str
    detail: str
    error_code: str | None
    recovery: bool
    trace: tuple[str, ...]
    report: Mapping[str, object]
    journal: tuple[Mapping[str, object], ...]


def fixture_root() -> Path:
    return repo_root() / "fixtures" / "ground" / "g32"


def load_case(io: IOPort, name: str) -> list[dict[str, object]]:
    if name == "catalog_mission":
        return _load_jsonl(io, fixture_root() / "catalog" / "example-events.jsonl")
    if name == "second_takeoff":
        return _load_documents(io, fixture_root() / "ordered" / "second-takeoff.json")
    return _load_playlist(io, _files_for(name))


def play(messages: list[dict[str, object]]) -> Play:
    state = _Player()
    for message in messages:
        state.consume(message)
    return state.finish()


def evaluate(name: str, seed: int, played: Play) -> Outcome:
    if name == "happy_path":
        return _when(
            played,
            seed,
            name,
            ok=played.trace == HAPPY_TRACE
            and not played.violations
            and played.goal == "reached"
            and played.landing == "verified",
            success_detail="happy_path",
            failure_detail="happy_path_mismatch",
        )
    if name == "unknown_landing":
        matched = (
            played.trace == UNKNOWN_TRACE
            and not played.violations
            and played.goal == "reached"
            and played.landing == "unverified"
        )
        detail = "goal_reached;landing_unverified" if matched else "unknown_landing_mismatch"
        return _failed(played, seed, name, "validation_failed", detail, recovery=matched)
    if name == "blocked_planner":
        matched = played.trace == BLOCKED_TRACE and "invented_candidate" not in played.violations
        if matched and "dog_step" not in played.trace:
            return _blocked(played, seed, name, "stopped_no_candidate")
        return _failed(played, seed, name, "validation_failed", "blocked_planner_mismatch")
    if name == "noisy_rssi":
        matched = played.trace == NOISY_TRACE and "dog_step" not in played.trace
        if matched:
            return _blocked(played, seed, name, "noisy_rssi_stop")
        return _failed(played, seed, name, "validation_failed", "noisy_rssi_mismatch")
    if name == "stale_frame":
        matched = played.trace == STALE_TRACE and "drone_step" not in played.trace
        detail = "stale_frame_dropped" if matched else "stale_frame_mismatch"
        return _failed(played, seed, name, "validation_failed", detail)
    if name == "uncontrolled_motion":
        matched = played.trace == UNCONTROLLED_TRACE and "random_search" not in played.trace
        return _when(
            played,
            seed,
            name,
            ok=matched,
            success_detail="supervised_or_stopped",
            failure_detail="uncontrolled_motion_mismatch",
        )
    if name == "catalog_mission":
        detail = "causal_order" if played.violations else "catalog_accepted"
        return _failed(
            played,
            seed,
            name,
            "validation_failed",
            detail,
            trace=("causal_order",) if played.violations else played.trace,
        )
    if name == "second_takeoff":
        matched = played.trace == SECOND_TRACE and "second_takeoff" in played.violations
        detail = "second_takeoff_rejected" if matched else "second_takeoff_mismatch"
        return _failed(played, seed, name, "unsafe_state", detail)
    raise RehearsalError("invalid_input", f"unknown rehearsal case {name}")


def command_exit(status: str) -> int:
    return 0 if status == "ok" else 1


def distinct_ids(seed: int) -> tuple[str, str]:
    return (f"rehearsal-a-seed{seed}", f"rehearsal-b-seed{seed}")


def overwrite_id(seed: int) -> str:
    return f"rehearsal-overwrite-seed{seed}"


def _files_for(name: str) -> tuple[tuple[str, str], ...]:
    goal = _HAPPY_FILES.index(("messages", "event-demo_goal_reached.json"))
    window = _HAPPY_FILES.index(("ordered", "pi-rssi-window-after-motion.json"))
    completed = _HAPPY_FILES.index(("messages", "drone-ack-completed.json"))
    if name == "happy_path":
        return _HAPPY_FILES
    if name == "unknown_landing":
        return _HAPPY_FILES[: goal + 1] + (
            ("messages", "ground-to-drone-land.json"),
            ("messages", "drone-landing-unknown.json"),
        )
    if name == "blocked_planner":
        return _HAPPY_FILES[: window + 1] + (("ordered", "dog-navigation-blocked.json"),)
    if name == "noisy_rssi":
        return _HAPPY_FILES[: completed + 1] + (("ordered", "pi-rssi-window-noisy.json"),)
    if name == "stale_frame":
        return (
            ("messages", "dog-capabilities.json"),
            ("messages", "drone-capabilities.json"),
            ("messages", "pi-capabilities.json"),
            ("ordered", "drone-observation-stale.json"),
        )
    if name == "uncontrolled_motion":
        return (
            ("messages", "dog-capabilities.json"),
            ("ordered", "drone-capabilities-uncontrolled.json"),
            ("messages", "pi-capabilities.json"),
        )
    raise RehearsalError("invalid_input", f"unknown rehearsal case {name}")


class _Player:
    def __init__(self) -> None:
        self.trace: list[str] = []
        self.violations: list[str] = []
        self.journal: list[dict[str, object]] = []
        self.roles: set[str] = set()
        self.capabilities_marked = False
        self.uncontrolled = False
        self.stop_motion = False
        self.hold_stable = False
        self.hold_epoch = 0
        self.current_epoch = 0
        self.pending_beacon = 0
        self.beacon_ready = False
        self.dog_stationary = False
        self.dog_moving = False
        self.drone_motion_open = False
        self.drone_motion_completed = False
        self.issued: dict[str, str] = {}
        self.unresolved_takeoff = False
        self.takeoffs = 0
        self.requests: dict[str, str] = {}
        self.drone_frame = ""
        self.dog_frame = ""
        self.track_id = ""
        self.safe_ids: set[str] = set()
        self.planner_blocked = False
        self.proximity_ok = False
        self.proximity_seen = False
        self.goal = "absent"
        self.landing = "absent"
        self.window_before_ready = False

    def consume(self, message: dict[str, object]) -> None:
        self._envelope(message)
        self._forbid_keys(message)
        self.journal.append(_correlation(message))
        kind = message.get("kind")
        payload = _object(message.get("payload"))
        source = message.get("source")
        destination = message.get("destination")
        if kind == "motion.proposal" and destination in {"dog", "drone"}:
            self._violation("model_json_to_device")
        if source == "vision" and destination in {"dog", "drone"}:
            self._violation("model_json_to_device")
        if kind == "capabilities.report":
            self._capabilities(payload)
        elif kind == "dog.observation":
            self._dog_observation(payload)
        elif kind == "drone.observation":
            self._drone_observation(message, payload)
        elif kind == "vision.request":
            self._vision_request(payload)
        elif kind == "vision.decision":
            self._vision_decision(payload)
        elif kind == "motion.proposal":
            self._proposal(payload)
        elif kind == "drone.command":
            self._drone_command(payload)
        elif kind == "dog.command":
            self._dog_command(payload)
        elif kind == "command.ack":
            self._ack(payload)
        elif kind == "rssi.window":
            self._window(payload)
        elif kind == "navigation.candidates":
            self._candidates(payload)
        elif kind == "proximity.evidence":
            self._proximity(payload)
        elif kind == "mission.event":
            self._event(payload)

    def finish(self) -> Play:
        return Play(
            trace=tuple(self.trace),
            violations=tuple(dict.fromkeys(self.violations)),
            goal=self.goal,
            landing=self.landing,
            journal=tuple(self.journal),
        )

    def _mark(self, name: str) -> None:
        if name not in self.trace:
            self.trace.append(name)

    def _violation(self, name: str) -> None:
        self.violations.append(name)

    def _envelope(self, message: dict[str, object]) -> None:
        if message.get("protocol_version") != "2.0-draft":
            self._violation("bad_envelope")
        if message.get("simulated") is not True:
            self._violation("simulated_required")
        for key in ("message_id", "mission_id", "epoch"):
            if message.get(key) in (None, ""):
                self._violation("missing_correlation")
        if message.get("mission_id") not in (None, MISSION_ID):
            self._violation("mission_mismatch")

    def _forbid_keys(self, value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in FORBIDDEN_KEYS:
                    self._violation("rssi_to_meters")
                self._forbid_keys(item)
        elif isinstance(value, list):
            for item in value:
                self._forbid_keys(item)

    def _capabilities(self, payload: dict[str, object]) -> None:
        role = payload.get("role")
        if isinstance(role, str):
            self.roles.add(role)
        features = payload.get("features")
        if role == "drone" and isinstance(features, dict):
            if features.get("controlled_motion") is False:
                self.uncontrolled = True
                self.stop_motion = True
        if not self.capabilities_marked and {"dog", "drone", "pi"} <= self.roles:
            self.capabilities_marked = True
            self._mark("capabilities")
            if self.uncontrolled:
                self._mark("supervised_stop")

    def _dog_observation(self, payload: dict[str, object]) -> None:
        self.dog_stationary = payload.get("stationary") is True and payload.get("standing") is True
        frame = payload.get("frame")
        if isinstance(frame, dict) and isinstance(frame.get("frame_id"), str):
            self.dog_frame = frame["frame_id"]

    def _drone_observation(self, message: dict[str, object], payload: dict[str, object]) -> None:
        frame = payload.get("frame")
        if isinstance(frame, dict) and _stale(message.get("sent_at"), frame.get("captured_at")):
            self._mark("stale_frame")
            self._violation("stale_frame")
            self.hold_stable = False
            return
        beacon = payload.get("beacon")
        if not isinstance(beacon, dict):
            return
        epoch = beacon.get("beacon_epoch")
        if (
            beacon.get("hold_state") == "stable"
            and isinstance(epoch, int)
            and not isinstance(epoch, bool)
        ):
            self.hold_stable = True
            self.hold_epoch = epoch
            if not self.beacon_ready:
                self.current_epoch = self.hold_epoch
            self._mark("stable_hold")
        if isinstance(frame, dict) and isinstance(frame.get("frame_id"), str):
            self.drone_frame = frame["frame_id"]

    def _vision_request(self, payload: dict[str, object]) -> None:
        request_id = payload.get("request_id")
        stage = payload.get("stage")
        if isinstance(request_id, str) and isinstance(stage, str):
            self.requests[request_id] = stage

    def _vision_decision(self, payload: dict[str, object]) -> None:
        request_id = payload.get("request_id")
        stage = self.requests.get(request_id) if isinstance(request_id, str) else None
        if payload.get("target_state") != "person_visible":
            return
        if stage == "drone_search" and payload.get("frame_id") == self.drone_frame:
            self._mark("drone_detection")
        if stage == "dog_acquire" and payload.get("suggested_action") == "switch_to_dog_vision":
            if payload.get("frame_id") == self.dog_frame and self._same_track(payload):
                self._mark("dog_camera_handoff")

    def _proposal(self, payload: dict[str, object]) -> None:
        track = payload.get("track_id")
        if isinstance(track, str) and track:
            self.track_id = track

    def _drone_command(self, payload: dict[str, object]) -> None:
        action = payload.get("action")
        command_id = payload.get("command_id")
        if isinstance(command_id, str):
            self.issued[command_id] = action if isinstance(action, str) else ""
        if payload.get("requested_height_m") is not None:
            self._violation("height_default")
        if action == "takeoff":
            self.takeoffs += 1
            if self.unresolved_takeoff or self.takeoffs > 1:
                self._violation("second_takeoff")
                self._mark("second_takeoff_rejected")
            return
        if action not in {"track_step", "search_step"}:
            return
        if self.stop_motion or self.uncontrolled:
            self._violation("uncontrolled_motion")
            return
        if self.window_before_ready:
            self._violation("window_before_epoch_advance")
        if not self.hold_stable:
            self._violation("motion_without_hold")
        if self.dog_moving or not self.dog_stationary:
            self._violation("dog_not_stopped")
        self._mark("drone_step")
        if self.dog_stationary and not self.dog_moving:
            self._mark("dog_stopped")
        self.drone_motion_open = True
        pending = payload.get("beacon_epoch")
        if isinstance(pending, int) and not isinstance(pending, bool):
            self.pending_beacon = pending

    def _dog_command(self, payload: dict[str, object]) -> None:
        action = payload.get("action")
        command_id = payload.get("command_id")
        if isinstance(command_id, str) and isinstance(action, str):
            self.issued[command_id] = action
        if action != "move_local":
            return
        if self.drone_motion_open or not self.drone_motion_completed:
            self._violation("dog_moved_during_drone")
        motion = payload.get("motion")
        candidate = motion.get("candidate_id") if isinstance(motion, dict) else None
        if self.planner_blocked or not isinstance(candidate, str) or candidate not in self.safe_ids:
            self._violation("invented_candidate")
        beacon = payload.get("beacon_epoch")
        if beacon != self.current_epoch or not self.beacon_ready:
            self._violation("stale_beacon")
        if "invented_candidate" not in self.violations and "stale_beacon" not in self.violations:
            self._mark("dog_step")
        self.dog_moving = True

    def _ack(self, payload: dict[str, object]) -> None:
        command_id = payload.get("command_id")
        if not isinstance(command_id, str) or command_id not in self.issued:
            self._violation("ack_without_command")
            return
        action = self.issued[command_id]
        state = payload.get("state")
        if action == "takeoff" and state == "unknown":
            self.unresolved_takeoff = True
            self._mark("takeoff_timeout")
        if action == "track_step" and state == "completed":
            self.drone_motion_open = False
            self.drone_motion_completed = True
            if self.pending_beacon > self.hold_epoch:
                self.current_epoch = self.pending_beacon
                self.beacon_ready = True
                self.hold_stable = False
                self._mark("beacon_epoch")
        if action == "land" and state == "completed":
            if payload.get("verified") is True and payload.get("observed_motion") == "grounded":
                self.landing = "verified"
                self._mark("landing")
        if action == "land" and (
            state == "unknown" or payload.get("reason_code") == "landing_not_verified"
        ):
            self.landing = "unverified"
            self._mark("landing_unverified")

    def _window(self, payload: dict[str, object]) -> None:
        if payload.get("median_rssi_dbm") == 0:
            self._violation("zero_dbm_sentinel")
        samples = payload.get("samples")
        if isinstance(samples, list) and not samples and payload.get("median_rssi_dbm") == 0:
            self._violation("zero_dbm_sentinel")
        if not self.beacon_ready:
            self.window_before_ready = True
            self._violation("window_before_epoch_advance")
            return
        if payload.get("quality") != "valid":
            self._mark("noisy_rssi")
            self._mark("dog_stop")
            return
        if payload.get("beacon_epoch") != self.current_epoch:
            self._violation("stale_beacon_window")
            return
        self._mark("pi_window")

    def _candidates(self, payload: dict[str, object]) -> None:
        candidates = payload.get("candidates")
        safe: set[str] = set()
        if isinstance(candidates, list):
            for item in candidates:
                if isinstance(item, dict) and item.get("safe") is True:
                    ident = item.get("candidate_id")
                    if isinstance(ident, str):
                        safe.add(ident)
        blocked = payload.get("blocked") is True or not safe
        self.safe_ids = set() if blocked else safe
        self.planner_blocked = blocked
        if blocked:
            self._mark("dog_stop")

    def _proximity(self, payload: dict[str, object]) -> None:
        self.proximity_seen = True
        dog = payload.get("dog")
        drone = payload.get("drone")
        thresholds = payload.get("thresholds")
        if not isinstance(dog, dict) or not isinstance(drone, dict):
            return
        if not isinstance(thresholds, dict):
            return
        dog_range = dog.get("range_m")
        offset = drone.get("horizontal_offset_m")
        dog_max = thresholds.get("dog_range_max_m")
        drone_max = thresholds.get("drone_horizontal_max_m")
        if (
            _number(dog_range)
            and _number(offset)
            and _number(dog_max)
            and _number(drone_max)
            and dog.get("association_valid") is True
            and dog.get("stationary") is True
            and payload.get("operator_confirmed") is True
            and payload.get("track_id") == self.track_id
            and float(cast(float, dog_range)) <= float(cast(float, dog_max))
            and float(cast(float, offset)) <= float(cast(float, drone_max))
        ):
            self.proximity_ok = True

    def _event(self, payload: dict[str, object]) -> None:
        if payload.get("event") != "demo_goal_reached":
            return
        if self.proximity_ok:
            self.goal = "reached"
            self._mark("proximity_goal")
        elif self.proximity_seen:
            self.goal = "unresolved"

    def _same_track(self, payload: dict[str, object]) -> bool:
        detections = payload.get("detections")
        if not isinstance(detections, list):
            return False
        for item in detections:
            if isinstance(item, dict) and item.get("track_id") == self.track_id and self.track_id:
                return True
        return False


def _when(
    played: Play,
    seed: int,
    name: str,
    *,
    ok: bool,
    success_detail: str,
    failure_detail: str,
) -> Outcome:
    if ok:
        return Outcome(
            "ok",
            success_detail,
            None,
            False,
            played.trace,
            _report(played, seed, name, "ok", success_detail),
            played.journal,
        )
    return _failed(played, seed, name, "validation_failed", failure_detail)


def _failed(
    played: Play,
    seed: int,
    name: str,
    code: str,
    detail: str,
    *,
    recovery: bool = False,
    trace: tuple[str, ...] | None = None,
) -> Outcome:
    shown = played.trace if trace is None else trace
    return Outcome(
        "failed",
        detail,
        code,
        recovery,
        shown,
        _report(played, seed, name, "failed", detail),
        played.journal,
    )


def _blocked(played: Play, seed: int, name: str, detail: str) -> Outcome:
    return Outcome(
        "blocked",
        detail,
        "rejected",
        False,
        played.trace,
        _report(played, seed, name, "blocked", detail),
        played.journal,
    )


def _report(played: Play, seed: int, name: str, status: str, detail: str) -> dict[str, object]:
    rows = (
        {"name": "goal", "ok": played.goal == "reached"},
        {"name": "landing", "ok": played.landing == "verified"},
        {"name": "no_invented_candidate", "ok": "invented_candidate" not in played.violations},
        {"name": "no_model_json_to_device", "ok": "model_json_to_device" not in played.violations},
        {"name": "no_rssi_meters", "ok": "rssi_to_meters" not in played.violations},
        {"name": "no_second_takeoff", "ok": "second_takeoff" not in played.violations},
        {
            "name": "dog_stopped_during_drone",
            "ok": "dog_stopped" in played.trace and "random_search" not in played.trace,
        },
    )
    return {
        "label": "software simulation",
        "evidence": "simulated",
        "physical_acceptance": False,
        "slot": SLOT,
        "schema_version": SCHEMA,
        "seed": seed,
        "scenario": name,
        "status": status,
        "detail": detail,
        "passed": status == "ok",
        "goal_status": played.goal,
        "landing_status": played.landing,
        "trace": list(played.trace),
        "violations": list(played.violations),
        "assertions": [dict(item) for item in rows],
        "live_logs": "artifacts/<mission_id>/events.jsonl",
        "runbook": "demo/script.md",
    }


def _correlation(message: dict[str, object]) -> dict[str, object]:
    payload = _object(message.get("payload"))
    record: dict[str, object] = {
        "message_id": message.get("message_id"),
        "mission_id": message.get("mission_id"),
        "epoch": message.get("epoch"),
        "kind": message.get("kind"),
        "simulated": True,
    }
    for key in ("command_id", "request_id", "track_id", "beacon_epoch", "frame_id", "map_epoch"):
        if key in payload:
            record[key] = payload[key]
    frame = payload.get("frame")
    if isinstance(frame, dict):
        if "frame_id" in frame:
            record["frame_id"] = frame["frame_id"]
        if "camera_epoch" in frame:
            record["camera_epoch"] = frame["camera_epoch"]
    beacon = payload.get("beacon")
    if isinstance(beacon, dict) and "beacon_epoch" in beacon:
        record["beacon_epoch"] = beacon["beacon_epoch"]
    motion = payload.get("motion")
    if isinstance(motion, dict) and "map_epoch" in motion:
        record["map_epoch"] = motion["map_epoch"]
    if "evidence_frame_id" in payload and "frame_id" not in record:
        record["frame_id"] = payload["evidence_frame_id"]
    details = payload.get("details")
    if isinstance(details, dict) and "track_id" in details and "track_id" not in record:
        record["track_id"] = details["track_id"]
    return record


def _load_playlist(io: IOPort, files: tuple[tuple[str, str], ...]) -> list[dict[str, object]]:
    loaded: list[dict[str, object]] = []
    for folder, name in files:
        loaded.extend(_load_documents(io, fixture_root() / folder / name))
    return loaded


def _load_documents(io: IOPort, path: Path) -> list[dict[str, object]]:
    try:
        text = io.read_text(path)
    except OSError as exc:
        raise RehearsalError("io_fault", "fixture could not be read", recovery=True) from exc
    return _messages_from_text(text)


def _load_jsonl(io: IOPort, path: Path) -> list[dict[str, object]]:
    try:
        text = io.read_text(path)
    except OSError as exc:
        raise RehearsalError("io_fault", "catalog could not be read", recovery=True) from exc
    messages: list[dict[str, object]] = []
    for line in text.splitlines():
        if line.strip():
            messages.extend(_messages_from_text(line))
    return messages


def _messages_from_text(text: str) -> list[dict[str, object]]:
    try:
        loaded = json.loads(text)
    except ValueError as exc:
        raise RehearsalError("invalid_input", "fixture is not json") from exc
    if isinstance(loaded, list):
        return [_as_object(item) for item in loaded]
    return [_as_object(loaded)]


def _as_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RehearsalError("invalid_input", "fixture message must be an object")
    return cast(dict[str, object], value)


def _object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _stale(sent_at: object, captured_at: object) -> bool:
    sent = _time(sent_at)
    captured = _time(captured_at)
    if sent is None or captured is None:
        return True
    return (sent - captured).total_seconds() > EVIDENCE_AGE_S


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
