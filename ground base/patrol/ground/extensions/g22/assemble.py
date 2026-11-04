"""Build homing inputs from the copied contract examples. This does not choose a step."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g22.policy import InvalidHoming
from patrol.ground.kernel.paths import repo_root

_NOW = "2026-11-04T13:00:10.000Z"
_BSSID = "02:00:00:00:00:01"


def case_from_fixture(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g22" / "cases" / f"{name}.json"
    if not path.is_file():
        raise InvalidHoming(f"unknown homing case {name}")
    raw = _read(path)
    if "homing" in raw:
        homing = raw["homing"]
        if not isinstance(homing, dict):
            raise InvalidHoming("homing fixture must be an object")
        return {str(key): value for key, value in homing.items()}
    return assemble(raw)


def assemble(spec: Mapping[str, object]) -> dict[str, object]:
    plan = spec.get("plan")
    if not isinstance(plan, str) or not plan:
        raise InvalidHoming("plan is required")
    examples = repo_root() / "fixtures" / "ground" / "g22" / "examples"
    window = _read(examples / "pi-rssi-window.json")
    navigation = _read(examples / "dog-navigation-candidates.json")
    motion = spec["dog_motion_allowed"] if "dog_motion_allowed" in spec else True
    hysteresis = spec["hysteresis_db"] if "hysteresis_db" in spec else 2
    steps = spec["steps_taken"] if "steps_taken" in spec else 0
    limit = spec["limit"] if "limit" in spec else 3
    hold = spec["hold_state"] if "hold_state" in spec else "stable"
    beacon_epoch = spec["beacon_epoch"] if "beacon_epoch" in spec else 3
    return {
        "dog_motion_allowed": motion,
        "hysteresis_db": hysteresis,
        "search_budget": {"steps_taken": steps, "limit": limit},
        "beacon": {
            "beacon_id": "tello-demo-01",
            "bssid": _BSSID,
            "beacon_epoch": beacon_epoch,
            "hold_state": hold,
        },
        "active_command_id": spec.get("active_command_id"),
        "previous_candidate_id": spec.get("previous_candidate_id"),
        "track_id": "target-001",
        "now": spec.get("now", _NOW),
        "dog_vision": _vision(spec.get("dog_vision")),
        "windows": _windows(plan, window),
        "candidates": _navigation(spec, navigation),
    }


def _windows(plan: str, example: dict[str, object]) -> list[object]:
    if plan == "example_only":
        return [example]
    if plan == "sentinel":
        return [_sentinel(example)]
    if plan == "strong_empty":
        return [
            _shifted(example, "msg-pi-rssi-strong-a", -48, [-50, -48, -46], 0.0, "rssi-s", 0),
            _shifted(example, "msg-pi-rssi-strong-b", -40, [-42, -40, -38], 0.3, "rssi-s", 3),
        ]
    second = _second(plan, example)
    return [example, second]


def _second(plan: str, example: dict[str, object]) -> dict[str, object]:
    if plan == "improving_forward":
        return _later(example, -54, [-56, -54, -52])
    if plan == "flat":
        return _later(example, -59.5, [-60.5, -59.5, -58.5])
    if plan == "noisy":
        window = _later(example, -54, [-56, -54, -52])
        _payload(window)["quality"] = "noisy"
        return window
    if plan == "stale":
        window = _later(example, -54, [-56, -54, -52])
        _payload(window)["quality"] = "stale"
        return window
    if plan == "unavailable":
        return _unavailable(example)
    if plan == "epoch_shift":
        window = _later(example, -54, [-56, -54, -52])
        _payload(window)["beacon_epoch"] = 4
        return window
    if plan == "bssid_shift":
        window = _later(example, -54, [-56, -54, -52])
        _payload(window)["bssid"] = "02:00:00:00:00:99"
        return window
    if plan == "same_pose":
        return _later(example, -50, [-52, -50, -48], 0.0)
    if plan == "weaker_forward":
        return _later(example, -70, [-68, -70, -72])
    if plan == "map_split":
        window = _later(example, -54, [-56, -54, -52])
        for sample in _samples(window):
            pose = sample.get("pose")
            if isinstance(pose, dict):
                pose["map_epoch"] = 2
        return window
    raise InvalidHoming(f"unknown window plan {plan}")


def _later(
    example: dict[str, object],
    median: float,
    readings: list[float],
    x0: float = 0.3,
) -> dict[str, object]:
    return _shifted(example, "msg-pi-rssi-window-later", median, readings, x0, "rssi-", 3)


def _shifted(
    example: dict[str, object],
    message_id: str,
    median: float,
    readings: list[float],
    x0: float,
    prefix: str,
    start: int,
) -> dict[str, object]:
    window = json.loads(json.dumps(example))
    if not isinstance(window, dict):
        raise InvalidHoming("window copy failed")
    window["message_id"] = message_id
    window["seq"] = 4
    payload = _payload(window)
    payload["median_rssi_dbm"] = median
    payload["spread_db"] = 4
    payload["window_start"] = "2026-11-04T13:00:10.600Z"
    payload["window_end"] = "2026-11-04T13:00:10.800Z"
    samples = _samples(window)
    for index, sample in enumerate(samples):
        sample["sample_id"] = f"{prefix}{start + index}"
        sample["rssi_dbm"] = readings[index]
        sample["captured_at"] = f"2026-11-04T13:00:10.{6 + index}00Z"
        pose = sample.get("pose")
        if isinstance(pose, dict):
            pose["x_m"] = x0 + (index * 0.1)
            pose["observed_at"] = sample["captured_at"]
    return window


def _unavailable(example: dict[str, object]) -> dict[str, object]:
    window = json.loads(json.dumps(example))
    if not isinstance(window, dict):
        raise InvalidHoming("window copy failed")
    window["message_id"] = "msg-pi-rssi-window-none"
    payload = _payload(window)
    payload["quality"] = "unavailable"
    payload["samples"] = []
    payload["median_rssi_dbm"] = None
    payload["spread_db"] = None
    payload["window_end"] = "2026-11-04T13:00:10.800Z"
    return window


def _sentinel(example: dict[str, object]) -> dict[str, object]:
    window = json.loads(json.dumps(example))
    if not isinstance(window, dict):
        raise InvalidHoming("window copy failed")
    payload = _payload(window)
    payload["quality"] = "valid"
    payload["samples"] = []
    payload["median_rssi_dbm"] = 0
    return window


def _navigation(spec: Mapping[str, object], example: dict[str, object]) -> dict[str, object]:
    document = json.loads(json.dumps(example))
    if not isinstance(document, dict):
        raise InvalidHoming("candidate copy failed")
    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise InvalidHoming("candidate payload is missing")
    mode = spec.get("candidates", "forward")
    if not isinstance(mode, str):
        raise InvalidHoming("candidates mode must be a string")
    payload["candidates"] = _candidate_rows(payload, mode)
    if "blocked" in spec:
        payload["blocked"] = spec["blocked"]
    return document


def _candidate_rows(payload: dict[str, object], mode: str) -> list[object]:
    raw = payload.get("candidates")
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        raise InvalidHoming("example candidate is missing")
    forward = raw[0]
    if mode == "forward":
        return [forward]
    if mode == "empty":
        return []
    if mode == "expired":
        copy = json.loads(json.dumps(forward))
        copy["valid_until"] = "2026-11-04T13:00:09.000Z"
        return [copy]
    if mode == "ranged":
        copy = json.loads(json.dumps(forward))
        copy["range_m"] = 1.2
        return [copy]
    if mode == "left":
        return [_clone(forward, "candidate-left", -0.05)]
    if mode == "back":
        return [_clone(forward, "candidate-back", -0.05)]
    if mode == "both":
        return [forward, _clone(forward, "candidate-back", -0.05)]
    if mode == "forward_and_left":
        return [forward, _clone(forward, "candidate-left", -0.05)]
    if mode == "unsafe":
        copy = json.loads(json.dumps(forward))
        copy["safe"] = False
        return [copy]
    if mode == "wrong_frame":
        copy = json.loads(json.dumps(forward))
        copy["frame_id"] = "museum/map"
        return [copy]
    if mode == "tie":
        return [
            _clone(forward, "candidate-b", 0.05),
            _clone(forward, "candidate-a", 0.05),
        ]
    raise InvalidHoming(f"unknown candidate mode {mode}")


def _clone(source: dict[str, object], candidate_id: str, delta_x: float) -> dict[str, object]:
    copy = json.loads(json.dumps(source))
    if not isinstance(copy, dict):
        raise InvalidHoming("candidate copy failed")
    copy["candidate_id"] = candidate_id
    copy["delta_x_m"] = delta_x
    return copy


def _vision(mode: object) -> dict[str, object] | None:
    if mode is None:
        return None
    if mode == "acquired":
        detections: list[object] = [
            {"label": "person", "track_id": "target-001", "confidence": 0.91}
        ]
        action = "switch_to_dog_vision"
        state = "person_visible"
    elif mode == "ambiguous":
        detections = [
            {"label": "person", "track_id": "target-001", "confidence": 0.8},
            {"label": "person", "track_id": "target-002", "confidence": 0.7},
        ]
        action = "review"
        state = "person_visible"
    else:
        raise InvalidHoming("dog_vision mode is not recognized")
    return {
        "protocol_version": "2.0-draft",
        "message_id": "msg-dog-vision-decision",
        "mission_id": "demo-20261104-001",
        "epoch": 1,
        "kind": "vision.decision",
        "simulated": True,
        "payload": {
            "request_id": "vision-dog-001",
            "target_state": state,
            "suggested_action": action,
            "detections": detections,
        },
    }


def _payload(window: dict[str, object]) -> dict[str, object]:
    payload = window.get("payload")
    if not isinstance(payload, dict):
        raise InvalidHoming("window payload is missing")
    return payload


def _samples(window: dict[str, object]) -> list[dict[str, object]]:
    samples = _payload(window).get("samples")
    if not isinstance(samples, list):
        raise InvalidHoming("samples are missing")
    typed: list[dict[str, object]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise InvalidHoming("sample is not an object")
        typed.append(sample)
    return typed


def _read(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InvalidHoming(f"could not read {path.name}") from exc
    if not isinstance(raw, dict):
        raise InvalidHoming(f"{path.name} must be an object")
    return raw
