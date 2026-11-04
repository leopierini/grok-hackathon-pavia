"""Demo goal from separate dog range and drone horizontal offset.

The frozen v1 harness validates ``kernel.foundation`` results, so ``execute``
reports the goal through those keys and a ``decision_received`` event. The v2
proposal itself is the event payload: a ``mission.event`` whose event is
``demo_goal_reached``. This module does not land the aircraft or edit recovery.
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from patrol.ground.kernel.catalog import FEATURE_KINDS
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeaturePort,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

_FIXTURES = repo_root() / "fixtures" / "ground" / "g26"
_SLOT = "feature.v2_proximity"
_SCHEMA = "ground-task-v2"
_GOAL_REASON = (
    "Both separately defined proximity checks passed; aircraft recovery remains separate."
)
_AUTOMATIC_DOG = frozenset({"lidar_associated", "depth"})
_DOG_SOURCES = frozenset({"lidar_associated", "depth", "operator", "unknown"})
_DRONE_SOURCES = frozenset({"calibrated_projection", "operator", "unknown"})
_HOLDS = frozenset({"stable", "moving", "unknown"})
_ORIGINS = frozenset({"obstacle_clearance", "rssi", "person_detection", "distance_3d"})
_CLEARANCE_KEYS = frozenset(
    {
        "obstacle_clearance_m",
        "clearance_m",
        "min_clearance_m",
        "min_obstacle_clearance_m",
    }
)
_TAIL = (
    "journal_untouched",
    "state_untouched",
    "flight_state_untouched",
    "recovery_untouched",
    "no_land",
)


class _Bad(Exception):
    def __init__(self, outcome: str, code: str, text: str) -> None:
        self.outcome = outcome
        self.code = code
        self.text = text


@dataclass(frozen=True)
class _Profile:
    dog_max_m: float | None
    drone_max_m: float | None
    operator_evidence: bool
    evidence_age_ms: int


@dataclass(frozen=True)
class _Verdict:
    status: str
    detail: str
    authorized: bool
    within_limit: bool
    trace: tuple[str, ...]
    error: GroundError | None
    event_payload: Mapping[str, object] | None


def create(services: BaseServices) -> FeaturePort:
    """Build the proximity feature. Construction does not read devices."""
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "proximity create expects base services")
    return ProximityFeature(services)


class ProximityFeature:
    """Propose ``demo_goal_reached`` only when both current checks pass."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        before = _call_trace(self.services)
        if request.kind not in FEATURE_KINDS or not request.name:
            return _invalid("feature request is not usable")
        try:
            prepared = _prepare(request)
        except GroundFault as exc:
            return _from_fault(exc)
        if prepared is None:
            return _invalid(f"unknown proximity case {request.name}")
        message, context, latch = prepared
        if latch:
            self.services.kernel.authority.latch_cancel("operator halt")
        if _call_trace(self.services) != before:
            return _unsafe()
        if self.services.kernel.authority.cancelled:
            return _cancelled()
        if request.ticket is not None:
            try:
                self.services.kernel.authority.require_current(request.ticket)
            except GroundFault as exc:
                return _from_fault(exc)
        verdict = evaluate(message, context)
        if _call_trace(self.services) != before:
            return _unsafe()
        event: GroundEvent | None = None
        if verdict.event_payload is not None:
            event = GroundEvent("decision_received", request.ticket, verdict.event_payload)
        return _pack(verdict, event)


def evaluate(message: Mapping[str, object], context: Mapping[str, object]) -> _Verdict:
    """Decide the goal from one evidence message and the current profile."""
    shown = ""
    try:
        profile = _profile(context)
        shown = _threshold_text(profile)
        _context_types(context)
        kind = _kind(message)
        if kind == "rssi.window":
            raise _Bad("rejected", "rssi", "RSSI cannot be converted into dog range")
        if kind == "vision.decision":
            raise _Bad(
                "unresolved",
                "person_detection",
                "a person detection is not a proximity measurement",
            )
        if kind != "proximity.evidence":
            raise _Bad("invalid_input", "kind", f"unsupported message kind {kind}")
        _geometry(message, context)
        if profile.dog_max_m is None or profile.drone_max_m is None:
            raise _Bad("unresolved", "thresholds_unset", "profile thresholds are not agreed")
        payload = _mapping(message.get("payload"), "payload")
        _track(payload, context)
        dog = _mapping(payload.get("dog"), "dog")
        drone = _mapping(payload.get("drone"), "drone")
        _timestamps(dog, drone, context, profile.evidence_age_ms)
        _motion(dog, drone, context)
        _origin(dog, context)
        if (dog.get("source") == "operator") != (drone.get("source") == "operator"):
            raise _Bad(
                "unresolved",
                "operator_incomplete",
                "operator confirmation must cover both the dog and the drone",
            )
        dog_label = _dog_check(dog, payload, profile)
        drone_label = _drone_check(drone, payload, profile)
        return _goal(message, payload, context, profile, shown, dog_label, drone_label)
    except _Bad as exc:
        return _stop(shown, exc)


