"""Read-only checks before a museum run.

Preflight may open a session. It does not stand the dog, take off, or speak.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from patrol.ground.museum.endpoint import (
    DRONE_BATTERY_MIN,
    ConfigError,
    redact,
    require_endpoint,
    secret_values,
)
from patrol.ground.museum.peers import DogPeer, DronePeer, open_dog, open_drone
from patrol.ground.museum.policy import MuseumPolicy
from patrol.ground.signal import SignalError, require_api_key

_JPEG = b"\xff\xd8\xff"
Row = dict[str, str]


def run_preflight(
    output: Path,
    *,
    dog: str = "fake",
    drone: str = "fake",
    grok: str = "fake",
    environ: Mapping[str, str] | None = None,
    file_config: Mapping[str, object] | None = None,
    dog_conn_factory: Any = None,
    drone_sdk_factory: Any = None,
    frames: Mapping[str, bytes] | None = None,
) -> tuple[int, str]:
    """Return ``(exit_code, table)``. Writes ``preflight.json`` under ``output``."""

    env = dict(environ) if environ is not None else {}
    secrets = secret_values(env, file_config)
    rows, payload = asyncio.run(
        _collect(
            output,
            dog=dog,
            drone=drone,
            grok=grok,
            environ=env,
            file_config=file_config,
            dog_conn_factory=dog_conn_factory,
            drone_sdk_factory=drone_sdk_factory,
            frames=frames or {},
        )
    )
    text = redact(format_table(rows), secrets)
    payload["table"] = text
    blob = redact(json.dumps(payload, indent=2, sort_keys=True) + "\n", secrets)
    output.mkdir(parents=True, exist_ok=True)
    (output / "preflight.json").write_text(blob, encoding="utf-8")
    failed = any(row["result"] == "FAIL" for row in rows)
    return (2 if failed else 0), text


def format_table(rows: list[Row]) -> str:
    headers = ("check", "result", "detail")
    widths = [
        max(len(headers[index]), *(len(row[headers[index]]) for row in rows))
        for index in range(3)
    ]

    def line(values: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    body = [line(headers), line(tuple("-" * width for width in widths))]
    for row in rows:
        body.append(line((row["check"], row["result"], row["detail"])))
    return "\n".join(body)


async def _collect(
    output: Path,
    *,
    dog: str,
    drone: str,
    grok: str,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
    dog_conn_factory: Any,
    drone_sdk_factory: Any,
    frames: Mapping[str, bytes],
) -> tuple[list[Row], dict[str, object]]:
    rows: list[Row] = []
    dog_peer: DogPeer | None = None
    drone_peer: DronePeer | None = None
    try:
        rows.append(_env_row("dog env", "dog", dog, environ, file_config))
        rows.append(_env_row("drone env", "drone", drone, environ, file_config))
        if rows[0]["result"] == "PASS":
            dog_peer, opened = await _open_dog(
                dog, output / "dog", environ, file_config, dog_conn_factory
            )
            rows.append(opened)
        else:
            rows.append(_row("dog reachable", False, "not attempted"))
        if rows[1]["result"] == "PASS":
            drone_peer, opened = await _open_drone(
                drone, output / "drone", environ, file_config, drone_sdk_factory
            )
            rows.append(opened)
        else:
            rows.append(_row("drone reachable", False, "not attempted"))
        rows.append(await _dog_telemetry(dog_peer, dog))
        rows.append(await _drone_telemetry(drone_peer, drone))
        rows.append(await _camera("dog camera", dog_peer, "dog", frames.get("dog"), output))
        rows.append(await _camera("drone camera", drone_peer, "drone", frames.get("drone"), output))
        rows.append(_grok_row(grok, environ))
        rows.append(_halt_row(dog_peer, drone_peer))
    finally:
        if dog_peer is not None:
            close = getattr(dog_peer.dog, "close", None)
            if close is not None:
                await close()
        if drone_peer is not None:
            await drone_peer.close()
    ok = all(row["result"] == "PASS" for row in rows)
    return rows, {"ok": ok, "motion_sent": False, "rows": rows}


def _row(check: str, passed: bool, detail: str) -> Row:
    return {"check": check, "result": "PASS" if passed else "FAIL", "detail": detail}


def _env_row(
    check: str,
    peer: str,
    mode: str,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
) -> Row:
    if mode == "fake":
        return _row(check, True, f"not required for --{peer} fake")
    if mode != "real":
        return _row(check, False, f"{peer} mode {mode!r} is not fake or real")
    try:
        require_endpoint(peer, environ, file_config)
    except ConfigError as exc:
        return _row(check, False, str(exc))
    host_env = f"PATROL_{peer.upper()}_HOST"
    port_env = f"PATROL_{peer.upper()}_PORT"
    return _row(check, True, f"{host_env} present, {port_env} present")


async def _open_dog(
    mode: str,
    output: Path,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
    conn_factory: Any,
) -> tuple[DogPeer | None, Row]:
    try:
        peer = open_dog(mode, output, environ, file_config, conn_factory=conn_factory)
        await peer.connect()
    except Exception as exc:
        return None, _row("dog reachable", False, _safe_detail(exc))
    detail = "session open; dog was not stood up" if mode == "real" else "session open"
    return peer, _row("dog reachable", True, detail)


async def _open_drone(
    mode: str,
    output: Path,
    environ: Mapping[str, str],
    file_config: Mapping[str, object] | None,
    sdk_factory: Any,
) -> tuple[DronePeer | None, Row]:
    try:
        peer = open_drone(
            mode,
            output,
            environ,
            file_config,
            motion_authorized=False,
            sdk_factory=sdk_factory,
        )
        await peer.drone.connect()
    except Exception as exc:
        return None, _row("drone reachable", False, _safe_detail(exc))
    return peer, _row("drone reachable", True, "session open; no takeoff")


async def _dog_telemetry(peer: DogPeer | None, mode: str) -> Row:
    if peer is None:
        return _row("dog telemetry", False, "no session")
    try:
        status = await peer.dog.get_status()
    except Exception as exc:
        return _row("dog telemetry", False, _safe_detail(exc))
    connected = bool(getattr(status, "connected", False))
    if mode != "real":
        return _row(
            "dog telemetry",
            connected,
            "fake dog has no battery reading; link connected" if connected else "link down",
        )
    battery = _dog_battery(peer.dog)
    if not connected or battery is None:
        return _row("dog telemetry", False, "battery or link unreadable")
    if battery < DRONE_BATTERY_MIN:
        return _row("dog telemetry", False, f"battery {battery} is below {DRONE_BATTERY_MIN}")
    return _row("dog telemetry", True, f"battery {battery}; link up")


async def _drone_telemetry(peer: DronePeer | None, mode: str) -> Row:
    if peer is None:
        return _row("drone telemetry", False, "no session")
    try:
        status = await peer.drone.get_status()
    except Exception as exc:
        return _row("drone telemetry", False, _safe_detail(exc))
    connected = bool(getattr(status, "connected", False))
    battery = getattr(status, "battery_percent", None)
    if not connected or not isinstance(battery, int):
        return _row("drone telemetry", False, "battery or link unreadable")
    if mode == "real" and battery < DRONE_BATTERY_MIN:
        return _row("drone telemetry", False, f"battery {battery} is below {DRONE_BATTERY_MIN}")
    return _row("drone telemetry", True, f"battery {battery}; link up")


async def _camera(
    check: str,
    peer: DogPeer | DronePeer | None,
    kind: str,
    injected: bytes | None,
    output: Path,
) -> Row:
    if peer is None:
        return _row(check, False, "no session")
    try:
        data = injected if injected is not None else await _frame_bytes(peer, kind)
    except Exception as exc:
        return _row(check, False, _safe_detail(exc))
    if not isinstance(data, (bytes, bytearray)) or not bytes(data).startswith(_JPEG):
        return _row(check, False, "camera frame was not a JPEG")
    digest = hashlib.sha256(bytes(data)).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{kind}.jpg").write_bytes(bytes(data))
    return _row(check, True, f"sha256 {digest}")


async def _frame_bytes(peer: DogPeer | DronePeer, kind: str) -> bytes:
    if kind == "drone" and not peer.real:
        path = _team_drone_jpeg()
        return path.read_bytes()
    if kind == "drone":
        capture = getattr(peer.drone, "capture_still", None)
        if capture is None:
            raise ConfigError("drone camera frame was not retrieved")
        data = await capture()
        if not isinstance(data, (bytes, bytearray)):
            raise ConfigError("drone camera frame was not retrieved")
        return bytes(data)
    from patrol.ground.museum.peers import _dog_context

    frame = await peer.dog.capture_frame("room_2", _dog_context())
    return Path(frame.path).read_bytes()


def _grok_row(grok: str, environ: Mapping[str, str]) -> Row:
    if grok == "fake":
        return _row("grok key", True, "not required for --grok fake")
    if grok != "real":
        return _row("grok key", False, "grok mode must be fake or real")
    try:
        require_api_key(environ)
    except SignalError:
        return _row("grok key", False, "XAI_API_KEY is unset")
    return _row("grok key", True, "XAI_API_KEY present")


def _halt_row(dog_peer: DogPeer | None, drone_peer: DronePeer | None) -> Row:
    policy = MuseumPolicy()
    policy.arm()
    policy.bind_track("preflight")
    commands = policy.halt_command("2026-11-04T13:00:10.000Z", "Preflight halt check.")
    if dog_peer is None or drone_peer is None or not commands:
        return _row("halt path", False, "a peer was not opened, so the halt path is not armed")
    dog_halt = getattr(dog_peer.dog, "halt", None)
    drone_halt = getattr(drone_peer, "halt", None)
    if not callable(dog_halt) or not callable(drone_halt):
        return _row("halt path", False, "halt callable is missing")
    return _row("halt path", True, "halt command validates; halt was not sent")


def _dog_battery(dog: Any) -> int | None:
    low = getattr(dog, "_low", None)
    if not isinstance(low, dict):
        return None
    bms = low.get("bms_state", low.get("bms"))
    if not isinstance(bms, dict):
        return None
    soc = bms.get("soc")
    if isinstance(soc, bool) or not isinstance(soc, (int, float)):
        return None
    value = int(soc)
    if 0 <= value <= 100:
        return value
    return None


def _safe_detail(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text.splitlines()[0][:240]


def _team_drone_jpeg() -> Path:
    from patrol.ground.kernel.paths import repo_root

    return repo_root().parent / "patrol" / "drone" / "assets" / "simulated.jpg"
