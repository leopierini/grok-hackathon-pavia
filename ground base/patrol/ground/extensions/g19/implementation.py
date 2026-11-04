"""Beacon hold feature. create(services) is the only public factory."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from datetime import datetime
from typing import cast

from patrol.ground.extensions.g19.policy import SCHEMA, SLOT, BeaconDecision, assess, trace_of
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

_CASES = frozenset(
    {
        "stable_hold",
        "moving_hold",
        "expired_hold",
        "reposition_old_epoch",
        "reposition_next_epoch",
        "bssid_mismatch",
        "no_dog_execute",
        "running_command",
        "unknown_flight",
        "hover_keeps_epoch",
    }
)
_ARMED = "02:00:00:00:00:01"
_EXPIRES = datetime.fromisoformat("2026-11-04T13:00:12+00:00")


class BeaconFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest", public=True)
        if request.kind == "diagnostic" and request.name in _CASES:
            return self._simulate(request.name)
        try:
            if self.services.kernel.authority.cancelled:
                raise fault("cancelled", "cancellation is latched", recovery_required=True)
            if request.ticket is not None:
                self.services.kernel.authority.require_current(request.ticket)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, public=True, ticket=request.ticket)
        if request.kind != "guard" or request.name != SLOT:
            return _failed(
                "invalid_input",
                "beacon feature name or kind is not accepted",
                public=True,
            )
        if isinstance(request.payload, (str, bytes)) or not isinstance(request.payload, Mapping):
            return _failed("invalid_input", "beacon request payload must be a mapping", public=True)
        try:
            decision = assess(self.services.kernel.clock.utc_now(), request.payload)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, public=True, ticket=request.ticket)
        return _public(decision, request.ticket)

    def _simulate(self, case_id: str) -> FeatureResult:
        try:
            decision = self._case(case_id)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, public=False)
        return _simulated(decision, self._call_count())

    def _case(self, case_id: str) -> BeaconDecision:
        if case_id == "expired_hold":
            self._advance_past_hold()
        observation = self._fixture("drone-observation.json")
        if case_id == "moving_hold":
            _set_hold(observation, "moving")
        if case_id == "unknown_flight":
            _set_flight(observation, "unknown")
        if case_id == "reposition_next_epoch":
            _set_epoch(observation, 4)
        armed = "02:00:00:00:00:99" if case_id == "bssid_mismatch" else _ARMED
        payload: dict[str, object] = {
            "armed_bssid": armed,
            "observation": observation,
            "windows": _windows(case_id),
        }
        if case_id in {"reposition_old_epoch", "reposition_next_epoch", "running_command"}:
            payload["drone_command"] = self._fixture("ground-to-drone-command.json")
            payload["previous_beacon_epoch"] = 3
            payload["drone_command_running"] = case_id == "running_command"
            payload["drone_command_status"] = (
                "running" if case_id == "running_command" else "completed"
            )
        if case_id == "hover_keeps_epoch":
            payload["drone_command"] = self._fixture("ground-to-drone-hover.json")
            payload["previous_beacon_epoch"] = 3
            payload["drone_command_running"] = False
            payload["drone_command_status"] = "completed"
            payload["beacon_moved"] = False
        return assess(self.services.kernel.clock.utc_now(), payload)

    def _fixture(self, name: str) -> dict[str, object]:
        path = repo_root() / "fixtures" / "ground" / "g19" / name
        loaded = json.loads(self.services.kernel.io.read_text(path))
        if not isinstance(loaded, dict):
            raise fault("invalid_input", "fixture must be an object")
        return cast(dict[str, object], copy.deepcopy(loaded))

    def _advance_past_hold(self) -> None:
        clock = self.services.kernel.clock
        if not isinstance(clock, ManualClock):
            raise fault("invalid_input", "expired hold case requires the manual clock")
        delta = (_EXPIRES - clock.utc_now()).total_seconds() + 1
        if delta > 0:
            clock.advance(delta)

    def _call_count(self) -> int:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", None)
        if not isinstance(calls, list):
            return 0
        return len(calls)


def create(services: BaseServices) -> BeaconFeature:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "beacon create expects BaseServices")
    return BeaconFeature(services)


def _public(decision: BeaconDecision, ticket: Ticket | None) -> FeatureResult:
    error = None
    if decision.status != "ok":
        error = GroundError(
            decision.error_code or "rejected",
            decision.error_detail or decision.reason,
            decision.recovery_required,
        )
    return FeatureResult(
        decision.status,
        decision.public_data(),
        (_event(ticket, decision),),
        error,
    )


def _simulated(decision: BeaconDecision, calls: int) -> FeatureResult:
    data = freeze_map(
        {
            "live_call_count": 0,
            "simulated": True,
            "trace": trace_of(decision),
            "within_limit": True,
            "device_calls": calls,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
            "authorized": decision.dog_motion_allowed,
            "detail": decision.reason,
            "retained": False,
        }
    )
    error = None
    status = decision.status
    if status != "ok":
        error = GroundError(
            decision.error_code or "rejected",
            decision.error_detail or decision.reason,
            decision.recovery_required,
        )
    return FeatureResult(status, data, (_event(None, decision),), error)


def _failed(
    code: str,
    detail: str,
    *,
    public: bool,
    ticket: Ticket | None = None,
) -> FeatureResult:
    recovery = code in {"io_fault", "unavailable"}
    error = GroundError(code, detail, recovery)
    event = GroundEvent(
        "state_changed",
        ticket,
        freeze_map(
            {
                "event": "beacon_hold",
                "dog_motion_allowed": False,
                "reason": detail,
            }
        ),
    )
    if public:
        data: Mapping[str, object] = freeze_map(
            {
                "hold_state": "unknown",
                "reported_hold_state": "unknown",
                "dog_motion_allowed": False,
                "dispatch_allowed": False,
                "comparisons_allowed": False,
                "beacon_epoch": None,
                "prior_epoch": None,
                "commanded_epoch": None,
                "epoch_required": None,
                "comparable_epoch": None,
                "flight_state": "unknown",
                "beacon_id": "",
                "bssid": "",
                "armed_bssid": "",
                "reason": detail,
                "windows": (),
            }
        )
        return FeatureResult("blocked", data, (event,), error)
    data = freeze_map(
        {
            "live_call_count": 0,
            "simulated": True,
            "trace": ("dog_command:none",),
            "within_limit": True,
            "device_calls": 0,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
            "authorized": False,
            "detail": detail,
            "retained": False,
        }
    )
    return FeatureResult("failed", data, (event,), error)


def _event(ticket: Ticket | None, decision: BeaconDecision) -> GroundEvent:
    payload: dict[str, object] = {
        "event": "beacon_hold",
        "hold_state": decision.hold_state,
        "dog_motion_allowed": decision.dog_motion_allowed,
        "comparisons_allowed": decision.comparisons_allowed,
        "reason": decision.reason,
    }
    payload.update(decision.correlation)
    return GroundEvent("state_changed", ticket, freeze_map(payload))


def _windows(case_id: str) -> tuple[dict[str, object], ...]:
    current = {
        "window_id": "pi-window-1",
        "beacon_epoch": 3,
        "bssid": _ARMED,
        "rssi_dbm": -60,
    }
    if case_id == "reposition_old_epoch":
        return (
            {
                "window_id": "pi-window-old",
                "beacon_epoch": 3,
                "bssid": _ARMED,
                "rssi_dbm": -60,
            },
        )
    if case_id == "reposition_next_epoch":
        return (
            {
                "window_id": "pi-window-old",
                "beacon_epoch": 3,
                "bssid": _ARMED,
                "rssi_dbm": -60,
            },
            {
                "window_id": "pi-window-new",
                "beacon_epoch": 4,
                "bssid": _ARMED,
                "rssi_dbm": -55,
            },
        )
    return (current,)


def _payload(observation: dict[str, object]) -> dict[str, object]:
    body = observation.get("payload")
    if not isinstance(body, dict):
        raise fault("invalid_input", "observation payload must be an object")
    return cast(dict[str, object], body)


def _set_hold(observation: dict[str, object], hold: str) -> None:
    beacon = _beacon(observation)
    beacon["hold_state"] = hold


def _set_flight(observation: dict[str, object], flight: str) -> None:
    _payload(observation)["flight_state"] = flight


def _set_epoch(observation: dict[str, object], epoch: int) -> None:
    _beacon(observation)["beacon_epoch"] = epoch


def _beacon(observation: dict[str, object]) -> dict[str, object]:
    beacon = _payload(observation).get("beacon")
    if not isinstance(beacon, dict):
        raise fault("invalid_input", "beacon must be an object")
    return cast(dict[str, object], beacon)
