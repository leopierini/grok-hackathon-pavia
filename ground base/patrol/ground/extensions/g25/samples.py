"""Fixture payloads for dog-camera handoff cases. Expected results live in scenarios."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.paths import repo_root

CASE_IDS: tuple[str, ...] = (
    "two_fresh_hits",
    "one_hit",
    "not_visible_resets",
    "drone_frame",
    "second_track",
    "stale_frame",
    "empty_detections",
    "multiple_strangers",
    "unlabeled_person",
    "epoch_mismatch",
    "suggestion_ignored",
    "threshold_three",
    "drone_between_hits",
    "homing_disabled",
    "example_contract",
    "rssi_records_kept",
    "no_goal_no_command",
    "cancelled",
)


def build(case_id: str) -> dict[str, object]:
    if case_id not in CASE_IDS:
        raise fault("invalid_input", f"unknown dog-acquire case {case_id}")
    if case_id == "cancelled":
        return _with_rssi(_history())
    if case_id in {"two_fresh_hits", "rssi_records_kept", "no_goal_no_command"}:
        return _with_rssi(_history())
    if case_id in {"one_hit", "suggestion_ignored"}:
        return _only_first(_history())
    if case_id == "not_visible_resets":
        return _not_visible_between(_history())
    if case_id == "drone_frame":
        return _drone()
    if case_id == "second_track":
        return _retarget(_only_first(_history()), "target-999")
    if case_id == "stale_frame":
        payload = _only_first(_history())
        payload["observed_at"] = "2026-11-04T13:00:14.500Z"
        return payload
    if case_id == "empty_detections":
        return _clear_detections(_only_first(_history()))
    if case_id == "multiple_strangers":
        return _add_stranger(_only_first(_history()))
    if case_id == "unlabeled_person":
        return _retarget(_only_first(_history()), None)
    if case_id == "epoch_mismatch":
        payload = _only_first(_history())
        payload["camera_epoch"] = 2
        return payload
    if case_id == "threshold_three":
        payload = _history()
        payload["consecutive_hit_threshold"] = 3
        return payload
    if case_id == "drone_between_hits":
        return _drone_between(_history())
    if case_id == "homing_disabled":
        payload = _clear_detections(_only_first(_history()))
        decisions = _as_list(payload["decisions"])
        body = _as_map(_as_map(decisions[0])["payload"])
        body["target_state"] = "not_visible"
        payload["homing_allowed"] = False
        return payload
    if case_id == "example_contract":
        return _example()
    raise fault("invalid_input", f"unknown dog-acquire case {case_id}")


def fixture(name: str) -> dict[str, object]:
    return _load(name)


def _history() -> dict[str, object]:
    return _load("history.json")


def _example() -> dict[str, object]:
    decision = _load("dog-vision-decision.json")
    request = _load("dog-vision-request.json")
    frame = _as_map(_as_map(request["payload"])["frame"])
    return {
        "track_id": "target-001",
        "camera_epoch": 1,
        "observed_at": "2026-11-04T13:00:11.000Z",
        "frames": [dict(frame)],
        "decisions": [decision],
        "requests": [request],
    }


def _with_rssi(payload: dict[str, object]) -> dict[str, object]:
    payload["rssi_records"] = [_load("pi-rssi-window.json")]
    return payload


def _only_first(payload: dict[str, object]) -> dict[str, object]:
    decisions = _as_list(payload["decisions"])
    frames = _as_list(payload["frames"])
    payload["decisions"] = [decisions[0]]
    payload["frames"] = [frames[0]]
    return payload


def _not_visible_between(payload: dict[str, object]) -> dict[str, object]:
    decisions = _as_list(payload["decisions"])
    frames = _as_list(payload["frames"])
    gap_frame = dict(_as_map(frames[0]))
    gap_frame["frame_id"] = "dog-front-gap"
    gap_frame["captured_at"] = "2026-11-04T13:00:10.500Z"
    gap = json.loads(json.dumps(decisions[0]))
    if not isinstance(gap, dict):
        raise fault("invalid_input", "gap decision could not be copied")
    gap_map = _as_string_dict(gap)
    gap_map["message_id"] = "msg-dog-vision-decision-gap"
    gap_map["seq"] = 4
    body = _as_map(gap_map["payload"])
    body["request_id"] = "vision-dog-gap"
    body["frame_id"] = "dog-front-gap"
    body["frame_captured_at"] = "2026-11-04T13:00:10.500Z"
    body["target_state"] = "not_visible"
    body["detections"] = []
    body["suggested_action"] = "stop"
    body["reason"] = "The staged person is not visible in this dog frame."
    payload["frames"] = [frames[0], gap_frame, frames[1]]
    payload["decisions"] = [decisions[0], gap_map, decisions[1]]
    return payload


def _drone() -> dict[str, object]:
    decision = _load("drone-vision-decision.json")
    request = _load("drone-vision-request.json")
    frame = _as_map(_as_map(request["payload"])["frame"])
    return {
        "track_id": "target-001",
        "camera_epoch": 1,
        "observed_at": "2026-11-04T13:00:11.000Z",
        "frames": [dict(frame)],
        "decisions": [decision],
    }


def _drone_between(payload: dict[str, object]) -> dict[str, object]:
    drone = _drone()
    decisions = _as_list(payload["decisions"])
    frames = _as_list(payload["frames"])
    payload["decisions"] = [decisions[0], _as_list(drone["decisions"])[0], decisions[1]]
    payload["frames"] = [frames[0], _as_list(drone["frames"])[0], frames[1]]
    return payload


def _retarget(payload: dict[str, object], track_id: str | None) -> dict[str, object]:
    body = _as_map(_as_map(_as_list(payload["decisions"])[0])["payload"])
    detection = _as_map(_as_list(body["detections"])[0])
    detection["track_id"] = track_id
    return payload


def _clear_detections(payload: dict[str, object]) -> dict[str, object]:
    body = _as_map(_as_map(_as_list(payload["decisions"])[0])["payload"])
    body["detections"] = []
    return payload


def _add_stranger(payload: dict[str, object]) -> dict[str, object]:
    body = _as_map(_as_map(_as_list(payload["decisions"])[0])["payload"])
    detections = _as_list(body["detections"])
    stranger = json.loads(json.dumps(detections[0]))
    if not isinstance(stranger, dict):
        raise fault("invalid_input", "detection could not be copied")
    copied = _as_string_dict(stranger)
    copied["track_id"] = "target-002"
    detections.append(copied)
    return payload


def _load(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g25" / name
    raw = json.loads(path.read_text(encoding="utf-8"))
    cloned = json.loads(json.dumps(raw))
    if not isinstance(cloned, dict):
        raise fault("invalid_input", f"{name} must be an object")
    return _as_string_dict(cloned)


def _as_string_dict(value: Mapping[object, object]) -> dict[str, object]:
    found: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise fault("invalid_input", "fixture keys must be strings")
        found[key] = _revive(item)
    return found


def _revive(value: object) -> object:
    if isinstance(value, dict):
        return _as_string_dict(cast(Mapping[object, object], value))
    if isinstance(value, list):
        return [_revive(item) for item in value]
    return value


def _as_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise fault("invalid_input", "fixture value must be an object")
    return cast(dict[str, object], value)


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise fault("invalid_input", "fixture value must be a list")
    return value
