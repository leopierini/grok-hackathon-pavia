"""Shared builders for GROUND-06 tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from patrol.contract import Frame
from patrol.ground.extensions.g06.clock import ManualClock
from patrol.ground.extensions.g06.images import write_jpeg
from patrol.ground.extensions.g06.implementation import EvidenceValidator, create
from patrol.ground.extensions.g06.io import RealIO
from patrol.ground.extensions.g06.model import (
    CaptureInterval,
    EvidenceLimits,
    EvidenceResult,
    KernelContext,
    ServicePorts,
)

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def kernel_with(
    io: object | None = None,
    *,
    limits: EvidenceLimits | None = None,
    now: datetime | None = None,
) -> tuple[KernelContext, ManualClock]:
    clock = ManualClock(utc=now or NOW)
    kernel = KernelContext(clock=clock, io=io or RealIO(), limits=limits or EvidenceLimits())
    return kernel, clock


def provider_for(
    io: object | None = None,
    *,
    limits: EvidenceLimits | None = None,
    peers: ServicePorts | None = None,
) -> EvidenceValidator:
    kernel, _clock = kernel_with(io, limits=limits)
    created = create(kernel, peers or ServicePorts())
    assert isinstance(created, EvidenceValidator)
    return created


def live_frame(
    root: Path,
    source: str = "dog",
    zone: str = "room_2",
    *,
    simulated: bool = False,
    captured_at: str | None = None,
    name: str = "frame.jpg",
) -> tuple[Frame, CaptureInterval]:
    path = root / name
    write_jpeg(path)
    interval = CaptureInterval(
        (NOW - timedelta(seconds=5)).isoformat(),
        NOW.isoformat(),
    )
    stamp = captured_at if captured_at is not None else (NOW - timedelta(seconds=1)).isoformat()
    frame = Frame(str(path), source, zone, stamp, simulated)  # type: ignore[arg-type]
    return frame, interval


async def validate(
    frame: Frame,
    *,
    source: str | None = None,
    zone: str | None = None,
    mode: str = "real",
    root: Path,
    interval: CaptureInterval | None = None,
    io: object | None = None,
    limits: EvidenceLimits | None = None,
    peers: ServicePorts | None = None,
) -> EvidenceResult:
    port = provider_for(io, limits=limits, peers=peers)
    return await port.validate(
        frame,
        expected_source=(source or frame.source),  # type: ignore[arg-type]
        zone=(zone or frame.zone),  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        output_root=root,
        interval=interval,
    )