def _prepare(
    request: FeatureRequest,
) -> tuple[Mapping[str, object], Mapping[str, object], bool] | None:
    if request.name == "evaluate":
        message = request.payload.get("message")
        if isinstance(message, str) or not isinstance(message, Mapping):
            raise fault("invalid_input", "evaluate requires a message object")
        context = {key: value for key, value in request.payload.items() if key != "message"}
        return message, context, False
    builder = _CASES.get(request.name)
    if builder is None:
        return None
    return builder()


def _example() -> dict[str, object]:
    return _load(_FIXTURES / "proximity-evidence.json")


def _profile_file(name: str) -> dict[str, object]:
    return _load(_FIXTURES / name)


def _base_context(profile: Mapping[str, object], **overrides: object) -> dict[str, object]:
    context: dict[str, object] = {
        "track_id": "target-001",
        "dog_stopped": True,
        "hold_state": "stable",
        "evaluated_at": "2026-11-04T13:00:11.000Z",
        "profile": dict(profile),
        "height_m": None,
        "distance_3d_m": None,
        "claim_3d_max_m": None,
        "satisfy_both_with": None,
        "range_origin": None,
        "person_center_height_m": 1.0,
    }
    context.update(overrides)
    return context


def _copy(message: Mapping[str, object]) -> dict[str, object]:
    return cast(dict[str, object], copy.deepcopy(message))


def _child(message: dict[str, object], name: str) -> dict[str, object]:
    payload = message["payload"]
    if not isinstance(payload, dict):
        raise fault("invalid_input", "evidence payload is not an object")
    child = payload[name]
    if not isinstance(child, dict):
        raise fault("invalid_input", f"{name} evidence is not an object")
    return child


def _confirmed(message: dict[str, object], value: bool) -> None:
    payload = message["payload"]
    if not isinstance(payload, dict):
        raise fault("invalid_input", "evidence payload is not an object")
    payload["operator_confirmed"] = value


def _case_example(
    profile_name: str = "profile-open.json",
    **context: object,
) -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    return _example(), _base_context(_profile_file(profile_name), **context), False


def _case_null_offset() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    _child(message, "dog")["source"] = "lidar_associated"
    drone = _child(message, "drone")
    drone["source"] = "calibrated_projection"
    drone["horizontal_offset_m"] = None
    _confirmed(message, False)
    return message, _base_context(_profile_file("profile-open.json")), False


def _case_moving_dog() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    _child(message, "dog")["stationary"] = False
    return message, _base_context(_profile_file("profile-open.json"), dog_stopped=False), False


def _case_operator_nulls() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    _child(message, "dog")["range_m"] = None
    _child(message, "drone")["horizontal_offset_m"] = None
    return message, _base_context(_profile_file("profile-open.json")), False


def _case_beacon() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    _child(message, "drone")["hold_state"] = "moving"
    return message, _base_context(_profile_file("profile-open.json"), hold_state="moving"), False


def _case_clearance() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    dog = _child(message, "dog")
    dog["source"] = "lidar_associated"
    dog["range_m"] = 0.4
    dog["association_valid"] = False
    context = _base_context(
        _profile_file("profile-open.json"),
        range_origin="obstacle_clearance",
    )
    return message, context, False


def _case_lidar() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    _child(message, "dog")["source"] = "lidar_associated"
    _child(message, "drone")["source"] = "calibrated_projection"
    _confirmed(message, False)
    return message, _base_context(_profile_file("profile-closed.json")), False


