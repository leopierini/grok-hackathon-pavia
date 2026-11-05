"""Vision-decision feature. The simulator runs these cases; it does not fly."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from patrol.ground.extensions.g16.decide import Assessment, assess
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_vision_decision"
SCHEMA = "ground-task-v2"


def create(services: BaseServices) -> VisionDecisionFeature:
    """Build the decision feature. Construction does not call a model or a device."""
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "vision decision create expects base services")
    return VisionDecisionFeature(services)


class VisionDecisionFeature:
    """Accept a Grok decision, update a track, and withhold motor authority."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services

    def assess(
        self,
        decision: Mapping[str, object],
        request: Mapping[str, object],
        *,
        current_track_id: str | None = None,
        current_camera_epoch: int | None = None,
        halt_latched: bool = False,
        staged_association: bool = False,
    ) -> Assessment:
        return assess(
            decision,
            request,
            current_track_id=current_track_id,
            current_camera_epoch=current_camera_epoch,
            halt_latched=halt_latched,
            staged_association=staged_association,
        )

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest")
        if request.kind == "stage" and request.name == SLOT:
            return self._stage(request)
        handler = self._handlers().get(request.name)
        if request.kind != "diagnostic" or handler is None:
            return _failed("invalid_input", f"unknown vision case {request.name}")
        before = _device_calls(self.services)
        try:
            assessment = handler()
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail)
        if _device_calls(self.services) != before:
            return _failed("unsafe_state", "vision decision touched a device")
        return _result(assessment)

    def _stage(self, request: FeatureRequest) -> FeatureResult:
        try:
            if request.ticket is None:
                raise fault("invalid_input", "a current ticket is required")
            self.services.kernel.authority.require_current(request.ticket)
            payload = request.payload
            allowed = {
                "decision",
                "request",
                "current_track_id",
                "current_camera_epoch",
                "staged_association",
            }
            if set(payload) - allowed:
                raise fault("invalid_input", "unknown decision input field")
            decision = payload.get("decision")
            outstanding = payload.get("request")
            if not isinstance(decision, Mapping) or not isinstance(outstanding, Mapping):
                raise fault("invalid_input", "decision and outstanding request are required")
            if outstanding.get("mission_id") != request.ticket.mission_id:
                raise fault("stale_ticket", "request belongs to another mission")
            if outstanding.get("epoch") != request.ticket.epoch:
                raise fault("epoch_mismatch", "request epoch is not current")
            expiry = outstanding.get("expires_at")
            if not isinstance(expiry, str):
                raise fault("invalid_input", "request expiry is required")
            try:
                end = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            except ValueError as exc:
                raise fault("invalid_input", "invalid request expiry") from exc
            if end.tzinfo is None:
                raise fault("invalid_input", "request expiry requires a timezone")
            if self.services.kernel.clock.utc_now() >= end:
                raise fault("expired_deadline", "request expired before decision receipt")
            original = outstanding.get("payload")
            returned = decision.get("payload")
            if not isinstance(original, Mapping) or not isinstance(returned, Mapping):
                raise fault("invalid_input", "vision payloads must be objects")
            frame = original.get("frame")
            budget = original.get("max_evidence_age_ms")
            if (
                not isinstance(frame, Mapping)
                or isinstance(budget, bool)
                or not isinstance(budget, int)
            ):
                raise fault("invalid_input", "frame and evidence budget are required")
            captured = frame.get("captured_at")
            if not isinstance(captured, str) or budget <= 0:
                raise fault(
                    "invalid_input", "capture time and positive evidence budget are required"
                )
            try:
                capture_time = datetime.fromisoformat(captured.replace("Z", "+00:00"))
            except ValueError as exc:
                raise fault("invalid_input", "capture time is invalid") from exc
            if capture_time.tzinfo is None:
                raise fault("invalid_input", "capture time requires a timezone")
            age_ms = (self.services.kernel.clock.utc_now() - capture_time).total_seconds() * 1000
            if age_ms < 0 or age_ms > budget:
                raise fault("expired_deadline", "frame is not current at decision receipt")
            if returned.get("frame_captured_at") != captured:
                raise fault("contract_mismatch", "decision capture time does not match its frame")
            if any(
                returned.get(key) != original.get(key)
                for key in (
                    "provider",
                    "model_id",
                    "prompt_version",
                )
            ):
                raise fault("contract_mismatch", "decision model metadata differs from the request")
            track = payload.get("current_track_id")
            camera = payload.get("current_camera_epoch")
            associated = payload.get("staged_association", False)
            if track is not None and not isinstance(track, str):
                raise fault("invalid_input", "track id must be a string")
            if camera is not None and (isinstance(camera, bool) or not isinstance(camera, int)):
                raise fault("invalid_input", "camera epoch must be an integer")
            if not isinstance(associated, bool):
                raise fault("invalid_input", "staged association must be a boolean")
            assessment = self.assess(
                decision,
                outstanding,
                current_track_id=track,
                current_camera_epoch=camera,
                halt_latched=self.services.kernel.authority.cancelled,
                staged_association=associated,
            )
            result = _result(assessment)
            data = dict(_event_payload(assessment))
            data["track_id"] = assessment.track_id
            data["slot"] = SLOT
            return FeatureResult(
                result.status,
                freeze_map(data),
                tuple(GroundEvent(e.kind, request.ticket, e.payload) for e in result.events),
                result.error,
            )
        except GroundFault as exc:
            return FeatureResult("blocked", freeze_map({"motion_authorized": False}), (), exc.error)

    def _handlers(self) -> dict[str, Callable[[], Assessment]]:
        return {
            "drone_example": _drone_example,
            "uncertain_review": _uncertain,
            "frame_mismatch": _frame_mismatch,
            "request_expired": self._request_expired,
            "multiple_people": _multiple_people,
            "unordered_box": _unordered_box,
            "dog_track_mismatch": _dog_mismatch,
            "unknown_sdk_field": _unknown_sdk_field,
            "sdk_reason": _sdk_reason,
            "not_visible": _not_visible,
            "uncalibrated_reposition": _uncalibrated,
            "stale_camera_epoch": self._stale_epoch,
            "halt_preserved": self._halt_preserved,
            "invented_distance": _invented_distance,
            "dog_track_update": _dog_update,
            "calibrated_reposition": _calibrated_reposition,
            "weapon_label": _weapon_label,
            "request_mismatch": _request_mismatch,
        }

    def _request_expired(self) -> Assessment:
        self.services.kernel.authority.latch_cancel("operator halt")
        decision = _clone("drone-vision-decision.json")
        decision["sent_at"] = "2026-11-04T13:00:14.000Z"
        return self._keep_halt(
            assess(
                decision,
                _load("drone-vision-request.json"),
                current_track_id="target-001",
                halt_latched=True,
            )
        )

    def _stale_epoch(self) -> Assessment:
        self.services.kernel.authority.latch_cancel("operator halt")
        return self._keep_halt(
            assess(
                _load("drone-vision-decision.json"),
                _load("drone-vision-request.json"),
                current_track_id="target-001",
                current_camera_epoch=2,
                halt_latched=True,
            )
        )

    def _halt_preserved(self) -> Assessment:
        self.services.kernel.authority.latch_cancel("operator halt")
        return self._keep_halt(
            assess(
                _load("drone-vision-decision.json"),
                _load("drone-vision-request.json"),
                halt_latched=True,
            )
        )

    def _keep_halt(self, assessment: Assessment) -> Assessment:
        if not self.services.kernel.authority.cancelled:
            raise fault("unsafe_state", "decision cleared a halt")
        return assessment


