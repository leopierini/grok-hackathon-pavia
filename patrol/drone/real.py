"""Real Tello adapter.

Importing this module does not import a flight SDK and does not open a socket.
``connect`` is the first method that binds a UDP port, and only when ``config``
already contains a host and a port. This module does not substitute the
address baked into ``tello_sdk.py``.

Motor commands stay inside this adapter. ``land_on_dog`` is not implemented
here and must not be aliased to ``land``.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from patrol.contract import (
    AdapterError,
    DroneStatus,
    FlightState,
    Frame,
    InspectionRequest,
    InspectionResult,
    RunContext,
)

# Museum ceiling. A caller can ask for less. It cannot ask for more.
MAX_FLIGHT_S = 8.0
DEFAULT_SETTLE_S = 1.0
DEFAULT_HOLD_S = 1.0
DEFAULT_BATTERY_MIN = 20
DEFAULT_COMMAND_TIMEOUT_S = 5.0
DEFAULT_LINK_TIMEOUT_S = 2.0
_TRANSLATION = frozenset(
    {
        "forward",
        "back",
        "left",
        "right",
        "up",
        "down",
        "go",
        "curve",
        "cw",
        "ccw",
        "flip",
        "speed",
    }
)


def _cap(config: Mapping[str, Any], key: str, default: float, ceiling: float) -> float:
    if key not in config:
        return default
    raw = config[key]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return default
    value = float(raw)
    if value < 0:
        return default
    return min(value, ceiling)


class RealDrone:
    """One Tello session. Construction does not bind a socket."""

    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        output_dir: Path,
        sdk_factory: Callable[[str, int], Any] | None = None,
        frame_source: Callable[[], bytes] | None = None,
    ) -> None:
        self.config = dict(config) if isinstance(config, Mapping) else {}
        self.output_dir = Path(output_dir)
        self.trace: list[str] = []
        self.commands: list[str] = []
        self._sdk_factory = sdk_factory
        self._frame_source = frame_source
        self._sdk: Any = None
        self._connected = False
        self._closed = False
        self._halted = False
        self._channel_ok = False
        self._flight: FlightState = "grounded"
        self._battery: int | None = None
        self._motion = self.config.get("motion_authorized") is True
        self._max_flight_s = _cap(self.config, "max_flight_s", MAX_FLIGHT_S, MAX_FLIGHT_S)
        self._settle_s = _cap(self.config, "settle_s", DEFAULT_SETTLE_S, DEFAULT_SETTLE_S)
        self._hold_s = _cap(self.config, "hold_s", DEFAULT_HOLD_S, DEFAULT_HOLD_S)
        battery_min = self.config.get("battery_min_percent", DEFAULT_BATTERY_MIN)
        if isinstance(battery_min, bool) or not isinstance(battery_min, (int, float)):
            battery_min = DEFAULT_BATTERY_MIN
        self._battery_min = int(battery_min)
        timeout = _cap(
            self.config,
            "command_timeout_s",
            DEFAULT_COMMAND_TIMEOUT_S,
            DEFAULT_COMMAND_TIMEOUT_S,
        )
        self._command_timeout_s = timeout if timeout > 0 else DEFAULT_COMMAND_TIMEOUT_S
        link = _cap(self.config, "link_timeout_s", DEFAULT_LINK_TIMEOUT_S, DEFAULT_LINK_TIMEOUT_S)
        self._link_timeout_s = link if link > 0 else DEFAULT_LINK_TIMEOUT_S

    async def connect(self) -> DroneStatus:
        self.trace.append("connect")
        self._require_open()
        if self._connected and self._sdk is not None:
            return await self.get_status()
        host, port = self._endpoint()
        self._sdk = self._open_sdk(host, port)
        reply = await self._query("command")
        if "ok" not in reply.lower():
            self._drop_sdk()
            raise AdapterError("device_error", "drone did not enter SDK mode; no motion was sent")
        battery_reply = await self._query("battery?")
        self._battery = _battery(battery_reply)
        self._read_height()
        self._connected = True
        self._channel_ok = True
        return await self.get_status()

    async def get_status(self) -> DroneStatus:
        self.trace.append("get_status")
        self._require_open()
        if not self._connected or self._sdk is None:
            raise AdapterError("not_connected", "drone is not connected")
        try:
            battery_reply = await self._query("battery?")
        except AdapterError:
            self._channel_ok = False
            return DroneStatus(False, "unknown", None)
        self._battery = _battery(battery_reply)
        self._read_height()
        connected = self.link_ok()
        battery = self._battery if connected else None
        return DroneStatus(connected, self._flight if connected else "unknown", battery)

    async def inspect(self, request: InspectionRequest, ctx: RunContext) -> InspectionResult:
        """Floor profile: one takeoff, one still, one land. No translation."""

        self.trace.append("inspect")
        self._require_open()
        self._require_connected()
        if not self._motion:
            raise AdapterError("unsafe_state", "motion not authorized; no takeoff was sent")
        if self._halted:
            raise AdapterError("cancelled", "halted; no takeoff was sent")
        if not self.link_ok():
            raise AdapterError("not_connected", "drone link is down; no takeoff was sent")
        self._check_profile(request)
        if ctx.cancel.is_set() or time.monotonic() >= ctx.deadline_monotonic:
            return InspectionResult("cancelled", None, self._flight, "stopped before takeoff")
        if self._battery is None or self._battery < self._battery_min:
            raise AdapterError(
                "unsafe_state",
                "battery below the floor minimum or unreadable; no takeoff was sent",
            )
        started = time.monotonic()
        deadline = min(ctx.deadline_monotonic, started + self._max_flight_s)
        reply = await self._query("takeoff", timeout=min(8.0, self._command_timeout_s))
        self.trace.append("takeoff_attempt")
        if "ok" not in reply.lower():
            self._flight = "unknown"
            raise AdapterError("device_error", "takeoff was not accepted; no retry")
        self._flight = "airborne"
        if not await self._wait(self._settle_s, ctx, deadline):
            await self._stop_flying()
            return InspectionResult("cancelled", None, self._flight, "stopped during settle")
        frame: Frame | None = None
        try:
            frame = self._store_frame(await self.capture_still(), request, ctx)
        except AdapterError:
            frame = None
        if not await self._wait(self._hold_s, ctx, deadline):
            await self._stop_flying()
            return InspectionResult(
                "failed" if frame is None else "captured",
                frame,
                self._flight,
                "stopped during hold",
            )
        await self._land_once()
        if frame is not None and self._flight == "grounded":
            return InspectionResult("captured", frame, "grounded", "floor profile")
        return InspectionResult("failed", frame, self._flight, "landing not confirmed")

    async def hover(self) -> None:
        """Hold still. A grounded aircraft is not given a motor command."""

        self.trace.append("hover")
        self._require_open()
        self._require_connected()
        if self._halted:
            raise AdapterError("cancelled", "halted")
        if self._flight != "airborne":
            return
        self._send("rc 0 0 0 0")

    async def land(self) -> None:
        """Floor land. Callers must not use this for land-on-dog."""

        self.trace.append("land")
        self._require_open()
        self._require_connected()
        if self._flight == "grounded":
            return
        if not self._motion and not self._halted:
            raise AdapterError("unsafe_state", "motion not authorized; no land was sent")
        await self._land_once()

    async def halt(self) -> None:
        """E-stop. Airborne or unknown cuts the motors. Grounded only zeroes rc."""

        self.trace.append("halt")
        self._halted = True
        if self._sdk is None:
            return
        if self._flight == "grounded":
            self._send("rc 0 0 0 0")
            return
        self._send("emergency")
        self._flight = "unknown"

    async def capture_still(self) -> bytes:
        """One JPEG. This does not take off."""

        self.trace.append("capture_still")
        self._require_open()
        self._require_connected()
        if self._frame_source is not None:
            data = self._frame_source()
            if not isinstance(data, (bytes, bytearray)) or not data:
                raise AdapterError("device_error", "no camera frame")
            return bytes(data)
        try:
            import av  # noqa: F401
        except ImportError as exc:
            raise AdapterError(
                "device_error",
                "camera decoder is not installed; no flight command was sent",
            ) from exc
        await self._query("streamon", timeout=min(3.0, self._command_timeout_s))
        try:
            return await asyncio.wait_for(asyncio.to_thread(_read_udp_jpeg), 3.0)
        except (AdapterError, TimeoutError, OSError) as exc:
            raise AdapterError(
                "device_error",
                "camera frame was not retrieved; no flight command was sent",
            ) from exc

    async def close(self) -> None:
        self.trace.append("close")
        if self._closed:
            return
        try:
            if self._flight == "airborne" and self._sdk is not None and not self._halted:
                await self._land_once()
        finally:
            self._drop_sdk()
            self._closed = True
            self._connected = False

    def link_ok(self) -> bool:
        if not self._connected or self._sdk is None or not self._channel_ok:
            return False
        snapshot = self._snapshot()
        stamp = snapshot.get("at")
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
            if time.monotonic() - float(stamp) > self._link_timeout_s:
                return False
        return True

    def _endpoint(self) -> tuple[str, int]:
        host = self.config.get("host")
        port = self.config.get("port")
        if not isinstance(host, str) or not host.strip() or port is None:
            raise AdapterError(
                "unsupported",
                "PATROL_DRONE_HOST and PATROL_DRONE_PORT are required; no socket was opened",
            )
        try:
            port_num = int(port)
        except (TypeError, ValueError) as exc:
            raise AdapterError(
                "unsupported",
                "PATROL_DRONE_PORT is not a valid port; no socket was opened",
            ) from exc
        if isinstance(port, bool) or not 1 <= port_num <= 65535:
            raise AdapterError(
                "unsupported",
                "PATROL_DRONE_PORT is not a valid port; no socket was opened",
            )
        return host.strip(), port_num

    def _open_sdk(self, host: str, port: int) -> Any:
        if self._sdk_factory is not None:
            return self._sdk_factory(host, port)
        from patrol.drone.tello_sdk import TelloSDK

        return TelloSDK(host=host, port=port)

    def _require_open(self) -> None:
        if self._closed:
            raise AdapterError("device_error", "adapter is closed")

    def _require_connected(self) -> None:
        if not self._connected or self._sdk is None:
            raise AdapterError("not_connected", "drone is not connected")

    def _check_profile(self, request: InspectionRequest) -> None:
        from patrol.drone.profile import allow

        allow(request.profile_id, request.zone, request.launch_origin)

    async def _query(self, command: str, timeout: float | None = None) -> str:
        self._reject_translation(command)
        self.commands.append(command)
        if self._sdk is None:
            raise AdapterError("not_connected", "drone is not connected")
        limit = self._command_timeout_s if timeout is None else timeout
        try:
            reply = await asyncio.to_thread(self._sdk.query, command, limit)
        except TimeoutError as exc:
            self._channel_ok = False
            raise AdapterError("timeout", "drone command timed out; no retry") from exc
        except OSError as exc:
            self._channel_ok = False
            raise AdapterError("device_error", "drone link lost; no further motion") from exc
        self._channel_ok = True
        text = reply if isinstance(reply, str) else str(reply)
        return text.strip()

    def _send(self, command: str) -> None:
        self._reject_translation(command)
        self.commands.append(command)
        if self._sdk is None:
            return
        try:
            self._sdk.send(command)
        except OSError as exc:
            self._channel_ok = False
            raise AdapterError("device_error", "drone link lost; no further motion") from exc

    @staticmethod
    def _reject_translation(command: str) -> None:
        head = command.split(" ", 1)[0].lower()
        if head in _TRANSLATION:
            raise AdapterError("unsafe_state", "translation is outside the museum ceiling")
        if head == "rc" and command.strip() != "rc 0 0 0 0":
            raise AdapterError("unsafe_state", "nonzero rc is outside the museum ceiling")

    def _snapshot(self) -> dict[str, Any]:
        if self._sdk is None:
            return {}
        snapshot = self._sdk.snapshot() if hasattr(self._sdk, "snapshot") else {}
        return snapshot if isinstance(snapshot, dict) else {}

    def _read_height(self) -> None:
        height = self._snapshot().get("h")
        if isinstance(height, bool) or not isinstance(height, (int, float)):
            return
        self._flight = "airborne" if float(height) > 0 else "grounded"

    async def _wait(self, seconds: float, ctx: RunContext, deadline: float) -> bool:
        if seconds <= 0:
            return not self._halted and not ctx.cancel.is_set() and time.monotonic() < deadline and self.link_ok()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._halted or ctx.cancel.is_set() or time.monotonic() >= deadline or not self.link_ok():
                return False
            await asyncio.sleep(min(0.05, end - time.monotonic()))
        return not self._halted and self.link_ok()

    async def _land_once(self) -> None:
        if self._flight == "grounded" or self._sdk is None:
            return
        try:
            reply = await self._query("land")
        except AdapterError:
            self._flight = "unknown"
            return
        self._flight = "grounded" if "ok" in reply.lower() else "unknown"

    async def _stop_flying(self) -> None:
        if self._flight == "grounded":
            return
        self._halted = True
        if self._sdk is not None:
            self._send("emergency")
        self._flight = "unknown"

    def _store_frame(self, data: bytes, request: InspectionRequest, ctx: RunContext) -> Frame:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.output_dir / f"{ctx.mission_id}_drone_{request.zone}_{stamp}.jpg"
        path.write_bytes(data)
        captured = datetime.now(timezone.utc).isoformat()
        return Frame(
            path=str(path),
            source="drone",
            zone=request.zone,
            captured_at=captured,
            simulated=False,
        )

    def _drop_sdk(self) -> None:
        sdk = self._sdk
        self._sdk = None
        self._channel_ok = False
        if sdk is None:
            return
        closer = getattr(sdk, "close", None)
        if closer is not None:
            try:
                closer()
            except Exception:
                pass


def _read_udp_jpeg() -> bytes:
    """One frame from the Tello video port. The caller already sent streamon."""

    import io

    import av

    container = av.open(
        "udp://0.0.0.0:11111",
        timeout=(2, 2),
        options={"overrun_nonfatal": "1", "fifo_size": "50000", "reuse": "1"},
    )
    try:
        for frame in container.decode(video=0):
            image = frame.to_image()
            if image.size[0] < 16:
                continue
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG")
            return buffer.getvalue()
    finally:
        container.close()
    raise AdapterError("device_error", "camera frame was not retrieved; no flight command was sent")


def _battery(reply: str) -> int | None:
    try:
        value = int(float(reply.strip()))
    except (TypeError, ValueError):
        return None
    if 0 <= value <= 100:
        return value
    return None
