"""Stable-beacon policy. RSSI samples are labeled, never scored."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_beacon"
SCHEMA = "ground-task-v2"
HOLD_STATES = frozenset({"stable", "moving", "unknown"})
FLIGHT_STATES = frozenset({"grounded", "airborne", "unknown"})
REPOSITION = frozenset({"search_step", "track_step"})
TRANSITIONS = frozenset({"takeoff", "land"})
DRONE_ACTIONS = REPOSITION | TRANSITIONS | {"hover"}
RUNNING = frozenset({"accepted", "running"})
COMMAND_STATUSES = RUNNING | {"completed"}
REQUEST_KEYS = frozenset(
    {
        "armed_bssid",
        "observation",
        "beacon",
        "flight_state",
        "drone_command",
        "drone_command_status",
        "drone_command_running",
        "previous_beacon_epoch",
        "beacon_moved",
        "windows",
        "map_epoch",
        "track_id",
    }
)
BEACON_KEYS = frozenset(
    {
        "beacon_id",
        "bssid",
        "ssid",
        "beacon_epoch",
        "hold_state",
        "verified_at",
        "hold_valid_until",
    }
)
_BSSID = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")


@dataclass(frozen=True)
class BeaconDecision:
    status: str
    reason: str
    error_code: str | None
    error_detail: str | None
    recovery_required: bool
    hold_state: str
    reported_hold_state: str
    dog_motion_allowed: bool
    dispatch_allowed: bool
    comparisons_allowed: bool
    beacon_epoch: int | None
    prior_epoch: int | None
    commanded_epoch: int | None
    epoch_required: int | None
    comparable_epoch: int | None
    flight_state: str
    beacon_id: str
    bssid: str
    armed_bssid: str
    windows: tuple[Mapping[str, object], ...]
    correlation: Mapping[str, object]

    def public_data(self) -> Mapping[str, object]:
        return freeze_map(
            {
                "hold_state": self.hold_state,
                "reported_hold_state": self.reported_hold_state,
                "dog_motion_allowed": self.dog_motion_allowed,
                "dispatch_allowed": self.dispatch_allowed,
                "comparisons_allowed": self.comparisons_allowed,
                "beacon_epoch": self.beacon_epoch,
                "prior_epoch": self.prior_epoch,
                "commanded_epoch": self.commanded_epoch,
                "epoch_required": self.epoch_required,
                "comparable_epoch": self.comparable_epoch,
                "flight_state": self.flight_state,
                "beacon_id": self.beacon_id,
                "bssid": self.bssid,
                "armed_bssid": self.armed_bssid,
                "reason": self.reason,
                "windows": self.windows,
            }
        )


def assess(now: datetime, payload: Mapping[str, object]) -> BeaconDecision:
    """Decide whether the current beacon hold may guide the dog."""
    if now.tzinfo is None:
        raise fault("invalid_input", "clock time must be timezone-aware")
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Mapping):
        raise fault("invalid_input", "beacon request payload must be a mapping")
    unknown = [key for key in payload if key not in REQUEST_KEYS]
    if unknown:
        raise fault("invalid_input", "unknown beacon input: " + ", ".join(sorted(unknown)))
    armed = _bssid(payload.get("armed_bssid"), "armed_bssid")
    observation = _mapping(payload.get("observation"), "observation")
    envelope = observation
    body = _unwrap(observation, "drone.observation")
    beacon = _beacon(payload.get("beacon"), body)
    flight = _flight(payload.get("flight_state"), body)
    reported = _choice(beacon.get("hold_state"), HOLD_STATES, "hold_state")
    observed_epoch = _whole(beacon.get("beacon_epoch"), "beacon_epoch")
    opened = _instant(beacon.get("verified_at"), "verified_at")
    closes = _instant(beacon.get("hold_valid_until"), "hold_valid_until")
    if opened > closes:
        raise fault("invalid_input", "hold window ends before it starts")
    identity = _text(beacon.get("beacon_id"), "beacon_id")
    ssid = beacon.get("ssid")
    if not isinstance(ssid, str) or not ssid.strip():
        raise fault("invalid_input", "ssid must be a non-empty string")
    radio = _bssid(beacon.get("bssid"), "bssid")
    prior = _optional_whole(payload.get("previous_beacon_epoch"), "previous_beacon_epoch")
    command, status, running, moved = _command(payload)
    correlation = _correlation(
        envelope,
        body,
        command,
        observed_epoch,
        payload.get("track_id"),
        payload.get("map_epoch"),
    )
    if radio != armed:
        return _decision(
            status="blocked",
            reason="bssid_mismatch",
            error_code="rejected",
            error_detail="beacon BSSID does not match the armed drone",
            hold_state=reported,
            reported=reported,
            allowed=False,
            comparisons=False,
            observed=observed_epoch,
            prior=prior,
            commanded=command.epoch if command is not None else None,
            required=None,
            comparable=None,
            flight=flight,
            beacon_id=identity,
            bssid=radio,
            armed=armed,
            windows=_views(
                payload.get("windows"),
                mode="rejected",
                comparisons=False,
                required=None,
                current=observed_epoch,
                bssid=radio,
            ),
            correlation=correlation,
        )
    if (
        _active_command(body)
        and command is None
        and not running
        and "drone_command_running" not in payload
    ):
        running = True
    if running and command is None:
        return _blocked_motion(
            reason="command_unspecified",
            hold_state="unknown",
            reported=reported,
            observed=observed_epoch,
            prior=prior,
            commanded=None,
            flight=flight,
            beacon_id=identity,
            bssid=radio,
            armed=armed,
            windows=_views(
                payload.get("windows"),
                mode="withheld",
                comparisons=False,
                required=None,
                current=observed_epoch,
                bssid=radio,
            ),
            correlation=correlation,
        )
    if running and command is not None and command.action in REPOSITION:
        return _blocked_motion(
            reason="running_reposition",
            hold_state="moving",
            reported=reported,
            observed=observed_epoch,
            prior=prior,
            commanded=command.epoch,
            flight=flight,
            beacon_id=identity,
            bssid=radio,
            armed=armed,
            windows=_views(
                payload.get("windows"),
                mode="suspended",
                comparisons=False,
                required=None,
                current=observed_epoch,
                bssid=radio,
            ),
            correlation=correlation,
        )
    if running and command is not None and command.action in TRANSITIONS:
        return _blocked_motion(
            reason="aircraft_transition",
            hold_state="unknown",
            reported=reported,
            observed=observed_epoch,
            prior=prior,
            commanded=command.epoch,
            flight=flight,
            beacon_id=identity,
            bssid=radio,
            armed=armed,
            windows=_views(
                payload.get("windows"),
                mode="withheld",
                comparisons=False,
                required=None,
                current=observed_epoch,
                bssid=radio,
            ),
            correlation=correlation,
        )
    required = _required_epoch(
        command=command,
        status=status,
        running=running,
        moved=moved,
        prior=prior,
        observed=observed_epoch,
    )
    pending = required is not None and observed_epoch < required
    expired = now > closes
    reason = _reason(
        pending=pending,
        flight=flight,
        expired=expired,
        reported=reported,
    )
    allowed = reason == "stable_hold"
    comparable: int | None = observed_epoch if allowed else None
    return _decision(
        status="ok",
        reason=reason,
        error_code=None,
        error_detail=None,
        hold_state=reported,
        reported=reported,
        allowed=allowed,
        comparisons=allowed,
        observed=observed_epoch,
        prior=prior,
        commanded=None if command is None else command.epoch,
        required=required if pending else None,
        comparable=comparable,
        flight=flight,
        beacon_id=identity,
        bssid=radio,
        armed=armed,
        windows=_views(
            payload.get("windows"),
            mode="compare" if allowed else "withheld",
            comparisons=allowed,
            required=required,
            current=observed_epoch,
            bssid=radio,
        ),
        correlation=correlation,
    )


@dataclass(frozen=True)
class _Command:
    action: str
    epoch: int | None
    command_id: str | None
    track_id: str | None


def trace_of(decision: BeaconDecision) -> tuple[str, ...]:
    items = [
        f"hold:{decision.hold_state}",
        f"dog_motion_allowed:{str(decision.dog_motion_allowed).lower()}",
        f"reason:{decision.reason}",
    ]
    if decision.beacon_epoch is not None:
        items.append(f"beacon_epoch:{decision.beacon_epoch}")
    if decision.prior_epoch is not None:
        items.append(f"prior_epoch:{decision.prior_epoch}")
    if decision.commanded_epoch is not None:
        items.append(f"commanded_epoch:{decision.commanded_epoch}")
    if decision.epoch_required is not None:
        items.append(f"required_epoch:{decision.epoch_required}")
    if decision.comparable_epoch is not None:
        items.append(f"comparable_epoch:{decision.comparable_epoch}")
    for window in decision.windows:
        items.append(f"window:{window['window_id']}:{window['label']}:retained")
    items.append("dog_command:none")
    return tuple(items)


def _decision(
    *,
    status: str,
    reason: str,
    error_code: str | None,
    error_detail: str | None,
    hold_state: str,
    reported: str,
    allowed: bool,
    comparisons: bool,
    observed: int,
    prior: int | None,
    commanded: int | None,
    required: int | None,
    comparable: int | None,
    flight: str,
    beacon_id: str,
    bssid: str,
    armed: str,
    windows: tuple[Mapping[str, object], ...],
    correlation: Mapping[str, object],
) -> BeaconDecision:
    return BeaconDecision(
        status=status,
        reason=reason,
        error_code=error_code,
        error_detail=error_detail,
        recovery_required=False,
        hold_state=hold_state,
        reported_hold_state=reported,
        dog_motion_allowed=allowed,
        dispatch_allowed=allowed,
        comparisons_allowed=comparisons,
        beacon_epoch=observed,
        prior_epoch=prior,
        commanded_epoch=commanded,
        epoch_required=required,
        comparable_epoch=comparable,
        flight_state=flight,
        beacon_id=beacon_id,
        bssid=bssid,
        armed_bssid=armed,
        windows=windows,
        correlation=correlation,
    )


def _blocked_motion(
    *,
    reason: str,
    hold_state: str,
    reported: str,
    observed: int,
    prior: int | None,
    commanded: int | None,
    flight: str,
    beacon_id: str,
    bssid: str,
    armed: str,
    windows: tuple[Mapping[str, object], ...],
    correlation: Mapping[str, object],
) -> BeaconDecision:
    return _decision(
        status="ok",
        reason=reason,
        error_code=None,
        error_detail=None,
        hold_state=hold_state,
        reported=reported,
        allowed=False,
        comparisons=False,
        observed=observed,
        prior=prior,
        commanded=commanded,
        required=None,
        comparable=None,
        flight=flight,
        beacon_id=beacon_id,
        bssid=bssid,
        armed=armed,
        windows=windows,
        correlation=correlation,
    )


def _active_command(body: Mapping[str, object]) -> bool:
    if "active_command_id" not in body:
        return False
    active = body.get("active_command_id")
    if active is None:
        return False
    if not isinstance(active, str) or not active.strip():
        raise fault("invalid_input", "active_command_id must be a non-empty string or null")
    return True


def _reason(*, pending: bool, flight: str, expired: bool, reported: str) -> str:
    if pending:
        return "epoch_pending"
    if flight == "unknown":
        return "flight_unknown"
    if flight == "grounded":
        return "grounded"
    if expired:
        return "expired"
    if reported == "moving":
        return "moving"
    if reported == "unknown":
        return "hold_unknown"
    return "stable_hold"


def _required_epoch(
    *,
    command: _Command | None,
    status: str | None,
    running: bool,
    moved: bool | None,
    prior: int | None,
    observed: int,
) -> int | None:
    if command is None or running or status != "completed":
        return None
    reposition = command.action in REPOSITION
    hover_moved = command.action == "hover" and moved is True
    if not reposition and not hover_moved:
        return None
    baseline = prior if prior is not None else observed
    floor = baseline + 1
    if command.epoch is not None and command.epoch > floor:
        return command.epoch
    return floor


def _command(
    payload: Mapping[str, object],
) -> tuple[_Command | None, str | None, bool, bool | None]:
    raw = payload.get("drone_command")
    status = payload.get("drone_command_status", None)
    flag = payload.get("drone_command_running", None)
    moved = payload.get("beacon_moved", None)
    if flag is not None:
        flag = _bool(flag, "drone_command_running")
    if moved is not None:
        moved = _bool(moved, "beacon_moved")
    if status is not None and status not in COMMAND_STATUSES:
        raise fault("invalid_input", "drone_command_status is not a command lifecycle state")
    if not isinstance(status, str) and status is not None:
        raise fault("invalid_input", "drone_command_status is not a command lifecycle state")
    if raw is None:
        if flag is True:
            return None, None, True, moved
        return None, None, False, moved
    body = _unwrap(_mapping(raw, "drone_command"), "drone.command")
    action = body.get("action")
    if action not in DRONE_ACTIONS:
        raise fault("invalid_input", "drone command action is not a beacon-relevant primitive")
    epoch_value = body.get("beacon_epoch", None)
    epoch = None if epoch_value is None else _whole(epoch_value, "command beacon_epoch")
    command_id = body.get("command_id")
    if command_id is not None and (not isinstance(command_id, str) or not command_id.strip()):
        raise fault("invalid_input", "command_id must be a non-empty string")
    track = body.get("track_id")
    if track is not None and not isinstance(track, str):
        raise fault("invalid_input", "track_id must be a string")
    if status is None:
        raise fault("invalid_input", "drone_command_status is required with a drone command")
    running = status in RUNNING
    if flag is True and status == "completed":
        raise fault("invalid_input", "a completed drone command is not running")
    if flag is False and running:
        raise fault("invalid_input", "drone_command_running contradicts the command status")
    return (
        _Command(
            str(action),
            epoch,
            None if command_id is None else command_id.strip(),
            None if track is None else track,
        ),
        status,
        running,
        moved,
    )


def _views(
    value: object,
    *,
    mode: str,
    comparisons: bool,
    required: int | None,
    current: int,
    bssid: str,
) -> tuple[Mapping[str, object], ...]:
    rows = _window_rows(value)
    labeled: list[Mapping[str, object]] = []
    for row in rows:
        comparable, label = _window_label(
            row,
            mode=mode,
            comparisons=comparisons,
            required=required,
            current=current,
            bssid=bssid,
        )
        labeled.append(
            freeze_map(
                {
                    "window_id": row["window_id"],
                    "beacon_epoch": row["beacon_epoch"],
                    "bssid": row["bssid"],
                    "comparable": comparable,
                    "label": label,
                    "retained": True,
                }
            )
        )
    return tuple(labeled)


def _window_label(
    row: Mapping[str, object],
    *,
    mode: str,
    comparisons: bool,
    required: int | None,
    current: int,
    bssid: str,
) -> tuple[bool, str]:
    epoch = row["beacon_epoch"]
    radio = row["bssid"]
    if not isinstance(epoch, int) or not isinstance(radio, str):
        raise fault("invalid_input", "window identity is incomplete")
    if radio != bssid or mode == "rejected":
        return False, "invalid"
    if required is not None and epoch < required:
        return False, "invalid"
    if not comparisons:
        if mode == "suspended":
            return False, "suspended"
        return False, "withheld"
    if epoch == current:
        return True, "current"
    return False, "invalid"


def _window_rows(value: object) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise fault("invalid_input", "windows must be a list")
    rows: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, (str, bytes)) or not isinstance(item, Mapping):
            raise fault("invalid_input", "each window must be an object")
        window_id = _text(item.get("window_id"), "window_id")
        epoch = _whole(item.get("beacon_epoch"), "window beacon_epoch")
        radio = _bssid(item.get("bssid"), "window bssid")
        rows.append(freeze_map({"window_id": window_id, "beacon_epoch": epoch, "bssid": radio}))
    return tuple(rows)


def _correlation(
    envelope: Mapping[str, object],
    body: Mapping[str, object],
    command: _Command | None,
    beacon_epoch: int,
    track_override: object,
    map_override: object,
) -> Mapping[str, object]:
    found: dict[str, object] = {"beacon_epoch": beacon_epoch}
    _copy_text(found, envelope, "message_id")
    _copy_text(found, envelope, "mission_id")
    _copy_whole(found, envelope, "epoch")
    frame = body.get("frame")
    if frame is not None:
        frame_map = _mapping(frame, "frame")
        _copy_text(found, frame_map, "frame_id")
        _copy_whole(found, frame_map, "camera_epoch")
    if command is not None and command.command_id is not None:
        found["command_id"] = command.command_id
    track = track_override if track_override is not None else None
    if track is None and command is not None:
        track = command.track_id
    if track is not None:
        if not isinstance(track, str) or not track.strip():
            raise fault("invalid_input", "track_id must be a non-empty string")
        found["track_id"] = track.strip()
    map_epoch = map_override
    if map_epoch is not None:
        found["map_epoch"] = _whole(map_epoch, "map_epoch")
    return freeze_map(found)


def _copy_text(target: dict[str, object], source: Mapping[str, object], key: str) -> None:
    if key not in source or source[key] is None:
        return
    target[key] = _text(source[key], key)


def _copy_whole(target: dict[str, object], source: Mapping[str, object], key: str) -> None:
    if key not in source or source[key] is None:
        return
    target[key] = _whole(source[key], key)


def _beacon(override: object, body: Mapping[str, object]) -> Mapping[str, object]:
    raw = body.get("beacon") if override is None else override
    beacon = _mapping(raw, "beacon")
    extra = [key for key in beacon if key not in BEACON_KEYS]
    if extra:
        raise fault("invalid_input", "unknown beacon field: " + ", ".join(sorted(extra)))
    missing = [key for key in sorted(BEACON_KEYS) if key not in beacon]
    if missing:
        raise fault("invalid_input", "beacon is missing " + ", ".join(missing))
    return beacon


def _flight(override: object, body: Mapping[str, object]) -> str:
    raw = body.get("flight_state") if override is None else override
    return _choice(raw, FLIGHT_STATES, "flight_state")


def _unwrap(value: Mapping[str, object], kind: str) -> Mapping[str, object]:
    if "kind" not in value and "payload" not in value:
        return value
    if value.get("kind") != kind:
        raise fault("invalid_input", f"expected kind {kind}")
    payload = value.get("payload")
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Mapping):
        raise fault("invalid_input", "message payload must be an object")
    return payload


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise fault("invalid_input", f"{label} must be an object")
    return value


def _choice(value: object, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise fault("invalid_input", f"{label} is not an accepted value")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{label} must be a non-empty string")
    return value.strip()


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise fault("invalid_input", f"{label} must be a boolean")
    return value


def _whole(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise fault("invalid_input", f"{label} must be a non-negative integer")
    return value


def _optional_whole(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _whole(value, label)


def _bssid(value: object, label: str) -> str:
    if not isinstance(value, str) or _BSSID.fullmatch(value) is None:
        raise fault("invalid_input", f"{label} must be a MAC address")
    return value.lower()


def _instant(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{label} must be a UTC timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise fault("invalid_input", f"{label} must be a UTC timestamp") from exc
    if parsed.tzinfo is None:
        raise fault("invalid_input", f"{label} must include a timezone")
    return parsed.astimezone(UTC)
