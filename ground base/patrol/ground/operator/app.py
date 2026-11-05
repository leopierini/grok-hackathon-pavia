"""Local FastAPI bridge. Mutations require the operator token."""

from __future__ import annotations

import asyncio
import hmac
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from patrol.ground.kernel.paths import repo_root
from patrol.ground.live.api import LiveController, mount_live
from patrol.ground.operator.artifacts import ArtifactError, resolve_jpeg
from patrol.ground.operator.coverage import coverage_payload
from patrol.ground.operator.host import Host

_ORIGINS = frozenset({"http://127.0.0.1:3000", "http://localhost:3000"})
_DOCS = {
    "operator-guide": "operator-guide.md",
    "ui-architecture": "ui-architecture.md",
    "ui-coverage": "ui-coverage.md",
    "verification": "verification.md",
}


def create_app(token: str, runs_root: Path) -> FastAPI:
    app = FastAPI(title="Ground Mission Control", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.host = Host(runs_root)
    app.state.token = token
    app.state.live = LiveController(runs_root)

    @app.middleware("http")
    async def authorize(request: Request, call_next: Any) -> Response:
        supplied = request.headers.get("x-ground-operator-token", "")
        if not hmac.compare_digest(supplied, token):
            return JSONResponse(_fail("unauthorized", "operator token was rejected"), status_code=401)
        origin = request.headers.get("origin")
        if origin and origin not in _ORIGINS:
            return JSONResponse(_fail("rejected", "origin was rejected"), status_code=403)
        return cast(Response, await call_next(request))

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"ok": "true", "service": "ground-mission-control"}

    @app.websocket("/ws/robot/v2")
    async def robot_v2(socket: WebSocket) -> None:
        supplied = socket.headers.get("x-ground-operator-token", "")
        if not hmac.compare_digest(supplied, token):
            await socket.close(code=1008)
            return
        await socket.accept()
        received = getattr(app.state, "robot_v2_messages", None)
        if not isinstance(received, list):
            received = []
            app.state.robot_v2_messages = received
        try:
            while True:
                raw = await socket.receive_text()
                if len(raw) > 65536:
                    await socket.send_json({"ok": False, "error": "message is too large"})
                    continue
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await socket.send_json({"ok": False, "error": "message must be JSON"})
                    continue
                if not isinstance(message, dict):
                    await socket.send_json({"ok": False, "error": "message must be an object"})
                    continue
                received.append(message)
                await socket.send_json(
                    {
                        "ok": True,
                        "accepted": True,
                        "route": "/ws/robot/v2",
                        "kind": message.get("kind"),
                    }
                )
        except WebSocketDisconnect:
            return

    mount_live(app, app.state.live, lambda: app.state.host.dog_link is not None)

    @app.get("/api/v1/session")
    async def session(request: Request) -> dict[str, Any]:
        return {"ok": True, "snapshot": request.app.state.host.snapshot}

    @app.get("/api/v1/events")
    async def events(request: Request, cursor: int | None = None) -> StreamingResponse:
        host: Host = request.app.state.host
        return StreamingResponse(_stream(host, cursor), media_type="text/event-stream")

    @app.post("/api/v1/actions/{name}")
    async def action(name: str, request: Request) -> JSONResponse:
        body = await _body(request)
        if isinstance(body, JSONResponse):
            return body
        key = request.headers.get("idempotency-key")
        live: LiveController = request.app.state.live
        if name == "halt":
            # The header Halt also halts the live mission, first and without waiting.
            asyncio.create_task(live.halt())
        if name == "start_patrol":
            # Home Start patrol runs the whole live demo by itself.
            started = await live.auto_start(request.app.state.host.dog_link is not None)
            status = 200 if started.get("ok") else 409
            return JSONResponse({**started, "status": status, "snapshot": request.app.state.host.snapshot},
                                status_code=status)
        if name == "stop_patrol":
            stopped = await live.stop()
            status = 200 if stopped.get("ok") else 409
            return JSONResponse({**stopped, "status": status, "snapshot": request.app.state.host.snapshot},
                                status_code=status)
        if name in {"dog_test", "dog_view"} and live.owns_dog:
            return JSONResponse(
                _fail("rejected", "The live mission holds the dog link. Disconnect it on the Live screen first."),
                status_code=409,
            )
        result = await request.app.state.host.act(name, body, key)
        return JSONResponse(result, status_code=int(result.get("status", 200)))

    @app.post("/api/v1/steps/command")
    async def steps(request: Request) -> JSONResponse:
        body = await _body(request)
        if isinstance(body, JSONResponse):
            return body
        result = await request.app.state.host.step_command(body)
        return JSONResponse(result, status_code=int(result.get("status", 200)))

    @app.get("/api/v1/config")
    async def get_config(request: Request) -> dict[str, Any]:
        host: Host = request.app.state.host
        return {"ok": True, "config": host.snapshot.get("config"), "unset": host.snapshot.get("unset"), "apply": host.snapshot.get("config_apply")}

    @app.post("/api/v1/config")
    async def post_config(request: Request) -> JSONResponse:
        body = await _body(request)
        if isinstance(body, JSONResponse):
            return body
        result = await request.app.state.host.update_config(body)
        return JSONResponse(result, status_code=int(result.get("status", 200)))

    @app.post("/api/v1/mode")
    async def mode(request: Request) -> JSONResponse:
        body = await _body(request)
        if isinstance(body, JSONResponse):
            return body
        selected = body.get("mode")
        result = await request.app.state.host.set_mode(selected if isinstance(selected, str) else "")
        return JSONResponse(result, status_code=int(result.get("status", 200)))

    @app.post("/api/v1/replay/{run_id}")
    async def replay(run_id: str, request: Request) -> JSONResponse:
        result = await request.app.state.host.open_replay(run_id)
        return JSONResponse(result, status_code=int(result.get("status", 200)))

    @app.get("/api/v1/journal")
    async def journal(
        request: Request,
        cursor: int = 0,
        limit: int = 50,
        source: str = "",
        category: str = "",
        severity: str = "",
        command_id: str = "",
        request_id: str = "",
        track_id: str = "",
    ) -> dict[str, Any]:
        bounded = min(max(limit, 1), 200)
        filters = {
            "source": source,
            "category": category,
            "severity": severity,
            "command_id": command_id,
            "request_id": request_id,
            "track_id": track_id,
        }
        return {"ok": True, **request.app.state.host.journal(cursor=cursor, limit=bounded, filters=filters)}

    @app.get("/api/v1/runs")
    async def runs(request: Request) -> dict[str, Any]:
        return {"ok": True, "runs": request.app.state.host.runs}

    @app.get("/api/v1/runs/{run_id}")
    async def run_detail(run_id: str, request: Request) -> JSONResponse:
        try:
            path = request.app.state.host._report_path(run_id)
            report = json.loads(path.read_text(encoding="utf-8"))
        except (ArtifactError, OSError, ValueError, json.JSONDecodeError):
            return JSONResponse(_fail("not_found", "run report was not found"), status_code=404)
        return JSONResponse({"ok": True, "report": _public_report(report)})

    @app.get("/api/v1/runs/{run_id}/export")
    async def export_run(run_id: str, request: Request) -> JSONResponse:
        try:
            path = request.app.state.host._report_path(run_id)
            report = json.loads(path.read_text(encoding="utf-8"))
        except (ArtifactError, OSError, ValueError, json.JSONDecodeError):
            return JSONResponse(_fail("not_found", "run report was not found"), status_code=404)
        return JSONResponse(_public_report(report) if isinstance(report, dict) else {})

    @app.get("/api/v1/evidence", response_model=None)
    async def evidence(request: Request, artifact_id: str) -> FileResponse | JSONResponse:
        host: Host = request.app.state.host
        roots = (repo_root() / "fixtures" / "ground" / "g14" / "store", host.runs_root)
        try:
            path = resolve_jpeg(artifact_id, roots)
        except ArtifactError as exc:
            return JSONResponse(_fail(exc.code, exc.detail), status_code=404 if exc.code == "not_found" else 422)
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/v1/dog/live.jpg", response_model=None)
    async def dog_live(request: Request) -> Response:
        host: Host = request.app.state.host
        try:
            jpeg = await host.dog_frame_jpeg()
        except Exception as exc:
            return JSONResponse(_fail("rejected", f"{type(exc).__name__}: {exc}"), status_code=409)
        if not jpeg:
            return JSONResponse(_fail("not_ready", "The dog camera has no frame yet."), status_code=404)
        return Response(jpeg, media_type="image/jpeg", headers={"cache-control": "no-store"})

    @app.get("/api/v1/dog/lidar")
    async def dog_lidar(request: Request) -> JSONResponse:
        host: Host = request.app.state.host
        try:
            payload = await host.dog_lidar_view()
        except Exception as exc:
            return JSONResponse(_fail("rejected", f"{type(exc).__name__}: {exc}"), status_code=409)
        if payload is None:
            return JSONResponse(_fail("not_ready", "LiDAR is not open."), status_code=404)
        return JSONResponse(payload, status_code=200 if payload.get("ok") else 409)

    @app.get("/api/v1/coverage")
    async def coverage() -> dict[str, Any]:
        return {"ok": True, **coverage_payload()}

    @app.get("/api/v1/scenarios")
    async def scenarios(request: Request) -> dict[str, Any]:
        return {"ok": True, "scenarios": request.app.state.host.snapshot.get("scenarios")}

    @app.get("/api/v1/docs/{name}")
    async def docs(name: str) -> JSONResponse:
        filename = _DOCS.get(name)
        if filename is None:
            return JSONResponse(_fail("not_found", "unknown document"), status_code=404)
        path = (repo_root() / "docs" / "ground" / filename).resolve()
        try:
            path.relative_to((repo_root() / "docs" / "ground").resolve())
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return JSONResponse(_fail("not_found", "document is not available yet"), status_code=404)
        return JSONResponse({"ok": True, "name": name, "text": text})

    return app


