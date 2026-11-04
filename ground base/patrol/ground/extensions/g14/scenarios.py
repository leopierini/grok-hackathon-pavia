"""Scripted frame checks. The harness runs the real provider against these."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from patrol.ground.extensions.g14.checks import FrameCheck, check_frame
from patrol.ground.extensions.g14.implementation import device_calls
from patrol.ground.extensions.g14.store import fixture_store
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureResult,
    GroundError,
    SimulationCase,
)
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_frame"
SCHEMA = "ground-task-v2"
CAPTURED = "2026-11-04T13:00:10.000Z"
_FORBIDDEN = (
    "dog.run_route",
    "dog.capture_frame",
    "drone.inspect",
    "drone.takeoff",
    "reasoner.assess_incident",
    "reasoner.assess_ground_view",
    "reasoner.resolve_incident",
    "vision.request",
)


class CaseHost(Protocol):
    services: BaseServices
    phase: str
    cleanup_paths: tuple[str, ...]


def _accept_trace(camera: str, epoch: int, *, uncalibrated: bool) -> tuple[str, ...]:
    return (
        "resolved",
        "evidence.validate",
        f"camera:{camera}",
        f"epoch:{epoch}",
        f"captured_at:{CAPTURED}",
        "uncalibrated" if uncalibrated else "calibrated",
        "accepted",
    )


_DOWNWARD = _accept_trace("downward", 1, uncalibrated=False)
_FRONT = _accept_trace("front", 1, uncalibrated=False)
_NULL = _accept_trace("downward", 1, uncalibrated=True)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    spec: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
        ("accept_downward", "ok", "accepted", _DOWNWARD, ""),
        ("accept_front", "ok", "accepted", _FRONT, ""),
        (
            "hash_mismatch",
            "failed",
            "hash_mismatch",
            ("resolved", "rejected:hash_mismatch"),
            "rejected",
        ),
        (
            "switched_old_epoch",
            "failed",
            "epoch_mismatch",
            ("rejected:epoch_mismatch",),
            "epoch_mismatch",
        ),
        ("rear_camera", "failed", "rear_camera", ("rejected:rear_camera",), "rejected"),
        (
            "file_disappears",
            "failed",
            "disappeared",
            ("resolved", "rejected:disappeared"),
            "io_fault",
        ),
        ("null_calibration", "ok", "accepted", _NULL, ""),
        ("laptop_path", "failed", "not_artifact", ("rejected:not_artifact",), "rejected"),
        (
            "stale_epoch",
            "failed",
            "stale_epoch",
            ("resolved", "rejected:stale_epoch"),
            "epoch_mismatch",
        ),
        (
            "non_jpeg",
            "failed",
            "not_jpeg",
            ("resolved", "evidence.validate", "rejected:not_jpeg"),
            "rejected",
        ),
        (
            "synthetic_placeholder",
            "failed",
            "synthetic_placeholder",
            ("resolved", "rejected:synthetic_placeholder"),
            "rejected",
        ),
        ("mtime_ignored", "ok", "accepted", _DOWNWARD, ""),
        (
            "changed_during_validation",
            "failed",
            "changed_during_validation",
            ("resolved", "rejected:changed_during_validation"),
            "io_fault",
        ),
        (
            "dimension_mismatch",
            "failed",
            "dimension_mismatch",
            ("resolved", "evidence.validate", "rejected:dimension_mismatch"),
            "rejected",
        ),
        ("path_escape", "failed", "path_escape", ("rejected:path_escape",), "path_escape"),
    )
    built: list[SimulationCase] = []
    for case_id, status, detail, trace, code in spec:
        expected: dict[str, object] = {
            "status": status,
            "detail": detail,
            "trace": trace,
            "simulated": True,
            "authorized": False,
            "device_calls": 0,
            "live_call_count": 0,
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
        if code:
            expected["error_code"] = code
        built.append(
            SimulationCase(
                task_id="GROUND-14",
                case_id=case_id,
                seed=seed,
                setup=freeze_map({"seed": seed, "schema": SCHEMA_VERSION}),
                stimuli=(),
                barriers=(),
                faults=(),
                expected=freeze_map(expected),
                forbidden_calls=_FORBIDDEN,
                teardown=(
                    "release_barriers",
                    "collect_tasks",
                    "remove_owned_temp",
                    "assert_no_socket",
                ),
            )
        )
    return tuple(built)


async def run_case(host: CaseHost, case_id: str) -> FeatureResult:
    runners = {
        "accept_downward": _accept_downward,
        "accept_front": _accept_front,
        "hash_mismatch": _hash_mismatch,
        "switched_old_epoch": _switched,
        "rear_camera": _rear,
        "file_disappears": _disappears,
        "null_calibration": _null_calibration,
        "laptop_path": _laptop,
        "stale_epoch": _stale,
        "non_jpeg": _non_jpeg,
        "synthetic_placeholder": _placeholder,
        "mtime_ignored": _mtime,
        "changed_during_validation": _changed,
        "dimension_mismatch": _dimension,
        "path_escape": _escape,
    }
    runner = runners.get(case_id)
    if runner is None:
        return FeatureResult(
            "failed",
            freeze_map(
                {
                    "simulated": True,
                    "detail": "unknown case",
                    "device_calls": 0,
                    "live_call_count": 0,
                    "authorized": False,
                    "slot": SLOT,
                    "schema_version": SCHEMA,
                }
            ),
            (),
            GroundError("invalid_input", "unknown case", False),
        )
    check = await runner(host)
    return _foundation(host, check)


async def _accept_downward(host: CaseHost) -> FrameCheck:
    return await _check(host, _frame("downward"))


async def _accept_front(host: CaseHost) -> FrameCheck:
    return await _check(host, _frame("front"), source="dog")


async def _hash_mismatch(host: CaseHost) -> FrameCheck:
    frame = _frame("downward")
    frame["sha256"] = _flip_bit(str(frame["sha256"]))
    return await _check(host, frame)


async def _switched(host: CaseHost) -> FrameCheck:
    return await _check(host, _frame("front"), source="dog", snapshot=_previous_downward())


async def _rear(host: CaseHost) -> FrameCheck:
    frame = _frame("downward")
    frame["camera_id"] = "rear"
    return await _check(host, frame)


async def _null_calibration(host: CaseHost) -> FrameCheck:
    frame = _frame("downward")
    frame["camera_to_body_calibration_id"] = None
    return await _check(host, frame)


async def _laptop(host: CaseHost) -> FrameCheck:
    frame = _frame("downward")
    frame["image_ref"] = r"C:\Users\sender\Pictures\frame.jpg"
    return await _check(host, frame)


async def _escape(host: CaseHost) -> FrameCheck:
    frame = _frame("downward")
    frame["image_ref"] = "artifact://demo-20261104-001/../../outside.jpg"
    return await _check(host, frame)


async def _placeholder(host: CaseHost) -> FrameCheck:
    frame = _frame("downward")
    frame["simulated"] = False
    return await _check(host, frame)


async def _dimension(host: CaseHost) -> FrameCheck:
    frame = _frame("downward")
    frame["width_px"] = 640
    frame["height_px"] = 480
    return await _check(host, frame)


async def _mtime(host: CaseHost) -> FrameCheck:
    root, _dest = _stage_copy(host, "drone", "downward-001.jpg")
    os.utime(root / "clip" / "frame.jpg", (0, 0))
    frame = _frame("downward")
    frame["image_ref"] = "artifact://clip/frame.jpg"
    return await _check(host, frame, store_root=str(root))


async def _non_jpeg(host: CaseHost) -> FrameCheck:
    root = _temp_root(host)
    dest = root / "clip" / "frame.jpg"
    dest.parent.mkdir(parents=True)
    payload = b"this is text, not a jpeg\n"
    dest.write_bytes(payload)
    frame = _frame("downward")
    frame["image_ref"] = "artifact://clip/frame.jpg"
    frame["sha256"] = hashlib.sha256(payload).hexdigest()
    return await _check(host, frame, store_root=str(root))


async def _disappears(host: CaseHost) -> FrameCheck:
    root, dest = _stage_copy(host, "drone", "downward-001.jpg")
    frame = _frame("downward")
    frame["image_ref"] = "artifact://clip/frame.jpg"

    def mutate() -> None:
        dest.unlink()

    return await _paused(host, frame, mutate, store_root=str(root))


async def _stale(host: CaseHost) -> FrameCheck:
    snapshot: dict[str, object] = {
        "camera_id": "downward",
        "camera_epoch": 1,
        "width_px": 320,
        "height_px": 240,
        "camera_to_body_calibration_id": "synthetic-calibration-v1",
        "switched": False,
    }

    def mutate() -> None:
        snapshot["camera_epoch"] = 2

    return await _paused(host, _frame("downward"), mutate, snapshot=snapshot)


async def _changed(host: CaseHost) -> FrameCheck:
    root, dest = _stage_copy(host, "drone", "downward-001.jpg")
    replacement = (fixture_store() / "placeholder.jpg").read_bytes()
    frame = _frame("downward")
    frame["image_ref"] = "artifact://clip/frame.jpg"

    def mutate() -> None:
        dest.write_bytes(replacement)

    return await _paused(host, frame, mutate, store_root=str(root))


async def _check(host: CaseHost, frame: dict[str, object], **extra: object) -> FrameCheck:
    payload: dict[str, object] = {
        "frame": frame,
        "zone": "display",
        "mission_id": "demo-20261104-001",
        "message_id": "msg-frame-check",
        "epoch": 1,
    }
    payload.update(extra)
    return await check_frame(host.services, payload, ticket=None, on_pause=None)


async def _paused(
    host: CaseHost,
    frame: dict[str, object],
    mutate: Callable[[], None],
    **extra: object,
) -> FrameCheck:
    host.services.kernel.barriers.arm("hold")
    payload: dict[str, object] = {
        "frame": frame,
        "zone": "display",
        "mission_id": "demo-20261104-001",
        "message_id": "msg-frame-check",
        "epoch": 1,
        "pause": "hold",
    }
    payload.update(extra)

    async def sabotage() -> None:
        for _ in range(2000):
            if host.phase == "paused":
                break
            await asyncio.sleep(0)
        else:
            raise RuntimeError("validation did not pause")
        mutate()
        host.services.kernel.barriers.release("hold")

    task = asyncio.create_task(sabotage())
    try:
        return await check_frame(
            host.services,
            payload,
            ticket=None,
            on_pause=lambda: setattr(host, "phase", "paused"),
        )
    finally:
        host.services.kernel.barriers.release("hold")
        await task


def _foundation(host: CaseHost, check: FrameCheck) -> FeatureResult:
    data = freeze_map(
        {
            "simulated": True,
            "live_call_count": 0,
            "device_calls": device_calls(host.services),
            "authorized": False,
            "slot": SLOT,
            "schema_version": SCHEMA,
            "detail": check.detail,
            "trace": check.trace,
        }
    )
    events = () if check.event is None else (check.event,)
    if check.status == "ok":
        return FeatureResult("ok", data, events, None)
    return FeatureResult(
        "failed",
        data,
        events,
        GroundError(check.code, check.detail, check.recovery_required),
    )


def _frame(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g14" / "accepted" / f"{name}.json"
    loaded = _object(path.read_text(encoding="utf-8"))
    return dict(loaded)


def _previous_downward() -> dict[str, object]:
    return {
        "camera_id": "downward",
        "camera_epoch": 1,
        "width_px": 320,
        "height_px": 240,
        "camera_to_body_calibration_id": "synthetic-calibration-v1",
        "switched": True,
    }


def _flip_bit(digest: str) -> str:
    raw = bytearray(bytes.fromhex(digest))
    raw[-1] ^= 0x01
    return raw.hex()


def _temp_root(host: CaseHost) -> Path:
    root = Path(tempfile.mkdtemp(prefix="g14-"))
    host.cleanup_paths = (*host.cleanup_paths, str(root))
    return root


def _stage_copy(host: CaseHost, folder: str, filename: str) -> tuple[Path, Path]:
    root = _temp_root(host)
    source = fixture_store() / "demo-20261104-001" / folder / filename
    dest = root / "clip" / "frame.jpg"
    dest.parent.mkdir(parents=True)
    shutil.copyfile(source, dest)
    return root, dest


def _object(text: str) -> Mapping[str, object]:
    loaded = json.loads(text)
    if isinstance(loaded, dict):
        return {str(key): value for key, value in loaded.items()}
    raise RuntimeError("frame fixture must be an object")