def _drone_example() -> Assessment:
    return assess(_load("drone-vision-decision.json"), _load("drone-vision-request.json"))


def _uncertain() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    _payload(decision)["target_state"] = "uncertain"
    return assess(decision, _load("drone-vision-request.json"))


def _frame_mismatch() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    _payload(decision)["frame_id"] = "other-frame"
    return assess(decision, _load("drone-vision-request.json"))


def _multiple_people() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    payload = _payload(decision)
    found = payload["detections"]
    if not isinstance(found, list) or not found or not isinstance(found[0], dict):
        raise fault("invalid_input", "fixture detection is missing")
    second = {str(key): value for key, value in found[0].items()}
    second["box_xyxy_norm"] = [0.6, 0.1, 0.9, 0.95]
    found.append(second)
    return assess(decision, _load("drone-vision-request.json"))


def _unordered_box() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    _first_detection(_payload(decision))["box_xyxy_norm"] = [0.8, 0.2, 0.3, 0.9]
    return assess(decision, _load("drone-vision-request.json"))


def _dog_mismatch() -> Assessment:
    decision = _clone("dog-vision-decision.json")
    _first_detection(_payload(decision))["track_id"] = "target-999"
    return assess(
        decision,
        _load("dog-vision-request.json"),
        current_track_id="target-001",
    )


def _unknown_sdk_field() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    _payload(decision)["sdk_command"] = "takeoff"
    return assess(decision, _load("drone-vision-request.json"))


def _sdk_reason() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    _payload(decision)["reason"] = "takeoff"
    return assess(decision, _load("drone-vision-request.json"))


