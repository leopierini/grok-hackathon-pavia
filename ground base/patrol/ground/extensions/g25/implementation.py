"""Feature port for handing the dog from RSSI to its own camera."""

from __future__ import annotations

from collections.abc import Mapping

from patrol.ground.extensions.g25.policy import Outcome, detail_of, evaluate, trace_of
from patrol.ground.extensions.g25.samples import CASE_IDS, build
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeaturePort,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
)
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.validation import freeze_map

_SLOT = "feature.v2_dog_acquire"
_SCHEMA = "ground-task-v2"


class DogAcquire:
    """Counts fresh dog-camera hits. It does not command the dog or declare arrival."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _error("invalid_input", "expected a FeatureRequest")
        try:
            if request.kind == "diagnostic" and request.name in CASE_IDS:
                return self._simulation(request)
            if request.kind != "stage" or request.name != "dog_acquire":
                return _error("invalid_input", "dog acquire request is not recognized")
            self._check_ticket(request)
            outcome = evaluate(_payload(request.payload))
        except GroundFault as exc:
            return _from_fault(exc)
        return _from_outcome(outcome, request)

    def _simulation(self, request: FeatureRequest) -> FeatureResult:
        if request.name == "cancelled":
            self.services.kernel.authority.latch_cancel("operator halt")
            outcome = _cancelled_outcome()
            return _sim(outcome, self._device_calls())
        outcome = evaluate(build(request.name))
        return _sim(outcome, self._device_calls())

    def _check_ticket(self, request: FeatureRequest) -> None:
        if request.ticket is None:
            if self.services.kernel.authority.cancelled:
                raise GroundFault(
                    GroundError("cancelled", "rejected:cancelled", recovery_required=True)
                )
            return
        self.services.kernel.authority.require_current(request.ticket)

    def _device_calls(self) -> int:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", ())
        if not isinstance(calls, list):
            return 0
        return len(calls)


def create(services: BaseServices) -> FeaturePort:
    if not isinstance(services, BaseServices):
        raise GroundFault(GroundError("invalid_input", "dog acquire requires BaseServices", False))
    return DogAcquire(services)


def _from_outcome(outcome: Outcome, request: FeatureRequest) -> FeatureResult:
    data = freeze_map(
        {
            "mode": outcome.mode,
            "phase": outcome.phase,
            "rssi_role": outcome.rssi_role,
            "hit_count": outcome.hit_count,
            "frame_ids": outcome.frame_ids,
            "track_id": outcome.track_id,
            "command": None,
            "goal_reached": False,
            "arrival_confirmed": False,
            "rssi_records": outcome.rssi_records,
            "rssi_selection": None,
            "handoff": outcome.handoff,
            "resets": outcome.resets,
            "journal": outcome.journal,
        }
    )
    events: tuple[GroundEvent, ...] = ()
    if outcome.handoff and isinstance(outcome.journal, Mapping):
        payload = outcome.journal.get("payload")
        details = payload.get("details") if isinstance(payload, Mapping) else None
        if isinstance(details, Mapping):
            events = (
                GroundEvent(
                    "decision_received",
                    request.ticket,
                    freeze_map(_event_details(details)),
                ),
            )
    error = None if outcome.status == "ok" else _ground_error(outcome)
    return FeatureResult(outcome.status, data, events, error)


def _sim(outcome: Outcome, device_calls: int) -> FeatureResult:
    status = outcome.status
    error = None if status == "ok" else _ground_error(outcome)
    detail = detail_of(outcome)
    if device_calls:
        status = "failed"
        error = GroundError("unsafe_state", "dog acquire called a device", True)
        detail = error.detail
    data = freeze_map(
        {
            "authorized": False,
            "retained": False,
            "detail": detail,
            "trace": trace_of(outcome),
            "device_calls": device_calls,
            "measurement_clock": "manual",
            "within_limit": True,
            "simulated": True,
            "live_call_count": 0,
            "slot": _SLOT,
            "schema_version": _SCHEMA,
        }
    )
    return FeatureResult(status, data, (), error)


def _cancelled_outcome() -> Outcome:
    return Outcome(
        status="blocked",
        mode="rssi",
        phase="rssi",
        rssi_role="primary",
        hit_count=0,
        frame_ids=(),
        track_id="",
        resets=(),
        ignored=(),
        reason_token="cancelled",
        error_code="cancelled",
        error_detail="rejected:cancelled",
        handoff=False,
        rssi_records=(),
        journal=None,
    )


def _ground_error(outcome: Outcome) -> GroundError:
    recovery = outcome.error_code in {"cancelled", "stale_ticket", "unsafe_state"}
    return GroundError(outcome.error_code, outcome.error_detail, recovery)


def _from_fault(exc: GroundFault) -> FeatureResult:
    return _error(exc.error.code, exc.error.detail, exc.error.recovery_required)


def _error(code: str, detail: str, recovery: bool = False) -> FeatureResult:
    safe_recovery = recovery or code in {"cancelled", "stale_ticket", "unsafe_state"}
    return FeatureResult(
        "failed" if code != "cancelled" else "blocked",
        freeze_map(
            {
                "mode": "rssi",
                "phase": "rssi",
                "rssi_role": "primary",
                "hit_count": 0,
                "frame_ids": (),
                "track_id": "",
                "command": None,
                "goal_reached": False,
                "arrival_confirmed": False,
                "rssi_records": (),
                "rssi_selection": None,
                "handoff": False,
                "resets": (),
                "journal": None,
            }
        ),
        (),
        GroundError(code, detail, safe_recovery),
    )


def _event_details(details: Mapping[str, object]) -> dict[str, object]:
    copied = dict(details)
    copied["event"] = "dog_vision_handoff"
    frame_ids = copied.get("frame_ids")
    if isinstance(frame_ids, list):
        copied["frame_ids"] = tuple(str(item) for item in frame_ids)
    return copied


def _payload(value: Mapping[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items()}
