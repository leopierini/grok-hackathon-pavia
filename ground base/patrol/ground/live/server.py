"""Live ground console: one local page, a JSON API and an event stream.

Binds 127.0.0.1 only. A request whose Origin is not this console is refused,
so another web page in the same browser cannot press Start or Halt.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from patrol.ground.live.mission import LiveMission

PAGE = Path(__file__).with_name("console.html")


def create_app(mission: LiveMission, port: int) -> FastAPI:
    app = FastAPI(title="Ground live console", docs_url=None, redoc_url=None, openapi_url=None)
    allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    @app.middleware("http")
    async def same_origin(request: Request, call_next: Any) -> Response:
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and origin not in allowed:
            return JSONResponse({"ok": False, "detail": "origin refused"}, status_code=403)
        return await call_next(request)  # type: ignore[no-any-return]

    @app.on_event("startup")
    async def startup() -> None:
        await mission.connect()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await mission.close()

    @app.get("/")
    async def page() -> FileResponse:
        return FileResponse(PAGE, headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return mission.snapshot()

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        return StreamingResponse(_stream(mission), media_type="text/event-stream")

    @app.post("/api/start")
    async def start(request: Request) -> dict[str, Any]:
        body = await _json(request)
        return await mission.start(takeoff=body.get("takeoff") is True)

    @app.post("/api/stop")
    async def stop() -> dict[str, Any]:
        return await mission.stop()

    @app.post("/api/halt")
    async def halt() -> dict[str, Any]:
        return await mission.halt()

    @app.post("/api/dog/step")
    async def dog_step(request: Request) -> dict[str, Any]:
        body = await _json(request)
        return await mission.dog_step(str(body.get("direction")))

    @app.post("/api/dog/stand")
    async def dog_stand() -> dict[str, Any]:
        return await mission.dog_stand()

    @app.post("/api/dog/say")
    async def dog_say(request: Request) -> dict[str, Any]:
        body = await _json(request)
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return {"ok": False, "detail": "text is empty"}
        return await mission.dog_say(text.strip()[:300])

    @app.post("/api/settings")
    async def settings(request: Request) -> dict[str, Any]:
        body = await _json(request)
        if isinstance(body.get("track"), bool):
            mission.settings.track = body["track"]
            mission.emit("settings", "ground", f"Drone tracking {'on' if body['track'] else 'off'}.")
        return {"ok": True, "settings": mission.settings.__dict__}

    @app.get("/api/frame/{camera}.jpg", response_model=None)
    async def frame(camera: str) -> Response:
        jpeg: bytes | None = None
        if camera == "drone":
            try:
                jpeg = await mission.drone.frame()
            except Exception:  # noqa: BLE001
                jpeg = None
        elif camera == "dog":
            jpeg = mission.dog_frame
        if jpeg is None:
            return Response(status_code=204)
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/runframe/{name}", response_model=None)
    async def runframe(name: str) -> Response:
        if "/" in name or ".." in name or not name.endswith(".jpg"):
            return Response(status_code=404)
        path = mission.run_dir / "frames" / name
        if not path.is_file():
            return Response(status_code=404)
        return FileResponse(path)

    return app


async def _json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return {}
    return body if isinstance(body, dict) else {}


async def _stream(mission: LiveMission) -> AsyncIterator[str]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
    mission.subscribers.add(queue)
    try:
        yield "retry: 1000\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), 15)
                yield f"data: {json.dumps(event, default=str)}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    finally:
        mission.subscribers.discard(queue)
