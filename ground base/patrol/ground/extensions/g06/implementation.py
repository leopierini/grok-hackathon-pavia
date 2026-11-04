"""JPEG evidence boundary.

A live dog or drone frame is accepted only when the file is a real JPEG inside
the adapter output directory and its UTC capture time falls inside the
operation interval. Landing may finish later: this check does not apply a
five-second limit at return time. The adapter still has to prove it did not
keep an old stream buffer; a timestamp inside the interval cannot prove that.

Phone images may keep ``captured_at=None``. This provider does not copy files
and does not replace an unknown or supplied capture time with the file mtime
or the current clock.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, overload

from patrol.contract import Frame
from patrol.ground.extensions.g06 import reasons as reason
from patrol.ground.extensions.g06.io import EvidenceIOError, FileSnapshot, RealIO
from patrol.ground.extensions.g06.model import (
    GROUND_ERROR_CODES,
    CaptureInterval,
    EvidenceLimits,
    EvidencePort,
    EvidenceResult,
    GroundError,
    GroundEvent,
    KernelContext,
    ServicePorts,
)
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult
from patrol.ground.kernel.contracts import GroundError as KernelGroundError
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

_ZONES = frozenset({"entrance", "room_2", "display"})
_SOURCES = frozenset({"phone", "dog", "drone"})
_MODES = frozenset({"fake", "real"})
_LIVE = frozenset({"dog", "drone"})


class EvidenceValidator:
    def __init__(
        self, kernel: KernelContext, peers: ServicePorts, limits: EvidenceLimits, io: Any
    ) -> None:
        self._clock = kernel.clock
        self._io = io
        self._peers = peers
        self._limits = limits

    async def validate(
        self,
        frame: Frame,
        *,
        expected_source: str,
        zone: str,
        mode: str,
        output_root: Path,
        interval: CaptureInterval | None,
    ) -> EvidenceResult:
        structural = self._structural(
            frame,
            expected_source=expected_source,
            zone=zone,
            mode=mode,
            output_root=output_root,
            interval=interval,
        )
        if isinstance(structural, EvidenceResult):
            return structural
        parsed, root, parsed_interval = structural

        try:
            inspected = await self._inspect(frame, root=root, live=frame.source in _LIVE)
        except EvidenceIOError as exc:
            return self._reject(exc.reason, exc.detail)
        if isinstance(inspected, EvidenceResult):
            return inspected
        snapshot, data, width, height = inspected

        try:
            confirm = await self._io.snapshot(Path(frame.path))
            confirm_bytes = await self._io.read(Path(frame.path), max_bytes=self._limits.max_bytes)
        except FileNotFoundError:
            return self._reject(
                reason.DISAPPEARED,
                "file disappeared during validation",
                identity=_identity(frame, snapshot, data),
            )
        except EvidenceIOError as exc:
            return self._reject(exc.reason, exc.detail)
        if (
            confirm.size != snapshot.size
            or confirm.resolved != snapshot.resolved
            or confirm.is_symlink != snapshot.is_symlink
            or confirm_bytes != data
            or len(confirm_bytes) > self._limits.max_bytes
        ):
            return self._reject(
                reason.CHANGED_DURING_VALIDATION,
                "file changed during validation",
                identity=_identity(frame, snapshot, data, width=width, height=height),
            )
        return self._decide_time(
            frame,
            mode=mode,
            parsed=parsed,
            interval=parsed_interval,
            snapshot=snapshot,
            data=data,
            width=width,
            height=height,
        )

    def _structural(
        self,
        frame: object,
        *,
        expected_source: object,
        zone: object,
        mode: object,
        output_root: object,
        interval: object,
    ) -> EvidenceResult | tuple[datetime | None, Path, tuple[datetime, datetime] | None]:
        if type(frame) is not Frame:
            return self._reject(reason.INVALID_TYPE, "evidence must be the frozen Frame type")
        if expected_source not in _SOURCES:
            return self._reject(reason.INVALID_SOURCE, "expected source is not a frozen source")
        if frame.source not in _SOURCES or frame.source != expected_source:
            return self._reject(
                reason.SOURCE_MISMATCH, "frame source does not match the expected source"
            )
        if zone not in _ZONES:
            return self._reject(reason.INVALID_ZONE, "expected zone is not a frozen zone")
        if frame.zone not in _ZONES or frame.zone != zone:
            return self._reject(reason.ZONE_MISMATCH, "frame zone does not match the trusted zone")
        if mode not in _MODES:
            return self._reject(reason.INVALID_MODE, "mode must be fake or real")
        if type(frame.simulated) is not bool:
            return self._reject(
                reason.INVALID_SIMULATION_FLAG,
                "simulation flag must be a boolean; strings are not coerced",
            )
        if mode == "real" and frame.simulated is True:
            return self._reject(
                reason.SIMULATION_MISMATCH,
                "real adapter returned simulated evidence",
            )
        if mode == "fake" and frame.simulated is False:
            return self._reject(
                reason.SIMULATION_MISMATCH,
                "fake adapter returned unsimulated evidence",
            )
        path_error = _path_error(frame.path)
        if path_error is not None:
            code, detail = path_error
            return self._reject(code, detail)
        root = _coerce_root(output_root)
        if root is None:
            return self._reject(reason.INVALID_OUTPUT_ROOT, "output root must be an absolute path")
        parsed_time, time_error = _parse_capture(frame.captured_at, source=frame.source)
        if time_error is not None:
            code, detail = time_error
            return self._reject(code, detail)
        parsed_interval, interval_error = _parse_interval(interval, source=frame.source)
        if interval_error is not None:
            code, detail = interval_error
            return self._reject(code, detail)
        return parsed_time, root, parsed_interval

    async def _inspect(
        self,
        frame: Frame,
        *,
        root: Path,
        live: bool,
    ) -> EvidenceResult | tuple[FileSnapshot, bytes, int, int]:
        path = Path(frame.path)
        if live:
            try:
                root_real = Path(os.path.realpath(root))
            except OSError as exc:
                return self._reject(
                    reason.INVALID_OUTPUT_ROOT, f"output root cannot be resolved: {exc}"
                )
            if not root_real.is_dir():
                return self._reject(
                    reason.INVALID_OUTPUT_ROOT, "live evidence output root is not a directory"
                )
        else:
            root_real = None
        try:
            snapshot = await self._io.snapshot(path)
        except FileNotFoundError:
            return self._reject(reason.NOT_FOUND, "file does not exist")
        except EvidenceIOError as exc:
            return self._reject(exc.reason, exc.detail)
        if snapshot.is_symlink:
            if root_real is not None and _inside(root_real, snapshot.resolved):
                return self._reject(
                    reason.NOT_REGULAR_FILE,
                    "symlink inside the output directory is not a regular file",
                )
            return self._reject(
                reason.SYMLINK_ESCAPE, "symlink does not resolve to the stated regular file"
            )
        if not snapshot.is_regular:
            return self._reject(reason.NOT_REGULAR_FILE, "path is not a regular file")
        if root_real is not None and not _inside(root_real, snapshot.resolved):
            return self._reject(
                reason.CONTAINMENT_ESCAPE,
                "resolved file is outside the adapter output directory",
            )
        if snapshot.size == 0:
            return self._reject(
                reason.EMPTY_FILE, "file is empty", identity=_identity(frame, snapshot, b"")
            )
        if snapshot.size > self._limits.max_bytes:
            return self._reject(
                reason.OVERSIZED,
                "file exceeds the JPEG size bound",
                identity=_identity(frame, snapshot, None),
            )
        try:
            data = await self._io.read(path, max_bytes=self._limits.max_bytes)
        except FileNotFoundError:
            return self._reject(reason.DISAPPEARED, "file disappeared while reading")
        except EvidenceIOError as exc:
            return self._reject(exc.reason, exc.detail)
        if len(data) != snapshot.size or len(data) > self._limits.max_bytes:
            return self._reject(reason.CHANGED_DURING_VALIDATION, "file size changed while reading")
        try:
            width, height = await self._io.decode_jpeg(data, max_pixels=self._limits.max_pixels)
        except EvidenceIOError as exc:
            return self._reject(exc.reason, exc.detail, identity=_identity(frame, snapshot, data))
        return snapshot, data, width, height

    def _decide_time(
        self,
        frame: Frame,
        *,
        mode: str,
        parsed: datetime | None,
        interval: tuple[datetime, datetime] | None,
        snapshot: FileSnapshot,
        data: bytes,
        width: int,
        height: int,
    ) -> EvidenceResult:
        now, clock_problem = _read_clock(self._clock)
        if clock_problem is not None:
            return self._reject(
                reason.CLOCK_ERROR,
                clock_problem,
                identity=_identity(frame, snapshot, data, width=width, height=height),
            )
        assert now is not None
        applied = interval if frame.source in _LIVE else None
        ignored_phone_interval = frame.source == "phone" and interval is not None
        age: float | None = None
        if parsed is not None:
            if parsed > now:
                return self._reject(
                    reason.FUTURE_TIMESTAMP,
                    "capture time is later than the kernel clock; the timestamp was not rewritten",
                    identity=_identity(frame, snapshot, data, width=width, height=height),
                    provenance=_provenance(
                        frame,
                        mode,
                        age_s=None,
                        interval=applied,
                        phone_interval_ignored=ignored_phone_interval,
                    ),
                )
            age = (now - parsed).total_seconds()
            if applied is not None:
                started, ended = applied
                if parsed < started:
                    return self._reject(
                        reason.PRE_REQUEST,
                        "capture time is before the operation started; "
                        "the timestamp was not rewritten",
                        identity=_identity(frame, snapshot, data, width=width, height=height),
                        provenance=_provenance(frame, mode, age_s=None, interval=applied),
                    )
                if parsed > ended:
                    return self._reject(
                        reason.OUTSIDE_INTERVAL,
                        "capture time is outside the recorded operation interval",
                        identity=_identity(frame, snapshot, data, width=width, height=height),
                        provenance=_provenance(frame, mode, age_s=None, interval=applied),
                    )
        identity = _identity(frame, snapshot, data, width=width, height=height)
        provenance = _provenance(
            frame,
            mode,
            age_s=age,
            interval=applied,
            phone_interval_ignored=ignored_phone_interval,
        )
        payload = {
            "reason": reason.ACCEPTED,
            "path": frame.path,
            "sha256": identity["sha256"],
            "source": frame.source,
            "zone": frame.zone,
            "simulated": frame.simulated,
            "captured_at": frame.captured_at,
            "age_s": age,
            "stream_selection_freshness": "not_claimed",
        }
        return EvidenceResult(
            status="accepted",
            frame=frame,
            identity=identity,
            provenance=provenance,
            reason=reason.ACCEPTED,
            detail="file and metadata accepted",
            error=None,
            events=(
                GroundEvent(
                    kind="frame_validated",
                    ticket=None,
                    payload=MappingProxyType(payload),
                ),
            ),
        )

    def _reject(
        self,
        code: str,
        detail: str,
        *,
        identity: Mapping[str, object] | None = None,
        provenance: Mapping[str, object] | None = None,
    ) -> EvidenceResult:
        if code not in GROUND_ERROR_CODES:
            code = reason.DECODER_ERROR
            detail = "validator produced an undeclared rejection"
        payload: dict[str, object] = {"reason": code, "detail": detail}
        if identity is not None and "sha256" in identity:
            payload["sha256"] = identity["sha256"]
        return EvidenceResult(
            status="rejected",
            frame=None,
            identity=identity,
            provenance=provenance,
            reason=code,
            detail=detail,
            error=GroundError(code, detail, False),
            events=(
                GroundEvent(kind="frame_rejected", ticket=None, payload=MappingProxyType(payload)),
            ),
        )


class EvidenceFeature:
    """Simulation entry. One case name runs the real validator and reports pass or fail."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        from patrol.ground.extensions.g06.scenarios import run_named

        seed = request.payload.get("seed", 0)
        if isinstance(seed, bool) or not isinstance(seed, int):
            seed = 0
        report = await run_named(request.name, seed=seed)
        passed = report.get("passed") is True
        detail = request.name
        if not passed:
            failures = report.get("failures")
            if isinstance(failures, list) and failures:
                detail = str(failures[0])
        data = freeze_map(
            {
                "simulated": True,
                "live_call_count": 0,
                "device_calls": 0,
                "authorized": False,
                "slot": "base.evidence",
                "schema_version": SCHEMA_VERSION,
                "detail": request.name,
            }
        )
        if passed:
            return FeatureResult("ok", data, (), None)
        return FeatureResult(
            "failed",
            data,
            (),
            KernelGroundError("validation_failed", detail, False),
        )


