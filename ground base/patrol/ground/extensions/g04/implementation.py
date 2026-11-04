"""Ordered local journal.

Queue policy: reject-new. ``emit`` never blocks and never drops an event that
was already accepted. At most ``max_queue`` events may be accepted and not yet
durable. One extra queue slot is reserved for a flush barrier and one for
shutdown, so a full event queue can still be asked to stop. Disk writes run
on a single thread started by ``open``. ``emit`` only enqueues. A stalled
flush does not run on the event-loop turn that records halt.

Durability claims are separate. ``queued`` means accepted and not yet synced.
``flushed`` means the bytes were written. ``synced`` means ``os.fsync`` returned.
A sync failure counts as flushed and not synced, and the line is not written
again. This is not a power-loss guarantee.

The kernel's ``GroundError`` allowlist has no persistence codes, and
``GroundEvent`` only allows frame events. Faults are returned on the journal
result instead of being forced into those types. The journal does not call
safety, workflow, or device ports.
"""

from __future__ import annotations

import asyncio
import json
import math
import queue
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from patrol.contract import CONTRACT_VERSION
from patrol.ground.extensions.g04.writer import ArtifactWriter, DiskWriter, WriterFault
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    KernelContext,
)
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

QUEUE_POLICY = "reject-new"
DEFAULT_MAX_QUEUE = 32
DEFAULT_MAX_EVENT_BYTES = 4096
DEFAULT_MAX_SUMMARY_BYTES = 65536

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_MISSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_OPERATION = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,80}$")
_ZONES = frozenset({"entrance", "room_2", "display"})
_MODES = ("dog", "drone", "grok")
_EVENT_KEYS = frozenset(
    {
        "seq",
        "timestamp_utc",
        "elapsed_s",
        "mission_id",
        "contract_version",
        "state",
        "event",
        "operation",
        "operation_id",
        "zone",
        "target",
        "modes",
        "data",
        "ticket",
        "error",
    }
)
_LAYOUT = ("events.jsonl", "summary.json", "summary.json.tmp")


class EventSanitizer(Protocol):
    def __call__(self, record: Mapping[str, object]) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class JournalLimits:
    max_event_bytes: int = DEFAULT_MAX_EVENT_BYTES
    max_queue: int = DEFAULT_MAX_QUEUE
    max_summary_bytes: int = DEFAULT_MAX_SUMMARY_BYTES
    flush_timeout_s: float = 30.0
    close_timeout_s: float = 0.3


@dataclass(frozen=True)
class JournalResult:
    ok: bool
    durability: str
    queued: int
    flushed: int
    synced: int
    published: bool
    pending: bool
    saved: bool
    seq: int | None
    run_dir: str | None
    fault_code: str | None
    detail: str
    mission_error: object
    writer_error: str | None
    prior_preserved: bool
    health: str
    scan: tuple[Mapping[str, object], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "durability": self.durability,
            "queued": self.queued,
            "flushed": self.flushed,
            "synced": self.synced,
            "published": self.published,
            "pending": self.pending,
            "saved": self.saved,
            "seq": self.seq,
            "run_dir": self.run_dir,
            "fault_code": self.fault_code,
            "detail": self.detail,
            "mission_error": self.mission_error,
            "writer_error": self.writer_error,
            "prior_preserved": self.prior_preserved,
            "health": self.health,
            "writer_health": {
                "state": self.health,
                "queued": self.queued,
                "flushed": self.flushed,
                "synced": self.synced,
                "published": self.published,
                "pending": self.pending,
                "fault_code": self.fault_code,
            },
            "scan": [dict(item) for item in self.scan],
        }