def _not_visible() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    payload = _payload(decision)
    payload["target_state"] = "not_visible"
    payload["detections"] = []
    return assess(decision, _load("drone-vision-request.json"))


def _uncalibrated() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    payload = _payload(decision)
    payload["suggested_action"] = "reposition"
    payload["image_direction"] = "left"
    request = _clone("drone-vision-request.json")
    _frame(_payload(request))["camera_to_body_calibration_id"] = None
    return assess(decision, request)


def _invented_distance() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    _payload(decision)["reason"] = "move five meters"
    return assess(decision, _load("drone-vision-request.json"))


def _dog_update() -> Assessment:
    return assess(
        _load("dog-vision-decision.json"),
        _load("dog-vision-request.json"),
        current_track_id="target-001",
    )


def _calibrated_reposition() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    payload = _payload(decision)
    payload["suggested_action"] = "reposition"
    payload["image_direction"] = "left"
    return assess(decision, _load("drone-vision-request.json"))


def _weapon_label() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    _first_detection(_payload(decision))["label"] = "weapon"
    return assess(decision, _load("drone-vision-request.json"))


def _request_mismatch() -> Assessment:
    decision = _clone("drone-vision-decision.json")
    _payload(decision)["request_id"] = "vision-other"
    return assess(decision, _load("drone-vision-request.json"))


def _result(assessment: Assessment) -> FeatureResult:
    data = freeze_map(
        {
            "authorized": False,
            "retained": False,
            "detail": assessment.detail,
            "trace": assessment.trace,
            "device_calls": 0,
            "measurement_clock": "manual",
            "within_limit": True,
            "simulated": True,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
    )
    event = GroundEvent(
        "decision_received",
        None,
        freeze_map(_event_payload(assessment)),
    )
    if assessment.status == "ok":
        return FeatureResult("ok", data, (event,), None)
    if assessment.error_code is None or assessment.error_detail is None:
        raise fault("internal", "rejected decision is missing an error")
    return FeatureResult(
        assessment.status,
        data,
        (event,),
        GroundError(assessment.error_code, assessment.error_detail, False),
    )


def _event_payload(assessment: Assessment) -> dict[str, object]:
    payload: dict[str, object] = {
        "outcome": assessment.outcome,
        "detail": assessment.detail,
        "track_changed": assessment.track_changed,
        "image_direction": assessment.image_direction,
        "image_direction_space": assessment.image_direction_space,
        "motion_authorized": assessment.motion_authorized,
        "halt_latched": assessment.halt_latched,
        "model_id": assessment.model_id,
        "model_score": assessment.model_score,
        "model_score_is_permission": False,
        "proposal": assessment.proposal,
        "device_commands": (),
        "motion_trace": (),
    }
    payload.update(assessment.journal)
    return payload


def _failed(code: str, detail: str) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "authorized": False,
                "retained": False,
                "detail": detail,
                "trace": ("failed", code),
                "device_calls": 0,
                "measurement_clock": "manual",
                "within_limit": True,
                "simulated": True,
                "live_call_count": 0,
                "slot": SLOT,
                "schema_version": SCHEMA,
            }
        ),
        (),
        GroundError(code, detail, code in {"unsafe_state", "io_fault"}),
    )


def _device_calls(services: BaseServices) -> tuple[str, ...]:
    devices = getattr(services.adapters, "devices", None)
    calls = getattr(devices, "calls", ())
    if isinstance(calls, list):
        return tuple(str(item) for item in calls)
    return ()


def _fixture(name: str) -> Path:
    return repo_root() / "fixtures" / "ground" / "g16" / name


def _load(name: str) -> dict[str, object]:
    parsed: object = json.loads(_fixture(name).read_text(encoding="utf-8"))
    return _as_dict(parsed, name)


def _clone(name: str) -> dict[str, object]:
    parsed: object = json.loads(json.dumps(_load(name)))
    return _as_dict(parsed, name)


def _as_dict(value: object, label: str) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    raise fault("invalid_input", f"{label} is not an object")


def _payload(message: dict[str, object]) -> dict[str, object]:
    return _nested(message, "payload")


def _frame(payload: dict[str, object]) -> dict[str, object]:
    return _nested(payload, "frame")


def _nested(owner: dict[str, object], key: str) -> dict[str, object]:
    raw = owner.get(key)
    if not isinstance(raw, dict):
        raise fault("invalid_input", f"{key} is not an object")
    copied = {str(name): item for name, item in raw.items()}
    owner[key] = copied
    return copied


def _first_detection(payload: dict[str, object]) -> dict[str, object]:
    raw = payload.get("detections")
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        raise fault("invalid_input", "fixture detection is missing")
    first = {str(key): value for key, value in raw[0].items()}
    raw[0] = first
    return first