@overload
def create(kernel: BaseServices, peers: None = None) -> EvidenceFeature: ...


@overload
def create(kernel: KernelContext, peers: ServicePorts) -> EvidencePort: ...


def create(
    kernel: KernelContext | BaseServices,
    peers: ServicePorts | None = None,
) -> EvidencePort | EvidenceFeature:
    """Build a validator. Construction does not read files, open sockets, or call peers."""

    if isinstance(kernel, BaseServices):
        if peers is not None:
            raise fault("invalid_input", "harness construction takes only services")
        return EvidenceFeature(kernel)
    if peers is None:
        raise fault("invalid_input", "evidence peers are required")
    if not hasattr(kernel, "clock") or not hasattr(kernel, "io"):
        raise TypeError("kernel must provide clock and io")
    limits = getattr(kernel, "limits", None)
    if not isinstance(limits, EvidenceLimits):
        limits = EvidenceLimits()
    if type(limits.max_bytes) is not int or limits.max_bytes <= 0:
        raise TypeError("max_bytes must be a positive int")
    if type(limits.max_pixels) is not int or limits.max_pixels <= 0:
        raise TypeError("max_pixels must be a positive int")
    io = kernel.io if kernel.io is not None else RealIO()
    return EvidenceValidator(kernel, peers, limits, io)