def _case_one_side() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    _child(message, "dog")["source"] = "lidar_associated"
    _child(message, "drone")["horizontal_offset_m"] = None
    return message, _base_context(_profile_file("profile-open.json")), False


def _case_equal() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    dog = _child(message, "dog")
    drone = _child(message, "drone")
    dog["source"] = "lidar_associated"
    dog["range_m"] = 1.5
    drone["source"] = "calibrated_projection"
    drone["horizontal_offset_m"] = 1.5
    _confirmed(message, False)
    return message, _base_context(_profile_file("profile-open.json")), False


def _case_vision() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    message["kind"] = "vision.decision"
    message["payload"] = {"person_visible": True, "track_id": "target-001"}
    return message, _base_context(_profile_file("profile-open.json")), False


def _case_rssi() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    dog = _child(message, "dog")
    dog["source"] = "lidar_associated"
    dog["range_m"] = 1.2
    context = _base_context(_profile_file("profile-open.json"), range_origin="rssi")
    return message, context, False


def _case_association() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    message = _copy(_example())
    dog = _child(message, "dog")
    dog["source"] = "lidar_associated"
    dog["range_m"] = 0.4
    dog["association_valid"] = False
    _child(message, "drone")["source"] = "calibrated_projection"
    _confirmed(message, False)
    return message, _base_context(_profile_file("profile-closed.json")), False


def _case_string_bool() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    return _example(), _base_context(_profile_file("profile-open.json"), dog_stopped="true"), False


def _case_cancelled() -> tuple[Mapping[str, object], Mapping[str, object], bool]:
    return _example(), _base_context(_profile_file("profile-open.json")), True


_CaseBuilder = Callable[[], tuple[Mapping[str, object], Mapping[str, object], bool]]


def _bind() -> dict[str, _CaseBuilder]:
    return {
        "example_accepted": lambda: _case_example(),
        "null_drone_offset": _case_null_offset,
        "full_3d_at_4m": lambda: _case_example(
            height_m=4,
            distance_3d_m=1,
            person_center_height_m=1,
        ),
        "moving_dog": _case_moving_dog,
        "operator_enabled": _case_operator_nulls,
        "operator_disabled": lambda: _case_example("profile-closed.json"),
        "moving_beacon": _case_beacon,
        "clearance_not_range": _case_clearance,
        "stale_timestamp": lambda: _case_example(evaluated_at="2026-11-04T13:00:14.001Z"),
        "age_boundary": lambda: _case_example(evaluated_at="2026-11-04T13:00:14.000Z"),
        "single_3d_distance": lambda: _case_example(
            satisfy_both_with="distance_3d",
            distance_3d_m=0.8,
        ),
        "operator_one_side": _case_one_side,
        "lidar_automatic": _case_lidar,
        "profile_threshold": lambda: _case_example("profile-tight.json"),
        "rssi_not_range": _case_rssi,
        "person_not_proximity": _case_vision,
        "track_mismatch": lambda: _case_example(track_id="target-002"),
        "association_invalid": _case_association,
        "cancelled": _case_cancelled,
        "string_bool": _case_string_bool,
        "timestamp_future": lambda: _case_example(evaluated_at="2026-11-04T13:00:10.000Z"),
        "thresholds_unset": lambda: _case_example("profile-unset.json"),
        "height_without_3d_claim": lambda: _case_example(height_m=4),
        "threshold_equal": _case_equal,
    }


_CASES: dict[str, _CaseBuilder] = _bind()


def _profile(context: Mapping[str, object]) -> _Profile:
    raw = context.get("profile")
    profile = _mapping(raw, "profile")
    age = profile.get("evidence_age_ms", 3000)
    return _Profile(
        dog_max_m=_optional_threshold(profile.get("dog_range_max_m"), "dog_range_max_m"),
        drone_max_m=_optional_threshold(
            profile.get("drone_horizontal_max_m"),
            "drone_horizontal_max_m",
        ),
        operator_evidence=_required_bool(profile.get("operator_evidence"), "operator_evidence"),
        evidence_age_ms=_age_budget(age),
    )


