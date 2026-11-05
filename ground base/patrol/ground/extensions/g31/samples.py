"""Scripted journals built from copied contract examples.

Times are milliseconds on the ground monotonic domain. The copied envelopes
keep their message ids. Timing fields are added here because the examples share
a few wall-clock stamps and are not one mission.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

MISSION = "demo-20261104-001"
DOMAIN = "ground"

CLOCK: dict[str, object] = {
    "domain": DOMAIN,
    "quality": "manual_simulation",
    "utc_error_bound_ms": 15,
    "utc_pairs_allowed": True,
}

TARGET_MS = 2000
HOLD_MS = 3500
ACTIVATION_MS = 4000
DOG_CAMERA_MS = 5180
PROXIMITY_MS = 7500
GOAL_MS = 8000
LANDING_MS = 11000
DRONE_REQUEST_MS = 1000
DRONE_FRAME_MS = 700
DRONE_DECISION_MS = 1200
DOG_REQUEST_MS = 5000
DOG_FRAME_MS = 4900
DOG_ISSUE_MS = 4100
DOG_ACCEPT_MS = 4220
DOG_RUN_MS = 4350
DOG_COMPLETE_MS = 4550
LAND_ISSUE_MS = 10500
LAND_ACCEPT_MS = 10600
LAND_RUN_MS = 10700


def examples_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "fixtures" / "ground" / "g31" / "examples"


def load_example(name: str) -> dict[str, object]:
    raw_obj: object = json.loads((examples_dir() / name).read_text(encoding="utf-8"))
    if not isinstance(raw_obj, dict):
        raise RuntimeError(name)
    loaded: dict[str, object] = {}
    for key, value in raw_obj.items():
        if not isinstance(key, str):
            raise RuntimeError(name)
        loaded[key] = value
    return loaded


def evaluation_manifest() -> dict[str, object]:
    path = examples_dir().parent / "evaluation.json"
    return load_json(path)


def full_journal() -> list[dict[str, object]]:
    rows = [
        _timed("drone-vision-request.json", DRONE_REQUEST_MS, frame_monotonic_ms=DRONE_FRAME_MS),
        _drop(1050, "msg-frame-dropped-001", "drone-downward-stale"),
        _timed("drone-vision-decision.json", DRONE_DECISION_MS),
        _timed("event-drone_target_acquired.json", TARGET_MS),
        _timed("drone-observation.json", HOLD_MS),
        _timed("event-dog_dispatched.json", ACTIVATION_MS),
        _timed("ground-to-dog-command.json", DOG_ISSUE_MS),
        _timed("dog-ack-accepted.json", DOG_ACCEPT_MS),
        _timed("dog-ack-running.json", DOG_RUN_MS),
        _timed("dog-ack-completed.json", DOG_COMPLETE_MS),
        _timed("dog-vision-request.json", DOG_REQUEST_MS, frame_monotonic_ms=DOG_FRAME_MS),
        _timed("dog-vision-decision.json", DOG_CAMERA_MS),
        _timed("pi-rssi-window.json", 5500),
        _rssi_noisy(),
        _blocked_candidates(),
        _note(6400, "msg-no-progress-001", "no_progress_stop", "safety"),
        _beacon_reset(),
        _timed("proximity-evidence.json", PROXIMITY_MS),
        _timed("event-demo_goal_reached.json", GOAL_MS),
        _timed("ground-to-drone-land.json", LAND_ISSUE_MS),
        _land_ack(
            "drone-ack-accepted.json", LAND_ACCEPT_MS, "msg-land-accepted", "accepted", False
        ),
        _land_ack("drone-ack-running.json", LAND_RUN_MS, "msg-land-running", "running", False),
        _land_ack("drone-ack-completed.json", LANDING_MS, "msg-land-completed", "completed", True),
    ]
    for index, row in enumerate(rows, start=1):
        row["seq"] = index
    return rows


def without_landing() -> list[dict[str, object]]:
    kept = [
        row
        for row in full_journal()
        if row.get("message_id")
        not in {"msg-land-accepted", "msg-land-running", "msg-land-completed"}
    ]
    kept.append(_timed("event-landing_unverified.json", LANDING_MS))
    for index, row in enumerate(kept, start=1):
        row["seq"] = index
    return kept


def without_dog_camera() -> list[dict[str, object]]:
    kept = [row for row in full_journal() if row.get("message_id") != "msg-dog-vision-decision"]
    for index, row in enumerate(kept, start=1):
        row["seq"] = index
    return kept


def with_extra_drop() -> list[dict[str, object]]:
    rows = full_journal()
    rows.append(_drop(1060, "msg-frame-dropped-002", "drone-downward-stale-2"))
    for index, row in enumerate(rows, start=1):
        row["seq"] = index
    return rows


def empty_journal() -> list[dict[str, object]]:
    return []


def mismatched_clocks() -> list[dict[str, object]]:
    rows = full_journal()
    for row in rows:
        if row.get("message_id") == "msg-event-drone_target_acquired":
            row["clock_domain"] = "drone_monotonic"
    return rows


def beacon_pair() -> list[dict[str, object]]:
    rows = [
        _timed("drone-observation.json", HOLD_MS),
        _beacon_reset(),
    ]
    for index, row in enumerate(rows, start=1):
        row["seq"] = index
    return rows


def request_payload(journal: list[dict[str, object]], **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "journal": journal,
        "mission_start_monotonic": 0,
        "clock": dict(CLOCK),
        "run_id": MISSION,
    }
    payload.update(extra)
    return payload


def _timed(
    name: str, monotonic_ms: int, *, frame_monotonic_ms: int | None = None
) -> dict[str, object]:
    message = load_example(name)
    record = _base(message, monotonic_ms)
    if frame_monotonic_ms is not None:
        record["frame_monotonic_ms"] = frame_monotonic_ms
    return record


def _base(message: dict[str, object], monotonic_ms: int) -> dict[str, object]:
    payload = message.get("payload")
    kind = message.get("kind")
    event = kind
    if isinstance(payload, dict):
        named = payload.get("event")
        if isinstance(named, str) and named:
            event = named
    record: dict[str, object] = {
        "schema_version": "ground-log-v2-proposed",
        "category": _category(message),
        "message_id": message.get("message_id"),
        "mission_id": message.get("mission_id"),
        "epoch": message.get("epoch"),
        "source": message.get("source"),
        "destination": message.get("destination"),
        "kind": kind,
        "event": event,
        "sent_at": message.get("sent_at"),
        "correlation_id": message.get("correlation_id"),
        "simulated": message.get("simulated"),
        "monotonic_ms": monotonic_ms,
        "clock_domain": DOMAIN,
        "payload": payload,
        "logs_requirements_status": "proposed_pending_team",
    }
    return record


def _category(message: dict[str, object]) -> str:
    kind = message.get("kind")
    event = ""
    payload = message.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("event"), str):
        event = payload["event"]
    if kind == "capabilities.report":
        return "session"
    if kind in {"vision.request", "vision.decision"}:
        return "vision"
    if kind in {"dog.command", "drone.command"}:
        return "command"
    if kind == "command.ack":
        return "acknowledgement"
    if kind in {"proximity.evidence"} or event in {
        "demo_goal_reached",
        "landing_unverified",
        "drone_target_acquired",
        "dog_dispatched",
    }:
        return "completion"
    if event in {"no_progress_stop"}:
        return "safety"
    return "observation"


def _drop(monotonic_ms: int, message_id: str, frame_id: str) -> dict[str, object]:
    return {
        "schema_version": "ground-log-v2-proposed",
        "category": "observation",
        "message_id": message_id,
        "mission_id": MISSION,
        "epoch": 1,
        "source": "ground",
        "destination": "ground",
        "kind": "scheduler.note",
        "event": "frame_dropped",
        "reason": "stale",
        "frame_id": frame_id,
        "sent_at": "2026-11-04T13:00:10.050Z",
        "simulated": True,
        "monotonic_ms": monotonic_ms,
        "clock_domain": DOMAIN,
        "logs_requirements_status": "proposed_pending_team",
    }


def _note(monotonic_ms: int, message_id: str, event: str, category: str) -> dict[str, object]:
    return {
        "schema_version": "ground-log-v2-proposed",
        "category": category,
        "message_id": message_id,
        "mission_id": MISSION,
        "epoch": 1,
        "source": "ground",
        "destination": "all",
        "kind": "mission.event",
        "event": event,
        "sent_at": "2026-11-04T13:00:10.640Z",
        "simulated": True,
        "monotonic_ms": monotonic_ms,
        "clock_domain": DOMAIN,
        "logs_requirements_status": "proposed_pending_team",
    }


def _rssi_noisy() -> dict[str, object]:
    record = _timed("pi-rssi-window.json", 6000)
    record["message_id"] = "msg-pi-rssi-window-noisy"
    payload = _payload(record)
    payload["quality"] = "noisy"
    record["payload"] = payload
    return record


def _blocked_candidates() -> dict[str, object]:
    record = _timed("dog-navigation-candidates.json", 6200)
    record["message_id"] = "msg-dog-navigation-blocked"
    payload = _payload(record)
    payload["blocked"] = True
    payload["candidates"] = []
    payload["reason"] = "Synthetic empty candidate list."
    record["payload"] = payload
    return record


def _beacon_reset() -> dict[str, object]:
    record = _timed("drone-observation.json", 7000)
    record["message_id"] = "msg-drone-observation-epoch-4"
    record["event"] = "beacon_epoch_reset"
    payload = _payload(record)
    beacon = payload.get("beacon")
    if isinstance(beacon, dict):
        updated = dict(beacon)
        updated["beacon_epoch"] = 4
        payload["beacon"] = updated
    record["payload"] = payload
    return record


def _land_ack(
    name: str,
    monotonic_ms: int,
    message_id: str,
    state: str,
    verified: bool,
) -> dict[str, object]:
    record = _timed(name, monotonic_ms)
    record["message_id"] = message_id
    record["correlation_id"] = "msg-ground-to-drone-land"
    payload = _payload(record)
    payload["command_id"] = "cmd-drone-land-001"
    payload["state"] = state
    payload["verified"] = verified
    payload["reason_code"] = "ok"
    payload["observed_motion"] = "stationary" if verified else "unknown"
    payload["detail"] = "Synthetic land acknowledgement for the timing fixture."
    record["payload"] = payload
    return record


def _payload(record: dict[str, object]) -> dict[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return {}
    copied: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(key, str):
            copied[key] = value
    return copied


def load_json(path: Path) -> dict[str, object]:
    raw_obj: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_obj, dict):
        raise RuntimeError(path.name)
    return cast(dict[str, object], raw_obj)