def _path_error(value: object) -> tuple[str, str] | None:
    if type(value) is not str:
        return reason.INVALID_PATH, "frame path must be a string"
    if value == "" or "\x00" in value or value != value.strip():
        return reason.INVALID_PATH, "frame path is empty, padded, or contains a null"
    path = Path(value)
    if not path.is_absolute():
        return reason.RELATIVE_PATH, "frame path must be absolute"
    return None


def _coerce_root(value: object) -> Path | None:
    if type(value) is not str and not isinstance(value, Path):
        return None
    root = Path(value)
    if not root.is_absolute():
        return None
    return root


def _parse_capture(value: object, *, source: str) -> tuple[datetime | None, tuple[str, str] | None]:
    if value is None:
        if source in _LIVE:
            return None, (reason.NULL_TIMESTAMP, "live dog and drone frames require a capture time")
        return None, None
    if type(value) is not str:
        return None, (reason.MALFORMED_TIMESTAMP, "capture time must be a string or null")
    parsed, error = _parse_utc(value)
    if error == "naive":
        return None, (reason.NAIVE_TIMESTAMP, "capture time must include a timezone")
    if error is not None or parsed is None:
        return None, (reason.MALFORMED_TIMESTAMP, "capture time is not a UTC ISO-8601 timestamp")
    return parsed, None


