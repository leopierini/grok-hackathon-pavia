"""Bounded file snapshot, read, and JPEG decode.

Pillow's pixel limit is process-global, so decode holds a lock and restores it.
The lock is not held across the async fault waits used to prove halt stays responsive.
"""

from __future__ import annotations

import asyncio
import os
import stat
import threading
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

_DECODE_LOCK = threading.Lock()


class EvidenceIOError(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class FileSnapshot:
    size: int
    is_symlink: bool
    is_regular: bool
    resolved: Path
    mtime_ns: int


class RealIO:
    async def snapshot(self, path: Path) -> FileSnapshot:
        return await asyncio.to_thread(self._snapshot_sync, path)

    async def read(self, path: Path, *, max_bytes: int) -> bytes:
        return await asyncio.to_thread(self._read_sync, path, max_bytes)

    async def decode_jpeg(self, data: bytes, *, max_pixels: int) -> tuple[int, int]:
        return await asyncio.to_thread(self._decode_sync, data, max_pixels)

    def _snapshot_sync(self, path: Path) -> FileSnapshot:
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise EvidenceIOError(
                "unreadable", f"could not stat file: {exc.strerror or exc}"
            ) from exc
        try:
            resolved = Path(os.path.realpath(path))
        except OSError as exc:
            raise EvidenceIOError(
                "unreadable", f"could not resolve file: {exc.strerror or exc}"
            ) from exc
        mode = info.st_mode
        mtime_ns = getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))
        return FileSnapshot(
            size=info.st_size,
            is_symlink=stat.S_ISLNK(mode) or os.path.islink(path),
            is_regular=stat.S_ISREG(mode),
            resolved=resolved,
            mtime_ns=int(mtime_ns),
        )

    def _read_sync(self, path: Path, max_bytes: int) -> bytes:
        try:
            with path.open("rb") as handle:
                return handle.read(max_bytes + 1)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise EvidenceIOError(
                "unreadable", f"could not read file: {exc.strerror or exc}"
            ) from exc

    def _decode_sync(self, data: bytes, max_pixels: int) -> tuple[int, int]:
        if not data.startswith(b"\xff\xd8"):
            raise EvidenceIOError(
                "not_jpeg", "file does not start with a JPEG start-of-image marker"
            )
        from PIL import Image, ImageFile, UnidentifiedImageError

        with _DECODE_LOCK:
            previous_limit = Image.MAX_IMAGE_PIXELS
            previous_truncated = ImageFile.LOAD_TRUNCATED_IMAGES
            Image.MAX_IMAGE_PIXELS = max_pixels
            ImageFile.LOAD_TRUNCATED_IMAGES = False
            try:
                try:
                    with Image.open(BytesIO(data)) as image:
                        if image.format != "JPEG":
                            raise EvidenceIOError("not_jpeg", "decoded content is not a JPEG")
                        image.load()
                        width, height = image.size
                except EvidenceIOError:
                    raise
                except Image.DecompressionBombError as exc:
                    raise EvidenceIOError("oversized", "image exceeds the pixel bound") from exc
                except UnidentifiedImageError as exc:
                    if data.startswith(b"\xff\xd8"):
                        raise EvidenceIOError(
                            "truncated_jpeg", "JPEG data ended before a full image"
                        ) from exc
                    raise EvidenceIOError("not_jpeg", "decoder could not identify a JPEG") from exc
                except OSError as exc:
                    text = str(exc).lower()
                    if "truncated" in text or "broken data stream" in text:
                        raise EvidenceIOError("truncated_jpeg", "JPEG data is truncated") from exc
                    raise EvidenceIOError("corrupt_jpeg", "JPEG could not be decoded") from exc
            finally:
                Image.MAX_IMAGE_PIXELS = previous_limit
                ImageFile.LOAD_TRUNCATED_IMAGES = previous_truncated
        if width < 1 or height < 1 or width * height > max_pixels:
            raise EvidenceIOError("oversized", "image exceeds the pixel bound")
        return width, height


class CountingIO(RealIO):
    """Real disk IO that counts reads. Escape tests use the count."""

    def __init__(self) -> None:
        self.reads = 0

    async def read(self, path: Path, *, max_bytes: int) -> bytes:
        self.reads += 1
        return await super().read(path, max_bytes=max_bytes)
