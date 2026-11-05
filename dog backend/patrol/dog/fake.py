"""Scripted, hardware-free DogPort implementation for tests and all-fake runs."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, get_args

from patrol.contract import AdapterError, DogStatus, Frame, RouteResult, RunContext, Zone

SCENARIOS = frozenset({
    "blocked_resolved", "dismiss", "ground_clear", "ground_confirmed",
    "drone_unavailable", "route_blocked", "invalid_model", "stale_frame",
    "takeoff_timeout", "landing_unknown", "slow_model",
})
DEFAULT_SCENARIO = "blocked_resolved"
ZONES = frozenset(get_args(Zone))
FIXTURE_FRAME = Path(__file__).resolve().parents[2] / "fixtures" / "dog" / "fake_frame.jpg"
STALE_AGE_S = 60.0
_STEP_S = 0.02  # route loop granularity; bounds halt/cancel latency


def _invalid(detail: str) -> AdapterError:
    return AdapterError("invalid_input", detail)


def _positive(config: Mapping[str, Any], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise _invalid(f"{key} must be a positive number, got {value!r}")
    return float(value)


def _now_iso(offset_s: float = 0.0) -> str:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=offset_s)
    return stamp.isoformat(timespec="milliseconds")


class FakeDog:
    """Simulated Go2. Never imports vendor code; every frame is simulated=True."""

    def __init__(self, *, config: Mapping[str, Any], output_dir: Path) -> None:
        if not isinstance(config, Mapping):
            raise _invalid("dog config must be a mapping")
        scenario = config.get("scenario", DEFAULT_SCENARIO)
        if scenario not in SCENARIOS:
            raise _invalid(f"unknown scenario {scenario!r}")
        routes = config.get("fake_routes", ["room_2"])
        if not isinstance(routes, (list, tuple)) or any(r not in ZONES for r in routes):
            raise _invalid(f"fake_routes must be a list of zones, got {routes!r}")

        self.scenario: str = scenario
        self.trace: list[str] = []
        self.spoken: list[str] = []   # what say()/play_* were asked to play, in order
        self._routes = frozenset(routes)
        self._route_s = _positive(config, "fake_route_s", 0.2)
        self._output_dir = Path(output_dir).resolve()
        self._connected = False
        self._closed = False
        self._halted = False
        self._route_running = False
        self._standing: bool | None = False
        self._stationary: bool | None = True
        self._avoidance: bool | None = False

    # -- helpers ---------------------------------------------------------

    def _status(self) -> DogStatus:
        return DogStatus(connected=self._connected, standing=self._standing,
                         stationary=self._stationary, avoidance_enabled=self._avoidance)

    def _require_connected(self) -> None:
        if self._closed:
            raise AdapterError("not_connected", "adapter closed; create a new one")
        if not self._connected:
            raise AdapterError("not_connected", "call connect() first")

    @staticmethod
    def _require_zone(zone: Any) -> None:
        if zone not in ZONES:
            raise _invalid(f"unknown zone {zone!r}")

    @staticmethod
    def _ctx_stop_reason(ctx: RunContext) -> str | None:
        if ctx.cancel.is_set():
            return "cancelled"
        if time.monotonic() >= ctx.deadline_monotonic:
            return "timeout"
        return None

    def _check_ctx(self, ctx: RunContext) -> None:
        reason = self._ctx_stop_reason(ctx)
        if reason == "cancelled":
            raise AdapterError("cancelled", "run context cancelled")
        if reason == "timeout":
            raise AdapterError("timeout", "run context deadline passed")

    # -- DogPort ---------------------------------------------------------

    async def connect(self) -> DogStatus:
        self.trace.append("connect")
        if self._closed:
            raise AdapterError("not_connected", "adapter closed; create a new one")
        self._connected = True  # connecting never stands or moves the dog
        return self._status()

    async def prepare(self, ctx: RunContext) -> DogStatus:
        self.trace.append("prepare")
        self._require_connected()
        if self._halted:
            raise AdapterError("unsafe_state", "halted; recreate the adapter after recovery")
        self._check_ctx(ctx)
        self._standing, self._stationary, self._avoidance = True, True, True
        return self._status()

    async def get_status(self) -> DogStatus:
        self.trace.append("get_status")
        self._require_connected()
        return self._status()

    async def run_route(self, zone: Zone, ctx: RunContext) -> RouteResult:
        self.trace.append("run_route")
        self._require_connected()
        self._require_zone(zone)
        if zone not in self._routes:
            raise AdapterError("unsupported", f"no calibrated route for {zone!r}")
        if self._halted:
            raise AdapterError("unsafe_state", "halted; recreate the adapter after recovery")
        if self._route_running:
            raise AdapterError("unsafe_state", "a route is already running")
        if not (self._standing and self._avoidance):
            raise AdapterError("unsafe_state", "call prepare() before run_route()")

        route_id = f"fake_{zone}"
        # route_blocked: the walk stops partway, as if an obstacle stopped it.
        walk_s = self._route_s * (0.5 if self.scenario == "route_blocked" else 1.0)
        self._route_running, self._stationary = True, False
        try:
            end = time.monotonic() + walk_s
            while True:
                if self._halted:
                    return RouteResult(False, True, route_id, "halted during route")
                reason = self._ctx_stop_reason(ctx)
                if reason:
                    return RouteResult(False, True, route_id, f"route {reason}")
                remaining = end - time.monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(_STEP_S, remaining))
            if self.scenario == "route_blocked":
                return RouteResult(False, True, route_id, "simulated obstacle: route blocked")
            return RouteResult(True, True, route_id, "simulated route completed")
        finally:
            self._route_running, self._stationary = False, True

    async def capture_frame(self, zone: Zone, ctx: RunContext) -> Frame:
        self.trace.append("capture_frame")
        self._require_connected()
        self._require_zone(zone)
        self._check_ctx(ctx)
        if not FIXTURE_FRAME.is_file():
            raise AdapterError("device_error", f"missing fixture {FIXTURE_FRAME}")

        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", ctx.mission_id)[:64] or "mission"
        name = f"dog_{safe_id}_{zone}_{uuid.uuid4().hex[:12]}.jpg"
        final = self._output_dir / name
        tmp = final.with_name(f".{name}.tmp")
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(FIXTURE_FRAME, tmp)
            os.replace(tmp, final)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise AdapterError("device_error", f"could not write frame: {exc}") from exc

        stale = self.scenario == "stale_frame"
        return Frame(path=str(final), source="dog", zone=zone,
                     captured_at=_now_iso(STALE_AGE_S if stale else 0.0), simulated=True)

    async def halt(self) -> None:
        # Never waits behind a route: it only flips a flag the route loop polls.
        self.trace.append("halt")
        self._halted = True

    async def play_warning(self, warning_id: str, text: str) -> None:
        from patrol.dog.commands import play_warning

        await play_warning(self, warning_id, text)

    async def execute(self, command: Mapping[str, Any]) -> str:
        from patrol.dog.commands import execute

        return await execute(self, command)

    async def close(self) -> None:
        self.trace.append("close")
        self._halted = True
        self._connected = False
        self._closed = True

    # -- audio extras (same names as RealDog; no audio libraries, nothing is played) ----

    async def get_volume(self) -> int | None:
        self._require_connected()
        self.trace.append("get_volume")
        return getattr(self, "_volume", 5)

    async def set_volume(self, level: float) -> int:
        self._require_connected()
        self.trace.append("set_volume")
        try:
            lvl = float(level)
        except (TypeError, ValueError) as e:
            raise _invalid(f"bad volume {level!r}") from e
        if lvl != lvl or lvl in (float("inf"), float("-inf")):
            raise _invalid(f"bad volume {level!r}")
        self._volume = int(max(0, min(10, round(lvl))))
        return self._volume

    def play_pcm(self, pcm: bytes, rate: int = 48000, channels: int = 1, *,
                 interrupt: bool = False, max_lag_s: float | None = None) -> float:
        """Records the call; returns the seconds of audio it would have queued."""
        self._require_connected()
        if not isinstance(rate, int) or not 8000 <= rate <= 192000 or channels not in (1, 2):
            raise _invalid(f"bad PCM format rate={rate!r} channels={channels!r}")
        self.trace.append("play_pcm")
        secs = len(pcm) / (2 * channels * rate)
        self.spoken.append(f"<pcm {secs:.2f} s>")
        return round(secs, 2)

    def play_chime(self, *, interrupt: bool = True) -> float:
        self._require_connected()
        self.trace.append("play_chime")
        self.spoken.append("<chime>")
        return 0.6

    async def play_audio_file(self, path: str | os.PathLike, *, interrupt: bool = True) -> float:
        self._require_connected()
        self.trace.append("play_audio_file")
        if not Path(path).is_file():
            raise _invalid(f"cannot play {path}: not found")
        self.spoken.append(f"<file {Path(path).name}>")
        return 1.0

    async def say(self, text: str, voice: str = "Alice", *, interrupt: bool = True) -> float:
        """Records the text in `spoken` (tests can assert what the dog said)."""
        self._require_connected()
        self.trace.append("say")
        text = (text or "").strip() if isinstance(text, str) else ""
        if not text or len(text) > 400:
            raise _invalid("say: text must be 1..400 characters")
        self.spoken.append(text)
        return round(0.35 * max(1, len(text.split())), 2)

    def stop_audio(self) -> None:
        self.trace.append("stop_audio")

    async def record_audio(self, seconds: float = 5.0, name: str | None = None,
                           rate: int = 48000) -> dict:
        """Writes a silent mono WAV (simulated) and returns the same fields as RealDog."""
        import wave
        self._require_connected()
        self.trace.append("record_audio")
        try:
            secs = float(seconds)
        except (TypeError, ValueError) as e:
            raise _invalid(f"bad seconds {seconds!r}") from e
        if not 0.2 <= secs <= 60:
            raise _invalid("seconds must be 0.2..60")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_-]", "", name or "mic")[:40] or "mic"
        path = self._output_dir / f"{safe}_{uuid.uuid4().hex[:8]}_simulated.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(int(secs * rate) * 2))
        return {"path": str(path), "seconds": round(secs, 2), "rate": rate, "peak_dbfs": -90.0,
                "levels_dbfs_100ms": [], "simulated": True}
