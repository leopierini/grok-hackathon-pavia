"""Frame provenance feature.

``create(services)`` returns a provider whose ``execute`` checks one frame.
The Task 01 harness calls it with ``kind="diagnostic"`` and a case name.
Direct tests call it with ``kind="stage"`` and the frame payload.
"""

from __future__ import annotations

from patrol.ground.extensions.g14.checks import FrameCheck, check_frame
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
)
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_frame"
SCHEMA = "ground-task-v2"


class FrameFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.phase = ""
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        try:
            if request.kind == "diagnostic":
                from patrol.ground.extensions.g14.scenarios import run_case

                return await run_case(self, request.name)
            if request.kind != "stage" or request.name != SLOT:
                return _failed("invalid_input", "unknown frame request")
            return _stage(
                await check_frame(
                    self.services,
                    request.payload,
                    ticket=request.ticket,
                    on_pause=self._mark_paused,
                )
            )
        finally:
            self.phase = ""

    def _mark_paused(self) -> None:
        self.phase = "paused"


def create(services: BaseServices) -> FrameFeature:
    """Build the frame check. Construction does not read files or call peers."""

    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "frame check create takes base services")
    return FrameFeature(services)


def _stage(check: FrameCheck) -> FeatureResult:
    events: tuple[GroundEvent, ...] = () if check.event is None else (check.event,)
    if check.status == "ok":
        return FeatureResult("ok", check.data, events, None)
    return FeatureResult(
        "failed",
        check.data,
        events,
        GroundError(check.code, check.detail, check.recovery_required),
    )


def _failed(code: str, detail: str) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map({"accepted": False, "reason": detail}),
        (),
        GroundError(code, detail, False),
    )


def device_calls(services: BaseServices) -> int:
    devices = getattr(services.adapters, "devices", None)
    calls = getattr(devices, "calls", ())
    if isinstance(calls, list):
        return len(calls)
    return 0

