"""Decide whether one frame handle may be passed onward.

The bytes stay in the artifact store. The result carries the handle, the
capture time from the frame, and a proposed evidence event. It does not call
a model or a device.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

from patrol.contract import Frame
from patrol.ground.extensions.g14.store import placeholder_digests, resolve_artifact
from patrol.ground.kernel.contracts import (
    BaseServices,
    CaptureInterval,
    GroundEvent,
    SessionSnapshot,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.validation import freeze_map

_FRAME_KEYS = frozenset(
    {
        "frame_id",
        "image_ref",
        "sha256",
        "captured_at",
        "camera_id",
        "camera_epoch",
        "width_px",
        "height_px",
        "camera_frame_id",
        "camera_to_body_calibration_id",
        "simulated",
    }
)
_CAMERAS = frozenset({"front", "downward"})
_REAR = frozenset({"rear", "back"})
_ZONES = frozenset({"entrance", "room_2", "display"})
_SOURCES = frozenset({"dog", "drone"})
_HISTORY = frozenset(
    {
        "camera_id",
        "camera_epoch",
        "width_px",
        "height_px",
        "camera_to_body_calibration_id",
        "switched",
    }
)
_SHA = 64
_READ_LIMIT = 8_000_000
ZoneName = Literal["entrance", "room_2", "display"]
SourceName = Literal["dog", "drone"]


class FrameCheck:
    def __init__(
        self,
        status: str,
        code: str,
        detail: str,
        recovery_required: bool,
        data: Mapping[str, object],
        event: GroundEvent | None,
        trace: tuple[str, ...],
    ) -> None:
        self.status = status
        self.code = code
        self.detail = detail
        self.recovery_required = recovery_required
        self.data = data
        self.event = event
        self.trace = trace


async def check_frame(
    services: BaseServices,
    payload: Mapping[str, object],
    *,
    ticket: Ticket | None,
    on_pause: Callable[[], None] | None = None,
) -> FrameCheck:
    if services.kernel.authority.cancelled:
        return _reject("cancelled", "cancelled", [], ticket, payload, {}, recovery=True)
    frame = payload.get("frame")
    if isinstance(frame, (str, bytes)) or not isinstance(frame, Mapping):
        return _reject("invalid_input", "invalid_frame", [], ticket, payload, {})
    structural = _structural(frame)
    if structural is not None:
        return _reject(structural[0], structural[1], [], ticket, payload, frame)
    snapshot, snapshot_error = _snapshot(payload.get("snapshot"))
    if snapshot_error is not None:
        return _reject("invalid_input", snapshot_error, [], ticket, payload, frame)
    history = _history_problem(snapshot)
    if history is not None:
        return _reject(history[0], history[1], [], ticket, payload, frame)
    epoch = _epoch_problem(frame, snapshot)
    if epoch is not None:
        return _reject("epoch_mismatch", epoch, [], ticket, payload, frame)
    source, zone, location = _context(payload, str(frame["camera_id"]))
    if location is not None:
        return _reject(location[0], location[1], [], ticket, payload, frame)
    assert source is not None and zone is not None
    store, store_error = _store_root(payload)
    if store_error is not None:
        return _reject(store_error[0], store_error[1], [], ticket, payload, frame)
    assert store is not None
    resolved, ref_error = resolve_artifact(str(frame["image_ref"]), store)
    if ref_error or resolved is None:
        if ref_error == "path_escape":
            code = "path_escape"
        elif ref_error == "artifact_missing":
            code = "io_fault"
        else:
            code = "rejected"
        return _reject(
            code,
            ref_error or "not_artifact",
            [],
            ticket,
            payload,
            frame,
            recovery=code == "io_fault",
        )
    trace = ["resolved"]
    seen_epoch = frame.get("camera_epoch")
    seen_snapshot = _token(payload.get("snapshot"))
    try:
        first = services.kernel.io.read_bytes(resolved, limit=_READ_LIMIT)
    except GroundFault as exc:
        detail = "artifact_missing" if "missing" in exc.error.detail else exc.error.code
        return _reject(exc.error.code, detail, trace, ticket, payload, frame, recovery=True)
    pause = payload.get("pause")
    if pause is not None:
        if not isinstance(pause, str) or not pause:
            return _reject("invalid_input", "invalid_frame", trace, ticket, payload, frame)
        if on_pause is not None:
            on_pause()
        await services.kernel.barriers.wait(pause)
    if services.kernel.authority.cancelled:
        return _reject("cancelled", "cancelled", trace, ticket, payload, frame, recovery=True)
    if frame.get("camera_epoch") != seen_epoch or _token(payload.get("snapshot")) != seen_snapshot:
        return _reject("epoch_mismatch", "stale_epoch", trace, ticket, payload, frame)
    try:
        second = services.kernel.io.read_bytes(resolved, limit=_READ_LIMIT)
    except GroundFault as exc:
        detail = "disappeared" if "missing" in exc.error.detail else exc.error.code
        return _reject("io_fault", detail, trace, ticket, payload, frame, recovery=True)
    if second != first:
        return _reject(
            "io_fault",
            "changed_during_validation",
            trace,
            ticket,
            payload,
            frame,
            recovery=True,
        )
    data = second
    digest = hashlib.sha256(data).hexdigest()
    if digest != frame["sha256"]:
        return _reject("rejected", "hash_mismatch", trace, ticket, payload, frame)
    if frame["simulated"] is False and digest in placeholder_digests():
        return _reject("rejected", "synthetic_placeholder", trace, ticket, payload, frame)
    interval = CaptureInterval(
        started_monotonic=services.kernel.clock.monotonic(),
        ended_monotonic=None,
        started_utc=str(frame["captured_at"]),
        ended_utc=None,
    )
    evidence = await services.evidence.validate(
        Frame(
            path=str(resolved),
            source=source,
            zone=zone,
            captured_at=str(frame["captured_at"]),
            simulated=bool(frame["simulated"]),
        ),
        expected_source=source,
        zone=zone,
        mode="fake" if frame["simulated"] is True else "real",
        output_root=store,
        interval=interval,
    )
    trace.append("evidence.validate")
    if not evidence.accepted:
        detail = "not_jpeg" if evidence.reason == "jpeg" else f"evidence:{evidence.reason}"
        code = "rejected"
        return _reject(code, detail, trace, ticket, payload, frame)
    if not _dimensions(data, frame):
        return _reject("rejected", "dimension_mismatch", trace, ticket, payload, frame)
    return _accept(frame, trace, ticket, payload)


def _structural(frame: Mapping[str, object]) -> tuple[str, str] | None:
    extra = [key for key in frame if key not in _FRAME_KEYS]
    if extra:
        return "invalid_input", "invalid_frame"
    missing = [key for key in _FRAME_KEYS if key not in frame]
    if missing:
        return "invalid_input", "invalid_frame"
    camera = frame["camera_id"]
    if not isinstance(camera, str) or not camera.strip() or camera != camera.strip():
        return "rejected", "camera_id"
    if camera in _REAR:
        return "rejected", "rear_camera"
    if camera not in _CAMERAS:
        return "rejected", "camera_id"
    if _bad_size(frame["width_px"]) or _bad_size(frame["height_px"]):
        return "invalid_input", "invalid_frame"
    if _bad_epoch(frame["camera_epoch"]):
        return "invalid_input", "invalid_frame"
    sha = frame["sha256"]
    if not isinstance(sha, str) or len(sha) != _SHA or sha.lower() != sha or any(
        char not in "0123456789abcdef" for char in sha
    ):
        return "invalid_input", "invalid_frame"
    if not isinstance(frame["simulated"], bool):
        return "invalid_input", "invalid_frame"
    if not isinstance(frame["frame_id"], str) or not frame["frame_id"].strip():
        return "invalid_input", "invalid_frame"
    if not isinstance(frame["camera_frame_id"], str) or not frame["camera_frame_id"].strip():
        return "invalid_input", "invalid_frame"
    if not isinstance(frame["image_ref"], str):
        return "invalid_input", "invalid_frame"
    captured = _capture(frame["captured_at"])
    if captured is None:
        return "invalid_input", "captured_at"
    calibration = frame["camera_to_body_calibration_id"]
    if calibration is not None and not _calibration_id(calibration):
        return "invalid_input", "invalid_frame"
    return None


def _snapshot(value: object) -> tuple[Mapping[str, object] | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, SessionSnapshot):
        return value.evidence, None
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        return None, "invalid_frame"
    if "evidence" in value and "camera_epoch" not in value and "camera_id" not in value:
        inner = value.get("evidence")
        if isinstance(inner, (str, bytes)) or not isinstance(inner, Mapping):
            return None, "invalid_frame"
        return inner, None
    return value, None


def _history_problem(view: Mapping[str, object] | None) -> tuple[str, str] | None:
    if view is None or not any(key in view for key in _HISTORY):
        return None
    if "camera_epoch" not in view or _bad_epoch(view.get("camera_epoch")):
        return "invalid_input", "invalid_frame"
    switched = view.get("switched")
    if "switched" in view and not isinstance(switched, bool):
        return "invalid_input", "invalid_frame"
    for key in ("width_px", "height_px"):
        if key in view and _bad_size(view.get(key)):
            return "invalid_input", "invalid_frame"
    camera = view.get("camera_id")
    if "camera_id" in view and (not isinstance(camera, str) or camera not in _CAMERAS):
        return "invalid_input", "invalid_frame"
    return None


def _epoch_problem(frame: Mapping[str, object], view: Mapping[str, object] | None) -> str | None:
    if view is None or "camera_epoch" not in view:
        return None
    previous = view["camera_epoch"]
    current = frame["camera_epoch"]
    assert isinstance(previous, int) and not isinstance(previous, bool)
    assert isinstance(current, int) and not isinstance(current, bool)
    changed = view.get("switched") is True
    if "camera_id" in view and view["camera_id"] != frame["camera_id"]:
        changed = True
    if "width_px" in view and view["width_px"] != frame["width_px"]:
        changed = True
    if "height_px" in view and view["height_px"] != frame["height_px"]:
        changed = True
    if (
        "camera_to_body_calibration_id" in view
        and view["camera_to_body_calibration_id"] != frame["camera_to_body_calibration_id"]
    ):
        changed = True
    if changed and current <= previous:
        return "epoch_mismatch"
    if current < previous:
        return "epoch_mismatch"
    return None


def _context(
    payload: Mapping[str, object],
    camera_id: str,
) -> tuple[SourceName | None, ZoneName | None, tuple[str, str] | None]:
    supplied = payload.get("source", "drone" if camera_id == "downward" else "dog")
    if supplied not in _SOURCES:
        return None, None, ("invalid_input", "invalid_frame")
    zone = payload.get("zone", "display")
    if zone not in _ZONES:
        return None, None, ("invalid_input", "invalid_frame")
    source: SourceName = "dog" if supplied == "dog" else "drone"
    if zone == "entrance":
        selected: ZoneName = "entrance"
    elif zone == "room_2":
        selected = "room_2"
    else:
        selected = "display"
    return source, selected, None


def _store_root(payload: Mapping[str, object]) -> tuple[Path | None, tuple[str, str] | None]:
    supplied = payload.get("store_root")
    if supplied is None:
        from patrol.ground.extensions.g14.store import fixture_store

        return fixture_store(), None
    if not isinstance(supplied, str) or not supplied.strip():
        return None, ("rejected", "not_artifact")
    root = Path(supplied)
    if not root.is_absolute():
        return None, ("rejected", "not_artifact")
    if not root.is_dir():
        return None, ("io_fault", "artifact_missing")
    return root, None


def _accept(
    frame: Mapping[str, object],
    trace: list[str],
    ticket: Ticket | None,
    payload: Mapping[str, object],
) -> FrameCheck:
    calibration = frame["camera_to_body_calibration_id"]
    uncalibrated = calibration is None
    camera_id = str(frame["camera_id"])
    epoch = frame["camera_epoch"]
    captured = str(frame["captured_at"])
    handle = freeze_map(
        {
            "frame_id": frame["frame_id"],
            "camera_id": camera_id,
            "camera_epoch": epoch,
            "captured_at": captured,
            "image_ref": frame["image_ref"],
            "sha256": frame["sha256"],
            "width_px": frame["width_px"],
            "height_px": frame["height_px"],
            "camera_frame_id": frame["camera_frame_id"],
            "camera_to_body_calibration_id": calibration,
            "uncalibrated": uncalibrated,
            "simulated": frame["simulated"],
        }
    )
    trace.append(f"camera:{camera_id}")
    trace.append(f"epoch:{epoch}")
    trace.append(f"captured_at:{captured}")
    trace.append("uncalibrated" if uncalibrated else "calibrated")
    trace.append("accepted")
    data = freeze_map(
        {
            "accepted": True,
            "handle": handle,
            "camera_id": camera_id,
            "camera_epoch": epoch,
            "captured_at": captured,
            "image_ref": frame["image_ref"],
            "frame_id": frame["frame_id"],
            "sha256": frame["sha256"],
            "width_px": frame["width_px"],
            "height_px": frame["height_px"],
            "camera_frame_id": frame["camera_frame_id"],
            "camera_to_body_calibration_id": calibration,
            "uncalibrated": uncalibrated,
            "simulated": frame["simulated"],
        }
    )
    return FrameCheck(
        "ok",
        "",
        "accepted",
        False,
        data,
        _event(ticket, "accepted", frame, payload, uncalibrated),
        tuple(trace),
    )


def _dimensions(data: bytes, frame: Mapping[str, object]) -> bool:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            format_name = image.format
            size = image.size
    except (UnidentifiedImageError, OSError, ValueError):
        return False
    width = frame["width_px"]
    height = frame["height_px"]
    return bool(format_name == "JPEG" and size == (width, height))


def _reject(
    code: str,
    detail: str,
    trace: list[str],
    ticket: Ticket | None,
    payload: Mapping[str, object],
    frame: Mapping[str, object],
    *,
    recovery: bool = False,
) -> FrameCheck:
    trace.append(f"rejected:{detail}")
    data = freeze_map({"accepted": False, "reason": detail, **_known(frame)})
    event = _event(ticket, detail, frame, payload, None)
    return FrameCheck("failed", code, detail, recovery, data, event, tuple(trace))


def _event(
    ticket: Ticket | None,
    reason: str,
    frame: Mapping[str, object],
    payload: Mapping[str, object],
    uncalibrated: bool | None,
) -> GroundEvent:
    kind = "frame_validated" if reason == "accepted" else "frame_rejected"
    body: dict[str, object] = {
        "message_id": _text_or_none(payload.get("message_id")),
        "mission_id": _text_or_none(payload.get("mission_id")),
        "epoch": _whole(payload.get("epoch")),
        "command_id": _text_or_none(payload.get("command_id")),
        "request_id": _text_or_none(payload.get("request_id")),
        "frame_id": frame.get("frame_id") if isinstance(frame.get("frame_id"), str) else None,
        "track_id": _text_or_none(payload.get("track_id")),
        "beacon_epoch": _whole(payload.get("beacon_epoch")),
        "map_epoch": _whole(payload.get("map_epoch")),
        "camera_epoch": _whole(frame.get("camera_epoch")),
        "camera_id": frame.get("camera_id") if isinstance(frame.get("camera_id"), str) else None,
        "image_ref": _artifact_or_none(frame.get("image_ref")),
        "sha256": _text_or_none(frame.get("sha256")),
        "captured_at": _text_or_none(frame.get("captured_at")),
        "reason": reason,
        "uncalibrated": uncalibrated,
    }
    return GroundEvent(kind, ticket, freeze_map(body))


def _known(frame: Mapping[str, object]) -> dict[str, object]:
    kept: dict[str, object] = {}
    frame_id = frame.get("frame_id")
    if isinstance(frame_id, str):
        kept["frame_id"] = frame_id
    camera = frame.get("camera_id")
    if isinstance(camera, str):
        kept["camera_id"] = camera
    image_ref = frame.get("image_ref")
    if isinstance(image_ref, str) and image_ref.startswith("artifact://"):
        kept["image_ref"] = image_ref
    return kept


def _token(snapshot: object) -> tuple[object, ...] | None:
    view, error = _snapshot(snapshot)
    if error is not None or view is None:
        return None
    return (
        view.get("camera_id"),
        view.get("camera_epoch"),
        view.get("width_px"),
        view.get("height_px"),
        view.get("camera_to_body_calibration_id"),
        view.get("switched"),
    )


def _capture(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return value


def _calibration_id(value: object) -> bool:
    return isinstance(value, str) and value.strip() != "" and value == value.strip()


def _bad_size(value: object) -> bool:
    return isinstance(value, bool) or not isinstance(value, int) or value <= 0


def _bad_epoch(value: object) -> bool:
    return isinstance(value, bool) or not isinstance(value, int) or value < 0


def _text_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _whole(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _artifact_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.startswith("artifact://"):
        return value
    return None
