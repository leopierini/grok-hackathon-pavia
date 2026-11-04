"""Scripted evidence cases. The harness calls the real provider; it does not print a canned pass."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from patrol.contract import Frame
from patrol.ground.extensions.g06.clock import ManualClock
from patrol.ground.extensions.g06.faults import FaultIO
from patrol.ground.extensions.g06.images import jpeg_bytes, write_jpeg
from patrol.ground.extensions.g06.implementation import create
from patrol.ground.extensions.g06.io import FileSnapshot
from patrol.ground.extensions.g06.model import (
    CaptureInterval,
    EvidenceLimits,
    EvidenceResult,
    KernelContext,
    ServicePorts,
)
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
FORBIDDEN = (
    "connect",
    "prepare",
    "run_route",
    "capture_frame",
    "inspect",
    "land",
    "assess_incident",
    "assess_ground_view",
    "resolve_incident",
    "compose_alert",
)

_SPECS: tuple[dict[str, object], ...] = (
    {
        "id": "live_dog_accepted",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "expect": "accepted",
    },
    {
        "id": "simulated_phone_unknown_time",
        "source": "phone",
        "zone": "room_2",
        "mode": "fake",
        "simulated": True,
        "captured": "none",
        "path": "outside",
        "expect": "accepted",
        "time_origin": "unknown_phone",
    },
    {
        "id": "simulated_drone_display",
        "source": "drone",
        "zone": "display",
        "mode": "fake",
        "simulated": True,
        "captured": "inside",
        "expect": "accepted",
    },
    {
        "id": "corrupt_non_jpeg",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "file": "text",
        "expect": "not_jpeg",
    },
    {
        "id": "truncated_jpeg",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "file": "truncated",
        "expect": "truncated_jpeg",
    },
    {
        "id": "empty_file",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "file": "empty",
        "expect": "empty_file",
    },
    {
        "id": "oversized_file",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "max_bytes": 32,
        "expect": "oversized",
        "reads": 0,
    },
    {
        "id": "wrong_zone",
        "source": "dog",
        "zone": "room_2",
        "frame_zone": "display",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "expect": "zone_mismatch",
    },
    {
        "id": "wrong_source",
        "source": "dog",
        "zone": "room_2",
        "frame_source": "drone",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "expect": "source_mismatch",
    },
    {
        "id": "simulated_on_real_adapter",
        "source": "drone",
        "zone": "room_2",
        "mode": "real",
        "simulated": True,
        "captured": "inside",
        "expect": "simulation_mismatch",
    },
    {
        "id": "fake_mode_unsimulated",
        "source": "dog",
        "zone": "entrance",
        "mode": "fake",
        "simulated": False,
        "captured": "inside",
        "expect": "simulation_mismatch",
    },
    {
        "id": "non_bool_simulation_flag",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": "false",
        "captured": "inside",
        "expect": "invalid_simulation_flag",
    },
    {
        "id": "relative_path",
        "source": "phone",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "none",
        "path": "relative",
        "expect": "relative_path",
    },
    {
        "id": "traversal_escape",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "path": "traversal",
        "expect": "containment_escape",
        "reads": 0,
    },
    {
        "id": "symlink_escape",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "path": "symlink",
        "expect": "symlink_escape",
        "reads": 0,
    },
    {
        "id": "aerial_landing_delay",
        "source": "drone",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "landing",
        "expect": "accepted",
        "age": 12.0,
    },
    {
        "id": "dog_older_than_five_seconds",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "over_five",
        "expect": "accepted",
        "age": 6.0,
    },
    {
        "id": "pre_request_buffer",
        "source": "drone",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "pre_request",
        "expect": "pre_request",
    },
    {
        "id": "future_timestamp",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "future",
        "expect": "future_timestamp",
    },
    {
        "id": "naive_timestamp",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "naive",
        "expect": "naive_timestamp",
    },
    {
        "id": "null_live_timestamp",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "none",
        "expect": "null_timestamp",
    },
    {
        "id": "phone_copy_preserves_unknown_time",
        "source": "phone",
        "zone": "entrance",
        "mode": "real",
        "simulated": False,
        "captured": "none",
        "path": "copy",
        "expect": "accepted",
        "time_origin": "unknown_phone",
    },
    {
        "id": "phone_keeps_supplied_zulu_time",
        "source": "phone",
        "zone": "display",
        "mode": "real",
        "simulated": False,
        "captured": "zulu",
        "path": "outside",
        "expect": "accepted",
        "time_origin": "supplied_phone",
    },
    {
        "id": "phone_ignores_operation_interval",
        "source": "phone",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "supplied",
        "path": "outside",
        "phone_interval": True,
        "expect": "accepted",
    },
    {
        "id": "changed_during_validation",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "fault": "change",
        "expect": "changed_during_validation",
    },
    {
        "id": "file_disappeared_halt_responsive",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "fault": "slow_disappear",
        "expect": "disappeared",
    },
    {
        "id": "decoder_failure_halt_responsive",
        "source": "drone",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "fault": "slow_decoder",
        "expect": "decoder_error",
    },
    {
        "id": "rejection_not_forwarded",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "file": "text",
        "expect": "not_jpeg",
    },
    {
        "id": "pixel_bound",
        "source": "dog",
        "zone": "room_2",
        "mode": "fake",
        "simulated": True,
        "captured": "inside",
        "max_pixels": 1,
        "expect": "oversized",
    },
    {
        "id": "directory_path",
        "source": "dog",
        "zone": "room_2",
        "mode": "real",
        "simulated": False,
        "captured": "inside",
        "path": "directory",
        "expect": "not_regular_file",
    },
)


class CallProbe:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> object:
        def record(*_args: object, **_kwargs: object) -> None:
            self.calls.append(name)

        return record


class _Check:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.count = 0

    def eq(self, actual: object, expected: object, label: str) -> None:
        self.count += 1
        if actual != expected:
            self.failures.append(f"{label}: {actual!r} != {expected!r}")

    def true(self, value: object, label: str) -> None:
        self.eq(bool(value), True, label)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    built: list[SimulationCase] = []
    for spec in _SPECS:
        case_id = str(spec["id"])
        built.append(
            SimulationCase(
                task_id="GROUND-06",
                case_id=case_id,
                seed=seed,
                setup=freeze_map({"fixture": "generated-jpeg"}),
                stimuli=(freeze_map(spec),),
                barriers=(),
                faults=(),
                expected=freeze_map(
                    {
                        "status": "ok",
                        "simulated": True,
                        "live_call_count": 0,
                        "device_calls": 0,
                        "authorized": False,
                        "slot": "base.evidence",
                        "schema_version": SCHEMA_VERSION,
                        "detail": case_id,
                    }
                ),
                forbidden_calls=FORBIDDEN,
                teardown=("release_barriers", "collect_tasks", "remove_owned_temp"),
            )
        )
    return tuple(built)


async def run_named(case_id: str, *, seed: int) -> dict[str, object]:
    spec = next((item for item in _SPECS if str(item["id"]) == case_id), None)
    if spec is None:
        return {
            "case_id": case_id,
            "passed": False,
            "assertions": 1,
            "failures": ["unknown case"],
            "observed": {},
            "halt_latency_s": None,
            "peer_calls": [],
            "forbidden_calls": list(FORBIDDEN),
        }
    return await _execute_spec(case_id, dict(spec), seed=seed, forbidden=FORBIDDEN)


async def execute(case: SimulationCase, *, seed: int) -> dict[str, object]:
    return await _execute_spec(
        case.case_id,
        dict(case.stimuli[0]),
        seed=seed,
        forbidden=case.forbidden_calls,
    )


async def _execute_spec(
    case_id: str,
    spec: dict[str, object],
    *,
    seed: int,
    forbidden: tuple[str, ...],
) -> dict[str, object]:
    check = _Check()
    observed: dict[str, object] = {}
    latency: float | None = None
    peer_calls: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="g06-") as raw:
            observed, latency, peer_calls = await _run_spec(spec, Path(raw), seed, check)
    except Exception as exc:  # noqa: BLE001 — one case failure must not hide the rest of the report
        check.failures.append(f"exception {type(exc).__name__}: {exc}")
    return {
        "case_id": case_id,
        "passed": not check.failures,
        "assertions": check.count,
        "failures": list(check.failures),
        "observed": observed,
        "halt_latency_s": latency,
        "peer_calls": peer_calls,
        "forbidden_calls": list(forbidden),
    }


async def _run_spec(
    spec: Mapping[str, object],
    folder: Path,
    seed: int,
    check: _Check,
) -> tuple[dict[str, object], float | None, list[str]]:
    source = str(spec["source"])
    zone = str(spec["zone"])
    mode = str(spec["mode"])
    captured_kind = str(spec["captured"])
    path_kind = str(spec.get("path", "inside"))
    file_kind = str(spec.get("file", "jpeg"))
    fault = spec.get("fault")
    fault_name = str(fault) if isinstance(fault, str) else None
    output_root = folder / "adapter"
    output_root.mkdir()
    color = (10 + (seed % 200), 40, 60)
    path, snapshot = _place_file(
        folder,
        output_root,
        path_kind=path_kind,
        file_kind=file_kind,
        color=color,
    )
    captured_at = _capture_text(captured_kind)
    interval = _interval_for(
        captured_kind, phone=source == "phone" and bool(spec.get("phone_interval"))
    )
    original_captured = captured_at
    simulated: object = spec["simulated"]
    frame_source = str(spec.get("frame_source", source))
    frame_zone = str(spec.get("frame_zone", zone))
    frame = Frame(
        path=str(path),
        source=frame_source,  # type: ignore[arg-type]
        zone=frame_zone,  # type: ignore[arg-type]
        captured_at=captured_at,
        simulated=simulated,  # type: ignore[arg-type]
    )
    io = FaultIO(fault_name, snapshot=snapshot)
    defaults = EvidenceLimits()
    limits = EvidenceLimits(
        max_bytes=_as_int(spec["max_bytes"]) if "max_bytes" in spec else defaults.max_bytes,
        max_pixels=_as_int(spec["max_pixels"]) if "max_pixels" in spec else defaults.max_pixels,
    )
    clock = ManualClock(utc=NOW)
    kernel = KernelContext(clock=clock, io=io, limits=limits)
    probe = CallProbe()
    peers = ServicePorts(reasoner=probe, dog=probe, drone=probe)
    provider = create(kernel, peers)

    async def validate() -> EvidenceResult:
        return await provider.validate(
            frame,
            expected_source=source,
            zone=zone,  # type: ignore[arg-type]
            mode=mode,  # type: ignore[arg-type]
            output_root=output_root,
            interval=interval,
        )

    latency: float | None = None
    if fault_name in {"slow_disappear", "slow_decoder"}:

        async def pulse() -> float:
            await asyncio.wait_for(io.started.wait(), timeout=2)
            measured = time.perf_counter() - (io.halt_mark or time.perf_counter())
            io.release.set()
            return measured

        result, latency = await asyncio.wait_for(asyncio.gather(validate(), pulse()), timeout=2)
    else:
        result = await validate()

    check.eq(frame.captured_at, original_captured, "timestamp not rewritten")
    check.eq(result.status, "accepted" if spec["expect"] == "accepted" else "rejected", "status")
    check.eq(result.reason, spec["expect"], "reason")
    check.eq(probe.calls, [], "peer calls")
    if spec["expect"] != "accepted":
        check.eq(result.frame, None, "rejected frame is not forwardable")
    else:
        check.true(result.frame is frame, "accepted frame is the original object")
        check.eq(result.error, None, "accepted error")
        assert result.provenance is not None
        check.eq(result.provenance["file_mtime_used"], False, "mtime not used as capture time")
        check.eq(
            result.provenance["five_second_return_rule_applied"],
            False,
            "no five-second return rule",
        )
        check.eq(
            result.provenance["stream_selection_freshness"],
            "not_claimed",
            "stream freshness not claimed",
        )
    if "age" in spec and result.provenance is not None:
        check.eq(result.provenance["age_s"], spec["age"], "age_s")
    if "time_origin" in spec and result.provenance is not None:
        check.eq(result.provenance["time_origin"], spec["time_origin"], "time_origin")
    if spec.get("phone_interval") and result.provenance is not None:
        check.eq(result.provenance["phone_interval_ignored"], True, "phone interval ignored")
    if "reads" in spec:
        check.eq(io.reads, spec["reads"], "reads")
    if latency is not None:
        check.true(latency < 0.5, f"halt latency {latency}")
    if path_kind == "copy" and result.frame is not None:
        check.eq(result.frame.captured_at, None, "copied phone keeps unknown time")
    try:
        if path.exists() and path.is_file():
            path.unlink()
            check.true(True, "file handle released")
    except OSError as exc:
        check.failures.append(f"file handle still open: {exc}")
        check.count += 1
    public = result.as_dict()
    public.pop("frame", None)
    return public, latency, list(probe.calls)


def _as_int(value: object) -> int:
    if type(value) is not int:
        raise TypeError(f"expected int, got {type(value).__name__}")
    return value


def _place_file(
    folder: Path,
    output_root: Path,
    *,
    path_kind: str,
    file_kind: str,
    color: tuple[int, int, int],
) -> tuple[Path, FileSnapshot | None]:
    target = output_root / "frame.jpg"
    if path_kind == "relative":
        return Path("photo.jpg"), None
    if path_kind == "missing":
        return output_root / "missing.jpg", None
    if path_kind == "directory":
        directory = output_root / "nested"
        directory.mkdir()
        return directory, None
    if path_kind == "symlink":
        outside = folder / "secret.jpg"
        write_jpeg(outside, color=color)
        link = output_root / "link.jpg"
        return link, FileSnapshot(
            size=0,
            is_symlink=True,
            is_regular=False,
            resolved=outside.resolve(),
            mtime_ns=0,
        )
    if path_kind in {"outside", "copy"}:
        outside = folder / "phone-original.jpg"
        data = write_jpeg(outside, color=color)
        if path_kind == "copy":
            copied = folder / "artifacts" / "phone-copy.jpg"
            copied.parent.mkdir()
            copied.write_bytes(data)
            os.utime(copied, (1_700_000_000, 1_700_000_000))
            return copied, None
        return outside, None
    if path_kind == "traversal":
        outside = folder / "outside.jpg"
        write_jpeg(outside, color=color)
        return output_root / ".." / "outside.jpg", None
    _write_kind(target, file_kind, color)
    return target, None


def _write_kind(path: Path, kind: str, color: tuple[int, int, int]) -> None:
    if kind == "empty":
        path.write_bytes(b"")
        return
    if kind == "text":
        path.write_bytes(b"this is not a jpeg\n")
        return
    data = jpeg_bytes(color=color)
    if kind == "truncated":
        path.write_bytes(data[: max(2, len(data) // 2)])
        return
    path.write_bytes(data)


def _capture_text(kind: str) -> str | None:
    if kind == "none":
        return None
    if kind == "naive":
        return "2026-11-04T12:00:00"
    if kind == "malformed":
        return "not-a-timestamp"
    if kind == "zulu":
        return "2026-11-04T11:00:00Z"
    if kind == "supplied":
        return (NOW - timedelta(hours=2)).isoformat()
    return _instant(kind).isoformat()


def _instant(kind: str) -> datetime:
    if kind == "landing":
        return NOW - timedelta(seconds=12)
    if kind == "over_five":
        return NOW - timedelta(seconds=6)
    if kind == "pre_request":
        return NOW - timedelta(seconds=10)
    if kind == "future":
        return NOW + timedelta(seconds=30)
    if kind == "after_end":
        return NOW - timedelta(seconds=5)
    return NOW - timedelta(seconds=1)


def _interval_for(kind: str, *, phone: bool) -> CaptureInterval | None:
    if kind == "landing":
        return CaptureInterval(
            (NOW - timedelta(seconds=13)).isoformat(),
            NOW.isoformat(),
        )
    if kind == "over_five":
        return CaptureInterval(
            (NOW - timedelta(seconds=10)).isoformat(),
            NOW.isoformat(),
        )
    if kind == "pre_request":
        return CaptureInterval(NOW.isoformat(), (NOW + timedelta(seconds=5)).isoformat())
    if kind == "future":
        return CaptureInterval(
            (NOW - timedelta(seconds=5)).isoformat(),
            (NOW + timedelta(seconds=60)).isoformat(),
        )
    if phone:
        return CaptureInterval(NOW.isoformat(), (NOW + timedelta(seconds=1)).isoformat())
    if kind in {"none", "naive", "malformed", "zulu", "supplied"}:
        return None
    return CaptureInterval((NOW - timedelta(seconds=5)).isoformat(), NOW.isoformat())
