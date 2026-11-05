"""Local artifact writer. Tests substitute a faulting double with the same methods."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Protocol

_LAYOUT = ("dog", "drone", "grok", "input")


class WriterFault(Exception):
    """Storage failure. ``code`` is a short token and ``wrote`` means bytes reached the file."""

    def __init__(self, code: str, *, wrote: bool) -> None:
        super().__init__(code)
        self.code = code
        self.wrote = wrote


class ArtifactWriter(Protocol):
    def prepare_run(self, run_dir: Path) -> None: ...

    def append_lines(self, path: Path, text: str) -> None: ...

    def replace_summary(self, directory: Path, payload: str) -> None: ...


def _translate(exc: OSError, *, wrote: bool) -> WriterFault:
    errno = exc.errno
    if isinstance(exc, PermissionError) or errno in {1, 13}:
        return WriterFault("permission", wrote=wrote)
    if errno in {28, 1224}:
        return WriterFault("disk_full", wrote=wrote)
    if "closed" in str(exc).lower():
        return WriterFault("closed_stream", wrote=wrote)
    return WriterFault("io_error", wrote=wrote)


class DiskWriter:
    """Append JSONL and publish ``summary.json`` with ``os.replace`` on the same directory."""

    def prepare_run(self, run_dir: Path) -> None:
        try:
            run_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError as exc:
            raise WriterFault("run_exists", wrote=False) from exc
        except OSError as exc:
            raise _translate(exc, wrote=False) from None
        try:
            for name in _LAYOUT:
                (run_dir / name).mkdir()
            (run_dir / "events.jsonl").write_text("", encoding="utf-8", newline="\n")
        except OSError as exc:
            raise _translate(exc, wrote=False) from None

    def append_lines(self, path: Path, text: str) -> None:
        try:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            wrote = path.is_file() and path.stat().st_size > 0
            raise _translate(exc, wrote=wrote) from None

    def replace_summary(self, directory: Path, payload: str) -> None:
        temporary = directory / "summary.json.tmp"
        target = directory / "summary.json"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except OSError as exc:
            raise _translate(exc, wrote=False) from None


class FaultWriter:
    """In-memory stand-in that can block or fail at a chosen boundary.

    ``fail`` is one of ``disk_full``, ``permission``, ``closed``, ``sync``, ``rename``,
    or ``boom``. ``gate`` blocks inside the write when it is clear.
    """

    def __init__(self, *, fail: str | None = None, gate: threading.Event | None = None) -> None:
        self.fail = fail
        self.gate = gate or threading.Event()
        self.gate.set()
        self.entered = threading.Event()
        self.calls: list[str] = []

    def prepare_run(self, run_dir: Path) -> None:
        self._wait("prepare")
        if self.fail in {"disk_full", "permission", "closed"}:
            raise WriterFault(_code(self.fail), wrote=False)
        if self.fail == "boom":
            raise RuntimeError("sk-live-secret")
        DiskWriter().prepare_run(run_dir)

    def append_lines(self, path: Path, text: str) -> None:
        self._wait("append")
        if self.fail == "disk_full":
            raise WriterFault("disk_full", wrote=False)
        if self.fail == "permission":
            raise WriterFault("permission", wrote=False)
        if self.fail == "closed":
            raise WriterFault("closed_stream", wrote=False)
        if self.fail == "boom":
            raise RuntimeError("sk-live-secret")
        if self.fail == "sync":
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
            raise WriterFault("sync", wrote=True)
        DiskWriter().append_lines(path, text)

    def replace_summary(self, directory: Path, payload: str) -> None:
        self._wait("replace")
        if self.fail in {"disk_full", "permission", "closed"}:
            raise WriterFault(_code(self.fail), wrote=False)
        if self.fail == "rename":
            temporary = directory / "summary.json.tmp"
            temporary.write_text(payload, encoding="utf-8", newline="\n")
            raise WriterFault("rename", wrote=False)
        if self.fail == "boom":
            raise RuntimeError("sk-live-secret")
        DiskWriter().replace_summary(directory, payload)

    def _wait(self, call: str) -> None:
        self.calls.append(call)
        if self.gate.is_set():
            return
        self.entered.set()
        if not self.gate.wait(30):
            raise WriterFault("flush_timeout", wrote=False)


def _code(fail: str) -> str:
    if fail == "closed":
        return "closed_stream"
    return fail