class Journal:
    """JournalPort implementation. Construction does not touch the filesystem."""

    def __init__(
        self,
        kernel: KernelContext,
        peers: object,
        *,
        writer: ArtifactWriter | None = None,
        sanitizer: EventSanitizer | None = None,
        limits: JournalLimits | None = None,
    ) -> None:
        self._clock = kernel.clock
        self._peers = peers
        self._writer = writer or DiskWriter()
        self._sanitizer = sanitizer
        self._limits = limits or JournalLimits()
        self._lock = threading.Lock()
        self._commands: queue.Queue[tuple[str, object]] | None = None
        self._thread: threading.Thread | None = None
        self._opened = False
        self._closing = False
        self._closed = False
        self._run_dir: Path | None = None
        self._events: Path | None = None
        self._summary: Path | None = None
        self._origin = 0.0
        self._seq = 0
        self._waiting = 0
        self._flushed = 0
        self._synced = 0
        self._published = False
        self._fault: str | None = None
        self._pending = False
        self._saved = False
        self._retry: list[str] = []

    def peer_ports(self) -> object:
        return self._peers

    async def open(self, run_id: str, output_root: Path) -> JournalResult:
        if self._opened:
            return self._result(False, "failed", "journal is already open", fault="already_open")
        if type(run_id) is not str or not _safe_run_id(run_id):
            return self._result(
                False, "failed", "run id is not a safe token", fault="invalid_run_id"
            )
        root = Path(output_root)
        if root.is_symlink() or not root.is_dir():
            return self._result(
                False, "failed", "output root is not a real directory", fault="invalid_output_root"
            )
        run_dir = root / run_id
        try:
            resolved_root = root.resolve()
            if run_dir.resolve().parent != resolved_root:
                return self._result(
                    False, "failed", "run id is not a safe token", fault="invalid_run_id"
                )
        except OSError:
            return self._result(
                False, "failed", "output root is not a real directory", fault="invalid_output_root"
            )
        try:
            await asyncio.to_thread(self._writer.prepare_run, run_dir)
        except WriterFault as exc:
            return self._result(False, "failed", _detail(exc.code), fault=exc.code)
        except Exception:  # noqa: BLE001 — keep the failure visible without echoing the payload
            return self._result(False, "failed", "writer failed", fault="writer_error")
        self._run_dir = run_dir
        self._events = run_dir / "events.jsonl"
        self._summary = run_dir / "summary.json"
        stamped = _read_clock(self._clock)
        if stamped is None:
            return self._result(
                False, "failed", "clock could not stamp the event", fault="clock_error"
            )
        self._origin = stamped[1]
        self._commands = queue.Queue(maxsize=self._limits.max_queue + 2)
        self._thread = threading.Thread(
            target=self._loop, name=f"ground-journal-{run_id}", daemon=False
        )
        self._opened = True
        self._thread.start()
        return self._result(True, "queued", "run directory created", health="idle")

    def emit(self, record: Mapping[str, object]) -> JournalResult:
        if not self._opened or self._commands is None:
            return self._result(False, "failed", "journal is not open", fault="not_open")
        if self._closing or self._closed:
            return self._result(False, "failed", "journal is closed", fault="closed")
        safe, fault = self._sanitize(record)
        if safe is None:
            return self._result(False, "failed", _detail(fault or "invalid_record"), fault=fault)
        body, supplied, fault = self._prepare(safe)
        if body is None:
            return self._result(False, "failed", _detail(fault or "invalid_record"), fault=fault)
        decision = "invalid_record"
        seq: int | None = None
        with self._lock:
            if self._fault is not None:
                decision = self._fault
            elif self._waiting >= self._limits.max_queue:
                decision = "queue_full"
            else:
                next_seq = self._seq + 1
                if supplied is not None and supplied != next_seq:
                    decision = "sequence_conflict"
                else:
                    stamped = dict(body)
                    stamped["seq"] = next_seq
                    try:
                        encoded = json.dumps(
                            stamped, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                        )
                    except (TypeError, ValueError):
                        decision = "invalid_record"
                    else:
                        line = encoded + "\n"
                        if len(line.encode("utf-8")) > self._limits.max_event_bytes:
                            decision = "oversized"
                        else:
                            try:
                                self._commands.put_nowait(("event", line))
                            except queue.Full:
                                decision = "queue_full"
                            else:
                                self._seq = next_seq
                                self._waiting += 1
                                decision = "queued"
                                seq = next_seq
        if decision == "queued":
            return self._result(True, "queued", "event queued", seq=seq)
        return self._result(False, "failed", _detail(decision), fault=decision)

    async def flush(self) -> JournalResult:
        if not self._opened or self._commands is None:
            return self._result(False, "failed", "journal is not open", fault="not_open")
        if self._closed:
            return self._result(False, "failed", "journal is closed", fault="closed")
        done = threading.Event()
        try:
            self._commands.put_nowait(("barrier", done))
        except queue.Full:
            self._pending = True
            return self._result(False, "pending", "writer is still running", pending=True)
        finished = await asyncio.to_thread(done.wait, self._limits.flush_timeout_s)
        if not finished:
            self._pending = True
            return self._result(
                False, "pending", "flush timed out", fault="flush_timeout", pending=True
            )
        self._pending = False
        if self._fault is not None:
            return self._result(False, "failed", _detail(self._fault), fault=self._fault)
        durability = "synced" if self._waiting == 0 else "flushed"
        return self._result(True, durability, "flush finished")

    async def publish(self, summary: Mapping[str, object]) -> JournalResult:
        mission_error = _mission_error(summary)
        if not self._opened or self._commands is None or self._run_dir is None:
            return self._result(
                False,
                "failed",
                "journal is not open",
                fault="not_open",
                mission_error=mission_error,
            )
        if self._closed:
            return self._result(
                False, "failed", "journal is closed", fault="closed", mission_error=mission_error
            )
        payload, fault = _encode_summary(summary, self._limits.max_summary_bytes)
        if payload is None:
            return self._result(
                False,
                "failed",
                "summary was rejected",
                fault=fault or "invalid_summary",
                mission_error=mission_error,
                writer_error=fault,
            )
        done = threading.Event()
        box: dict[str, object] = {"fault": None, "prior_preserved": False}
        try:
            self._commands.put_nowait(("summary", (payload, done, box)))
        except queue.Full:
            self._pending = True
            return self._result(
                False,
                "pending",
                "writer is still running",
                pending=True,
                mission_error=mission_error,
            )
        finished = await asyncio.to_thread(done.wait, self._limits.flush_timeout_s)
        if not finished:
            self._pending = True
            return self._result(
                False,
                "pending",
                "flush timed out",
                fault="flush_timeout",
                pending=True,
                mission_error=mission_error,
            )
        fault_code = box["fault"] if type(box["fault"]) is str else None
        prior = box["prior_preserved"] is True
        if fault_code is not None:
            return self._result(
                False,
                "failed",
                _detail(fault_code),
                fault=fault_code,
                mission_error=mission_error,
                writer_error=fault_code,
                prior_preserved=prior,
            )
        self._published = True
        return self._result(
            True,
            "published",
            "summary replaced",
            mission_error=mission_error,
            prior_preserved=prior,
        )

    async def scan(self, output_root: Path) -> JournalResult:
        try:
            rows = await asyncio.to_thread(_scan_tree, Path(output_root))
        except Exception:  # noqa: BLE001 — keep the failure visible without echoing the payload
            return self._result(False, "failed", "scan failed", fault="writer_error")
        return self._result(True, "scanned", "scan finished", scan=tuple(rows))

    async def read(self, output_root: Path) -> JournalResult:
        return await self.scan(output_root)

    async def close(self) -> JournalResult:
        if not self._opened or self._thread is None or self._commands is None:
            self._closed = True
            return self._result(
                True, "closed", "journal was not open", saved=False, health="closed"
            )
        if self._closed and not self._thread.is_alive():
            return self._result(
                True,
                "closed",
                "journal closed",
                saved=self._saved,
                health="closed",
            )
        self._closing = True
        try:
            self._commands.put_nowait(("stop", None))
        except queue.Full:
            self._pending = True
        await asyncio.to_thread(self._thread.join, self._limits.close_timeout_s)
        if self._thread.is_alive():
            self._pending = True
            self._saved = False
            return self._result(
                False, "pending", "writer is still running", pending=True, saved=False
            )
        self._closed = True
        self._pending = False
        self._saved = self._fault is None and self._waiting == 0
        detail = "artifacts saved" if self._saved else "writer stopped with unsaved events"
        return self._result(True, "closed", detail, saved=self._saved, health="closed")

    def _sanitize(
        self, record: Mapping[str, object]
    ) -> tuple[Mapping[str, object] | None, str | None]:
        if not isinstance(record, Mapping) or isinstance(record, (str, bytes)):
            return None, "invalid_record"
        current: Mapping[str, object] = record
        if self._sanitizer is not None:
            try:
                current = self._sanitizer(record)
            except Exception:  # noqa: BLE001 — keep the failure visible without echoing the payload
                return None, "sanitizer_failed"
            if not isinstance(current, Mapping) or isinstance(current, (str, bytes)):
                return None, "invalid_record"
        return current, None

    def _prepare(
        self, record: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, int | None, str | None]:
        if any(type(key) is not str for key in record):
            return None, None, "invalid_record"
        raw = dict(record)
        if not set(raw).issubset(_EVENT_KEYS):
            return None, None, "invalid_record"
        mission = _text(raw.get("mission_id"), _MISSION)
        state = _text(raw.get("state"), _TOKEN)
        event = _text(raw.get("event"), _TOKEN)
        if mission is None or state is None or event is None:
            return None, None, "invalid_record"
        zone = raw.get("zone", None)
        target = raw.get("target", None)
        if zone is not None and (type(zone) is not str or zone not in _ZONES):
            return None, None, "invalid_record"
        if target is not None and (
            type(target) is not str or not target or len(target) > 80 or "\n" in target
        ):
            return None, None, "invalid_record"
        modes = _modes(raw.get("modes"))
        if modes is None or "data" not in raw or not _json_value(raw.get("data"), 0):
            return None, None, "invalid_record"
        if type(raw.get("data")) is not dict:
            return None, None, "invalid_record"
        stamped = _read_clock(self._clock)
        if stamped is None:
            return None, None, "clock_error"
        timestamp, monotonic = stamped
        elapsed = monotonic - self._origin
        if "timestamp_utc" in raw:
            supplied = raw["timestamp_utc"]
            if type(supplied) is not str or not _utc_text(supplied):
                return None, None, "invalid_record"
            timestamp = supplied
        if "elapsed_s" in raw:
            supplied_elapsed = raw["elapsed_s"]
            if not _number(supplied_elapsed) or _as_float(supplied_elapsed) < 0:
                return None, None, "invalid_record"
            elapsed = _as_float(supplied_elapsed)
        version = raw.get("contract_version", CONTRACT_VERSION)
        if version != CONTRACT_VERSION:
            return None, None, "invalid_record"
        body: dict[str, object] = {
            "timestamp_utc": timestamp,
            "elapsed_s": elapsed,
            "mission_id": mission,
            "contract_version": CONTRACT_VERSION,
            "state": state,
            "event": event,
            "zone": zone,
            "target": target,
            "modes": modes,
            "data": raw["data"],
        }
        for key in ("operation", "operation_id"):
            if key in raw:
                value = _text(raw[key], _OPERATION)
                if value is None:
                    return None, None, "invalid_record"
                body[key] = value
        if "ticket" in raw and not _ticket(raw["ticket"]):
            return None, None, "invalid_record"
        if "ticket" in raw:
            body["ticket"] = raw["ticket"]
        if "error" in raw:
            error = raw["error"]
            if error is not None and (type(error) is not str or len(error) > 200 or "\n" in error):
                return None, None, "invalid_record"
            body["error"] = error
        retained_seq: int | None = None
        if "seq" in raw:
            supplied_seq = raw["seq"]
            if type(supplied_seq) is not int or supplied_seq < 1:
                return None, None, "sequence_conflict"
            retained_seq = supplied_seq
        return body, retained_seq, None

    def _loop(self) -> None:
        commands = self._commands
        if commands is None:
            return
        try:
            while True:
                kind, payload = commands.get()
                if kind == "stop":
                    self._drain_retry()
                    return
                if kind == "event" and type(payload) is str:
                    self._drain_retry()
                    with self._lock:
                        blocked = bool(self._retry)
                    if blocked:
                        with self._lock:
                            self._retry.append(payload)
                    else:
                        self._write_line(payload)
                elif kind == "barrier" and isinstance(payload, threading.Event):
                    self._drain_retry()
                    payload.set()
                elif kind == "summary" and isinstance(payload, tuple):
                    self._write_summary(payload)
        except Exception:  # noqa: BLE001 — keep the failure visible without echoing the payload
            with self._lock:
                self._fault = "writer_error"
        finally:
            self._release_remaining(commands)

    def _drain_retry(self) -> None:
        while True:
            with self._lock:
                if not self._retry:
                    return
                line = self._retry.pop(0)
            if not self._write_line(line):
                return

    def _write_line(self, line: str) -> bool:
        path = self._events
        if path is None:
            with self._lock:
                self._fault = "writer_error"
                self._retry.insert(0, line)
            return False
        try:
            self._writer.append_lines(path, line)
        except WriterFault as exc:
            with self._lock:
                self._fault = exc.code
                if exc.wrote:
                    self._waiting = max(0, self._waiting - 1)
                    self._flushed += 1
                else:
                    self._retry.insert(0, line)
            return False
        except Exception:  # noqa: BLE001 — keep the failure visible without echoing the payload
            with self._lock:
                self._fault = "writer_error"
                self._retry.insert(0, line)
            return False
        with self._lock:
            self._waiting = max(0, self._waiting - 1)
            self._flushed += 1
            self._synced += 1
            self._fault = None
        return True

    def _write_summary(self, payload: tuple[object, ...]) -> None:
        if len(payload) != 3:
            return
        text, done, box = payload
        if not isinstance(done, threading.Event) or not isinstance(box, dict):
            return
        directory = self._run_dir
        prior = False
        try:
            if directory is None or type(text) is not str:
                raise WriterFault("writer_error", wrote=False)
            prior = (directory / "summary.json").is_file()
            self._writer.replace_summary(directory, text)
            box["fault"] = None
            box["prior_preserved"] = False
            with self._lock:
                self._published = True
        except WriterFault as exc:
            box["fault"] = exc.code
            box["prior_preserved"] = prior and not exc.wrote
            with self._lock:
                self._fault = exc.code
        except Exception:  # noqa: BLE001 — keep the failure visible without echoing the payload
            box["fault"] = "writer_error"
            box["prior_preserved"] = (directory / "summary.json").is_file() if directory else False
            with self._lock:
                self._fault = "writer_error"
        finally:
            done.set()

    def _release_remaining(self, commands: queue.Queue[tuple[str, object]]) -> None:
        while True:
            try:
                kind, payload = commands.get_nowait()
            except queue.Empty:
                return
            if kind == "barrier" and isinstance(payload, threading.Event):
                payload.set()
            elif kind == "summary" and isinstance(payload, tuple) and len(payload) == 3:
                done = payload[1]
                box = payload[2]
                if isinstance(box, dict) and box.get("fault") is None:
                    box["fault"] = self._fault or "writer_error"
                if isinstance(done, threading.Event):
                    done.set()

    def _result(
        self,
        ok: bool,
        durability: str,
        detail: str,
        *,
        fault: str | None = None,
        seq: int | None = None,
        pending: bool = False,
        saved: bool = False,
        mission_error: object = None,
        writer_error: str | None = None,
        prior_preserved: bool = False,
        health: str | None = None,
        scan: tuple[Mapping[str, object], ...] = (),
    ) -> JournalResult:
        with self._lock:
            queued = self._waiting
            flushed = self._flushed
            synced = self._synced
            published = self._published
            sticky = self._fault
        fault_code = fault if fault is not None else sticky
        if health is None:
            if self._closed:
                health = "closed"
            elif pending or (self._thread is not None and self._thread.is_alive() and pending):
                health = "pending"
            elif fault_code is not None and not ok:
                health = "failed"
            elif self._thread is not None and self._thread.is_alive() and durability == "pending":
                health = "writing"
            else:
                health = "idle"
        if pending:
            health = "pending"
        return JournalResult(
            ok=ok,
            durability=durability,
            queued=queued,
            flushed=flushed,
            synced=synced,
            published=published,
            pending=pending,
            saved=saved,
            seq=seq,
            run_dir=None if self._run_dir is None else str(self._run_dir),
            fault_code=fault_code,
            detail=detail,
            mission_error=mission_error,
            writer_error=writer_error,
            prior_preserved=prior_preserved,
            health=health,
            scan=scan,
        )


