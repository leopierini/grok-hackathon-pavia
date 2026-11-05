"""Boundary checks. Dataclasses themselves do not validate."""

from __future__ import annotations

import math
from collections.abc import Mapping
from types import MappingProxyType

from patrol.ground.kernel.catalog import (
    BOOLEAN_KEYS,
    COMMON_INPUTS,
    ERROR_CODES,
    EVENT_KINDS,
    FEATURE_KINDS,
    FEATURE_STATUSES,
    NULLABLE_KEYS,
    SLOT_BY_NAME,
)
from patrol.ground.kernel.contracts import FeatureRequest, FeatureResult, GroundError, GroundEvent
from patrol.ground.kernel.faults import fault


def require_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise fault("invalid_input", f"{label} must be a boolean")
    return value


def freeze_map(value: Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise fault("invalid_input", "expected a mapping")
    frozen: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise fault("invalid_input", "mapping keys must be strings")
        frozen[key] = item
    return MappingProxyType(frozen)


def freeze_str_map(value: Mapping[str, str]) -> Mapping[str, str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise fault("invalid_input", "expected a string mapping")
    frozen: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise fault("invalid_input", "modes and profiles must be strings")
        frozen[key] = item
    return MappingProxyType(frozen)


class BoundaryValidation:
    def payload(
        self,
        slot: str,
        direction: str,
        data: Mapping[str, object],
    ) -> Mapping[str, object]:
        spec = SLOT_BY_NAME.get(slot)
        if spec is None:
            raise fault("unknown_slot", f"unknown slot {slot}")
        if direction not in {"input", "output"}:
            raise fault("invalid_input", "payload direction must be input or output")
        frozen = freeze_map(data)
        if direction == "input":
            allowed = set(spec.inputs) | set(COMMON_INPUTS)
        else:
            allowed = set(spec.outputs)
        unknown = [key for key in frozen if key not in allowed]
        if unknown:
            raise fault("validation_failed", "unknown payload key: " + ", ".join(sorted(unknown)))
        for key, value in frozen.items():
            if key in BOOLEAN_KEYS and value is not None:
                require_bool(value, label=key)
            elif key in NULLABLE_KEYS and value is None:
                continue
            elif key.endswith("_s") or key in {
                "arrival_monotonic",
                "live_call_count",
                "device_calls",
                "seed",
            }:
                _number(value, key)
        return frozen

    def feature_request(self, slot: str, request: FeatureRequest) -> FeatureRequest:
        if not isinstance(request, FeatureRequest):
            raise fault("invalid_input", "expected a FeatureRequest")
        if request.kind not in FEATURE_KINDS:
            raise fault("validation_failed", "unknown feature request kind")
        if not isinstance(request.name, str) or not request.name:
            raise fault("invalid_input", "feature name is required")
        payload = self.payload(slot, "input", request.payload)
        return FeatureRequest(request.kind, request.name, request.ticket, payload)

    def feature_result(self, slot: str, result: FeatureResult) -> FeatureResult:
        if not isinstance(result, FeatureResult):
            raise fault("invalid_input", "expected a FeatureResult")
        if result.status not in FEATURE_STATUSES:
            raise fault("validation_failed", "unknown feature status")
        if result.status == "ok" and result.error is not None:
            raise fault("validation_failed", "ok result cannot carry an error")
        if result.status != "ok" and result.error is None:
            raise fault("validation_failed", "failed result requires a GroundError")
        if result.error is not None:
            _error(result.error)
        for event in result.events:
            _event(event)
        data = self.payload(slot, "output", result.data)
        return FeatureResult(result.status, data, tuple(result.events), result.error)


def _error(error: GroundError) -> None:
    if not isinstance(error, GroundError):
        raise fault("validation_failed", "error must be a GroundError")
    if error.code not in ERROR_CODES:
        raise fault("validation_failed", "error code is not in the allowlist")
    if not isinstance(error.detail, str) or not error.detail:
        raise fault("validation_failed", "error detail is required")
    require_bool(error.recovery_required, label="recovery_required")


def _event(event: GroundEvent) -> None:
    if not isinstance(event, GroundEvent):
        raise fault("validation_failed", "event must be a GroundEvent")
    if event.kind not in EVENT_KINDS:
        raise fault("validation_failed", "event kind is not in the allowlist")
    freeze_map(event.payload)


def _number(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("validation_failed", f"{label} must be numeric")
    if not math.isfinite(float(value)):
        raise fault("validation_failed", f"{label} must be finite")
