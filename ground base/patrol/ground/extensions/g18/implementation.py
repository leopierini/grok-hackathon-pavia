"""Feature port for drone command.ack tracking."""

from __future__ import annotations

import math
from collections.abc import Mapping

from patrol.ground.extensions.g18.lifecycle import Outcome, Tracker
from patrol.ground.extensions.g18.script import run_case
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map

_ROUTES = {
    "apply_ack": "command",
    "register": "command",
    "expire": "guard",
    "project": "projection",
}


class DroneAckFeature:
    """Records drone acknowledgements. It does not issue a command or clear a goal."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.tracker = Tracker()
        self.cleanup_paths: tuple[str, ...] = ()
        self.observations: dict[str, object] = {}

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest")
        try:
            if request.ticket is not None:
                self.services.kernel.authority.require_current(request.ticket)
            if request.kind == "diagnostic":
                return run_case(request.name, self.tracker, self.services.kernel.clock)
            expected = _ROUTES.get(request.name)
            if expected is None or expected != request.kind:
                return _failed("invalid_input", "unknown drone ack request")
            if request.name == "apply_ack":
                outcome = self.tracker.apply(
                    _object(request.payload, "ack"),
                    _object(request.payload, "command"),
                    _optional_object(request.payload, "observation"),
                    _optional_deadline(request.payload),
                    request.ticket,
                )
            elif request.name == "register":
                outcome = self.tracker.register(
                    _object(request.payload, "command"),
                    _required_deadline(request.payload),
                    request.ticket,
                )
            elif request.name == "expire":
                outcome = self.tracker.expire(
                    _text(request.payload.get("command_id"), "command_id"),
                    self.services.kernel.clock.monotonic(),
                    request.ticket,
                )
            else:
                outcome = self.tracker.project(
                    _text(request.payload.get("command_id"), "command_id"),
                    request.ticket,
                )
            return _from_outcome(outcome)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, recovery=exc.error.recovery_required)


def create(services: BaseServices) -> DroneAckFeature:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "drone ack create expects base services")
    return DroneAckFeature(services)


def _from_outcome(outcome: Outcome) -> FeatureResult:
    error = None
    if outcome.status != "ok":
        error = GroundError(outcome.code or "internal", outcome.detail, outcome.recovery)
    return FeatureResult(outcome.status, outcome.data, outcome.events, error)


def _failed(code: str, detail: str, *, recovery: bool = False) -> FeatureResult:
    if not detail:
        detail = "drone acknowledgement failed"
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "proposed_commands": (),
                "grounded": False,
                "landing_proof": False,
                "demo_goal_cleared": False,
                "recovery_required": recovery,
                "detail": detail,
            }
        ),
        (),
        GroundError(code, detail, recovery),
    )


def _object(payload: Mapping[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        raise fault("invalid_input", f"{key} must be an object")
    found: dict[str, object] = {}
    for item_key, item in value.items():
        if not isinstance(item_key, str):
            raise fault("invalid_input", f"{key} keys must be strings")
        found[item_key] = item
    return found


def _optional_object(payload: Mapping[str, object], key: str) -> dict[str, object] | None:
    if key not in payload or payload[key] is None:
        return None
    return _object(payload, key)


def _optional_deadline(payload: Mapping[str, object]) -> float | None:
    if "reply_deadline_monotonic" not in payload or payload["reply_deadline_monotonic"] is None:
        return None
    return _deadline(payload["reply_deadline_monotonic"])


def _required_deadline(payload: Mapping[str, object]) -> float:
    if "reply_deadline_monotonic" not in payload:
        raise fault("invalid_input", "reply deadline is required")
    return _deadline(payload["reply_deadline_monotonic"])


def _deadline(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", "reply deadline must be a real number")
    if not math.isfinite(float(value)):
        raise fault("invalid_input", "reply deadline must be finite")
    return float(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{label} must be a non-empty string")
    return value
