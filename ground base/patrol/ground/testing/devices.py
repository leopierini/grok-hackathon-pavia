"""Scripted Dog, Drone, and Reasoner doubles. They never open a socket."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from patrol.contract import (
    AdapterError,
    DispatchDecision,
    DogStatus,
    DroneStatus,
    Frame,
    GroundDecision,
    Incident,
    InspectionRequest,
    InspectionResult,
    Resolution,
    RouteResult,
    RunContext,
    Zone,
)
from patrol.ground.kernel.contracts import KernelContext
from patrol.ground.kernel.jpeg import tiny_jpeg_bytes


class DeviceBundle:
    def __init__(self, kernel: KernelContext, *, scenario: str, output_dir: Path) -> None:
        self.calls: list[str] = []
        self.output_dir = output_dir
        self.dog = FakeDog(kernel, scenario=scenario, bundle=self)
        self.drone = FakeDrone(kernel, scenario=scenario, bundle=self)
        self.reasoner = FakeReasoner(kernel, scenario=scenario, bundle=self)

    @property
    def live_call_count(self) -> int:
        return 0

    def note(self, name: str) -> None:
        self.calls.append(name)

    def component(self, name: str) -> FakeDog | FakeDrone | FakeReasoner:
        if name == "dog":
            return self.dog
        if name == "drone":
            return self.drone
        if name == "reasoner":
            return self.reasoner
        raise AdapterError("invalid_input", "unknown component")


class _Device:
    def __init__(self, kernel: KernelContext, *, scenario: str, bundle: DeviceBundle) -> None:
        self.kernel = kernel
        self.scenario = scenario
        self.bundle = bundle

    def _refuse_if_stopped(self, name: str, ctx: RunContext) -> None:
        if ctx.cancel.is_set() or self.kernel.authority.cancelled:
            self.bundle.note(f"refused:{name}")
            raise AdapterError("cancelled", "cancelled")

    def _frame(self, source: str, zone: str, ctx: RunContext, *, stale: bool) -> Frame:
        path = self.bundle.output_dir / f"{ctx.mission_id}-{source}.jpg"
        self.kernel.io.write_bytes(path, tiny_jpeg_bytes())
        if stale:
            captured = "2000-01-01T00:00:00Z"
        else:
            captured = self.kernel.clock.utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
        if source not in {"phone", "dog", "drone"}:
            raise AdapterError("invalid_input", "unknown frame source")
        if zone not in {"entrance", "room_2", "display"}:
            raise AdapterError("invalid_input", "unknown zone")
        return Frame(
            str(path.resolve()),
            cast(Literal["phone", "dog", "drone"], source),
            cast(Zone, zone),
            captured,
            True,
        )


class FakeDog(_Device):
    async def connect(self) -> DogStatus:
        self.bundle.note("dog.connect")
        return DogStatus(True, None, None, None)

    async def prepare(self, ctx: RunContext) -> DogStatus:
        self._refuse_if_stopped("dog.prepare", ctx)
        await self.kernel.barriers.wait("dog.prepare")
        self.bundle.note("dog.prepare")
        return DogStatus(True, True, True, True)

    async def get_status(self) -> DogStatus:
        self.bundle.note("dog.get_status")
        return DogStatus(True, True, True, True)

    async def run_route(self, zone: str, ctx: RunContext) -> RouteResult:
        self._refuse_if_stopped("dog.run_route", ctx)
        await self.kernel.barriers.wait("dog.run_route")
        self.bundle.note("dog.run_route")
        if self.scenario == "route_blocked":
            return RouteResult(False, True, zone, "route blocked")
        return RouteResult(True, True, zone, "simulated stop")

    async def capture_frame(self, zone: str, ctx: RunContext) -> Frame:
        self._refuse_if_stopped("dog.capture_frame", ctx)
        self.bundle.note("dog.capture_frame")
        return self._frame("dog", zone, ctx, stale=self.scenario == "stale_frame")

    async def halt(self) -> None:
        self.bundle.note("dog.halt")

    async def close(self) -> None:
        self.bundle.note("dog.close")


class FakeDrone(_Device):
    async def connect(self) -> DroneStatus:
        self.bundle.note("drone.connect")
        return DroneStatus(True, "grounded", 80)

    async def get_status(self) -> DroneStatus:
        self.bundle.note("drone.get_status")
        return DroneStatus(True, "grounded", 80)

    async def inspect(self, request: InspectionRequest, ctx: RunContext) -> InspectionResult:
        self._refuse_if_stopped("drone.inspect", ctx)
        await self.kernel.barriers.wait("drone.inspect")
        if self.scenario == "drone_unavailable":
            self.bundle.note("drone.inspect")
            return InspectionResult("unavailable", None, "grounded", "drone unavailable")
        if self.scenario == "takeoff_timeout":
            self.bundle.note("takeoff_attempt")
            self.bundle.note("abort_attempt")
            self.bundle.note("drone.inspect")
            return InspectionResult("failed", None, "unknown", "takeoff timeout")
        frame = self._frame("drone", request.zone, ctx, stale=False)
        self.bundle.note("drone.inspect")
        if self.scenario == "landing_unknown":
            return InspectionResult("captured", frame, "unknown", "landing unknown")
        return InspectionResult("captured", frame, "grounded", "simulated landing")

    async def land(self) -> None:
        self.bundle.note("drone.land")
        if self.scenario == "takeoff_timeout":
            self.bundle.note("abort_attempt")

    async def close(self) -> None:
        self.bundle.note("drone.close")


class FakeReasoner(_Device):
    def metadata(self) -> dict[str, str]:
        self.bundle.note("reasoner.metadata")
        return {
            "mode": "fake",
            "scenario": self.scenario,
            "model": "scripted",
            "prompt_version": "fake-v1",
        }

    async def assess_incident(self, incident: Incident, ctx: RunContext) -> DispatchDecision:
        del incident
        await self.kernel.barriers.wait("reasoner.assess_incident")
        self._refuse_if_stopped("reasoner.assess_incident", ctx)
        if self.scenario == "invalid_model":
            raise AdapterError("api_error", "invalid model output")
        self.bundle.note("reasoner.assess_incident")
        if self.scenario == "dismiss":
            return DispatchDecision("dismiss", "scene does not match the target")
        return DispatchDecision("dispatch", "scripted dispatch")

    async def assess_ground_view(
        self,
        incident: Incident,
        frame: Frame,
        ctx: RunContext,
    ) -> GroundDecision:
        del incident, frame
        self._refuse_if_stopped("reasoner.assess_ground_view", ctx)
        self.bundle.note("reasoner.assess_ground_view")
        if self.scenario == "blocked_resolved":
            return GroundDecision("inspect", "ground view is blocked", "need a higher view")
        return GroundDecision("sufficient", "ground view is usable", "no extra view")

    async def resolve_incident(
        self,
        incident: Incident,
        ground: Frame,
        aerial: Frame | None,
        ctx: RunContext,
    ) -> Resolution:
        del incident, ground, aerial
        self._refuse_if_stopped("reasoner.resolve_incident", ctx)
        self.bundle.note("reasoner.resolve_incident")
        if self.scenario == "ground_clear":
            return Resolution("cleared", "area is clear", "ground evidence")
        if self.scenario in {"ground_confirmed", "blocked_resolved"}:
            return Resolution("confirmed", "target is present", "scripted evidence")
        return Resolution("inconclusive", "evidence is incomplete", "scripted fallback")

    async def compose_alert(self, incident: Incident, result: Resolution, ctx: RunContext) -> str:
        del incident
        self._refuse_if_stopped("reasoner.compose_alert", ctx)
        self.bundle.note("reasoner.compose_alert")
        return f"simulated report: {result.outcome}"

    async def close(self) -> None:
        self.bundle.note("reasoner.close")