def _context_types(context: Mapping[str, object]) -> None:
    if "dog_stopped" in context and not isinstance(context.get("dog_stopped"), bool):
        raise _Bad("invalid_input", "dog_stopped", "dog_stopped must be a boolean")
    hold = context.get("hold_state")
    if not isinstance(hold, str) or hold not in _HOLDS:
        raise _Bad("invalid_input", "hold_state", "hold_state must be stable, moving, or unknown")
    track = context.get("track_id")
    if track is not None and (not isinstance(track, str) or not track.strip()):
        raise _Bad("invalid_input", "track_id", "track_id must be a non-empty string")
    origin = context.get("range_origin")
    if origin is not None and origin not in _ORIGINS:
        raise _Bad("invalid_input", "range_origin", "range_origin is not a known quantity")
    satisfy = context.get("satisfy_both_with")
    if satisfy is not None and satisfy != "distance_3d":
        raise _Bad("invalid_input", "satisfy_both_with", "unsupported combined distance claim")


def _kind(message: Mapping[str, object]) -> str:
    kind = message.get("kind")
    if not isinstance(kind, str) or not kind:
        raise _Bad("invalid_input", "kind", "message kind is required")
    if message.get("protocol_version") != "2.0-draft":
        raise _Bad("invalid_input", "protocol", "protocol_version must be 2.0-draft")
    if not isinstance(message.get("simulated"), bool):
        raise _Bad("invalid_input", "simulated", "simulated must be a boolean")
    return kind


def _geometry(message: Mapping[str, object], context: Mapping[str, object]) -> None:
    combined = context.get("satisfy_both_with") == "distance_3d"
    from_origin = context.get("range_origin") == "distance_3d"
    if combined or from_origin:
        raise _Bad(
            "rejected",
            "single_3d_distance",
            "one 3D distance cannot satisfy both the dog range and the drone horizontal offset",
        )
    payload = message.get("payload")
    embedded = payload.get("distance_3d_m") if isinstance(payload, Mapping) else None
    raw_distance = context.get("distance_3d_m")
    if raw_distance is None:
        raw_distance = embedded
    distance = _optional_meters(raw_distance, "distance_3d_m")
    claim = _optional_meters(context.get("claim_3d_max_m"), "claim_3d_max_m")
    height = _optional_meters(context.get("height_m"), "height_m")
    if height is None and isinstance(payload, Mapping):
        height = _optional_meters(payload.get("height_m"), "height_m")
    limit = distance if distance is not None else claim
    if height is None or limit is None:
        if distance is not None and not _separate_metrics(payload):
            raise _Bad(
                "rejected",
                "single_3d_distance",
                "one 3D distance cannot satisfy both the dog range and the drone horizontal offset",
            )
        return
    person_raw = context.get("person_center_height_m", 1.0)
    person_m = _optional_meters(person_raw, "person_center_height_m")
    if person_m is None:
        person_m = 1.0
    if person_m < 0 or person_m >= height:
        raise _Bad(
            "invalid_input",
            "person_center",
            "person center height must sit below the aircraft",
        )
    if height - person_m > limit:
        raise _Bad(
            "rejected",
            "full_3d_at_4m",
            "a 4 m aircraft height cannot be within 1 m of the person in full 3D",
        )


def _separate_metrics(payload: object) -> bool:
    if not isinstance(payload, Mapping):
        return False
    dog = payload.get("dog")
    drone = payload.get("drone")
    if not isinstance(dog, Mapping) or not isinstance(drone, Mapping):
        return False
    return "range_m" in dog and "horizontal_offset_m" in drone


def _track(payload: Mapping[str, object], context: Mapping[str, object]) -> None:
    evidence_track = payload.get("track_id")
    current = context.get("track_id")
    if not isinstance(evidence_track, str) or not evidence_track:
        raise _Bad("unresolved", "track_mismatch", "evidence has no track")
    if not isinstance(current, str) or current != evidence_track:
        raise _Bad("unresolved", "track_mismatch", "evidence is for a different track")


