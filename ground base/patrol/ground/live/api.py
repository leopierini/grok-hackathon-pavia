"""Live mission routes inside Mission Control's operator API (``/api/v1/live/*``).

The Next.js console reaches these through its token proxy (``/api/ground/live/...``).
The mission is created on ``connect`` only, so a rehearsal never grabs the dog's
single WebRTC slot. Peers come from the environment:

    GROUND_LIVE_DRONE   drone flight server URL (default http://127.0.0.1:8766)
    GROUND_LIVE_DOG     ethernet | sim | none   (default ethernet)
    GROUND_LIVE_DOG_IP  default 192.168.123.161
    GROUND_LIVE_ARM_DOG 1 to allow stand and operator steps (halt always works)
    GROUND_LIVE_GROK    real | fake             (default real; key from ~/.config/patrol/xai.env)
    GROUND_LIVE_TARGET  who to look for, e.g. "a person wearing a red cap" (ignore everyone else)
    GROUND_LIVE_PATTERN sweep (forward/back/turn, default) | spin (turn only)
    GROUND_LIVE_STROKE_S forward/back stroke length in seconds (default 1.5, max 2)
    GROUND_LIVE_TAKEOFF 0 to leave takeoff to the pilot (default 1: Start patrol takes off)
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from patrol.ground.dog_limits import clamp_limits
from patrol.ground.dog_link import EthernetDogLink
from patrol.ground.live.drone import DroneHttp
from patrol.ground.live.grok import RealGrok, ScriptedGrok
from patrol.ground.live.mission import LiveMission, Settings


def _flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


class LiveController:
    def __init__(self, runs_root: Path, environ: Mapping[str, str] | None = None) -> None:
        self.runs_root = runs_root
        self.env = dict(os.environ if environ is None else environ)
        self.mission: LiveMission | None = None
        self.error: str | None = None

    def config(self) -> dict[str, Any]:
        e = self.env
        return {
            "drone": e.get("GROUND_LIVE_DRONE", "http://127.0.0.1:8766"),
            "dog": e.get("GROUND_LIVE_DOG", "ethernet"),
            "dog_ip": e.get("GROUND_LIVE_DOG_IP", "192.168.123.161"),
            "arm_dog": _flag(e, "GROUND_LIVE_ARM_DOG"),
            "grok": e.get("GROUND_LIVE_GROK", "real"),
            "target": e.get("GROUND_LIVE_TARGET", "").strip() or "the person standing or walking in the open floor area",
            "pattern": e.get("GROUND_LIVE_PATTERN", "sweep"),
            "stroke_s": float(e.get("GROUND_LIVE_STROKE_S", "1.5") or 1.5),
            "takeoff": e.get("GROUND_LIVE_TAKEOFF", "1").strip().lower() in {"1", "true", "yes", "on"},
        }

    @property
    def owns_dog(self) -> bool:
        return self.mission is not None and self.mission.dog is not None

    async def connect(self, dog_busy: bool) -> dict[str, Any]:
        if self.mission is not None:
            return {"ok": True, "detail": "Live mission is already connected."}
        cfg = self.config()
        if cfg["dog"] not in {"ethernet", "sim", "none"}:
            return {"ok": False, "detail": "GROUND_LIVE_DOG must be ethernet, sim or none."}
        if cfg["dog"] != "none" and dog_busy:
            return {"ok": False, "detail": "Close the Mission page dog test or dog view first. The dog allows one connection."}
        try:
            grok = RealGrok(cfg["target"]) if cfg["grok"] == "real" else ScriptedGrok()
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            return {"ok": False, "detail": f"Grok refused: {exc}"}
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir = self.runs_root / "live" / f"live-{stamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        dog = None
        if cfg["dog"] != "none":
            # Dog-folder recommendation ceiling (no extra Ground scale-down); the dog adapter keeps its own caps.
            limits = clamp_limits({"forward_m_s": 0.3, "side_m_s": 0.2, "yaw_rad_s": 0.6, "step_s": 1.0})
            dog = EthernetDogLink(run_dir / "dog", armed=cfg["arm_dog"], fake=cfg["dog"] == "sim",
                                  ip=cfg["dog_ip"], limits=limits)
        self.mission = LiveMission(drone=DroneHttp(cfg["drone"]), dog=dog, grok=grok, run_dir=run_dir,
                                   settings=Settings(allow_takeoff=cfg["takeoff"],
                                                     pattern="spin" if cfg["pattern"] == "spin" else "sweep",
                                                     stroke_s=max(0.3, min(2.0, cfg["stroke_s"]))), dog_mode=cfg["dog"])
        await self.mission.connect()
        self.error = None
        return {"ok": True, "detail": "Live mission connected. Nothing moves in standby."}

    async def auto_start(self, dog_busy: bool) -> dict[str, Any]:
        """Home Start patrol: connect (or replace a finished/halted run) and run the whole demo."""
        mission = self.mission
        if mission is not None and (mission.halt_latched or mission.phase in {"done", "stopped"}):
            self.mission = None
            await mission.close()
        if self.mission is None:
            connected = await self.connect(dog_busy)
            if connected.get("ok") is not True:
                return connected
        assert self.mission is not None
        return await self.mission.start(takeoff=True)

    async def stop(self) -> dict[str, Any]:
        if self.mission is None:
            return {"ok": False, "detail": "Live mission is not connected."}
        return await self.mission.stop()

    async def disconnect(self) -> dict[str, Any]:
        mission = self.mission
        if mission is None:
            return {"ok": True, "detail": "Not connected."}
        if mission.phase in {"takeoff", "patrol", "detected", "approach", "engaged", "finishing"}:
            return {"ok": False, "detail": "Stop patrol before disconnecting."}
        self.mission = None
        await mission.close()
        return {"ok": True, "detail": "Live mission disconnected; the dog link is free."}

    async def halt(self) -> None:
        if self.mission is not None:
            await self.mission.halt("Operator halt from Mission Control.")

    def state(self) -> dict[str, Any]:
        base = {"config": self.config(), "connected": self.mission is not None, "error": self.error}
        if self.mission is None:
            return {"ok": True, **base, "phase": "disconnected"}
        return {"ok": True, **base, **self.mission.snapshot()}


def mount_live(app: FastAPI, controller: LiveController, dog_busy: Any) -> None:
    """``dog_busy()`` tells whether Mission Control's own dog link is open."""

    def need() -> LiveMission | JSONResponse:
        if controller.mission is None:
            return JSONResponse({"ok": False, "detail": "Connect the live mission first."}, status_code=409)
        return controller.mission

    async def body(request: Request) -> dict[str, Any]:
        try:
            parsed = await request.json()
        except Exception:  # noqa: BLE001
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @app.get("/api/v1/live/state")
    async def live_state() -> dict[str, Any]:
        return controller.state()

    @app.post("/api/v1/live/connect")
    async def live_connect() -> dict[str, Any]:
        return await controller.connect(bool(dog_busy()))

    @app.post("/api/v1/live/disconnect")
    async def live_disconnect() -> dict[str, Any]:
        return await controller.disconnect()

    @app.post("/api/v1/live/halt")
    async def live_halt() -> dict[str, Any]:
        await controller.halt()
        return {"ok": True, "detail": "Halt sent." if controller.mission else "Not connected."}

    @app.post("/api/v1/live/{action}")
    async def live_action(action: str, request: Request) -> Any:
        mission = need()
        if isinstance(mission, JSONResponse):
            return mission
        data = await body(request)
        if action == "start":
            return await controller.auto_start(bool(dog_busy()))
        if action == "stop":
            return await mission.stop()
        if action == "dog_stand":
            return await mission.dog_stand()
        if action == "dog_step":
            return await mission.dog_step(str(data.get("direction")))
        if action == "dog_say":
            text = data.get("text")
            if not isinstance(text, str) or not text.strip():
                return {"ok": False, "detail": "text is empty"}
            return await mission.dog_say(text.strip()[:300])
        if action == "track":
            if isinstance(data.get("enabled"), bool):
                mission.settings.track = data["enabled"]
                mission.emit("settings", "ground", f"Drone tracking {'on' if data['enabled'] else 'off'}.")
            return {"ok": True}
        return JSONResponse({"ok": False, "detail": f"unknown live action {action!r}"}, status_code=404)

    @app.get("/api/v1/live/frame/{camera}", response_model=None)
    async def live_frame(camera: str) -> Response:
        mission = controller.mission
        jpeg: bytes | None = None
        if mission is not None and camera == "drone.jpg":
            try:
                jpeg = await mission.drone.frame()
            except Exception:  # noqa: BLE001
                jpeg = None
        elif mission is not None and camera == "dog.jpg":
            jpeg = mission.dog_frame
        if jpeg is None:
            return Response(status_code=204)
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
