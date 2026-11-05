"""Real Tello adapter. Not implemented in this build.

Importing this module does not import a flight SDK and does not open a socket.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from patrol.contract import AdapterError, DroneStatus, InspectionRequest, InspectionResult, RunContext


class RealDrone:
    def __init__(self, *, config: Mapping[str, Any], output_dir: Path) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.trace: list[str] = []

    async def connect(self) -> DroneStatus:
        self.trace.append("connect")
        raise AdapterError("unsupported", "real Tello flight is not in this build")

    async def get_status(self) -> DroneStatus:
        self.trace.append("get_status")
        raise AdapterError("unsupported", "real Tello flight is not in this build")

    async def inspect(
        self, request: InspectionRequest, ctx: RunContext
    ) -> InspectionResult:
        self.trace.append("inspect")
        raise AdapterError("unsupported", "real Tello flight is not in this build")

    async def land(self) -> None:
        self.trace.append("land")
        raise AdapterError("unsupported", "real Tello flight is not in this build")

    async def close(self) -> None:
        self.trace.append("close")
