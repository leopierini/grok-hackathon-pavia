"""Filesystem and decoder faults for evidence tests. Production create() does not install these."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from patrol.ground.extensions.g06.io import EvidenceIOError, FileSnapshot, RealIO


class FaultIO:
    def __init__(
        self,
        fault: str | None = None,
        *,
        inner: RealIO | None = None,
        snapshot: FileSnapshot | None = None,
    ) -> None:
        self.fault = fault
        self.inner = inner or RealIO()
        self.snapshot_override = snapshot
        self.reads = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.halt_mark: float | None = None

    async def snapshot(self, path: Path) -> FileSnapshot:
        if self.snapshot_override is not None:
            return self.snapshot_override
        return await self.inner.snapshot(path)

    async def read(self, path: Path, *, max_bytes: int) -> bytes:
        self.reads += 1
        if self.fault == "slow_disappear":
            self.halt_mark = time.perf_counter()
            self.started.set()
            await self.release.wait()
            raise FileNotFoundError(path)
        if self.fault == "disappear":
            raise FileNotFoundError(path)
        data = await self.inner.read(path, max_bytes=max_bytes)
        if self.fault == "change" and self.reads >= 2:
            return data + b"\x00"
        return data

    async def decode_jpeg(self, data: bytes, *, max_pixels: int) -> tuple[int, int]:
        if self.fault in {"decoder", "slow_decoder"}:
            if self.fault == "slow_decoder":
                self.halt_mark = time.perf_counter()
                self.started.set()
                await self.release.wait()
            raise EvidenceIOError("decoder_error", "injected decoder failure")
        return await self.inner.decode_jpeg(data, max_pixels=max_pixels)
