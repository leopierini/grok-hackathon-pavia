"""Scripted adapters for gateway tests. They do not open sockets or import SDKs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal, TypeVar, cast

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
)
from patrol.ground.kernel.contracts import KernelContext


class RecordedDog:
    def __init__(self, log: list[str], kernel: KernelContext) -> None:
        self.log = log
        self.kernel = kernel
        self.connect_result: object = DogStatus(True, True, True, True)
        self.status_result: object = DogStatus(True, True, True, True)
        self.route_result: object = RouteResult(True, True, "room_2", "stopped")
        self.close_error: Exception | None = None
        self.hold: str | None = None
        self.output_dir = ""

    async def connect(self) -> DogStatus:
        self.log.append("dog.connect")
        return _raise_or(self.connect_result, DogStatus)

    async def prepare(self, ctx: RunContext) -> DogStatus:
        del ctx
        self.log.append("dog.prepare")
        return DogStatus(True, True, True, True)

    async def get_status(self) -> DogStatus:
        self.log.append("dog.get_status")
        return _raise_or(self.status_result, DogStatus)

    async def run_route(self, zone: str, ctx: RunContext) -> RouteResult:
        del zone, ctx
        self.log.append("dog.run_route")
        if self.hold is not None:
            await self.kernel.barriers.wait(self.hold)
        return _raise_or(self.route_result, RouteResult)

    async def capture_frame(self, zone: str, ctx: RunContext) -> Frame:
        del ctx
        self.log.append("dog.capture_frame")
        if zone not in {"entrance", "room_2", "display"}:
            raise AdapterError("invalid_input", "zone")
        trusted = cast(Literal["entrance", "room_2", "display"], zone)
        return Frame(f"{self.output_dir}/dog.jpg", "dog", trusted, None, True)

    async def halt(self) -> None:
        self.log.append("dog.halt")

    async def close(self) -> None:
        self.log.append("dog.close")
        if self.close_error is not None:
            raise self.close_error


class RecordedDrone:
    def __init__(self, log: list[str], kernel: KernelContext) -> None:
        self.log = log
        self.kernel = kernel
        self.connect_result: object = DroneStatus(True, "grounded", 80)
        self.status_result: object = DroneStatus(True, "grounded", 80)
        self.close_error: Exception | None = None
        self.output_dir = ""

    async def connect(self) -> DroneStatus:
        self.log.append("drone.connect")
        return _raise_or(self.connect_result, DroneStatus)

    async def get_status(self) -> DroneStatus:
        self.log.append("drone.get_status")
        return _raise_or(self.status_result, DroneStatus)

    async def inspect(self, request: InspectionRequest, ctx: RunContext) -> InspectionResult:
        del ctx
        self.log.append("drone.inspect")
        frame = Frame(f"{self.output_dir}/drone.jpg", "drone", request.zone, None, True)
        return InspectionResult("captured", frame, "grounded", "simulated")

    async def land(self) -> None:
        self.log.append("drone.land")

    async def close(self) -> None:
        self.log.append("drone.close")
        if self.close_error is not None:
            raise self.close_error


class RecordedReasoner:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.output_dir = ""
        self.fail = False

    def metadata(self) -> dict[str, str]:
        self.log.append("reasoner.metadata")
        if self.fail:
            raise AdapterError("api_error", "reasoner unavailable")
        return {"mode": "fake", "model": "scripted", "prompt_version": "fake-v1"}

    async def assess_incident(self, incident: Incident, ctx: RunContext) -> DispatchDecision:
        del incident, ctx
        self.log.append("reasoner.assess_incident")
        return DispatchDecision("dispatch", "scripted dispatch")

    async def assess_ground_view(
        self,
        incident: Incident,
        frame: Frame,
        ctx: RunContext,
    ) -> GroundDecision:
        del incident, frame, ctx
        self.log.append("reasoner.assess_ground_view")
        return GroundDecision("sufficient", "usable", "ground only")

    async def resolve_incident(
        self,
        incident: Incident,
        ground: Frame,
        aerial: Frame | None,
        ctx: RunContext,
    ) -> Resolution:
        del incident, ground, aerial, ctx
        self.log.append("reasoner.resolve_incident")
        return Resolution("confirmed", "target is present", "scripted")

    async def compose_alert(self, incident: Incident, result: Resolution, ctx: RunContext) -> str:
        del incident, result, ctx
        self.log.append("reasoner.compose_alert")
        return "room_2: target is present"

    async def close(self) -> None:
        self.log.append("reasoner.close")


class Bundle:
    def __init__(self, kernel: KernelContext) -> None:
        self.log: list[str] = []
        self.kwargs: list[dict[str, object]] = []
        self.dog = RecordedDog(self.log, kernel)
        self.drone = RecordedDrone(self.log, kernel)
        self.reasoner = RecordedReasoner(self.log)

    def resolver(self) -> dict[str, object]:
        return {
            "source": "private-stub",
            "dog": self._factory("dog", self.dog),
            "drone": self._factory("drone", self.drone),
            "reasoner": self._factory("reasoner", self.reasoner),
        }

    def _factory(self, component: str, adapter: object) -> Callable[..., object]:
        def create(
            *,
            mode: str,
            config: Mapping[str, object],
            output_dir: str,
        ) -> object:
            transport = config.get("transport", "none")
            self.log.append(f"{component}.create:{transport}")
            self.kwargs.append(
                {
                    "component": component,
                    "mode": mode,
                    "config": config,
                    "output_dir": output_dir,
                }
            )
            _remember_output(adapter, output_dir)
            return adapter

        return create


_T = TypeVar("_T")


def _remember_output(adapter: object, output_dir: str) -> None:
    if isinstance(adapter, (RecordedDog, RecordedDrone, RecordedReasoner)):
        adapter.output_dir = output_dir


def _raise_or(value: object, kind: type[_T]) -> _T:
    if isinstance(value, Exception):
        raise value
    if not isinstance(value, kind):
        raise AdapterError("invalid_input", "scripted result has the wrong type")
    return value
