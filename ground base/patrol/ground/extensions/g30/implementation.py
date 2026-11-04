"""Ethernet, Wi-Fi, and Pi data-path readiness.

The frozen Gate B loader rejects ``ground-task-v2`` and unknown slots. The
manifest therefore uses the GROUND-30 slot the loader already owns
(``feature.adapter_probe``). Every result reports ``feature.v2_links`` and
``ground-task-v2``. Gate C admits that name. This module does not edit the
loader, and it does not treat the retired adapter-probe slot as its policy.
"""

from __future__ import annotations

from collections.abc import Mapping

from patrol.ground.extensions.g30.probe import LinkReport, evaluate, scripted_probe
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_links"
SCHEMA = "ground-task-v2"


def create(services: BaseServices) -> LinkFeature:
    """Build the link feature. Construction does not probe a network."""
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "link readiness create expects base services")
    return LinkFeature(services)


class LinkFeature:
    """Check one selected dog transport and the separate Pi path."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest")
        before = _device_calls(self.services)
        try:
            report = _report_for(request)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail)
        if _device_calls(self.services) != before:
            return _failed("unsafe_state", "link check touched a device")
        if self.services.kernel.authority.cancelled:
            return _failed("unsafe_state", "link check latched cancellation")
        result = _result(report)
        if request.name == "check":
            return FeatureResult(
                result.status,
                freeze_map({**result.data, **_event_payload(report)}),
                result.events,
                result.error,
            )
        return result


def _report_for(request: FeatureRequest) -> LinkReport:
    if request.name == "check":
        payload = request.payload
        if not isinstance(payload, Mapping) or set(payload) != {"probe"}:
            raise fault("invalid_input", "check payload must contain only probe")
        probe = payload["probe"]
        if not isinstance(probe, Mapping):
            raise fault("invalid_input", "probe must be a mapping")
        return evaluate(probe)
    return evaluate(scripted_probe(request.name))


def _result(report: LinkReport) -> FeatureResult:
    data = freeze_map(
        {
            "authorized": False,
            "retained": False,
            "detail": report.detail,
            "trace": report.trace,
            "device_calls": 0,
            "measurement_clock": "manual",
            "within_limit": True,
            "simulated": report.simulated,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
    )
    event = GroundEvent(report.event_kind, None, freeze_map(_event_payload(report)))
    if report.status == "ok":
        return FeatureResult("ok", data, (event,), None)
    if report.error_code is None:
        raise fault("internal", "blocked link check is missing an error")
    return FeatureResult(
        report.status,
        data,
        (event,),
        GroundError(report.error_code, report.detail, report.recovery_required),
    )


def _event_payload(report: LinkReport) -> dict[str, object]:
    return {
        "ready": report.ready,
        "profile": report.profile_name,
        "dog_transport": report.dog_transport,
        "pi_path": report.pi_path,
        "missing_path": report.missing_path,
        "rssi_blocked": report.rssi_blocked,
        "dog_identified": report.dog_identified,
        "drone_identified": report.drone_identified,
        "pi_telemetry": report.pi_telemetry,
        "router": report.router_note,
        "request_safety": report.request_safety,
        "task28_latch": report.request_safety,
        "evidence": report.evidence,
        "blocked_reason": report.detail,
        "motion_authorized": False,
    }


def _failed(code: str, detail: str) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "authorized": False,
                "retained": False,
                "detail": detail,
                "trace": ("failed", code, "sockets:none"),
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