class JournalFeature:
    """Simulation entry. One case name runs the real journal and reports pass or fail."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        from patrol.ground.extensions.g04.scenarios import cases, execute

        seed = request.payload.get("seed", 0)
        if isinstance(seed, bool) or not isinstance(seed, int):
            seed = 0
        selected = [case for case in cases(seed) if case.case_id == request.name]
        if not selected:
            return _feature_failed("invalid_input", "unknown journal case")
        report = await execute(selected[0], seed=seed)
        return _feature_view(request.name, report.get("passed") is True, report)


def create(
    kernel: KernelContext | BaseServices,
    peers: object | None = None,
    *,
    writer: ArtifactWriter | None = None,
    sanitizer: EventSanitizer | None = None,
    limits: JournalLimits | None = None,
) -> Journal | JournalFeature:
    """Build a journal. No directory is created and no thread is started."""

    if isinstance(kernel, BaseServices):
        if peers is not None or writer is not None or sanitizer is not None or limits is not None:
            raise fault("invalid_input", "harness construction takes only services")
        return JournalFeature(kernel)
    if peers is None:
        raise fault("invalid_input", "journal peers are required")
    return Journal(kernel, peers, writer=writer, sanitizer=sanitizer, limits=limits)


def _feature_view(name: str, passed: bool, report: object) -> FeatureResult:
    detail = name
    if not passed and isinstance(report, dict):
        failures = report.get("failures")
        if isinstance(failures, list) and failures:
            detail = str(failures[0])
    data = freeze_map(
        {
            "simulated": True,
            "live_call_count": 0,
            "device_calls": 0,
            "authorized": False,
            "slot": "base.journal",
            "schema_version": SCHEMA_VERSION,
            "detail": name,
        }
    )
    if passed:
        return FeatureResult("ok", data, (), None)
    return FeatureResult("failed", data, (), GroundError("validation_failed", detail, False))


def _feature_failed(code: str, detail: str) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "simulated": True,
                "live_call_count": 0,
                "device_calls": 0,
                "authorized": False,
                "slot": "base.journal",
                "schema_version": SCHEMA_VERSION,
                "detail": detail,
            }
        ),
        (),
        GroundError(code, detail, False),
    )


def _safe_run_id(value: str) -> bool:
    if value in {".", ".."} or ".." in value:
        return False
    return _RUN_ID.fullmatch(value) is not None


def _text(value: object, pattern: re.Pattern[str]) -> str | None:
    if type(value) is not str or pattern.fullmatch(value) is None:
        return None
    return value


def _modes(value: object) -> dict[str, str] | None:
    if type(value) is not dict or set(value) != set(_MODES):
        return None
    parsed: dict[str, str] = {}
    for key in _MODES:
        item = value[key]
        if item not in {"fake", "real"}:
            return None
        parsed[key] = item
    return parsed


def _ticket(value: object) -> bool:
    if value is None:
        return True
    if type(value) is not dict or set(value) != {"mission_id", "epoch", "stage_id"}:
        return False
    return (
        _text(value["mission_id"], _MISSION) is not None
        and type(value["epoch"]) is int
        and _text(value["stage_id"], _TOKEN) is not None
    )


def _json_value(value: object, depth: int) -> bool:
    if value is None or type(value) is str or type(value) is bool:
        return True
    if type(value) is int:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if depth >= 6:
        return False
    if type(value) is list:
        return all(_json_value(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_value(item, depth + 1) for key, item in value.items())
    return False


def _number(value: object) -> bool:
    return type(value) in {int, float} and not isinstance(value, bool)


def _as_float(value: object) -> float:
    if type(value) is int:
        return float(value)
    if type(value) is float:
        return value
    return -1.0


def _utc_text(value: str) -> bool:
    if value.endswith("Z"):
        candidate = value[:-1] + "+00:00"
    else:
        candidate = value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == UTC.utcoffset(None)


def _read_clock(clock: object) -> tuple[str, float] | None:
    monotonic = getattr(clock, "monotonic", None)
    utc_now = getattr(clock, "utc_now", None)
    if not callable(monotonic) or not callable(utc_now):
        return None
    try:
        raw_mono = monotonic()
        raw_utc = utc_now()
    except Exception:  # noqa: BLE001 — a faulty clock must reject, not crash the journal
        return None
    if not _number(raw_mono) or not isinstance(raw_utc, datetime) or raw_utc.tzinfo is None:
        return None
    text = raw_utc.astimezone(UTC).isoformat()
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text, _as_float(raw_mono)


def _mission_error(summary: object) -> object:
    if isinstance(summary, Mapping) and "error" in summary:
        return summary["error"]
    return None


def _encode_summary(summary: object, limit: int) -> tuple[str | None, str | None]:
    if not isinstance(summary, Mapping) or isinstance(summary, (str, bytes)):
        return None, "invalid_summary"
    if any(type(key) is not str for key in summary):
        return None, "invalid_summary"
    body = dict(summary)
    if not _json_value(body, 0):
        return None, "invalid_summary"
    try:
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError):
        return None, "invalid_summary"
    payload = encoded + "\n"
    if len(payload.encode("utf-8")) > limit:
        return None, "oversized"
    return payload, None


def _detail(code: str) -> str:
    details = {
        "disk_full": "no space left on device",
        "permission": "permission denied",
        "closed_stream": "stream is closed",
        "sync": "fsync failed",
        "rename": "summary replace failed",
        "run_exists": "run directory already exists",
        "queue_full": "event queue is full",
        "oversized": "event exceeds the byte limit",
        "invalid_record": "event record was rejected",
        "sequence_conflict": "sequence does not match the next value",
        "sanitizer_failed": "sanitizer failed",
        "writer_error": "writer failed",
        "flush_timeout": "flush timed out",
        "clock_error": "clock could not stamp the event",
        "invalid_summary": "summary was rejected",
        "io_error": "writer failed",
        "already_open": "journal is already open",
        "not_open": "journal is not open",
        "closed": "journal is closed",
        "invalid_run_id": "run id is not a safe token",
        "invalid_output_root": "output root is not a real directory",
    }
    return details.get(code, "writer failed")


def _scan_tree(root: Path) -> list[dict[str, object]]:
    if root.is_symlink() or not root.is_dir():
        return [
            {
                "run_id": "",
                "complete_events": 0,
                "partial_tail": False,
                "diagnostics": ["output root is not a directory"],
                "summary_present": False,
                "summary_valid": False,
                "incomplete": True,
            }
        ]
    rows: list[dict[str, object]] = []
    children = sorted(root.iterdir(), key=lambda item: item.name)
    for child in children:
        if child.name in _LAYOUT:
            continue
        if child.is_symlink():
            rows.append(_scan_row(child.name, 0, False, ["symlink skipped"], False, False))
            continue
        if not child.is_dir():
            continue
        rows.append(_scan_run(child))
    return rows


def _scan_run(directory: Path) -> dict[str, object]:
    diagnostics: list[str] = []
    events = directory / "events.jsonl"
    summary = directory / "summary.json"
    count = 0
    partial = False
    if not events.is_file() or events.is_symlink():
        diagnostics.append("missing events")
    else:
        raw = events.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
            diagnostics.append("corrupt line")
        else:
            body, partial = _complete_prefix(text)
            if partial:
                diagnostics.append("truncated final line")
            for line in body.splitlines():
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    diagnostics.append("corrupt line")
                    continue
                if type(parsed) is not dict:
                    diagnostics.append("corrupt line")
                    continue
                count += 1
    summary_present = summary.is_file() and not summary.is_symlink()
    summary_valid = False
    if not summary_present:
        diagnostics.append("missing summary")
    else:
        try:
            parsed_summary = json.loads(summary.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            diagnostics.append("corrupt summary")
        else:
            if type(parsed_summary) is dict:
                summary_valid = True
            else:
                diagnostics.append("summary is not an object")
    return _scan_row(directory.name, count, partial, diagnostics, summary_present, summary_valid)


def _complete_prefix(text: str) -> tuple[str, bool]:
    if text == "" or text.endswith("\n"):
        return text, False
    body, separator, _tail = text.rpartition("\n")
    if separator:
        return body + "\n", True
    return "", True


def _scan_row(
    run_id: str,
    count: int,
    partial: bool,
    diagnostics: list[str],
    summary_present: bool,
    summary_valid: bool,
) -> dict[str, object]:
    incomplete = partial or not summary_valid or bool(diagnostics)
    if summary_valid and not partial and not diagnostics:
        incomplete = False
    return {
        "run_id": run_id,
        "complete_events": count,
        "partial_tail": partial,
        "diagnostics": list(diagnostics),
        "summary_present": summary_present,
        "summary_valid": summary_valid,
        "incomplete": incomplete,
    }