def _timestamps(
    dog: Mapping[str, object],
    drone: Mapping[str, object],
    context: Mapping[str, object],
    budget_ms: int,
) -> None:
    evaluated = _clock(context.get("evaluated_at"), "evaluated_at")
    for label, side in (("dog", dog), ("drone", drone)):
        observed = _clock(side.get("observed_at"), f"{label}.observed_at")
        age_ms = (evaluated - observed).total_seconds() * 1000.0
        if age_ms < 0:
            raise _Bad("unresolved", "timestamp_future", f"{label} timestamp is in the future")
        if age_ms > budget_ms:
            raise _Bad(
                "unresolved",
                "stale",
                f"{label} observation is older than the evidence budget",
            )


def _motion(
    dog: Mapping[str, object],
    drone: Mapping[str, object],
    context: Mapping[str, object],
) -> None:
    if dog.get("stationary") is not True or context.get("dog_stopped") is not True:
        raise _Bad("unresolved", "dog_moving", "the dog is not stationary")
    evidence_hold = drone.get("hold_state")
    current_hold = context.get("hold_state")
    if not isinstance(evidence_hold, str) or evidence_hold not in _HOLDS:
        raise _Bad("invalid_input", "hold_state", "drone hold_state is not usable")
    if evidence_hold == "moving" or current_hold == "moving":
        raise _Bad("unresolved", "beacon_moving", "the beacon hold is moving")
    if evidence_hold != "stable" or current_hold != "stable":
        raise _Bad("unresolved", "beacon_not_stable", "the beacon hold is not stable")


def _origin(dog: Mapping[str, object], context: Mapping[str, object]) -> None:
    origin = context.get("range_origin")
    if origin == "obstacle_clearance" or _CLEARANCE_KEYS.intersection(dog):
        raise _Bad("rejected", "clearance", "obstacle clearance is not the dog-to-target range")
    if origin == "rssi":
        raise _Bad("rejected", "rssi", "RSSI cannot be converted into dog range")
    if origin == "person_detection":
        raise _Bad(
            "unresolved",
            "person_detection",
            "a person detection is not a proximity measurement",
        )


def _dog_check(
    dog: Mapping[str, object],
    payload: Mapping[str, object],
    profile: _Profile,
) -> str:
    source = _source(dog.get("source"), _DOG_SOURCES, "dog.source")
    range_m = _optional_meters(dog.get("range_m"), "dog.range_m")
    if source in _AUTOMATIC_DOG:
        if not isinstance(dog.get("association_valid"), bool):
            raise _Bad("invalid_input", "association_valid", "association_valid must be a boolean")
        if dog.get("association_valid") is not True:
            raise _Bad("unresolved", "association_invalid", "dog range is not associated")
        if range_m is None:
            raise _Bad("unresolved", "missing_dog_range", "dog range is missing")
        _inside(range_m, profile.dog_max_m, "dog range")
        return "dog_range_ok"
    if source == "operator":
        _require_operator(payload, profile)
        if range_m is not None:
            _inside(range_m, profile.dog_max_m, "dog range")
        return "operator_dog_ok"
    raise _Bad("unresolved", "dog_source", "dog range source cannot authorize the goal")


def _drone_check(
    drone: Mapping[str, object],
    payload: Mapping[str, object],
    profile: _Profile,
) -> str:
    source = _source(drone.get("source"), _DRONE_SOURCES, "drone.source")
    offset = _optional_meters(drone.get("horizontal_offset_m"), "drone.horizontal_offset_m")
    if source == "calibrated_projection":
        if offset is None:
            raise _Bad("unresolved", "missing_drone_offset", "drone horizontal offset is missing")
        _inside(offset, profile.drone_max_m, "drone horizontal offset")
        return "drone_horizontal_ok"
    if source == "operator":
        _require_operator(payload, profile)
        if offset is not None:
            _inside(offset, profile.drone_max_m, "drone horizontal offset")
        return "operator_drone_ok"
    raise _Bad("unresolved", "drone_source", "drone offset source cannot authorize the goal")


def _require_operator(payload: Mapping[str, object], profile: _Profile) -> None:
    if not profile.operator_evidence:
        raise _Bad(
            "unresolved",
            "operator_disabled",
            "operator evidence is disabled in the profile",
        )
    confirmed = payload.get("operator_confirmed")
    if confirmed is True:
        return
    if confirmed is not False and confirmed is not None:
        raise _Bad(
            "invalid_input",
            "operator_confirmed",
            "operator_confirmed must be a boolean",
        )
    raise _Bad(
        "unresolved",
        "operator_unconfirmed",
        "operator confirmation is not current on both sides",
    )