def _parse_interval(
    value: object, *, source: str
) -> tuple[tuple[datetime, datetime] | None, tuple[str, str] | None]:
    if value is None:
        if source in _LIVE:
            return None, (reason.MISSING_INTERVAL, "live capture requires the operation interval")
        return None, None
    if not isinstance(value, CaptureInterval):
        return None, (reason.INVALID_INTERVAL, "interval must be a CaptureInterval")
    if (
        value.started_monotonic is not None
        and value.ended_monotonic is not None
        and value.ended_monotonic < value.started_monotonic
    ):
        return None, (reason.INVALID_INTERVAL, "monotonic interval ends before it starts")
    started, start_error = _parse_utc(value.started_at)
    ended, end_error = _parse_utc(value.ended_at)
    if start_error is not None or end_error is not None or started is None or ended is None:
        return None, (
            reason.INVALID_INTERVAL,
            "interval bounds must be timezone-aware UTC timestamps",
        )
    if ended < started:
        return None, (reason.INVALID_INTERVAL, "interval ends before it starts")
    return (started, ended), None


def _parse_utc(value: str) -> tuple[datetime | None, str | None]:
    if value == "" or value != value.strip():
        return None, "malformed"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None, "malformed"
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        return None, "naive"
    return parsed.astimezone(UTC), None


