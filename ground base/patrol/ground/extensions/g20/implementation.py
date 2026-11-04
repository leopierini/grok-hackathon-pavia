"""Dog navigation feature. create(services) does not command the dog."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from patrol.ground.extensions.g20.policy import (
    PARSE_TRACE,
    SCHEMA,
    SLOT,
    NavDecision,
    assess,
    trace_of,
)
from patrol.ground.extensions.g20.scenarios import CASE_IDS
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

_EXPIRES = datetime(2026, 11, 4, 13, 0, 11, tzinfo=UTC)


class NavigationFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest", public=True)
        if request.ticket is not None:
            try:
                self.services.kernel.authority.require_current(request.ticket)
            except GroundFault as exc:
                return _failed(exc.error.code, exc.error.detail, public=True, ticket=request.ticket)
        if request.kind == "diagnostic" and request.name in CASE_IDS:
            return self._simulate(request.name)
        if request.kind != "guard" or request.name != SLOT:
            return _failed(
                "invalid_input",
                "navigation feature name or kind is not accepted",
                public=True,
                ticket=request.ticket,
            )
        if isinstance(request.payload, (str, bytes)) or not isinstance(request.payload, Mapping):
            return _failed(
                "invalid_input",
                "navigation request payload must be a mapping",
                public=True,
            )
        try:
            decision = assess(self.services.kernel.clock.utc_now(), request.payload)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, public=True, ticket=request.ticket)
        return _public(decision, request.ticket)

    def _simulate(self, case_id: str) -> FeatureResult:
        try:
            if case_id == "expired_candidate":
                self._advance_past_deadline()
            decision = assess(self.services.kernel.clock.utc_now(), self._payload(case_id))
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, public=False)
        return _simulated(decision, self._calls())

    def _payload(self, case_id: str) -> dict[str, object]:
        observation = self._fixture("dog-observation.json")
        candidates = self._fixture("dog-navigation-candidates.json")
        capabilities = self._fixture("dog-capabilities.json")
        profile: dict[str, object] = {
            "dog_transport": "ethernet",
            "profile_identity": "ethernet-default",
        }
        map_epoch = 1
        obs = _object(observation.get("payload"), "observation payload")
        nav = _object(candidates.get("payload"), "candidates payload")
        if case_id == "blocked_empty" or case_id == "no_move_local":
            nav["candidates"] = []
            nav["blocked"] = True
            nav["reason"] = "No safe local step."
        elif case_id == "slam_disarmed":
            capability = _object(capabilities.get("payload"), "capabilities")
            features = _object(capability.get("features"), "features")
            features["slam"] = False
        elif case_id == "standing_null":
            obs["standing"] = None
        elif case_id == "map_epoch_changed":
            map_epoch = 2
        elif case_id == "transport_mismatch":
            profile["dog_transport"] = "wifi"
        elif case_id == "target_range":
            _candidate(nav)["target_range_m"] = 1.2
        elif case_id == "wrong_frame":
            _candidate(nav)["frame_id"] = "museum/map"
        elif case_id == "avoidance_null":
            obs["avoidance_enabled"] = None
        elif case_id == "wifi_profile":
            obs["transport"] = "wifi"
            profile["dog_transport"] = "wifi"
        elif case_id == "blocked_inconsistent":
            nav["blocked"] = True
        elif case_id == "safe_false":
            _candidate(nav)["safe"] = False
        elif case_id == "string_boolean":
            obs["standing"] = "true"
        elif case_id == "lidar_missing":
            obs["lidar_observed_at"] = None
        return {
            "observation": observation,
            "candidates": candidates,
            "capabilities": capabilities,
            "map_epoch": map_epoch,
            "profile": profile,
        }

    def _fixture(self, name: str) -> dict[str, object]:
        path = repo_root() / "fixtures" / "ground" / "g20" / name
        loaded = json.loads(self.services.kernel.io.read_text(path))
        if not isinstance(loaded, dict):
            raise fault("invalid_input", "fixture must be an object")
        return cast(dict[str, object], loaded)

    def _advance_past_deadline(self) -> None:
        clock = self.services.kernel.clock
        if not isinstance(clock, ManualClock):
            raise fault("invalid_input", "expired candidate case requires the manual clock")
        delta = (_EXPIRES - clock.utc_now()).total_seconds()
        if delta > 0:
            clock.advance(delta)

    def _calls(self) -> int:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", None)
        if not isinstance(calls, list):
            return 0
        return len(calls)


def create(services: BaseServices) -> NavigationFeature:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "navigation create expects BaseServices")
    return NavigationFeature(services)


def _public(decision: NavDecision, ticket: Ticket | None) -> FeatureResult:
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


def _simulated(decision: NavDecision, calls: int) -> FeatureResult:
    data = _foundation(trace_of(decision), decision.reason, calls)
    error = None
    if decision.status != "ok":
        error = GroundError(
            decision.error_code or "rejected",
            decision.error_detail or decision.reason,
            decision.recovery_required,
        )
    return FeatureResult(decision.status, data, (_event(None, decision),), error)


def _failed(
    code: str,
    detail: str,
    *,
    public: bool,
    ticket: Ticket | None = None,
) -> FeatureResult:
    error = GroundError(code, detail, code in {"cancelled", "stale_ticket", "io_fault"})
    event = _failure_event(ticket, detail)
    if public:
        data: Mapping[str, object] = freeze_map(
            {
                "readiness": freeze_map(
                    {
                        "standing": None,
                        "stationary": None,
                        "avoidance": None,
                        "navigation_mode": "",
                        "slam_state": "",
                        "minimum_clearance_m": None,
                    }
                ),
                "candidate_ids": (),
                "blocked": False,
                "ready": False,
                "ready_to_wait": False,
                "route_ready": False,
                "map_id": None,
                "map_epoch": None,
                "pose_map_epoch": None,
                "transport": "",
                "profile_transport": "",
                "frame": None,
                "commands": (),
                "motion_proposed": False,
                "dropped": "",
                "withheld": "",
                "reason": detail,
                "correlation": freeze_map({}),
            }
        )
    else:
        data = _foundation(PARSE_TRACE, detail, 0)
    return FeatureResult("failed", data, (event,), error)


def _foundation(trace: tuple[str, ...], detail: str, calls: int) -> Mapping[str, object]:
    return freeze_map(
        {
            "live_call_count": 0,
            "simulated": True,
            "trace": trace,
            "within_limit": True,
            "device_calls": calls,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
            "authorized": False,
            "detail": detail,
            "retained": False,
        }
    )


def _event(ticket: Ticket | None, decision: NavDecision) -> GroundEvent:
    payload = {
        "event": "dog_navigation",
        "message_id": decision.correlation.get("message_id"),
        "candidates_message_id": decision.correlation.get("candidates_message_id"),
        "mission_id": decision.correlation.get("mission_id"),
        "epoch": decision.correlation.get("epoch"),
        "command_id": decision.correlation.get("command_id"),
        "frame_id": decision.correlation.get("frame_id"),
        "track_id": decision.correlation.get("track_id"),
        "beacon_epoch": decision.correlation.get("beacon_epoch"),
        "map_epoch": decision.correlation.get("map_epoch"),
        "camera_epoch": decision.correlation.get("camera_epoch"),
        "candidate_ids": decision.candidate_ids,
        "blocked": decision.blocked,
        "ready": decision.ready,
        "ready_to_wait": decision.ready_to_wait,
        "reason": decision.reason,
        "commands": (),
    }
    return GroundEvent("decision_received", ticket, freeze_map(payload))


def _failure_event(ticket: Ticket | None, detail: str) -> GroundEvent:
    return GroundEvent(
        "decision_received",
        ticket,
        freeze_map(
            {
                "event": "dog_navigation",
                "ready": False,
                "candidate_ids": (),
                "commands": (),
                "reason": detail,
            }
        ),
    )


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise fault("invalid_input", f"{label} must be an object")
    return cast(dict[str, object], value)


def _candidate(payload: dict[str, object]) -> dict[str, object]:
    rows = payload.get("candidates")
    if not isinstance(rows, list) or not rows:
        raise fault("invalid_input", "fixture candidate list is empty")
    first = rows[0]
    if not isinstance(first, dict):
        raise fault("invalid_input", "fixture candidate must be an object")
    return cast(dict[str, object], first)