def _inside(value: float, limit: float | None, label: str) -> None:
    if limit is None:
        raise _Bad("unresolved", "thresholds_unset", "profile thresholds are not agreed")
    if value > limit:
        raise _Bad("unresolved", "outside_threshold", f"{label} is outside the profile threshold")


def _goal(
    message: Mapping[str, object],
    payload: Mapping[str, object],
    context: Mapping[str, object],
    profile: _Profile,
    shown: str,
    dog_label: str,
    drone_label: str,
) -> _Verdict:
    track = payload.get("track_id")
    mission_id = message.get("mission_id")
    epoch = message.get("epoch")
    source_id = message.get("message_id")
    seq = message.get("seq")
    evaluated_at = context.get("evaluated_at")
    if not isinstance(track, str) or not isinstance(mission_id, str) or not mission_id:
        raise _Bad("invalid_input", "identity", "goal evidence is missing mission identity")
    if not isinstance(source_id, str) or not source_id:
        raise _Bad("invalid_input", "message_id", "evidence message_id is required")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise _Bad("invalid_input", "evaluated_at", "evaluated_at is required")
    if isinstance(epoch, bool) or not isinstance(epoch, int):
        raise _Bad("invalid_input", "epoch", "epoch must be an integer")
    if isinstance(seq, bool) or not isinstance(seq, int):
        raise _Bad("invalid_input", "seq", "seq must be an integer")
    if profile.dog_max_m is None or profile.drone_max_m is None:
        raise _Bad("unresolved", "thresholds_unset", "profile thresholds are not agreed")
    goal_id = "msg-event-demo_goal_reached"
    envelope: dict[str, object] = {
        "protocol_version": "2.0-draft",
        "message_id": goal_id,
        "mission_id": mission_id,
        "epoch": epoch,
        "seq": seq + 1,
        "sent_at": evaluated_at,
        "source": "ground",
        "destination": "all",
        "kind": "mission.event",
        "correlation_id": source_id,
        "expires_at": None,
        "simulated": message.get("simulated") is True,
        "payload": {
            "event": "demo_goal_reached",
            "phase": "proximity_verify",
            "outcome": "completed",
            "device_recovery_required": False,
            "reason": _GOAL_REASON,
            "details": {
                "logs_requirements_status": "proposed_pending_team",
                "track_id": track,
                "message_id": goal_id,
                "mission_id": mission_id,
                "epoch": epoch,
                "dog_range_max_m": profile.dog_max_m,
                "drone_horizontal_max_m": profile.drone_max_m,
            },
        },
    }
    return _Verdict(
        status="ok",
        detail="goal_reached",
        authorized=True,
        within_limit=True,
        trace=(shown, dog_label, drone_label, "mission.event", "demo_goal_reached", *_TAIL),
        error=None,
        event_payload=envelope,
    )


def _stop(shown: str, exc: _Bad) -> _Verdict:
    reason = "invalid_input" if exc.outcome == "invalid_input" else f"{exc.outcome}:{exc.code}"
    head: tuple[str, ...] = (reason, "no_goal_event")
    if shown:
        head = (shown, *head)
    error: GroundError | None = None
    if exc.outcome != "unresolved":
        code = "invalid_input" if exc.outcome == "invalid_input" else "rejected"
        error = GroundError(code, exc.text, False)
    return _Verdict(
        status="ok" if exc.outcome == "unresolved" else "failed",
        detail=exc.outcome,
        authorized=False,
        within_limit=False,
        trace=head + _TAIL,
        error=error,
        event_payload=None,
    )


def _pack(verdict: _Verdict, event: GroundEvent | None) -> FeatureResult:
    return _result(
        status=verdict.status,
        detail=verdict.detail,
        authorized=verdict.authorized,
        within_limit=verdict.within_limit,
        trace=verdict.trace,
        error=verdict.error,
        event=event,
    )