def _read_clock(clock: object) -> tuple[datetime | None, str | None]:
    reader = getattr(clock, "utc_now", None)
    if not callable(reader):
        return None, "kernel clock has no utc_now"
    try:
        current = reader()
    except Exception as exc:  # noqa: BLE001 — a faulty clock must reject, not crash validation
        return None, f"kernel clock failed: {type(exc).__name__}"
    if (
        not isinstance(current, datetime)
        or current.tzinfo is None
        or current.tzinfo.utcoffset(current) is None
    ):
        return None, "kernel clock returned a naive or non-datetime value"
    return current.astimezone(UTC), None


def _inside(root: Path, candidate: Path) -> bool:
    root_text = os.path.normcase(str(root))
    child_text = os.path.normcase(str(candidate))
    prefix = root_text if root_text.endswith(os.sep) else root_text + os.sep
    return child_text.startswith(prefix)


def _identity(
    frame: Frame,
    snapshot: FileSnapshot,
    data: bytes | None,
    *,
    width: int | None = None,
    height: int | None = None,
) -> Mapping[str, object]:
    if data is None:
        size: int = snapshot.size
        digest = ""
    else:
        size = len(data)
        digest = hashlib.sha256(data).hexdigest()
    values: dict[str, object] = {
        "path": frame.path,
        "resolved_path": str(snapshot.resolved),
        "size_bytes": size,
        "sha256": digest,
        "mtime_ns": snapshot.mtime_ns,
    }
    if width is not None and height is not None:
        values["width"] = width
        values["height"] = height
    return MappingProxyType(values)


def _provenance(
    frame: Frame,
    mode: str,
    *,
    age_s: float | None,
    interval: tuple[datetime, datetime] | None,
    phone_interval_ignored: bool = False,
) -> Mapping[str, object]:
    if frame.source == "phone" and frame.captured_at is None:
        origin = "unknown_phone"
    elif frame.source == "phone":
        origin = "supplied_phone"
    else:
        origin = "live_metadata"
    started = interval[0].isoformat() if interval is not None else None
    ended = interval[1].isoformat() if interval is not None else None
    return MappingProxyType(
        {
            "source": frame.source,
            "zone": frame.zone,
            "mode": mode,
            "simulated": frame.simulated,
            "captured_at": frame.captured_at,
            "time_origin": origin,
            "age_s": age_s,
            "file_mtime_used": False,
            "stream_selection_freshness": "not_claimed",
            "five_second_return_rule_applied": False,
            "acceptance_scope": "file_integrity_and_metadata",
            "interval_started_at": started,
            "interval_ended_at": ended,
            "phone_interval_ignored": phone_interval_ignored,
        }
    )
