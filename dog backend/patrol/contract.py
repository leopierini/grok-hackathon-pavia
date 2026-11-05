"""Frozen integration contract v1.0, copied unchanged from the Linear "plan" doc, section 6."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Literal, Mapping, Protocol
CONTRACT_VERSION = "1.0"
Zone = Literal["entrance", "room_2", "display"]
Mode = Literal["fake", "real"]
LaunchOrigin = Literal["dog_pad", "floor"]
FlightState = Literal["grounded", "airborne", "unknown"]
ErrorCode = Literal[
    "unsupported", "invalid_input", "not_connected", "timeout",
    "cancelled", "device_error", "api_error", "unsafe_state",
]
class AdapterError(RuntimeError):
    def __init__(self, code: ErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")
@dataclass(frozen=True)
class RunContext:
    mission_id: str
    deadline_monotonic: float
    cancel: Event
@dataclass(frozen=True)
class Frame:
    path: str                    # absolute path to an existing JPEG
    source: Literal["phone", "dog", "drone"]
    zone: Zone                   # trusted caller metadata, not model output
    captured_at: str | None      # UTC ISO 8601; None only for unknown phone time
    simulated: bool
@dataclass(frozen=True)
class Incident:
    mission_id: str
    zone: Zone
    target: str
    initial_frame: Frame
@dataclass(frozen=True)
class DogStatus:
    connected: bool
    standing: bool | None
    stationary: bool | None
    avoidance_enabled: bool | None
@dataclass(frozen=True)
class RouteResult:
    completed: bool              # route execution, NOT verified arrival
    stopped: bool
    route_id: str
    detail: str
@dataclass(frozen=True)
class DroneStatus:
    connected: bool
    flight_state: FlightState
    battery_percent: int | None
@dataclass(frozen=True)
class InspectionRequest:
    zone: Zone
    profile_id: str              # allowlisted local profile, chosen by Ground
    launch_origin: LaunchOrigin
@dataclass(frozen=True)
class InspectionResult:
    outcome: Literal["captured", "unavailable", "failed", "cancelled"]
    frame: Frame | None
    flight_state: FlightState    # state AFTER landing attempt
    detail: str
@dataclass(frozen=True)
class DispatchDecision:
    action: Literal["dispatch", "dismiss", "review"]
    reason: str
@dataclass(frozen=True)
class GroundDecision:
    action: Literal["sufficient", "inspect", "review"]
    observation: str
    reason: str
@dataclass(frozen=True)
class Resolution:
    outcome: Literal["confirmed", "cleared", "inconclusive"]
    summary: str
    reason: str
class DogPort(Protocol):
    async def connect(self) -> DogStatus: ...
    async def prepare(self, ctx: RunContext) -> DogStatus: ...
    async def get_status(self) -> DogStatus: ...
    async def run_route(self, zone: Zone, ctx: RunContext) -> RouteResult: ...
    async def capture_frame(self, zone: Zone, ctx: RunContext) -> Frame: ...
    async def halt(self) -> None: ...
    async def play_warning(self, warning_id: str, text: str) -> None: ...
    async def execute(self, command: Mapping[str, Any]) -> str: ...
    async def close(self) -> None: ...
class DronePort(Protocol):
    async def connect(self) -> DroneStatus: ...
    async def get_status(self) -> DroneStatus: ...
    async def inspect(self, request: InspectionRequest,
                      ctx: RunContext) -> InspectionResult: ...
    async def land(self) -> None: ...
    async def close(self) -> None: ...
class ReasonerPort(Protocol):
    def metadata(self) -> Mapping[str, str]: ...
    async def assess_incident(self, incident: Incident,
                              ctx: RunContext) -> DispatchDecision: ...
    async def assess_ground_view(self, incident: Incident, frame: Frame,
                                 ctx: RunContext) -> GroundDecision: ...
    async def resolve_incident(self, incident: Incident, ground: Frame,
                               aerial: Frame | None,
                               ctx: RunContext) -> Resolution: ...
    async def compose_alert(self, incident: Incident, result: Resolution,
                            ctx: RunContext) -> str: ...
    async def close(self) -> None: ...
