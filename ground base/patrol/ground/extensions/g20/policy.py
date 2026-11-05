"""Dog navigation health. Safe candidate ids only; no path is invented."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from patrol.ground.kernel.contracts import GroundSettings
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_dog_navigation"
SCHEMA = "ground-task-v2"
MODES = frozenset({"slam_local_planner", "reactive_avoidance", "unavailable"})
SLAM_STATES = frozenset({"localized", "lost", "not_available"})
TRANSPORTS = frozenset({"ethernet", "wifi"})
BODY_FRAME = "dog/base_link"
ENVELOPE_KEYS = frozenset(
    {
        "protocol_version",
        "message_id",
        "mission_id",
        "epoch",
        "seq",
        "sent_at",
        "source",
        "destination",
        "kind",
        "correlation_id",
        "expires_at",
        "simulated",
        "payload",
    }
)
REQUEST_KEYS = frozenset(
    {
        "observation",
        "candidates",
        "capabilities",
        "map_epoch",
        "profile",
        "settings",
    }
)
OBSERVATION_KEYS = frozenset(
    {
        "device_id",
        "standing",
        "stationary",
        "avoidance_enabled",
        "transport",
        "pose",
        "navigation_mode",
        "slam_state",
        "lidar_observed_at",
        "minimum_clearance_m",
        "frame",
        "active_command_id",
    }
)
CANDIDATE_MESSAGE_KEYS = frozenset(
    {
        "device_id",
        "snapshot_id",
        "map_id",
        "map_epoch",
        "navigation_mode",
        "observed_at",
        "candidates",
        "blocked",
        "reason",
    }
)
CANDIDATE_KEYS = frozenset(
    {
        "candidate_id",
        "snapshot_id",
        "frame_id",
        "map_id",
        "map_epoch",
        "delta_x_m",
        "delta_y_m",
        "delta_yaw_rad",
        "safe",
        "clearance_m",
        "valid_until",
    }
)
POSE_KEYS = frozenset(
    {
        "frame_id",
        "map_id",
        "map_epoch",
        "x_m",
        "y_m",
        "z_m",
        "yaw_rad",
        "observed_at",
        "valid",
    }
)
FRAME_KEYS = frozenset(
    {
        "frame_id",
        "image_ref",
        "sha256",
        "captured_at",
        "camera_id",
        "camera_epoch",
        "width_px",
        "height_px",
        "camera_frame_id",
        "camera_to_body_calibration_id",
        "simulated",
    }
)
FEATURE_KEYS = frozenset(
    {
        "controlled_motion",
        "downward_video",
        "rssi_receiver",
        "lidar",
        "slam",
        "target_range",
    }
)
CAPABILITY_KEYS = frozenset(
    {
        "device_id",
        "role",
        "model",
        "software_version",
        "supported_commands",
        "camera_ids",
        "pose_frames",
        "features",
        "validated",
        "acceptance_evidence_ref",
    }
)
PROFILE_KEYS = frozenset({"dog_transport", "profile_identity"})
TARGET_RANGE_KEYS = frozenset(
    {
        "target_range",
        "target_range_m",
        "range_m",
        "person_range_m",
        "target_distance_m",
        "distance_m",
    }
)
PARSE_TRACE = (
    "standing:invalid",
    "ready:false",
    "ready_to_wait:false",
    "usable:empty",
    "target_range:absent",
    "command:none",
    "move_local:none",
    "invented:none",
)


@dataclass(frozen=True)
class NavDecision:
    status: str
    reason: str
    error_code: str | None
    error_detail: str | None
    recovery_required: bool
    standing: bool | None
    stationary: bool | None
    avoidance: bool | None
    navigation_mode: str
    slam_state: str
    minimum_clearance_m: float | None
    candidate_ids: tuple[str, ...]
    blocked: bool
    ready: bool
    ready_to_wait: bool
    map_id: str | None
    map_epoch: int | None
    pose_epoch: int | None
    transport: str
    profile_transport: str
    frame: Mapping[str, object] | None
    dropped: str
    withheld: str
    correlation: Mapping[str, object]

    def public_data(self) -> Mapping[str, object]:
        clearance: object = self.minimum_clearance_m
        return freeze_map(
            {
                "readiness": freeze_map(
                    {
                        "standing": self.standing,
                        "stationary": self.stationary,
                        "avoidance": self.avoidance,
                        "navigation_mode": self.navigation_mode,
                        "slam_state": self.slam_state,
                        "minimum_clearance_m": clearance,
                    }
                ),
                "candidate_ids": self.candidate_ids,
                "blocked": self.blocked,
                "ready": self.ready,
                "ready_to_wait": self.ready_to_wait,
                "route_ready": self.ready,
                "map_id": self.map_id,
                "map_epoch": self.map_epoch,
                "pose_map_epoch": self.pose_epoch,
                "transport": self.transport,
                "profile_transport": self.profile_transport,
                "frame": self.frame,
                "commands": (),
                "motion_proposed": False,
                "dropped": self.dropped,
                "withheld": self.withheld,
                "reason": self.reason,
                "correlation": self.correlation,
            }
        )


def trace_of(decision: NavDecision) -> tuple[str, ...]:
    usable = "empty" if not decision.candidate_ids else ",".join(decision.candidate_ids)
    rows = [
        f"standing:{_flag(decision.standing)}",
        f"stationary:{_flag(decision.stationary)}",
        f"avoidance:{_flag(decision.avoidance)}",
        f"mode:{decision.navigation_mode or 'none'}",
        f"slam:{decision.slam_state or 'none'}",
        f"transport:{decision.transport or 'none'}",
        f"profile:{decision.profile_transport or 'none'}",
        f"clearance:{_clearance_text(decision.minimum_clearance_m)}",
        "target_range:absent",
        f"blocked:{_flag(decision.blocked)}",
        f"ready:{_flag(decision.ready)}",
        f"ready_to_wait:{_flag(decision.ready_to_wait)}",
        f"usable:{usable}",
        f"pose_epoch:{_epoch_text(decision.pose_epoch)}",
        f"map_epoch:{_epoch_text(decision.map_epoch)}",
        "command:none",
        "move_local:none",
        "invented:none",
    ]
    if decision.dropped:
        rows.append(f"dropped:{decision.dropped}")
    if decision.withheld:
        rows.append(f"withheld:{decision.withheld}")
    return tuple(rows)


def assess(now: datetime, payload: Mapping[str, object]) -> NavDecision:
    if now.tzinfo is None:
        raise fault("invalid_input", "navigation clock must be timezone-aware")
    _exact(payload, REQUEST_KEYS, "navigation request")
    observation = _envelope(payload.get("observation"), "dog.observation")
    candidates = _envelope(payload.get("candidates"), "navigation.candidates")
    capabilities = _envelope(payload.get("capabilities"), "capabilities.report")
    current_epoch = _epoch_value(payload.get("map_epoch"), "map_epoch")
    profile = _profile_transport(payload)
    if observation["mission_id"] != candidates["mission_id"]:
        raise fault("contract_mismatch", "observation and candidates use different missions")
    if observation["epoch"] != candidates["epoch"]:
        raise fault("epoch_mismatch", "observation and candidates use different epochs")
    obs_raw = _as_map(observation["payload"], "observation payload")
    _reject_target_range(obs_raw, "observation")
    obs = _exact(obs_raw, OBSERVATION_KEYS, "observation payload")
    nav_raw = _as_map(candidates["payload"], "candidates payload")
    _reject_target_range(nav_raw, "candidates")
    nav = _exact(nav_raw, CANDIDATE_MESSAGE_KEYS, "candidates payload")
    standing = _tri(obs.get("standing"), "standing")
    stationary = _tri(obs.get("stationary"), "stationary")
    avoidance = _tri(obs.get("avoidance_enabled"), "avoidance_enabled")
    transport = _transport_value(obs.get("transport"), "observation transport")
    mode = _choice(obs.get("navigation_mode"), MODES, "navigation_mode")
    slam_state = _choice(obs.get("slam_state"), SLAM_STATES, "slam_state")
    clearance = _clearance(obs.get("minimum_clearance_m"))
    _unused_pose, pose_epoch, map_id, pose_valid = _pose(obs.get("pose"))
    del _unused_pose
    frame = _frame(obs.get("frame"))
    device_id = _text(obs.get("device_id"), "device_id")
    blocked = _bool(nav.get("blocked"), "blocked")
    nav_mode = _choice(nav.get("navigation_mode"), MODES, "candidates navigation_mode")
    raw_candidates = _candidate_list(nav.get("candidates"))
    lidar_at = obs.get("lidar_observed_at")
    slam_armed, lidar_armed = _arms(capabilities, device_id)
    if nav.get("device_id") != device_id:
        raise fault("contract_mismatch", "observation and candidates name different devices")
    if nav_mode != mode:
        return _blocked(
            "mode_mismatch",
            "rejected",
            "observation and candidates disagree on navigation_mode",
            standing=standing,
            stationary=stationary,
            avoidance=avoidance,
            navigation_mode=mode,
            slam_state=slam_state,
            minimum_clearance_m=clearance,
            blocked=blocked,
            map_id=map_id,
            map_epoch=current_epoch,
            pose_epoch=pose_epoch,
            transport=transport,
            profile_transport=profile,
            frame=frame,
            correlation=_correlation(observation, candidates, pose_epoch, frame),
        )
    if mode == "slam_local_planner" and not slam_armed:
        return _blocked(
            "slam_disarmed",
            "rejected",
            "slam_local_planner was claimed while slam is disarmed",
            standing=standing,
            stationary=stationary,
            avoidance=avoidance,
            navigation_mode=mode,
            slam_state=slam_state,
            minimum_clearance_m=clearance,
            blocked=blocked,
            map_id=map_id,
            map_epoch=current_epoch,
            pose_epoch=pose_epoch,
            transport=transport,
            profile_transport=profile,
            frame=frame,
            correlation=_correlation(observation, candidates, pose_epoch, frame),
        )
    if slam_state != "not_available" and not slam_armed:
        return _blocked(
            "slam_disarmed",
            "rejected",
            "slam state was reported while slam is disarmed",
            standing=standing,
            stationary=stationary,
            avoidance=avoidance,
            navigation_mode=mode,
            slam_state=slam_state,
            minimum_clearance_m=clearance,
            blocked=blocked,
            map_id=map_id,
            map_epoch=current_epoch,
            pose_epoch=pose_epoch,
            transport=transport,
            profile_transport=profile,
            frame=frame,
            correlation=_correlation(observation, candidates, pose_epoch, frame),
        )
    snapshot_id = _text(nav.get("snapshot_id"), "snapshot_id")
    nav_map_id = _map_id(nav.get("map_id"), "candidates map_id")
    nav_epoch = _epoch_value(nav.get("map_epoch"), "candidates map_epoch")
    _time(nav.get("observed_at"), "candidates observed_at")
    if not isinstance(nav.get("reason"), str):
        raise fault("invalid_input", "candidates reason must be a string")
    parsed, range_hit = _parse_candidates(raw_candidates, snapshot_id)
    if range_hit:
        return _blocked(
            "target_range",
            "rejected",
            "a candidate included a target range; clearance is not target range",
            standing=standing,
            stationary=stationary,
            avoidance=avoidance,
            navigation_mode=mode,
            slam_state=slam_state,
            minimum_clearance_m=clearance,
            blocked=blocked,
            map_id=map_id,
            map_epoch=current_epoch,
            pose_epoch=pose_epoch,
            transport=transport,
            profile_transport=profile,
            frame=frame,
            correlation=_correlation(observation, candidates, pose_epoch, frame),
        )
    if blocked and parsed:
        return _blocked(
            "blocked_inconsistent",
            "rejected",
            "blocked true requires an empty candidate list",
            standing=standing,
            stationary=stationary,
            avoidance=avoidance,
            navigation_mode=mode,
            slam_state=slam_state,
            minimum_clearance_m=clearance,
            blocked=True,
            map_id=map_id,
            map_epoch=current_epoch,
            pose_epoch=pose_epoch,
            transport=transport,
            profile_transport=profile,
            frame=frame,
            correlation=_correlation(observation, candidates, pose_epoch, frame),
        )
    if parsed and (lidar_at is None or clearance is None or not lidar_armed):
        missing = lidar_at is None or clearance is None
        detail = (
            "non-empty candidates require lidar_observed_at and minimum_clearance_m"
            if missing
            else "lidar is disarmed"
        )
        return _failed_decision(
            "lidar_required" if missing else "lidar_disarmed",
            "validation_failed",
            detail,
            standing=standing,
            stationary=stationary,
            avoidance=avoidance,
            navigation_mode=mode,
            slam_state=slam_state,
            minimum_clearance_m=clearance,
            blocked=blocked,
            map_id=map_id,
            map_epoch=current_epoch,
            pose_epoch=pose_epoch,
            transport=transport,
            profile_transport=profile,
            frame=frame,
            correlation=_correlation(observation, candidates, pose_epoch, frame),
        )
    if parsed and lidar_at is not None:
        _time(lidar_at, "lidar_observed_at")
    kept, drop = _keep(
        parsed,
        now=now,
        pose_valid=pose_valid,
        pose_epoch=pose_epoch,
        map_id=map_id,
        nav_map_id=nav_map_id,
        nav_epoch=nav_epoch,
        current_epoch=current_epoch,
        snapshot_id=snapshot_id,
    )
    reason, ready, waiting, published, withheld = _readiness(
        standing=standing,
        stationary=stationary,
        avoidance=avoidance,
        mode=mode,
        slam_state=slam_state,
        transport=transport,
        profile=profile,
        pose_valid=pose_valid,
        blocked=blocked,
        raw_count=len(parsed),
        kept=kept,
        drop=drop,
    )
    return NavDecision(
        status="ok",
        reason=reason,
        error_code=None,
        error_detail=None,
        recovery_required=False,
        standing=standing,
        stationary=stationary,
        avoidance=avoidance,
        navigation_mode=mode,
        slam_state=slam_state,
        minimum_clearance_m=clearance,
        candidate_ids=published,
        blocked=blocked,
        ready=ready,
        ready_to_wait=waiting,
        map_id=map_id,
        map_epoch=current_epoch,
        pose_epoch=pose_epoch,
        transport=transport,
        profile_transport=profile,
        frame=frame,
        dropped=drop,
        withheld=withheld,
        correlation=_correlation(observation, candidates, current_epoch, frame),
    )


def _readiness(
    *,
    standing: bool | None,
    stationary: bool | None,
    avoidance: bool | None,
    mode: str,
    slam_state: str,
    transport: str,
    profile: str,
    pose_valid: bool,
    blocked: bool,
    raw_count: int,
    kept: tuple[str, ...],
    drop: str,
) -> tuple[str, bool, bool, tuple[str, ...], str]:
    if transport != profile:
        return "transport_mismatch", False, False, (), "transport"
    withheld = _posture(standing, stationary, avoidance)
    if withheld:
        return "not_ready", False, False, (), withheld
    if not pose_valid:
        return "not_ready", False, False, (), "pose"
    if blocked and raw_count == 0:
        return "ready_to_wait", False, True, (), ""
    if mode == "unavailable":
        return "not_ready", False, False, (), "mode"
    if mode == "slam_local_planner" and slam_state != "localized":
        return "not_ready", False, False, (), "slam_state"
    if not kept:
        token = {
            "expired": "expired",
            "map_epoch": "epoch_dropped",
            "frame": "frame_dropped",
            "unsafe": "unsafe_dropped",
            "map_id": "map_dropped",
            "snapshot": "snapshot_dropped",
        }.get(drop, "no_candidate")
        return token, False, False, (), ""
    return kept[0], True, False, kept, ""


def _posture(standing: bool | None, stationary: bool | None, avoidance: bool | None) -> str:
    if standing is not True:
        return "standing"
    if stationary is not True:
        return "stationary"
    if avoidance is not True:
        return "avoidance"
    return ""


def _keep(
    parsed: tuple[Mapping[str, object], ...],
    *,
    now: datetime,
    pose_valid: bool,
    pose_epoch: int | None,
    map_id: str | None,
    nav_map_id: str | None,
    nav_epoch: int,
    current_epoch: int,
    snapshot_id: str,
) -> tuple[tuple[str, ...], str]:
    kept: list[str] = []
    reasons: list[str] = []
    for item in parsed:
        reason = _drop_reason(
            item,
            now=now,
            pose_valid=pose_valid,
            pose_epoch=pose_epoch,
            map_id=map_id,
            nav_map_id=nav_map_id,
            nav_epoch=nav_epoch,
            current_epoch=current_epoch,
            snapshot_id=snapshot_id,
        )
        if reason is None:
            kept.append(_text(item.get("candidate_id"), "candidate_id"))
        else:
            reasons.append(reason)
    unique = tuple(dict.fromkeys(reasons))
    drop = unique[0] if len(unique) == 1 else ("mixed" if unique else "")
    return tuple(kept), drop


def _drop_reason(
    item: Mapping[str, object],
    *,
    now: datetime,
    pose_valid: bool,
    pose_epoch: int | None,
    map_id: str | None,
    nav_map_id: str | None,
    nav_epoch: int,
    current_epoch: int,
    snapshot_id: str,
) -> str | None:
    if item.get("safe") is not True:
        return "unsafe"
    if item.get("frame_id") != BODY_FRAME:
        return "frame"
    if item.get("snapshot_id") != snapshot_id:
        return "snapshot"
    deadline = _time(item.get("valid_until"), "valid_until")
    if deadline <= now:
        return "expired"
    if not pose_valid or pose_epoch is None or map_id is None:
        return "map_epoch"
    candidate_epoch = item.get("map_epoch")
    if (
        candidate_epoch != pose_epoch
        or candidate_epoch != nav_epoch
        or candidate_epoch != current_epoch
    ):
        return "map_epoch"
    if item.get("map_id") != map_id or nav_map_id != map_id:
        return "map_id"
    return None


def _parse_candidates(
    raw: tuple[object, ...],
    snapshot_id: str,
) -> tuple[tuple[Mapping[str, object], ...], bool]:
    parsed: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for item in raw:
        body = _exact(_as_map(item, "candidate"), CANDIDATE_KEYS | TARGET_RANGE_KEYS, "candidate")
        if TARGET_RANGE_KEYS.intersection(body):
            return (), True
        _exact(body, CANDIDATE_KEYS, "candidate")
        identifier = _text(body.get("candidate_id"), "candidate_id")
        if identifier in seen:
            raise fault("invalid_input", "candidate ids must be unique")
        seen.add(identifier)
        if body.get("snapshot_id") != snapshot_id:
            pass
        _text(body.get("snapshot_id"), "candidate snapshot_id")
        _text(body.get("frame_id"), "candidate frame_id")
        _map_id(body.get("map_id"), "candidate map_id")
        _epoch_value(body.get("map_epoch"), "candidate map_epoch")
        _number(body.get("delta_x_m"), "delta_x_m")
        _number(body.get("delta_y_m"), "delta_y_m")
        _number(body.get("delta_yaw_rad"), "delta_yaw_rad")
        _bool(body.get("safe"), "candidate safe")
        if body.get("clearance_m") is not None:
            clearance = _number(body.get("clearance_m"), "clearance_m")
            if clearance < 0:
                raise fault("invalid_input", "clearance_m must be zero or greater")
        _time(body.get("valid_until"), "valid_until")
        parsed.append(body)
    return tuple(parsed), False


def _candidate_list(value: object) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise fault("invalid_input", "candidates must be a list")
    if len(value) > 16:
        raise fault("invalid_input", "candidates exceed 16")
    return tuple(value)


def _arms(capabilities: Mapping[str, object], device_id: str) -> tuple[bool, bool]:
    body = _exact(
        _as_map(capabilities["payload"], "capabilities payload"),
        CAPABILITY_KEYS,
        "capabilities payload",
    )
    if body.get("device_id") != device_id:
        raise fault("contract_mismatch", "capabilities name a different device")
    if body.get("role") != "dog":
        raise fault("contract_mismatch", "capabilities role must be dog")
    if body.get("validated") is not True:
        return False, False
    features = _exact(_as_map(body.get("features"), "features"), FEATURE_KEYS, "features")
    lidar = features.get("lidar")
    slam = features.get("slam")
    if not isinstance(lidar, bool) or not isinstance(slam, bool):
        raise fault("invalid_input", "lidar and slam flags must be booleans")
    for key, value in features.items():
        if not isinstance(value, bool):
            raise fault("invalid_input", f"{key} must be a boolean")
    return slam is True, lidar is True


def _pose(value: object) -> tuple[Mapping[str, object] | None, int | None, str | None, bool]:
    if value is None:
        return None, None, None, False
    body = _exact(_as_map(value, "pose"), POSE_KEYS, "pose")
    _text(body.get("frame_id"), "pose frame_id")
    map_id = _map_id(body.get("map_id"), "pose map_id")
    epoch = _epoch_value(body.get("map_epoch"), "pose map_epoch")
    for key in ("x_m", "y_m", "z_m", "yaw_rad"):
        _number(body.get(key), key)
    _time(body.get("observed_at"), "pose observed_at")
    valid = _bool(body.get("valid"), "pose valid")
    return body, epoch, map_id, valid and map_id is not None


def _frame(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    body = _exact(_as_map(value, "frame"), FRAME_KEYS, "frame")
    _text(body.get("frame_id"), "frame_id")
    _text(body.get("image_ref"), "image_ref")
    digest = body.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise fault("invalid_input", "frame sha256 is not a 64 character digest")
    _time(body.get("captured_at"), "captured_at")
    if body.get("camera_id") not in {"front", "downward"}:
        raise fault("invalid_input", "camera_id is not a dog camera")
    _epoch_value(body.get("camera_epoch"), "camera_epoch")
    for key in ("width_px", "height_px"):
        size = body.get(key)
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise fault("invalid_input", f"{key} must be a positive integer")
    _text(body.get("camera_frame_id"), "camera_frame_id")
    calibration = body.get("camera_to_body_calibration_id")
    if calibration is not None:
        _text(calibration, "camera_to_body_calibration_id")
    _bool(body.get("simulated"), "frame simulated")
    return freeze_map(dict(body))


def _correlation(
    observation: Mapping[str, object],
    candidates: Mapping[str, object],
    map_epoch: int | None,
    frame: Mapping[str, object] | None,
) -> Mapping[str, object]:
    payload = observation.get("payload")
    command_id = None
    if isinstance(payload, Mapping):
        command_id = payload.get("active_command_id")
    frame_id = None if frame is None else frame.get("frame_id")
    camera_epoch = None if frame is None else frame.get("camera_epoch")
    return freeze_map(
        {
            "message_id": observation.get("message_id"),
            "candidates_message_id": candidates.get("message_id"),
            "mission_id": observation.get("mission_id"),
            "epoch": observation.get("epoch"),
            "command_id": command_id,
            "frame_id": frame_id,
            "track_id": None,
            "beacon_epoch": None,
            "map_epoch": map_epoch,
            "camera_epoch": camera_epoch,
        }
    )


def _envelope(value: object, kind: str) -> Mapping[str, object]:
    body = _exact(_as_map(value, kind), ENVELOPE_KEYS, kind)
    if body.get("protocol_version") != "2.0-draft":
        raise fault("contract_mismatch", f"{kind} protocol_version is not 2.0-draft")
    if body.get("kind") != kind:
        raise fault("contract_mismatch", f"expected kind {kind}")
    if body.get("source") != "dog" or body.get("destination") != "ground":
        raise fault("contract_mismatch", f"{kind} is not a dog-to-ground message")
    _text(body.get("message_id"), "message_id")
    _text(body.get("mission_id"), "mission_id")
    _epoch_value(body.get("epoch"), "epoch")
    _epoch_value(body.get("seq"), "seq")
    _time(body.get("sent_at"), "sent_at")
    if body.get("correlation_id") is not None:
        _text(body.get("correlation_id"), "correlation_id")
    if body.get("expires_at") is not None:
        _time(body.get("expires_at"), "expires_at")
    _bool(body.get("simulated"), "simulated")
    return body


def _profile_transport(payload: Mapping[str, object]) -> str:
    found: list[str] = []
    profile = payload.get("profile")
    if profile is not None:
        body = _exact(_as_map(profile, "profile"), PROFILE_KEYS, "profile")
        found.append(_transport_value(body.get("dog_transport"), "profile dog_transport"))
    settings = payload.get("settings")
    if isinstance(settings, GroundSettings):
        found.append(_transport_value(settings.dog_transport, "settings dog_transport"))
    elif settings is not None:
        body = _as_map(settings, "settings")
        found.append(_transport_value(body.get("dog_transport"), "settings dog_transport"))
    if not found:
        raise fault("invalid_input", "selected dog transport profile is required")
    if any(item != found[0] for item in found):
        raise fault("invalid_input", "dog transport profile conflicts with settings")
    return found[0]


def _blocked(
    reason: str,
    code: str,
    detail: str,
    **kwargs: object,
) -> NavDecision:
    return _terminal("blocked", reason, code, detail, **kwargs)


def _failed_decision(
    reason: str,
    code: str,
    detail: str,
    **kwargs: object,
) -> NavDecision:
    return _terminal("failed", reason, code, detail, **kwargs)


def _terminal(
    status: str,
    reason: str,
    code: str,
    detail: str,
    **kwargs: object,
) -> NavDecision:
    standing = kwargs.get("standing")
    stationary = kwargs.get("stationary")
    avoidance = kwargs.get("avoidance")
    return NavDecision(
        status=status,
        reason=reason,
        error_code=code,
        error_detail=detail,
        recovery_required=False,
        standing=standing if isinstance(standing, bool) or standing is None else None,
        stationary=stationary if isinstance(stationary, bool) or stationary is None else None,
        avoidance=avoidance if isinstance(avoidance, bool) or avoidance is None else None,
        navigation_mode=str(kwargs.get("navigation_mode") or ""),
        slam_state=str(kwargs.get("slam_state") or ""),
        minimum_clearance_m=_optional_float(kwargs.get("minimum_clearance_m")),
        candidate_ids=(),
        blocked=kwargs.get("blocked") is True,
        ready=False,
        ready_to_wait=False,
        map_id=_text_or_none(kwargs.get("map_id")),
        map_epoch=_epoch_or_none(kwargs.get("map_epoch")),
        pose_epoch=_epoch_or_none(kwargs.get("pose_epoch")),
        transport=str(kwargs.get("transport") or ""),
        profile_transport=str(kwargs.get("profile_transport") or ""),
        frame=_frame_or_none(kwargs.get("frame")),
        dropped="",
        withheld="",
        correlation=_as_map(kwargs.get("correlation"), "correlation"),
    )


def _frame_or_none(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _text_or_none(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _epoch_or_none(value: object) -> int | None:
    if type(value) is int:
        return value
    return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _reject_target_range(body: Mapping[str, object], label: str) -> None:
    found = TARGET_RANGE_KEYS.intersection(body)
    if found:
        raise fault("rejected", f"{label} included a target range")


def _exact(
    value: Mapping[str, object],
    allowed: frozenset[str],
    label: str,
) -> Mapping[str, object]:
    unknown = [key for key in value if key not in allowed]
    if unknown:
        raise fault("invalid_input", f"{label} has an unknown field: {', '.join(sorted(unknown))}")
    return value


def _as_map(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise fault("invalid_input", f"{label} must be an object")
    return value


def _tri(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise fault("invalid_input", f"{label} must be true, false, or null")


def _bool(value: object, label: str) -> bool:
    if isinstance(value, bool):
        return value
    raise fault("invalid_input", f"{label} must be a boolean")


def _choice(value: object, allowed: frozenset[str], label: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    raise fault("invalid_input", f"{label} is not an accepted value")


def _text(value: object, label: str) -> str:
    if isinstance(value, str) and value.strip() and len(value) <= 160:
        return value
    raise fault("invalid_input", f"{label} must be a short string")


def _map_id(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _epoch_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise fault("invalid_input", f"{label} must be a non-negative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise fault("invalid_input", f"{label} must be finite")
    return number


def _clearance(value: object) -> float | None:
    if value is None:
        return None
    number = _number(value, "minimum_clearance_m")
    if number < 0:
        raise fault("invalid_input", "minimum_clearance_m must be zero or greater")
    return number


def _transport_value(value: object, label: str) -> str:
    if isinstance(value, str) and value in TRANSPORTS:
        return value
    raise fault("invalid_input", f"{label} must be ethernet or wifi")


def _time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise fault("invalid_input", f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise fault("invalid_input", f"{label} must be a timestamp") from exc
    if parsed.tzinfo is None:
        raise fault("invalid_input", f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _flag(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "null"


def _clearance_text(value: float | None) -> str:
    if value is None:
        return "none"
    return format(value, ".12g")


def _epoch_text(value: int | None) -> str:
    if value is None:
        return "none"
    return str(value)