async def _body(request: Request) -> dict[str, Any] | JSONResponse:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > 65536:
        return JSONResponse(_fail("rejected", "request body is too large"), status_code=413)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_fail("invalid_input", "request body must be JSON"), status_code=422)
    if not isinstance(body, dict):
        return JSONResponse(_fail("invalid_input", "request body must be an object"), status_code=422)
    return body


async def _stream(host: Host, cursor: int | None) -> AsyncIterator[str]:
    snapshot = host.snapshot
    if cursor is None:
        yield _sse("snapshot", {"cursor": snapshot.get("cursor", 0), "snapshot": snapshot})
        cursor = int(snapshot.get("cursor") or 0)
    else:
        status, _rows = host.since(cursor)
        kind = "resync" if status == "gap" else "snapshot"
        yield _sse(kind, {"cursor": snapshot.get("cursor", 0), "snapshot": snapshot})
        cursor = int(snapshot.get("cursor") or 0)
    queue = host.subscribe()
    try:
        while True:
            try:
                await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            current = host.snapshot
            current_cursor = int(current.get("cursor") or 0)
            kind = "resync" if current_cursor > cursor + 1 else "event"
            yield _sse(kind, {"cursor": current_cursor, "snapshot": current})
            cursor = current_cursor
    finally:
        host.unsubscribe(queue)


def _sse(name: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, default=str, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"


def _public_report(report: object) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    hidden = {"trace", "messages", "provider_journal"}
    return {key: value for key, value in report.items() if key not in hidden and "secret" not in key.lower()}


def _fail(code: str, detail: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "detail": detail}}
