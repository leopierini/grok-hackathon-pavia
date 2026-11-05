"""RSSI homing feature. It names one safe candidate or stops. It never commands the dog."""

from __future__ import annotations

from collections.abc import Mapping

from patrol.ground.extensions.g22.assemble import case_from_fixture
from patrol.ground.extensions.g22.policy import (
    DISPATCH_EVENT,
    DISPATCH_LOG_STATUS,
    DISPATCH_PHASE,
    SCHEMA,
    SLOT,
    Decision,
    InvalidHoming,
    decide,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeaturePort,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map

_TRACE_ONLY = ("no_range_m", "no_dog_command")


class RssiHoming:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest")
        authority = self.services.kernel.authority
        if authority.cancelled:
            return _failed(
                "cancelled",
                "cancellation is latched",
                status="blocked",
                recovery_required=True,
            )
        if request.ticket is not None:
            try:
                authority.require_current(request.ticket)
            except GroundFault as exc:
                return _from_fault(exc)
        try:
            case = _case(request)
            decision = decide(case)
        except InvalidHoming as exc:
            return _failed("invalid_input", exc.detail, detail=f"invalid:{_token(exc.detail)}")
        return _ok(request, decision)


def create(services: BaseServices) -> FeaturePort:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "expected BaseServices")
    return RssiHoming(services)


def _case(request: FeatureRequest) -> dict[str, object]:
    supplied = request.payload.get("homing")
    if isinstance(supplied, Mapping):
        return {str(key): value for key, value in supplied.items()}
    if not request.name or request.name == "seed":
        raise InvalidHoming("homing case is required")
    return case_from_fixture(request.name)


def _ok(request: FeatureRequest, decision: Decision) -> FeatureResult:
    data = _data(decision.detail(), decision.trace())
    if request.kind != "diagnostic":
        data = freeze_map({**data, **_event_payload(decision)})
    return FeatureResult(
        status="ok",
        data=data,
        events=(GroundEvent("decision_received", request.ticket, _event_payload(decision)),),
        error=None,
    )


def _event_payload(decision: Decision) -> Mapping[str, object]:
    payload: dict[str, object] = {
        "action": decision.action,
        "reason": decision.reason,
        "candidate_id": decision.candidate_id,
        "beacon_epoch": decision.beacon_epoch,
        "map_epoch": decision.map_epoch,
        "quality": decision.quality,
        "sample_ids": decision.sample_ids,
        "window_ids": decision.window_ids,
        "blocked": decision.blocked,
        "message_id": _message_id(decision),
        "mission_id": decision.mission_id,
        "epoch": decision.epoch,
        "command_id": decision.command_id,
        "slot": SLOT,
        "schema_version": SCHEMA,
    }
    if decision.action == "select":
        payload["event"] = DISPATCH_EVENT
        payload["phase"] = DISPATCH_PHASE
        payload["track_id"] = decision.track_id
        payload["details"] = freeze_map(
            {
                "logs_requirements_status": DISPATCH_LOG_STATUS,
                "track_id": decision.track_id,
                "candidate_id": decision.candidate_id,
                "beacon_epoch": decision.beacon_epoch,
                "map_epoch": decision.map_epoch,
                "sample_ids": decision.sample_ids,
                "window_ids": decision.window_ids,
            }
        )
    return freeze_map(payload)


def _message_id(decision: Decision) -> str:
    if decision.action == "select":
        return "msg-event-dog_dispatched"
    return f"msg-rssi-homing-{decision.reason}"


def _failed(
    code: str,
    message: str,
    *,
    status: str = "failed",
    detail: str | None = None,
    recovery_required: bool = False,
) -> FeatureResult:
    text = detail or f"invalid:{_token(message)}"
    return FeatureResult(
        status=status,
        data=_data(text, _TRACE_ONLY),
        events=(),
        error=GroundError(code, message, recovery_required),
    )


def _from_fault(exc: GroundFault) -> FeatureResult:
    status = "blocked" if exc.error.code == "cancelled" else "failed"
    return _failed(
        exc.error.code,
        exc.error.detail,
        status=status,
        recovery_required=exc.error.recovery_required,
    )


def _data(detail: str, trace: tuple[str, ...]) -> Mapping[str, object]:
    return freeze_map(
        {
            "live_call_count": 0,
            "simulated": True,
            "trace": trace,
            "within_limit": True,
            "device_calls": 0,
            "retained": False,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
            "authorized": False,
            "detail": detail,
        }
    )


def _token(detail: str) -> str:
    if "boolean" in detail:
        return "dog_motion_allowed"
    if "median 0" in detail:
        return "rssi_sentinel"
    return "input"
