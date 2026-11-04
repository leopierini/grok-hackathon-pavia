"""Rank one safe dog candidate from comparable RSSI windows.

This module does not build a heading from signal strength, convert dBm to
meters, or emit a dog command. Task 23 is the only later step that may do that.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

SLOT = "feature.v2_rssi_homing"
SCHEMA = "ground-task-v2"
CANDIDATE_FRAME = "dog/base_link"
DISPATCH_EVENT = "dog_dispatched"
DISPATCH_PHASE = "rssi_homing"
DISPATCH_LOG_STATUS = "proposed_pending_team"
_QUALITIES = frozenset({"valid", "noisy", "stale", "unavailable"})
_HOLDS = frozenset({"stable", "moving", "unknown"})
_MIN_DBM = -150.0
_MAX_DBM = 0.0
_SPACE = 1e-6
_DOT = 1e-9


class InvalidHoming(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    candidate_id: str | None
    beacon_epoch: int | None
    map_epoch: int | None
    quality: str | None
    sample_ids: tuple[str, ...]
    window_ids: tuple[str, ...]
    blocked: bool
    mission_id: str
    epoch: int | None
    track_id: str | None
    command_id: str | None

    def detail(self) -> str:
        if self.action == "select" and self.candidate_id:
            return f"select:{self.candidate_id}"
        return f"{self.action}:{self.reason}"

    def trace(self) -> tuple[str, ...]:
        return (
            f"action:{self.action}",
            f"reason:{self.reason}",
            f"candidate_id:{self.candidate_id or ''}",
            f"beacon_epoch:{'' if self.beacon_epoch is None else self.beacon_epoch}",
            f"map_epoch:{'' if self.map_epoch is None else self.map_epoch}",
            f"quality:{self.quality or ''}",
            "sample_ids:" + ",".join(self.sample_ids),
            "window_ids:" + ",".join(self.window_ids),
            f"blocked:{str(self.blocked).lower()}",
            "no_range_m",
            "no_dog_command",
        )


@dataclass(frozen=True)
class _Sample:
    sample_id: str
    x_m: float
    y_m: float
    map_id: str
    map_epoch: int


@dataclass(frozen=True)
class _Window:
    message_id: str
    mission_id: str
    epoch: int
    beacon_epoch: int
    bssid: str
    quality: str
    median: float | None
    window_end: datetime
    samples: tuple[_Sample, ...]


@dataclass(frozen=True)
class _Candidate:
    candidate_id: str
    delta_x_m: float
    delta_y_m: float
    map_id: str
    map_epoch: int
    valid_until: datetime


def decide(case: Mapping[str, object]) -> Decision:
    """Return one selection, or a stop/hold/handoff/review with no new step."""
    motion = _bool(case.get("dog_motion_allowed"), "dog_motion_allowed")
    hysteresis = _positive(case.get("hysteresis_db"), "hysteresis_db")
    steps_taken, limit = _budget(case.get("search_budget"))
    beacon_epoch, hold_state, beacon_bssid = _beacon(case.get("beacon"))
    command_id = _optional_text(case.get("active_command_id"), "active_command_id")
    previous = _optional_text(case.get("previous_candidate_id"), "previous_candidate_id")
    now = _time(case.get("now"), "now")
    track_id = _optional_text(case.get("track_id"), "track_id")
    windows = _windows(case.get("windows"))
    blocked, map_epoch, map_id, mission_id, epoch, candidates = _candidates(
        case.get("candidates"),
        now,
    )
    context = _Context(
        beacon_epoch=beacon_epoch,
        map_epoch=map_epoch,
        mission_id=mission_id,
        epoch=epoch,
        track_id=track_id or "target-001",
        command_id=command_id,
        blocked=blocked,
    )
    vision = _vision(case.get("dog_vision", None))
    if vision == "handoff":
        return context.finish("handoff", "dog_vision", None, None, (), ())
    if vision == "review":
        return context.finish("review", "vision_ambiguous", None, None, (), ())
    if motion is not True:
        return context.finish("stop", "motion_not_allowed", None, None, (), ())
    if command_id:
        return context.finish("stop", "command_active", None, None, (), ())
    if blocked:
        return context.finish("stop", "planner_blocked", None, None, (), ())
    if hold_state != "stable":
        return context.finish("stop", "beacon_not_stable", None, None, (), ())
    if steps_taken >= limit:
        return context.finish("stop", "budget_exhausted", None, None, (), ())
    if not windows:
        raise InvalidHoming("at least one rssi window is required")
    ordered = tuple(sorted(windows, key=lambda item: (item.window_end, item.message_id)))
    sample_ids = tuple(sample.sample_id for window in ordered for sample in window.samples)
    window_ids = tuple(window.message_id for window in ordered)
    bad_quality = next((window.quality for window in ordered if window.quality != "valid"), None)
    if bad_quality is not None:
        return context.finish("stop", bad_quality, bad_quality, None, sample_ids, window_ids)
    if len(ordered) < 2:
        return context.finish(
            "hold",
            "single_window",
            ordered[0].quality,
            None,
            sample_ids,
            window_ids,
        )
    try:
        _same_epoch(ordered, beacon_epoch, beacon_bssid, map_id, map_epoch)
    except _Stop as exc:
        return context.finish("stop", exc.reason, "valid", None, sample_ids, window_ids)
    earliest, latest = ordered[0], ordered[-1]
    if earliest.median is None or latest.median is None:
        raise InvalidHoming("valid window is missing a median")
    improvement = latest.median - earliest.median
    start = earliest.samples[-1]
    end = latest.samples[-1]
    dx = end.x_m - start.x_m
    dy = end.y_m - start.y_m
    if abs(improvement) < hysteresis:
        if previous and any(item.candidate_id == previous for item in candidates):
            return context.finish("hold", "hysteresis", "valid", None, sample_ids, window_ids)
        return context.finish("stop", "flat_trend", "valid", None, sample_ids, window_ids)
    if math.hypot(dx, dy) < _SPACE:
        return context.finish("stop", "no_spatial_gradient", "valid", None, sample_ids, window_ids)
    if not candidates:
        return context.finish("stop", "no_safe_candidate", "valid", None, sample_ids, window_ids)
    sign = 1.0 if improvement > 0 else -1.0
    chosen = _aligned(candidates, (sign * dx, sign * dy))
    if chosen is None:
        return context.finish("stop", "no_aligned_candidate", "valid", None, sample_ids, window_ids)
    return context.finish(
        "select",
        "aligned_improvement",
        "valid",
        chosen,
        sample_ids,
        window_ids,
    )


@dataclass(frozen=True)
class _Context:
    beacon_epoch: int
    map_epoch: int
    mission_id: str
    epoch: int
    track_id: str
    command_id: str | None
    blocked: bool

    def finish(
        self,
        action: str,
        reason: str,
        quality: str | None,
        candidate_id: str | None,
        sample_ids: tuple[str, ...],
        window_ids: tuple[str, ...],
    ) -> Decision:
        return Decision(
            action=action,
            reason=reason,
            candidate_id=candidate_id,
            beacon_epoch=self.beacon_epoch,
            map_epoch=self.map_epoch,
            quality=quality,
            sample_ids=sample_ids,
            window_ids=window_ids,
            blocked=self.blocked,
            mission_id=self.mission_id,
            epoch=self.epoch,
            track_id=self.track_id if action == "select" else None,
            command_id=self.command_id,
        )


def _aligned(candidates: tuple[_Candidate, ...], gradient: tuple[float, float]) -> str | None:
    if not candidates:
        return None
    scored: list[tuple[float, str]] = []
    for candidate in candidates:
        dot = gradient[0] * candidate.delta_x_m + gradient[1] * candidate.delta_y_m
        if dot > _DOT:
            scored.append((dot, candidate.candidate_id))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def _same_epoch(
    windows: tuple[_Window, ...],
    beacon_epoch: int,
    bssid: str,
    map_id: str,
    map_epoch: int,
) -> None:
    epochs = {window.beacon_epoch for window in windows}
    if epochs != {beacon_epoch}:
        raise _Stop("beacon_epoch_mismatch")
    if any(window.bssid.lower() != bssid.lower() for window in windows):
        raise _Stop("bssid_mismatch")
    for window in windows:
        for sample in window.samples:
            if sample.map_epoch != map_epoch or sample.map_id != map_id:
                raise _Stop("map_epoch_mismatch")


class _Stop(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidHoming(f"{label} must be a boolean")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidHoming(f"{label} must be a string or null")
    text = value.strip()
    return text or None


def _positive(value: object, label: str) -> float:
    number = _real(value, label)
    if number <= 0:
        raise InvalidHoming(f"{label} must be positive")
    return number


def _real(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidHoming(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidHoming(f"{label} must be finite")
    return number


def _int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidHoming(f"{label} must be an integer")
    return value


def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InvalidHoming(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidHoming(f"{label} must be a timestamp") from exc
    if parsed.tzinfo is None:
        raise InvalidHoming(f"{label} must include a timezone")
    return parsed


def _budget(value: object) -> tuple[int, int]:
    if not isinstance(value, Mapping):
        raise InvalidHoming("search_budget must be an object")
    taken = _int(value.get("steps_taken"), "steps_taken")
    limit = _int(value.get("limit"), "limit")
    if taken < 0 or limit < 1:
        raise InvalidHoming("search_budget is out of range")
    return taken, limit


def _beacon(value: object) -> tuple[int, str, str]:
    if not isinstance(value, Mapping):
        raise InvalidHoming("beacon must be an object")
    epoch = _int(value.get("beacon_epoch"), "beacon_epoch")
    if epoch < 0:
        raise InvalidHoming("beacon_epoch must be non-negative")
    hold = value.get("hold_state")
    if not isinstance(hold, str) or hold not in _HOLDS:
        raise InvalidHoming("hold_state is not a beacon hold")
    bssid = value.get("bssid")
    if not isinstance(bssid, str) or not bssid.strip():
        raise InvalidHoming("beacon bssid is required")
    return epoch, hold, bssid.strip()


def _windows(value: object) -> tuple[_Window, ...]:
    if not isinstance(value, list):
        raise InvalidHoming("windows must be a list")
    return tuple(_window(item) for item in value)


def _window(value: object) -> _Window:
    if not isinstance(value, Mapping):
        raise InvalidHoming("rssi window must be an object")
    if value.get("kind") != "rssi.window":
        raise InvalidHoming("window kind must be rssi.window")
    message_id = _required_text(value.get("message_id"), "message_id")
    mission_id = _required_text(value.get("mission_id"), "mission_id")
    epoch = _int(value.get("epoch"), "epoch")
    payload = value.get("payload")
    if not isinstance(payload, Mapping):
        raise InvalidHoming("window payload must be an object")
    quality = payload.get("quality")
    if not isinstance(quality, str) or quality not in _QUALITIES:
        raise InvalidHoming("window quality is not recognized")
    samples = _samples(payload.get("samples"))
    median = _median(payload.get("median_rssi_dbm"), quality, samples)
    return _Window(
        message_id=message_id,
        mission_id=mission_id,
        epoch=epoch,
        beacon_epoch=_int(payload.get("beacon_epoch"), "beacon_epoch"),
        bssid=_required_text(payload.get("bssid"), "bssid"),
        quality=quality,
        median=median,
        window_end=_time(payload.get("window_end"), "window_end"),
        samples=samples,
    )


def _median(value: object, quality: str, samples: tuple[_Sample, ...]) -> float | None:
    if value is None:
        if quality != "unavailable" or samples:
            raise InvalidHoming("only an empty unavailable window may have a null median")
        return None
    number = _real(value, "median_rssi_dbm")
    if not samples and number == 0:
        raise InvalidHoming("rssi median 0 is not a no-signal value")
    if number < _MIN_DBM or number > _MAX_DBM:
        raise InvalidHoming("median_rssi_dbm is outside -150 to 0")
    if quality == "valid" and not samples:
        raise InvalidHoming("valid window has no samples")
    if quality == "unavailable":
        raise InvalidHoming("unavailable window must use a null median")
    return number


def _samples(value: object) -> tuple[_Sample, ...]:
    if not isinstance(value, list):
        raise InvalidHoming("samples must be a list")
    parsed = tuple(_sample(item) for item in value)
    ids = [item.sample_id for item in parsed]
    if len(ids) != len(set(ids)):
        raise InvalidHoming("sample ids must be unique inside a window")
    return parsed


def _sample(value: object) -> _Sample:
    if not isinstance(value, Mapping):
        raise InvalidHoming("sample must be an object")
    rssi = _real(value.get("rssi_dbm"), "rssi_dbm")
    if rssi < _MIN_DBM or rssi > _MAX_DBM:
        raise InvalidHoming("rssi_dbm is outside -150 to 0")
    pose = value.get("pose")
    if not isinstance(pose, Mapping):
        raise InvalidHoming("sample pose must be an object")
    if pose.get("valid") is not True:
        raise InvalidHoming("sample pose is not valid")
    return _Sample(
        sample_id=_required_text(value.get("sample_id"), "sample_id"),
        x_m=_real(pose.get("x_m"), "x_m"),
        y_m=_real(pose.get("y_m"), "y_m"),
        map_id=_required_text(pose.get("map_id"), "map_id"),
        map_epoch=_int(pose.get("map_epoch"), "map_epoch"),
    )


def _candidates(
    value: object,
    now: datetime,
) -> tuple[bool, int, str, str, int, tuple[_Candidate, ...]]:
    if not isinstance(value, Mapping):
        raise InvalidHoming("candidates must be an object")
    if value.get("kind") != "navigation.candidates":
        raise InvalidHoming("candidates kind must be navigation.candidates")
    payload = value.get("payload")
    if not isinstance(payload, Mapping):
        raise InvalidHoming("candidates payload must be an object")
    blocked = _bool(payload.get("blocked"), "blocked")
    map_epoch = _int(payload.get("map_epoch"), "map_epoch")
    map_id = payload.get("map_id")
    if not isinstance(map_id, str) or not map_id:
        raise InvalidHoming("map_id is required")
    mission_id = _required_text(value.get("mission_id"), "mission_id")
    epoch = _int(value.get("epoch"), "epoch")
    raw = payload.get("candidates")
    if not isinstance(raw, list):
        raise InvalidHoming("candidate list must be a list")
    if blocked:
        return blocked, map_epoch, map_id, mission_id, epoch, ()
    usable: list[_Candidate] = []
    for item in raw:
        parsed = _candidate(item, now, map_id, map_epoch)
        if parsed is not None:
            usable.append(parsed)
    return blocked, map_epoch, map_id, mission_id, epoch, tuple(usable)


def _candidate(
    value: object,
    now: datetime,
    map_id: str,
    map_epoch: int,
) -> _Candidate | None:
    if not isinstance(value, Mapping):
        raise InvalidHoming("candidate must be an object")
    if "range_m" in value or "target_range_m" in value:
        return None
    if value.get("safe") is not True:
        return None
    if value.get("frame_id") != CANDIDATE_FRAME:
        return None
    if value.get("map_id") != map_id:
        return None
    if value.get("map_epoch") != map_epoch:
        return None
    expires = _time(value.get("valid_until"), "valid_until")
    if expires <= now:
        return None
    delta_x = _real(value.get("delta_x_m"), "delta_x_m")
    delta_y = _real(value.get("delta_y_m"), "delta_y_m")
    if math.hypot(delta_x, delta_y) < _SPACE:
        return None
    return _Candidate(
        candidate_id=_required_text(value.get("candidate_id"), "candidate_id"),
        delta_x_m=delta_x,
        delta_y_m=delta_y,
        map_id=map_id,
        map_epoch=map_epoch,
        valid_until=expires,
    )


def _vision(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InvalidHoming("dog_vision must be an object or null")
    if value.get("kind") != "vision.decision":
        raise InvalidHoming("dog_vision kind must be vision.decision")
    payload = value.get("payload")
    if not isinstance(payload, Mapping):
        raise InvalidHoming("dog_vision payload must be an object")
    detections = payload.get("detections")
    if not isinstance(detections, list):
        raise InvalidHoming("detections must be a list")
    tracks = []
    for item in detections:
        if not isinstance(item, Mapping):
            raise InvalidHoming("detection must be an object")
        track = item.get("track_id")
        if isinstance(track, str) and track.strip():
            tracks.append(track.strip())
    acquired = (
        payload.get("target_state") == "person_visible"
        and payload.get("suggested_action") == "switch_to_dog_vision"
        and len(tracks) == 1
        and len(detections) == 1
    )
    if acquired:
        return "handoff"
    if len(detections) > 1 or len(tracks) > 1:
        return "review"
    return None


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidHoming(f"{label} is required")
    return value.strip()
