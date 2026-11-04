"""Drone observation intake. It stores telemetry and never sends a flight command."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g13.normalize import (
    SCHEMA,
    SLOT,
    ObservationRecord,
    normalize,
    rejection,
)
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
from patrol.ground.kernel.validation import freeze_map

_DIRECT = frozenset(
    {"envelope", "capability", "mission_epoch", "received_monotonic", "height_label"}
)
_CASES = frozenset(
    {"accept_example", "reference_unknown", "pose_null", "bad_bssid", "stale_epoch"}
)


class ObservationFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self._seen: dict[str, tuple[str, Mapping[str, object]]] = {}

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failure(GroundError("invalid_input", "expected a FeatureRequest", False))
        if request.name in _CASES and "envelope" not in request.payload:
            try:
                return await self._simulate(request.name)
            except GroundFault as exc:
                return _sim_failure(exc.error, self)
        try:
            return self._ingest(request)
        except GroundFault as exc:
            return _failure(exc.error, self)

    def _ingest(self, request: FeatureRequest) -> FeatureResult:
        unknown = [key for key in request.payload if key not in _DIRECT]
        if unknown:
            raise fault("invalid_input", "unknown observation input")
        if "envelope" not in request.payload or "capability" not in request.payload:
            raise fault("invalid_input", "envelope and capability are required")
        if "mission_epoch" not in request.payload:
            raise fault("invalid_input", "mission_epoch is required")
        supplied = request.payload.get("received_monotonic")
        monotonic = self.services.kernel.clock.monotonic() if supplied is None else supplied
        if isinstance(monotonic, bool) or not isinstance(monotonic, (int, float)):
            raise fault("invalid_input", "received_monotonic must be a number")
        record = normalize(
            request.payload["envelope"],
            request.payload["capability"],
            mission_epoch=request.payload["mission_epoch"],
            received_utc=self.services.kernel.clock.utc_now().isoformat(),
            received_monotonic=float(monotonic),
            height_label=request.payload.get("height_label"),
        )
        self._current_ticket(request.ticket, record)
        canonical = _canonical(request.payload["envelope"])
        previous = self._seen.get(record.message_id)
        if previous is not None:
            if previous[0] != canonical:
                raise fault("rejected", "message_id was replayed with a different observation")
            replayed = dict(previous[1])
            replayed["replayed"] = True
            return FeatureResult("ok", freeze_map(replayed), (), None)
        data = _direct_data(record, self, replayed=False)
        self._seen[record.message_id] = (canonical, data)
        return FeatureResult("ok", data, (_event(record, request.ticket),), None)

    def _current_ticket(self, ticket: Ticket | None, record: ObservationRecord) -> None:
        if ticket is None:
            if self.services.kernel.authority.cancelled:
                reason = getattr(self.services.kernel.authority, "reason", "")
                if not isinstance(reason, str) or not reason.strip():
                    reason = "cancellation is latched"
                raise fault("cancelled", reason, recovery_required=True)
            return
        if ticket.mission_id != record.mission_id or ticket.epoch != record.epoch:
            raise fault(
                "stale_ticket",
                "observation ticket does not match the mission epoch",
                recovery_required=True,
            )
        self.services.kernel.authority.require_current(ticket)

    async def _simulate(self, case_id: str) -> FeatureResult:
        if case_id == "stale_epoch":
            return await self._stale_epoch()
        envelope = _load("drone-observation.json")
        if case_id == "reference_unknown":
            payload = _object(envelope["payload"])
            payload["height_reference"] = "unknown"
            envelope["payload"] = payload
        elif case_id == "bad_bssid":
            payload = _object(envelope["payload"])
            beacon = _object(payload["beacon"])
            beacon["bssid"] = "02:00:00:00:ZZ"
            payload["beacon"] = beacon
            envelope["payload"] = payload
        try:
            record = normalize(
                envelope,
                _load("drone-capabilities.json"),
                mission_epoch=1,
                received_utc=self.services.kernel.clock.utc_now().isoformat(),
                received_monotonic=float(self.services.kernel.clock.monotonic()),
            )
        except GroundFault as exc:
            return _sim_failure(exc.error, self, marker=rejection(exc.error))
        trace = _pose_trace(record, self) if case_id == "pose_null" else _full_trace(record, self)
        return _sim_ok(trace, record, self)

    async def _stale_epoch(self) -> FeatureResult:
        authority = self.services.kernel.authority
        barriers = self.services.kernel.barriers
        ticket = authority.issue("demo-20261104-001", "drone.observation")
        barriers.arm("apply")
        outcome = {"stale": False, "applied": False}

        async def commit() -> None:
            await barriers.wait("apply")
            try:
                authority.require_current(ticket)
            except GroundFault as exc:
                outcome["stale"] = exc.error.code == "stale_ticket"
                return
            outcome["applied"] = True

        task = asyncio.create_task(commit(), name="observation-apply")
        self.services.kernel.tasks.retain("observation-apply", task)
        for _ in range(5):
            await asyncio.sleep(0)
            if "observation-apply" in self.services.kernel.tasks.pending():
                break
        else:
            raise fault("internal", "observation apply did not park")
        authority.reset_generation("epoch advanced before observation apply")
        barriers.release("apply")
        await self.services.kernel.tasks.collect(deadline=2)
        if outcome["stale"] is not True or outcome["applied"] is not False:
            raise fault("validation_failed", "stale observation was applied")
        if self._state_writes() != 0:
            raise fault("validation_failed", "stale observation wrote state")
        return _sim_failure(
            GroundError(
                "stale_ticket",
                "observation became stale before apply",
                True,
            ),
            self,
            marker="stale",
            extra=("applied=false",),
        )

    def _state_writes(self) -> int:
        trace = getattr(self.services.state, "trace", ())
        if not isinstance(trace, list):
            return 0
        return sum(1 for item in trace if item == "state.apply")

    def _command_names(self) -> tuple[str, ...]:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", ())
        if not isinstance(calls, list):
            return ()
        return tuple(str(item) for item in calls)

    def _call_counts(self) -> tuple[int, int]:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", ())
        live = getattr(devices, "live_call_count", 0)
        count = len(calls) if isinstance(calls, list) else 0
        if isinstance(live, bool) or not isinstance(live, int):
            return count, 0
        return count, live


def create(services: BaseServices) -> FeaturePort:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "observation feature requires base services")
    return ObservationFeature(services)


def _event(record: ObservationRecord, ticket: Ticket | None) -> GroundEvent:
    return GroundEvent("decision_received", ticket, record.journal())


def _direct_data(
    record: ObservationRecord,
    feature: ObservationFeature,
    *,
    replayed: bool,
) -> Mapping[str, object]:
    return freeze_map(
        {
            "observation": record.to_mapping(),
            "journal": record.journal(),
            "replayed": replayed,
            "state_writes": feature._state_writes(),
            "command_methods": feature._command_names(),
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
    )


def _full_trace(record: ObservationRecord, feature: ObservationFeature) -> tuple[str, ...]:
    frame_id = "null" if record.frame_id is None else record.frame_id
    camera = "null" if record.camera_epoch is None else str(record.camera_epoch)
    command = "null" if record.active_command_id is None else record.active_command_id
    pose = "null" if record.pose is None else "present"
    return (
        f"flight_state={record.flight_state}",
        f"height_estimate_m={_num(record.height_estimate_m)}",
        f"height_reference={record.height_reference}",
        f"floor_agl_claim={_bool(record.floor_agl_claim)}",
        f"beacon_epoch={record.beacon_epoch}",
        f"pose={pose}",
        f"battery_percent={_num(record.battery_percent)}",
        f"sent_at={record.sent_at}",
        f"received_utc={record.received_utc}",
        f"received_monotonic={_num(record.received_monotonic)}",
        f"state_writes={feature._state_writes()}",
        f"command_methods={','.join(feature._command_names())}",
        f"frame_id={frame_id}",
        f"camera_epoch={camera}",
        f"active_command_id={command}",
    )


def _pose_trace(record: ObservationRecord, feature: ObservationFeature) -> tuple[str, ...]:
    if record.pose is None:
        axes = ("x_m=", "y_m=", "yaw_rad=")
        pose = "null"
    else:
        axes = (
            f"x_m={_num(record.pose.get('x_m'))}",
            f"y_m={_num(record.pose.get('y_m'))}",
            f"yaw_rad={_num(record.pose.get('yaw_rad'))}",
        )
        pose = "present"
    return (
        f"pose={pose}",
        *axes,
        f"state_writes={feature._state_writes()}",
        f"command_methods={','.join(feature._command_names())}",
    )


def _sim_ok(
    trace: tuple[str, ...],
    record: ObservationRecord,
    feature: ObservationFeature,
) -> FeatureResult:
    calls, live = feature._call_counts()
    return FeatureResult(
        "ok",
        freeze_map(
            {
                "trace": trace,
                "detail": "observation stored with its height reference",
                "device_calls": calls,
                "live_call_count": live,
                "simulated": True,
                "slot": SLOT,
                "schema_version": SCHEMA,
            }
        ),
        (_event(record, None),),
        None,
    )


def _sim_failure(
    error: GroundError,
    feature: ObservationFeature,
    *,
    marker: str | None = None,
    extra: tuple[str, ...] = (),
) -> FeatureResult:
    calls, live = feature._call_counts()
    label = marker or rejection(error)
    trace = (
        f"state_writes={feature._state_writes()}",
        f"command_methods={','.join(feature._command_names())}",
        f"rejected={label}",
        *extra,
    )
    return FeatureResult(
        _status(error.code),
        freeze_map(
            {
                "trace": trace,
                "detail": error.detail,
                "device_calls": calls,
                "live_call_count": live,
                "simulated": True,
                "slot": SLOT,
                "schema_version": SCHEMA,
            }
        ),
        (),
        error,
    )


def _failure(error: GroundError, feature: ObservationFeature | None = None) -> FeatureResult:
    writes = 0 if feature is None else feature._state_writes()
    commands: tuple[str, ...] = () if feature is None else feature._command_names()
    return FeatureResult(
        _status(error.code),
        freeze_map(
            {
                "state_writes": writes,
                "command_methods": commands,
                "slot": SLOT,
                "schema_version": SCHEMA,
            }
        ),
        (),
        error,
    )


def _status(code: str) -> str:
    if code in {"rejected", "stale_ticket", "epoch_mismatch"}:
        return "blocked"
    return "failed"


def _load(name: str) -> dict[str, object]:
    path = Path(__file__).resolve().parents[4] / "fixtures" / "ground" / "g13" / name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise fault(
            "io_fault",
            "observation fixture could not be read",
            recovery_required=True,
        ) from exc
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise fault("invalid_input", "observation fixture is not json") from exc
    return _object(raw)


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise fault("invalid_input", "expected an object")
    found: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise fault("invalid_input", "object keys must be strings")
        found[key] = item
    return found


def _canonical(value: object) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"))


def _plain(value: object) -> object:
    if isinstance(value, Mapping) and not isinstance(value, (str, bytes)):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _num(value: object) -> str:
    if value is None:
        return "null"
    return str(value)


def _bool(value: bool) -> str:
    return "true" if value else "false"
