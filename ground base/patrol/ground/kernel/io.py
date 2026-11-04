"""Filesystem access with one-shot fault injection for the harness."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.kernel.faults import fault

_OPS = frozenset({"read", "write"})


class FaultyIO:
    def __init__(self) -> None:
        self._faults: list[tuple[str, str]] = []

    def fail_next(self, op: str, reason: str) -> None:
        if op not in _OPS:
            raise fault("invalid_input", "io fault operation must be read or write")
        if not isinstance(reason, str) or not reason:
            raise fault("invalid_input", "io fault reason is required")
        self._faults.append((op, reason))

    def read_bytes(self, path: Path, *, limit: int) -> bytes:
        self._consume("read")
        return self._read(path, limit)

    def read_text(self, path: Path, *, limit: int = 1_000_000) -> str:
        data = self.read_bytes(path, limit=limit)
        try:
            return data.decode("utf-8")
        except UnicodeError as exc:
            raise fault("invalid_input", "file is not utf-8") from exc

    def write_bytes(self, path: Path, data: bytes) -> None:
        self._consume("write")
        if not isinstance(data, bytes):
            raise fault("invalid_input", "write payload must be bytes")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        temporary.write_bytes(data)
        temporary.replace(target)

    def _consume(self, op: str) -> None:
        if self._faults and self._faults[0][0] == op:
            _kind, reason = self._faults.pop(0)
            raise fault("io_fault", reason, recovery_required=True)

    def _read(self, path: Path, limit: int) -> bytes:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise fault("invalid_input", "read limit must be a positive integer")
        target = Path(path)
        if not target.is_file():
            raise fault("io_fault", "file is missing", recovery_required=True)
        data = target.read_bytes()
        if len(data) > limit:
            raise fault("validation_failed", "file exceeds the read limit")
        return data
