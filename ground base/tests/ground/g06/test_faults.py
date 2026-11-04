"""Disappearing files, changed bytes, decoder faults, and halt responsiveness."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from patrol.ground.extensions.g06.faults import FaultIO
from patrol.ground.extensions.g06.model import ServicePorts
from tests.ground.g06.support import live_frame, validate


def test_changed_bytes_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    frame, interval = live_frame(root)
    io = FaultIO("change")

    result = asyncio.run(validate(frame, root=root, interval=interval, io=io))

    assert result.reason == "changed_during_validation"
    assert result.frame is None


def test_disappearance_and_decoder_failure_leave_halt_responsive(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    frame, interval = live_frame(root)
    peers = ServicePorts()

    disappear = asyncio.run(_halted(frame, root, interval, FaultIO("slow_disappear"), peers))
    decoder = asyncio.run(_halted(frame, root, interval, FaultIO("slow_decoder"), peers))

    assert disappear[0].reason == "disappeared"
    assert decoder[0].reason == "decoder_error"
    assert disappear[1] < 0.5
    assert decoder[1] < 0.5
    assert disappear[0].frame is None and decoder[0].frame is None


def test_deleted_file_is_an_explicit_disappearance(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    frame, interval = live_frame(root)

    class DeleteOnRead(FaultIO):
        async def read(self, path: Path, *, max_bytes: int) -> bytes:
            path.unlink()
            return await super().read(path, max_bytes=max_bytes)

    result = asyncio.run(validate(frame, root=root, interval=interval, io=DeleteOnRead()))

    assert result.reason == "disappeared"


async def _halted(
    frame: object,
    root: Path,
    interval: object,
    io: FaultIO,
    peers: ServicePorts,
) -> tuple[object, float]:
    from patrol.contract import Frame
    from patrol.ground.extensions.g06.model import CaptureInterval

    assert isinstance(frame, Frame)
    assert isinstance(interval, CaptureInterval)

    async def run() -> object:
        return await validate(frame, root=root, interval=interval, io=io, peers=peers)

    async def pulse() -> float:
        await asyncio.wait_for(io.started.wait(), timeout=2)
        latency = time.perf_counter() - (io.halt_mark or time.perf_counter())
        io.release.set()
        return latency

    result, latency = await asyncio.wait_for(asyncio.gather(run(), pulse()), timeout=2)
    return result, latency