def _result(
    *,
    status: str,
    detail: str,
    authorized: bool,
    within_limit: bool,
    trace: tuple[str, ...],
    error: GroundError | None,
    event: GroundEvent | None,
) -> FeatureResult:
    data = freeze_map(
        {
            "authorized": authorized,
            "retained": False,
            "detail": detail,
            "trace": trace,
            "device_calls": 0,
            "measurement_clock": "manual",
            "within_limit": within_limit,
            "simulated": True,
            "live_call_count": 0,
            "slot": _SLOT,
            "schema_version": _SCHEMA,
        }
    )
    events = () if event is None else (event,)
    return FeatureResult(status, data, events, error)


def _invalid(text: str) -> FeatureResult:
    return _result(
        status="failed",
        detail="invalid_input",
        authorized=False,
        within_limit=False,
        trace=("invalid_input", "no_goal_event", *_TAIL),
        error=GroundError("invalid_input", text, False),
        event=None,
    )


def _cancelled() -> FeatureResult:
    return _result(
        status="failed",
        detail="cancelled",
        authorized=False,
        within_limit=False,
        trace=("cancelled", "no_goal_event", *_TAIL),
        error=GroundError("cancelled", "cancellation is latched", False),
        event=None,
    )


def _unsafe() -> FeatureResult:
    return _result(
        status="failed",
        detail="unsafe_state",
        authorized=False,
        within_limit=False,
        trace=("unsafe_state",),
        error=GroundError("unsafe_state", "proximity observed an unexpected device call", True),
        event=None,
    )


def _from_fault(exc: GroundFault) -> FeatureResult:
    return _result(
        status="failed",
        detail=exc.error.code,
        authorized=False,
        within_limit=False,
        trace=(exc.error.code, "no_goal_event", *_TAIL),
        error=exc.error,
        event=None,
    )


def _call_trace(services: BaseServices) -> tuple[object, ...]:
    journal_records = getattr(services.journal, "records", None)
    state_trace = getattr(services.state, "trace", None)
    devices = getattr(services.adapters, "devices", None)
    calls = getattr(devices, "calls", None)
    return (
        tuple(journal_records) if isinstance(journal_records, list) else (),
        tuple(state_trace) if isinstance(state_trace, list) else (),
        tuple(calls) if isinstance(calls, list) else (),
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, str) or not isinstance(value, Mapping):
        raise _Bad("invalid_input", label, f"{label} must be an object")
    return value


def _required_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise _Bad("invalid_input", label, f"{label} must be a boolean")
    return value


def _optional_threshold(value: object, label: str) -> float | None:
    if value is None:
        return None
    number = _finite(value, label)
    if number <= 0:
        raise _Bad("invalid_input", label, f"{label} must be greater than zero")
    return number


def _optional_meters(value: object, label: str) -> float | None:
    if value is None:
        return None
    number = _finite(value, label)
    if number < 0:
        raise _Bad("invalid_input", label, f"{label} must be non-negative")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Bad("invalid_input", label, f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise _Bad("invalid_input", label, f"{label} must be finite")
    return number


def _age_budget(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Bad("invalid_input", "evidence_age_ms", "evidence_age_ms must be an integer")
    if value <= 0:
        raise _Bad("invalid_input", "evidence_age_ms", "evidence_age_ms must be positive")
    return value


def _source(value: object, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _Bad("invalid_input", label, f"{label} is not a known source")
    return value


def _clock(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _Bad("invalid_input", label, f"{label} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _Bad("invalid_input", label, f"{label} must be a UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise _Bad("invalid_input", label, f"{label} must be a UTC timestamp")
    return parsed.astimezone(UTC)


def _threshold_text(profile: _Profile) -> str:
    if profile.dog_max_m is None or profile.drone_max_m is None:
        return "thresholds:unset"
    return f"thresholds:{_fmt(profile.dog_max_m)},{_fmt(profile.drone_max_m)}"


def _fmt(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _load(path: Path) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise fault("invalid_input", f"duplicate key {key} in {path.name}")
            result[key] = value
        return result

    def reject_constant(_constant: str) -> object:
        raise fault("invalid_input", f"nonfinite number in {path.name}")

    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
    except GroundFault:
        raise
    except (OSError, ValueError) as exc:
        raise fault("io_fault", f"{path.name} could not be read", recovery_required=True) from exc
    if isinstance(raw, (str, bytes)) or not isinstance(raw, dict):
        raise fault("invalid_input", f"{path.name} must be an object")
    return cast(dict[str, object], raw)
