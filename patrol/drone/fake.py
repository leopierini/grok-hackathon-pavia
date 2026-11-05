"""Scripted drone. No SDK import and no network."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from patrol.contract import (
    AdapterError,
    DroneStatus,
    FlightState,
    Frame,
    InspectionRequest,
    InspectionResult,
    RunContext,
)
from patrol.drone.profile import allow

_BUNDLED_JPEG = Path(__file__).resolve().parent / "assets" / "simulated.jpg"

_SCENARIOS = {
    "blocked_resolved",
    "dismiss",
    "ground_clear",
    "ground_confirmed",
    "drone_unavailable",
    "route_blocked",
    "invalid_model",
    "stale_frame",
    "takeoff_timeout",
    "landing_unknown",
    "slow_model",
}
_ZONES = {"entrance", "room_2", "display"}
_ORIGINS = {"dog_pad", "floor"}
_BATTERY = 90


class FakeDrone:
    """One inspection, then grounded, unless the scenario says otherwise."""

    def __init__(self, *, config: Mapping[str, Any], output_dir: Path) -> None:
        scenario = config.get("scenario", "blocked_resolved")
        if not isinstance(scenario, str) or scenario not in _SCENARIOS:
            raise AdapterError("invalid_input", f"unknown scenario {scenario!r}")
        self.scenario = scenario
        self.output_dir = Path(output_dir)
        self.trace: list[str] = []
        self._connected = False
        self._closed = False
        self._flight_state: FlightState = "grounded"
        self._cleanup_error: str | None = None

    async def connect(self) -> DroneStatus:
        self.trace.append("connect")
        self._require_open()
        self._connected = True
        self._flight_state = "grounded"
        return self._status()

    async def get_status(self) -> DroneStatus:
        self.trace.append("get_status")
        self._require_open()
        self._require_connected()
        return self._status()

    async def inspect(
        self, request: InspectionRequest, ctx: RunContext
    ) -> InspectionResult:
        self.trace.append("inspect")
        self._require_open()
        self._require_connected()
        self._validate(request)
        if self._flight_state == "unknown":
            raise AdapterError(
                "unsafe_state",
                "flight state is unknown; operator recovery required",
            )
        if ctx.cancel.is_set() or time.monotonic() >= ctx.deadline_monotonic:
            return InspectionResult(
                "cancelled", None, self._flight_state, "stopped before takeoff"
            )
        if self.scenario == "drone_unavailable":
            return InspectionResult(
                "unavailable",
                None,
                "grounded",
                "drone unavailable; no takeoff",
            )
        self.trace.append("takeoff_attempt")
        if self.scenario == "takeoff_timeout":
            self.trace.append("abort_attempt")
            self._flight_state = "unknown"
            return InspectionResult(
                "failed",
                None,
                "unknown",
                "takeoff timed out after one attempt; no retry",
            )
        frame = self._save_frame(request, ctx)
        if self.scenario == "landing_unknown":
            self.trace.append("abort_attempt")
            self._flight_state = "unknown"
            return InspectionResult(
                "failed",
                frame,
                "unknown",
                "frame saved but landing state is unknown",
            )
        self._flight_state = "grounded"
        return InspectionResult(
            "captured", frame, "grounded", "simulated inspection"
        )

    async def land(self) -> None:
        self.trace.append("land")
        self._require_open()
        if self._flight_state == "grounded":
            return
        raise AdapterError(
            "unsafe_state",
            "landing not confirmed; operator recovery required",
        )

    async def close(self) -> None:
        self.trace.append("close")
        if self._closed:
            return
        if self._flight_state == "airborne":
            self._flight_state = "grounded"
        elif self._flight_state == "unknown":
            self._cleanup_error = "landing not confirmed"
        self._closed = True
        self._connected = False

    def _status(self) -> DroneStatus:
        battery = _BATTERY if self._flight_state != "unknown" else None
        return DroneStatus(self._connected, self._flight_state, battery)

    def _require_open(self) -> None:
        if self._closed:
            raise AdapterError("device_error", "adapter is closed")

    def _require_connected(self) -> None:
        if not self._connected:
            raise AdapterError("not_connected", "drone is not connected")

    def _validate(self, request: InspectionRequest) -> None:
        if request.zone not in _ZONES:
            raise AdapterError("invalid_input", "zone is not allowed")
        if request.launch_origin not in _ORIGINS:
            raise AdapterError("invalid_input", "launch origin is not allowed")
        if not isinstance(request.profile_id, str) or not request.profile_id.strip():
            raise AdapterError("invalid_input", "profile_id is required")
        allow(request.profile_id, request.zone, request.launch_origin)

    def _save_frame(self, request: InspectionRequest, ctx: RunContext) -> Frame:
        if not _BUNDLED_JPEG.is_file():
            raise AdapterError("device_error", "bundled simulated JPEG is missing")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(
            ch if ch.isalnum() or ch in "-_" else "_" for ch in ctx.mission_id
        ) or "mission"
        dest = self.output_dir / f"{safe}-aerial.jpg"
        stem = dest.stem
        n = 2
        while dest.exists():
            dest = self.output_dir / f"{stem}-{n}.jpg"
            n += 1
        partial = dest.with_suffix(".jpg.partial")
        partial.write_bytes(_BUNDLED_JPEG.read_bytes())
        partial.replace(dest)
        captured = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return Frame(
            path=str(dest.resolve()),
            source="drone",
            zone=request.zone,
            captured_at=captured,
            simulated=True,
        )
