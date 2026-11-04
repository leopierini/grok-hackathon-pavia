"""Validate a dog-mounted Pi RSSI window. This module does not open a radio or move the dog."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from patrol.ground.kernel.contracts import (
    BaseServices,
    FeaturePort,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_rssi"
SCHEMA = "ground-task-v2"
PROTOCOL = "2.0-draft"
_BSSID = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
_QUALITIES = frozenset({"valid", "noisy", "stale", "unavailable"})
_HOLDS = frozenset({"stable", "moving", "unknown"})
_ENVELOPE = frozenset(
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
_WINDOW = frozenset(
    {
        "receiver_id",
        "receiver_mount",
        "interface",
        "beacon_id",
        "bssid",
        "beacon_epoch",
        "window_start",
        "window_end",
        "clock_error_ms",
        "samples",
        "median_rssi_dbm",
        "spread_db",
        "quality",
    }
)
_SAMPLE = frozenset({"sample_id", "captured_at", "rssi_dbm", "pose"})
_POSE = frozenset(
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
_HEARTBEAT = frozenset(
    {"device_id", "uptime_ms", "clock_error_ms", "healthy", "last_observation_at"}
)
PROBE_NAMES = frozenset(
    {
        "example_window",
        "epoch_changed",
        "bssid_swapped",
        "no_signal",
        "sentinel_zero",
        "clock_error",
        "stale_heartbeat",
        "foreign_map",
        "moving_hold",
        "laptop_rssi",
    }
)
_TAIL = ("no_heading", "no_range", "no_socket", "no_dog_command")


class _Fail(Exception):
    def __init__(self, code: str, reason: str, short: str, marker: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.short = short
        self.marker = marker


def _bad(code: str, reason: str, marker: str) -> _Fail:
    return _Fail(code, reason, "rejected", marker)


def _gap(reason: str, marker: str = "incomparable") -> _Fail:
    return _Fail("epoch_mismatch", reason, "incomparable", marker)


@dataclass
class _Ctx:
    quality: str | None = None
    epoch: int | None = None
    beacon_epoch: int | None = None
    map_epoch: int | None = None
    mission_epoch: int | None = None
    median: object = None
    spread: object = None
    interface: str | None = None
    clock_error: object = None
    follow: bool = False
    comparable: bool = False
    within_limit: bool = True
    message_id: str | None = None
    mission_id: str | None = None
    receiver_id: str | None = None
    bssid: str | None = None
    beacon_id: str | None = None
    map_id: str | None = None
    armed_id: str | None = None
    sample_ids: tuple[str, ...] = ()
    samples: tuple[Mapping[str, object], ...] = ()
    include_stats: bool = False
    marker: str = ""


@dataclass(frozen=True)
class Outcome:
    status: str
    short: str
    reason: str
    code: str | None
    within_limit: bool
    data: Mapping[str, object]
    trace: tuple[str, ...]


class RssiFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if request.ticket is not None:
            try:
                self.services.kernel.authority.require_current(request.ticket)
            except GroundFault as exc:
                return _ticket_result(request.ticket, exc)
        if _is_probe(request):
            return _project(evaluate(scripted_payload(request.name)), request.ticket, probe=True)
        return _project(evaluate(request.payload), request.ticket, probe=False)


def create(services: BaseServices) -> FeaturePort:
    return RssiFeature(services)


def scripted_payload(case_id: str) -> dict[str, object]:
    if case_id not in PROBE_NAMES:
        raise fault("invalid_input", f"unknown rssi case {case_id}")
    window = _read("no-signal-window.json" if case_id == "no_signal" else "pi-rssi-window.json")
    heartbeat = _read("pi-heartbeat.json")
    beacon = _read("beacon-hold.json")
    navigation = _read("navigation.json")
    limits = _read("limits.json")
    if case_id == "epoch_changed":
        _body(window)["beacon_epoch"] = 2
    elif case_id == "bssid_swapped":
        _body(window)["bssid"] = "02:00:00:00:00:02"
    elif case_id == "sentinel_zero":
        body = _body(window)
        body["samples"] = []
        body["median_rssi_dbm"] = 0
        body["spread_db"] = None
        body["quality"] = "unavailable"
    elif case_id == "clock_error":
        _body(window)["clock_error_ms"] = 51
    elif case_id == "stale_heartbeat":
        limits["received_at"] = "2026-11-04T13:00:20.000Z"
    elif case_id == "foreign_map":
        _first_pose(window)["map_epoch"] = 2
    elif case_id == "moving_hold":
        beacon["hold_state"] = "moving"
    elif case_id == "laptop_rssi":
        window["source"] = "laptop"
    return {
        "window": window,
        "heartbeat": heartbeat,
        "beacon": beacon,
        "navigation": navigation,
        "limits": limits,
    }


def evaluate(payload: Mapping[str, object]) -> Outcome:
    ctx = _Ctx()
    try:
        _evaluate(payload, ctx)
    except _Fail as stopped:
        return _stopped(ctx, stopped)
    return _accept(ctx)


def _evaluate(payload: Mapping[str, object], ctx: _Ctx) -> None:
    window = _mapping(payload.get("window"), "window")
    beacon = _mapping(payload.get("beacon"), "beacon")
    navigation = _mapping(payload.get("navigation"), "navigation")
    limits = _mapping(payload.get("limits"), "limits")
    if "heartbeat" not in payload:
        raise _bad("rejected", "heartbeat is missing", "rejected:heartbeat")
    _load_context(ctx, beacon, navigation, limits)
    _load_window(ctx, window)
    _bind_identity(ctx, window, beacon)
    _read_signal(ctx, _mapping(window.get("payload"), "window payload"))
    _load_heartbeat(ctx, payload.get("heartbeat"), window, limits)
    _enforce_clock(ctx, limits)
    _compare_hold(ctx, beacon)


def _load_context(
    ctx: _Ctx,
    beacon: dict[str, object],
    navigation: dict[str, object],
    limits: dict[str, object],
) -> None:
    epoch = _integer(beacon.get("beacon_epoch"), "beacon_epoch", minimum=0)
    published = _integer(beacon.get("epoch"), "hold epoch", minimum=0)
    if published != epoch:
        raise _bad("invalid_input", "hold epoch does not match beacon_epoch", "rejected:field")
    hold = _token(beacon.get("hold_state"), "hold_state")
    if hold not in _HOLDS:
        raise _bad(
            "invalid_input",
            "hold_state is not stable, moving, or unknown",
            "rejected:field",
        )
    ctx.epoch = epoch
    ctx.map_epoch = _integer(navigation.get("map_epoch"), "map_epoch", minimum=0)
    ctx.map_id = _token(navigation.get("map_id"), "map_id")
    ctx.armed_id = _token(limits.get("armed_receiver_id"), "armed_receiver_id")
    _number(limits.get("clock_error_limit_ms"), "clock_error_limit_ms")
    _number(limits.get("heartbeat_max_age_ms"), "heartbeat_max_age_ms")
    _stamp(limits.get("received_at"), "received_at")


def _load_window(ctx: _Ctx, window: dict[str, object]) -> None:
    _require_keys(window, _ENVELOPE, "window envelope")
    if window.get("protocol_version") != PROTOCOL:
        raise _bad("invalid_input", "window protocol is not 2.0-draft", "rejected:envelope")
    if window.get("destination") != "ground":
        raise _bad("invalid_input", "window destination must be ground", "rejected:envelope")
    if not isinstance(window.get("simulated"), bool):
        raise _bad("invalid_input", "simulated must be a boolean", "rejected:field")
    source = window.get("source")
    kind = window.get("kind")
    if source == "laptop" or (isinstance(kind, str) and "laptop" in kind):
        raise _bad("rejected", "laptop RSSI is not a supported message", "rejected:laptop")
    if source != "pi" or kind != "rssi.window":
        raise _bad("rejected", "only a Pi rssi.window is accepted", "rejected:kind")
    ctx.message_id = _token(window.get("message_id"), "message_id")
    ctx.mission_id = _token(window.get("mission_id"), "mission_id")
    ctx.mission_epoch = _integer(window.get("epoch"), "mission epoch", minimum=0)
    _integer(window.get("seq"), "seq", minimum=0)
    _stamp(window.get("sent_at"), "sent_at")
    _optional_text(window.get("correlation_id"), "correlation_id")
    _optional_text(window.get("expires_at"), "expires_at")


def _load_heartbeat(
    ctx: _Ctx,
    heartbeat: object,
    window: dict[str, object],
    limits: dict[str, object],
) -> None:
    if heartbeat is None:
        raise _bad("rejected", "heartbeat is missing", "rejected:heartbeat")
    message = _mapping(heartbeat, "heartbeat")
    _require_keys(message, _ENVELOPE, "heartbeat envelope")
    if message.get("source") == "laptop":
        raise _bad("rejected", "laptop RSSI is not a supported message", "rejected:laptop")
    if message.get("source") != "pi" or message.get("kind") != "heartbeat":
        raise _bad("rejected", "heartbeat must come from the dog Pi", "rejected:heartbeat")
    if message.get("protocol_version") != PROTOCOL or message.get("destination") != "ground":
        raise _bad("invalid_input", "heartbeat envelope is not 2.0-draft", "rejected:envelope")
    if not isinstance(message.get("simulated"), bool):
        raise _bad("invalid_input", "heartbeat simulated must be a boolean", "rejected:field")
    if message.get("mission_id") != window.get("mission_id"):
        raise _bad("rejected", "heartbeat mission does not match the window", "rejected:heartbeat")
    if message.get("epoch") != window.get("epoch"):
        raise _bad(
            "rejected",
            "heartbeat mission epoch does not match the window",
            "rejected:heartbeat",
        )
    _integer(message.get("seq"), "heartbeat seq", minimum=0)
    _stamp(message.get("sent_at"), "heartbeat sent_at")
    body = _mapping(message.get("payload"), "heartbeat payload")
    _require_keys(body, _HEARTBEAT, "heartbeat payload")
    if body.get("device_id") != ctx.receiver_id:
        raise _bad("rejected", "heartbeat device does not match the receiver", "rejected:heartbeat")
    if body.get("healthy") is not True:
        if not isinstance(body.get("healthy"), bool):
            raise _bad("invalid_input", "healthy must be a boolean", "rejected:field")
        raise _bad("rejected", "heartbeat is unhealthy", "rejected:heartbeat")
    _integer(body.get("uptime_ms"), "uptime_ms", minimum=0)
    heart_clock = _number(body.get("clock_error_ms"), "heartbeat clock_error_ms")
    if float(heart_clock) < 0:
        raise _bad("invalid_input", "heartbeat clock_error_ms must be >= 0", "rejected:field")
    limit = _number(limits.get("clock_error_limit_ms"), "clock_error_limit_ms")
    if _exceeds(heart_clock, limit):
        ctx.clock_error = heart_clock
        ctx.within_limit = False
        raise _bad(
            "rejected",
            "heartbeat clock_error_ms exceeds the fixture limit",
            "rejected:clock_error",
        )
    observed = body.get("last_observation_at")
    if observed is None:
        observed = message.get("sent_at")
    age_limit = _number(limits.get("heartbeat_max_age_ms"), "heartbeat_max_age_ms")
    received = _stamp(limits.get("received_at"), "received_at")
    delta_ms = (received - _stamp(observed, "last_observation_at")).total_seconds() * 1000
    if delta_ms < -1e-6:
        raise _bad("rejected", "heartbeat is ahead of the receive time", "rejected:heartbeat")
    if delta_ms - float(age_limit) > 1e-6:
        ctx.within_limit = False
        raise _bad(
            "rejected",
            "heartbeat is older than the fixture limit",
            "rejected:stale_heartbeat",
        )


def _bind_identity(ctx: _Ctx, window: dict[str, object], beacon: dict[str, object]) -> None:
    body = _mapping(window.get("payload"), "window payload")
    _require_keys(body, _WINDOW, "window payload")
    if body.get("receiver_mount") != "dog":
        raise _bad("rejected", "receiver_mount must be dog", "rejected:receiver")
    receiver = _token(body.get("receiver_id"), "receiver_id")
    if receiver != ctx.armed_id:
        raise _bad("rejected", "receiver_id does not match the armed Pi", "rejected:receiver")
    ctx.receiver_id = receiver
    ctx.interface = _token(body.get("interface"), "interface")
    ctx.beacon_id = _token(body.get("beacon_id"), "beacon_id")
    if ctx.beacon_id != _token(beacon.get("beacon_id"), "armed beacon_id"):
        raise _bad("rejected", "beacon id does not match the armed beacon", "rejected:beacon_id")
    bssid = _token(body.get("bssid"), "bssid")
    if _BSSID.fullmatch(bssid) is None:
        raise _bad("invalid_input", "bssid must be six octets", "rejected:bssid")
    armed_bssid = _token(beacon.get("bssid"), "armed bssid")
    if _BSSID.fullmatch(armed_bssid) is None or bssid.casefold() != armed_bssid.casefold():
        raise _bad("rejected", "bssid does not match the armed beacon", "rejected:bssid")
    ctx.bssid = bssid
    _token(beacon.get("ssid"), "ssid")
    ctx.beacon_epoch = _integer(body.get("beacon_epoch"), "beacon_epoch", minimum=0)
    clock = _number(body.get("clock_error_ms"), "clock_error_ms")
    if float(clock) < 0:
        raise _bad("invalid_input", "clock_error_ms must be >= 0", "rejected:field")
    ctx.clock_error = clock
    start = _stamp(body.get("window_start"), "window_start")
    end = _stamp(body.get("window_end"), "window_end")
    if end < start:
        raise _bad("invalid_input", "window_end is before window_start", "rejected:window_time")


def _enforce_clock(ctx: _Ctx, limits: dict[str, object]) -> None:
    limit = _number(limits.get("clock_error_limit_ms"), "clock_error_limit_ms")
    clock = ctx.clock_error
    if isinstance(clock, bool) or not isinstance(clock, (int, float)):
        raise _bad("invalid_input", "clock_error_ms must be a number", "rejected:field")
    if _exceeds(clock, limit):
        ctx.within_limit = False
        raise _bad("rejected", "clock_error_ms exceeds the fixture limit", "rejected:clock_error")


def _read_signal(ctx: _Ctx, body: dict[str, object]) -> None:
    quality = body.get("quality")
    if not isinstance(quality, str) or quality not in _QUALITIES:
        raise _bad(
            "invalid_input",
            "quality is not valid, noisy, stale, or unavailable",
            "rejected:quality",
        )
    ctx.quality = quality
    ctx.median = _optional_number(body.get("median_rssi_dbm"), "median_rssi_dbm")
    ctx.spread = _optional_number(body.get("spread_db"), "spread_db")
    samples = body.get("samples")
    if not isinstance(samples, list):
        raise _bad("invalid_input", "samples must be a list", "rejected:field")
    if len(samples) > 100:
        raise _bad("invalid_input", "a window can carry at most 100 samples", "rejected:samples")
    empty = len(samples) == 0
    if empty and (ctx.median == 0 or ctx.spread == 0):
        raise _bad("rejected", "0 dBm is not a no-signal sentinel", "rejected:sentinel_zero")
    if quality == "unavailable":
        if not empty or ctx.median is not None or ctx.spread is not None:
            raise _bad(
                "rejected",
                "no-signal requires empty samples and null statistics",
                "rejected:quality",
            )
        ctx.samples = ()
        ctx.sample_ids = ()
        ctx.include_stats = True
        ctx.marker = "samples:0"
        return
    if empty:
        raise _bad("rejected", "this quality requires samples", "rejected:quality")
    parsed = _parse_samples(ctx, samples)
    reported_median = ctx.median
    reported_spread = ctx.spread
    if not isinstance(reported_median, (int, float)) or isinstance(reported_median, bool):
        raise _bad("invalid_input", "median_rssi_dbm is required", "rejected:median")
    if not isinstance(reported_spread, (int, float)) or isinstance(reported_spread, bool):
        raise _bad("invalid_input", "spread_db is required", "rejected:spread")
    if float(reported_spread) < 0:
        raise _bad("invalid_input", "spread_db must be >= 0", "rejected:spread")
    values = [float(cast(int | float, item["rssi_dbm"])) for item in parsed]
    if not _close(reported_median, _median(values)):
        raise _bad("rejected", "reported median does not match the samples", "rejected:median")
    if not _close(reported_spread, _spread(values)):
        raise _bad("rejected", "reported spread does not match the samples", "rejected:spread")
    ctx.samples = tuple(parsed)
    ctx.sample_ids = tuple(str(item["sample_id"]) for item in parsed)
    ctx.include_stats = True
    ctx.marker = ""


def _parse_samples(ctx: _Ctx, samples: list[object]) -> list[Mapping[str, object]]:
    parsed: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for index, raw in enumerate(samples):
        sample = _mapping(raw, f"sample {index}")
        _require_keys(sample, _SAMPLE, f"sample {index}")
        sample_id = _token(sample.get("sample_id"), "sample_id")
        if sample_id in seen:
            raise _bad("rejected", "duplicate sample_id", "rejected:sample_id")
        seen.add(sample_id)
        _stamp(sample.get("captured_at"), "captured_at")
        rssi = _number(sample.get("rssi_dbm"), "rssi_dbm")
        if float(rssi) < -150 or float(rssi) > 0:
            raise _bad("rejected", "rssi_dbm must be from -150 to 0", "rejected:rssi")
        pose = _freeze_pose(ctx, _mapping(sample.get("pose"), "pose"))
        parsed.append(
            freeze_map(
                {
                    "sample_id": sample_id,
                    "captured_at": sample.get("captured_at"),
                    "rssi_dbm": rssi,
                    "pose": pose,
                }
            )
        )
    return parsed


def _freeze_pose(ctx: _Ctx, pose: dict[str, object]) -> Mapping[str, object]:
    _require_keys(pose, _POSE, "pose")
    if pose.get("valid") is not True:
        if not isinstance(pose.get("valid"), bool):
            raise _bad("invalid_input", "pose valid must be a boolean", "rejected:field")
        raise _bad("rejected", "sample pose is not valid", "rejected:pose")
    map_epoch = _integer(pose.get("map_epoch"), "pose map_epoch", minimum=0)
    if map_epoch != ctx.map_epoch:
        raise _bad("rejected", "sample pose is on another map epoch", "rejected:map_epoch")
    map_id = pose.get("map_id")
    if map_id is not None and map_id != ctx.map_id:
        raise _bad("rejected", "sample pose is on another map", "rejected:map_epoch")
    _token(pose.get("frame_id"), "frame_id")
    for label in ("x_m", "y_m", "z_m", "yaw_rad"):
        _number(pose.get(label), label)
    _stamp(pose.get("observed_at"), "observed_at")
    return freeze_map(dict(pose))


def _compare_hold(ctx: _Ctx, beacon: dict[str, object]) -> None:
    hold = beacon.get("hold_state")
    if hold == "moving":
        raise _gap("beacon epoch was moving", "hold:moving")
    if hold != "stable":
        raise _gap("beacon hold is unknown", "hold:unknown")
    if ctx.beacon_epoch != ctx.epoch:
        raise _gap("beacon epoch does not match the current hold")


def _accept(ctx: _Ctx) -> Outcome:
    if ctx.quality == "valid":
        ctx.comparable = True
        ctx.follow = True
        short = "comparable"
        reason = "window matches the armed beacon, hold epoch, and dog map"
    elif ctx.quality == "unavailable":
        short = "no_signal"
        reason = "no signal; statistics stay null"
    else:
        short = "observation"
        reason = f"quality {ctx.quality} must not be followed"
    return _finish(ctx, "ok", short, reason, None)


def _stopped(ctx: _Ctx, stopped: _Fail) -> Outcome:
    ctx.comparable = False
    ctx.follow = False
    ctx.marker = stopped.marker
    status = "blocked" if stopped.short == "incomparable" else "failed"
    return _finish(ctx, status, stopped.short, stopped.reason, stopped.code)


def _finish(
    ctx: _Ctx,
    status: str,
    short: str,
    reason: str,
    code: str | None,
) -> Outcome:
    data: dict[str, object] = {
        "detail": short,
        "reason": reason,
        "comparable": ctx.comparable,
        "follow": ctx.follow,
        "quality": ctx.quality,
        "epoch": ctx.epoch,
        "mission_epoch": ctx.mission_epoch,
        "beacon_epoch": ctx.beacon_epoch,
        "map_epoch": ctx.map_epoch,
        "interface": ctx.interface,
        "clock_error_ms": ctx.clock_error,
        "message_id": ctx.message_id,
        "mission_id": ctx.mission_id,
        "receiver_id": ctx.receiver_id,
        "bssid": ctx.bssid,
        "beacon_id": ctx.beacon_id,
        "sample_ids": ctx.sample_ids,
    }
    if ctx.include_stats and status == "ok":
        data["median_rssi_dbm"] = ctx.median
        data["spread_db"] = ctx.spread
        data["samples"] = ctx.samples
    return Outcome(
        status=status,
        short=short,
        reason=reason,
        code=code,
        within_limit=ctx.within_limit,
        data=freeze_map(data),
        trace=_trace(ctx),
    )


def _trace(ctx: _Ctx) -> tuple[str, ...]:
    rows = [
        f"quality:{ctx.quality if ctx.quality is not None else 'none'}",
        f"epoch:{ctx.epoch if ctx.epoch is not None else 'missing'}",
    ]
    if ctx.beacon_epoch is not None:
        rows.append(f"beacon_epoch:{ctx.beacon_epoch}")
    if ctx.map_epoch is not None:
        rows.append(f"map_epoch:{ctx.map_epoch}")
    rows.append(f"median:{_fmt(ctx.median)}")
    rows.append(f"spread:{_fmt(ctx.spread)}")
    if ctx.interface is not None:
        rows.append(f"interface:{ctx.interface}")
    if ctx.clock_error is not None:
        rows.append(f"clock_error_ms:{_fmt(ctx.clock_error)}")
    rows.append("follow:true" if ctx.follow else "follow:false")
    if ctx.marker:
        rows.append(ctx.marker)
    rows.extend(_TAIL)
    return tuple(rows)


def _project(outcome: Outcome, ticket: Ticket | None, *, probe: bool) -> FeatureResult:
    data = _foundation(outcome) if probe else outcome.data
    error = None
    if outcome.status != "ok":
        if outcome.code is None:
            raise fault("internal", "rejection is missing an error code")
        recovery = outcome.code in {"cancelled", "expired_deadline", "io_fault", "timeout"}
        error = GroundError(outcome.code, outcome.reason, recovery)
    event = GroundEvent("decision_received", ticket, freeze_map(_event_body(outcome)))
    return FeatureResult(outcome.status, data, (event,), error)


def _foundation(outcome: Outcome) -> Mapping[str, object]:
    return freeze_map(
        {
            "live_call_count": 0,
            "simulated": True,
            "trace": outcome.trace,
            "within_limit": outcome.within_limit,
            "device_calls": 0,
            "retained": False,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
            "authorized": False,
            "detail": outcome.short,
        }
    )


def _event_body(outcome: Outcome) -> dict[str, object]:
    data = outcome.data
    body: dict[str, object] = {
        "outcome": outcome.short,
        "reason": outcome.reason,
        "slot": SLOT,
        "comparable": data.get("comparable", False),
        "follow": data.get("follow", False),
        "quality": data.get("quality"),
        "epoch": data.get("epoch"),
        "mission_epoch": data.get("mission_epoch"),
        "beacon_epoch": data.get("beacon_epoch"),
        "map_epoch": data.get("map_epoch"),
        "message_id": data.get("message_id"),
        "mission_id": data.get("mission_id"),
        "command_id": None,
        "request_id": None,
        "frame_id": None,
        "track_id": None,
        "camera_epoch": None,
        "interface": data.get("interface"),
        "clock_error_ms": data.get("clock_error_ms"),
        "sample_ids": data.get("sample_ids", ()),
    }
    if outcome.status == "ok":
        body["median_rssi_dbm"] = data.get("median_rssi_dbm")
        body["spread_db"] = data.get("spread_db")
    return body


def _ticket_result(ticket: Ticket, exc: GroundFault) -> FeatureResult:
    reason = exc.error.detail
    data = freeze_map(
        {
            "detail": "rejected",
            "reason": reason,
            "comparable": False,
            "follow": False,
            "quality": None,
            "epoch": None,
        }
    )
    event = GroundEvent(
        "decision_received",
        ticket,
        freeze_map({"outcome": "rejected", "reason": reason, "slot": SLOT}),
    )
    return FeatureResult("failed", data, (event,), exc.error)


def _is_probe(request: FeatureRequest) -> bool:
    return (
        request.kind == "diagnostic"
        and request.name in PROBE_NAMES
        and set(request.payload) <= {"seed"}
    )


def _read(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g21" / name
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (OSError, ValueError) as exc:
        raise fault("io_fault", f"{name} could not be read", recovery_required=True) from exc
    if not isinstance(loaded, dict):
        raise fault("invalid_input", f"{name} must be an object")
    return cast(dict[str, object], loaded)


def _body(window: dict[str, object]) -> dict[str, object]:
    body = window.get("payload")
    if not isinstance(body, dict):
        raise fault("invalid_input", "fixture window payload is not an object")
    return cast(dict[str, object], body)


def _first_pose(window: dict[str, object]) -> dict[str, object]:
    samples = _body(window).get("samples")
    if not isinstance(samples, list) or not samples:
        raise fault("invalid_input", "fixture samples are missing")
    sample = samples[0]
    if not isinstance(sample, dict):
        raise fault("invalid_input", "fixture sample is not an object")
    pose = cast(dict[str, object], sample).get("pose")
    if not isinstance(pose, dict):
        raise fault("invalid_input", "fixture pose is not an object")
    return cast(dict[str, object], pose)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise ValueError("duplicate key")
        found[key] = value
    return found


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _bad("invalid_input", f"{label} must be an object", "rejected:field")
    return cast(dict[str, object], value)


def _require_keys(value: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    missing = allowed - set(value)
    if missing:
        names = ", ".join(sorted(missing))
        raise _bad("invalid_input", f"{label} is missing {names}", "rejected:field")
    extra = [key for key in value if key not in allowed]
    if extra:
        names = ", ".join(sorted(extra))
        raise _bad("invalid_input", f"unknown {label} field {names}", "rejected:field")


def _token(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise _bad("invalid_input", f"{label} must be a string", "rejected:field")
    if len(value) > 160:
        raise _bad("invalid_input", f"{label} is too long", "rejected:field")
    return value


def _optional_text(value: object, label: str) -> None:
    if value is None:
        return
    _token(value, label)


def _integer(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad("invalid_input", f"{label} must be an integer", "rejected:field")
    if value < minimum:
        raise _bad("invalid_input", f"{label} is out of range", "rejected:field")
    return value


def _number(value: object, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad("invalid_input", f"{label} must be a number", "rejected:field")
    if not math.isfinite(float(value)):
        raise _bad("invalid_input", f"{label} must be finite", "rejected:field")
    return value


def _optional_number(value: object, label: str) -> int | float | None:
    if value is None:
        return None
    return _number(value, label)


def _stamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise _bad("invalid_input", f"{label} must be a timestamp", "rejected:field")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _bad("invalid_input", f"{label} must be a timestamp", "rejected:field") from exc
    if parsed.tzinfo is None:
        raise _bad("invalid_input", f"{label} must include a timezone", "rejected:field")
    return parsed.astimezone(UTC)


def _exceeds(value: int | float, limit: int | float) -> bool:
    return float(value) - float(limit) > 1e-6


def _close(reported: int | float, actual: float) -> bool:
    return abs(float(reported) - actual) <= 1e-6


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[middle])
    return (float(ordered[middle - 1]) + float(ordered[middle])) / 2.0


def _spread(values: list[float]) -> float:
    return float(max(values) - min(values))


def _fmt(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
