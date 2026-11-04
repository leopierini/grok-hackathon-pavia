"""Scripted journal cases. The harness calls the real provider."""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g04.implementation import (
    EventSanitizer,
    Journal,
    JournalLimits,
    create,
)
from patrol.ground.extensions.g04.peers import ServicePorts
from patrol.ground.extensions.g04.writer import FaultWriter
from patrol.ground.kernel.build import build_kernel
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

NOW_MODES = {"dog": "fake", "drone": "fake", "grok": "fake"}
FORBIDDEN = (
    "connect",
    "prepare",
    "run_route",
    "capture_frame",
    "inspect",
    "land",
    "halt",
    "assess_incident",
    "latch_cancel",
)
_CASES = (
    "ordered_barrier_flush",
    "disk_full_before_open",
    "permission_on_append",
    "closed_stream_on_append",
    "rename_preserves_summary",
    "queue_full_halt_independent",
    "truncated_tail_and_missing_summary",
    "normal_shutdown",
    "stalled_writer_shutdown",
    "seeded_repeat",
    "sanitizer_hides_secret",
    "duplicate_run_rejected",
)


class _Check:
    def __init__(self) -> None:
        self.count = 0
        self.failures: list[str] = []

    def expect(self, condition: bool, detail: str) -> None:
        self.count += 1
        if not condition:
            self.failures.append(detail)


class _Probe:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> object:
        def record(*_args: object, **_kwargs: object) -> None:
            self.calls.append(name)

        return record


class _Authority:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.event = threading.Event()

    def latch_cancel(self, reason: str) -> None:
        self.calls.append(reason)
        self.event.set()


class _Idle:
    async def snapshot(self, path: Path) -> object:
        raise AssertionError(path)

    async def read(self, path: Path, *, max_bytes: int) -> bytes:
        raise AssertionError(max_bytes)

    async def decode_jpeg(self, data: bytes, *, max_pixels: int) -> tuple[int, int]:
        raise AssertionError(max_pixels)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    built: list[SimulationCase] = []
    for case_id in _CASES:
        built.append(
            SimulationCase(
                task_id="GROUND-04",
                case_id=case_id,
                seed=seed,
                setup=freeze_map({"storage": "temporary", "queue_policy": "reject-new"}),
                stimuli=(freeze_map({"case_id": case_id, "seed": seed}),),
                barriers=(),
                faults=(),
                expected=freeze_map(
                    {
                        "status": "ok",
                        "simulated": True,
                        "live_call_count": 0,
                        "device_calls": 0,
                        "authorized": False,
                        "slot": "base.journal",
                        "schema_version": SCHEMA_VERSION,
                        "detail": case_id,
                    }
                ),
                forbidden_calls=FORBIDDEN,
                teardown=("release_barriers", "collect_tasks", "remove_owned_temp"),
            )
        )
    return tuple(built)


async def execute(case: SimulationCase, *, seed: int) -> dict[str, object]:
    check = _Check()
    observed: dict[str, object] = {}
    latency: float | None = None
    peer_calls: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="g04-") as raw:
            observed, latency, peer_calls = await _run(case.case_id, Path(raw), seed, check)
    except Exception as exc:  # noqa: BLE001 — one case failure must not hide the rest of the report
        check.failures.append(f"exception {type(exc).__name__}")
        if "sk-live-secret" in str(exc):
            check.failures.append("secret leaked through an exception")
    return {
        "case_id": case.case_id,
        "passed": not check.failures,
        "assertions": check.count,
        "failures": list(check.failures),
        "observed": observed,
        "halt_latency_s": latency,
        "peer_calls": peer_calls,
        "forbidden_calls": list(case.forbidden_calls),
    }


async def _run(
    case_id: str, root: Path, seed: int, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    if case_id == "ordered_barrier_flush":
        return await _ordered(root, seed, check)
    if case_id == "disk_full_before_open":
        return await _open_fault(root, "disk_full", check)
    if case_id == "permission_on_append":
        return await _append_fault(root, "permission", "permission", check)
    if case_id == "closed_stream_on_append":
        return await _append_fault(root, "closed", "closed_stream", check)
    if case_id == "rename_preserves_summary":
        return await _rename(root, seed, check)
    if case_id == "queue_full_halt_independent":
        return await _halt(root, seed, check)
    if case_id == "truncated_tail_and_missing_summary":
        return await _truncated(root, check)
    if case_id == "normal_shutdown":
        return await _shutdown(root, seed, check, stall=False)
    if case_id == "stalled_writer_shutdown":
        return await _shutdown(root, seed, check, stall=True)
    if case_id == "seeded_repeat":
        return await _repeat(root, seed, check)
    if case_id == "sanitizer_hides_secret":
        return await _secret(root, check)
    if case_id == "duplicate_run_rejected":
        return await _duplicate(root, seed, check)
    check.expect(False, f"unknown case {case_id}")
    return {}, None, []


def _provider(
    *,
    writer: FaultWriter | None = None,
    sanitizer: EventSanitizer | None = None,
    limits: JournalLimits | None = None,
    authority: _Authority | None = None,
) -> tuple[Journal, _Probe, ServicePorts]:
    probe = _Probe()
    peers = ServicePorts(dog=probe, drone=probe, reasoner=probe, safety=probe, workflow=probe)
    clock = ManualClock()
    kernel = build_kernel(clock_mode="manual", seed=0, mode="simulation")
    kernel.clock = clock
    if authority is not None:
        kernel.authority = authority  # type: ignore[assignment]
    created = create(kernel, peers, writer=writer, sanitizer=sanitizer, limits=limits)
    assert isinstance(created, Journal)
    return created, probe, peers


def _record(seed: int, name: str, state: str = "IDLE") -> dict[str, object]:
    return {
        "mission_id": f"sim-{seed}",
        "state": state,
        "event": name,
        "zone": "room_2",
        "target": "person",
        "modes": dict(NOW_MODES),
        "data": {"seed": seed},
    }


def _summary(seed: int, *, error: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "contract_version": "1.0",
        "mission_id": f"sim-{seed}",
        "zone": "room_2",
        "modes": dict(NOW_MODES),
        "dispatch": "dispatch",
        "outcome": "alerted",
        "arrival_confirmed": False,
        "arrival_method": "simulated",
        "time_to_arrival_s": None,
        "inspection_requested": False,
        "launch_tier": "floor",
        "flight_state": "grounded",
        "recovery_required": False,
        "alert": "simulated",
    }
    if error is not None:
        body["error"] = error
    return body


def _observed(result: object, **extra: object) -> dict[str, object]:
    payload = result.as_dict() if hasattr(result, "as_dict") else {}
    assert isinstance(payload, dict)
    payload.update(extra)
    return payload


async def _ordered(
    root: Path, seed: int, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    gate = threading.Event()
    gate.set()
    writer = FaultWriter(gate=gate)
    journal, probe, _peers = _provider(writer=writer)
    flush_task: asyncio.Task[object] | None = None
    try:
        opened = await journal.open(f"sim-{seed}", root)
        gate.clear()
        check.expect(opened.ok is True, "open failed")
        check.expect(
            journal.emit(_record(seed, "incident_accepted")).ok is True, "first emit failed"
        )
        check.expect(
            journal.emit(_record(seed, "state_changed", "INSPECT")).ok is True, "second emit failed"
        )
        flush_task = asyncio.create_task(journal.flush())
        entered = await asyncio.to_thread(writer.entered.wait, 2)
        check.expect(entered is True, "writer did not reach the barrier")
        check.expect(flush_task.done() is False, "flush finished while the barrier was held")
        gate.set()
        flushed = await flush_task
        flush_task = None
        published = await journal.publish(_summary(seed))
        check.expect(getattr(flushed, "durability", None) == "synced", "flush was not synced")
        check.expect(getattr(published, "published", None) is True, "summary was not published")
        lines = _read_lines(root / f"sim-{seed}" / "events.jsonl")
        check.expect([item["seq"] for item in lines] == [1, 2], "sequence was not ordered")
        check.expect(
            [item["event"] for item in lines] == ["incident_accepted", "state_changed"],
            "event names diverged",
        )
        stored = json.loads((root / f"sim-{seed}" / "summary.json").read_text(encoding="utf-8"))
        check.expect(stored["time_to_arrival_s"] is None, "null arrival was rewritten")
        check.expect(probe.calls == [], "peer was called")
        return (
            _observed(published, queued=0, flushed=2, synced=2, published=True),
            None,
            probe.calls,
        )
    finally:
        gate.set()
        if flush_task is not None:
            await flush_task
        await journal.close()


async def _open_fault(
    root: Path, fail: str, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    writer = FaultWriter(fail=fail)
    journal, probe, _peers = _provider(writer=writer)
    try:
        opened = await journal.open("run-1", root)
        check.expect(opened.ok is False, "open succeeded")
        check.expect(opened.fault_code == fail, f"fault was {opened.fault_code}")
        check.expect(not (root / "run-1").exists(), "run directory was created")
        check.expect(probe.calls == [], "peer was called")
        return _observed(opened), None, probe.calls
    finally:
        await journal.close()


async def _append_fault(
    root: Path, fail: str, code: str, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    writer = FaultWriter()
    journal, probe, _peers = _provider(writer=writer)
    try:
        check.expect((await journal.open("run-1", root)).ok is True, "open failed")
        writer.fail = fail
        check.expect(journal.emit(_record(0, "incident_accepted")).ok is True, "emit failed")
        failed = await journal.flush()
        check.expect(failed.fault_code == code, f"fault was {failed.fault_code}")
        check.expect(failed.synced == 0, "sync was claimed")
        text = (root / "run-1" / "events.jsonl").read_text(encoding="utf-8")
        check.expect(text == "", "a failed append changed the log")
        check.expect(probe.calls == [], "peer was called")
        return _observed(failed), None, probe.calls
    finally:
        await journal.close()


async def _rename(
    root: Path, seed: int, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    writer = FaultWriter()
    journal, probe, _peers = _provider(writer=writer)
    try:
        check.expect((await journal.open("run-1", root)).ok is True, "open failed")
        first = await journal.publish(_summary(seed, error="route failed"))
        check.expect(first.ok is True, "first summary failed")
        before = (root / "run-1" / "summary.json").read_bytes()
        writer.fail = "rename"
        second = await journal.publish(_summary(seed, error="cleanup failed"))
        check.expect(second.ok is False, "replace reported success")
        check.expect(second.prior_preserved is True, "prior summary was not preserved")
        check.expect(second.mission_error == "cleanup failed", "mission error was dropped")
        check.expect(second.writer_error == "rename", "writer error was dropped")
        check.expect(
            (root / "run-1" / "summary.json").read_bytes() == before, "summary bytes changed"
        )
        check.expect(probe.calls == [], "peer was called")
        return _observed(second), None, probe.calls
    finally:
        await journal.close()


async def _halt(
    root: Path, seed: int, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    gate = threading.Event()
    gate.set()
    writer = FaultWriter(gate=gate)
    authority = _Authority()
    journal, probe, _peers = _provider(
        writer=writer,
        limits=JournalLimits(max_queue=2, flush_timeout_s=5, close_timeout_s=0.2),
        authority=authority,
    )
    flush_task: asyncio.Task[object] | None = None
    try:
        check.expect((await journal.open("run-1", root)).ok is True, "open failed")
        gate.clear()
        check.expect(
            journal.emit(_record(seed, "incident_accepted")).ok is True, "first emit failed"
        )
        check.expect(
            journal.emit(_record(seed, "state_changed", "ROUTE")).ok is True, "second emit failed"
        )
        full = journal.emit(_record(seed, "halt_requested", "HALT"))
        check.expect(full.fault_code == "queue_full", "queue did not reject the new event")
        flush_task = asyncio.create_task(journal.flush())
        check.expect(
            await asyncio.to_thread(writer.entered.wait, 2) is True, "writer did not block"
        )
        started = time.perf_counter()
        authority.latch_cancel("operator_halt")
        latency = time.perf_counter() - started
        emit_started = time.perf_counter()
        while_blocked = journal.emit(_record(seed, "mission_finished", "HALT"))
        emit_latency = time.perf_counter() - emit_started
        check.expect(authority.event.is_set(), "latch was not set")
        check.expect(authority.calls == ["operator_halt"], "journal called the latch")
        check.expect(latency < 0.5, f"latch waited {latency}")
        check.expect(emit_latency < 0.5, f"emit waited {emit_latency}")
        check.expect(while_blocked.fault_code == "queue_full", "blocked emit did not return")
        check.expect(flush_task.done() is False, "flush finished during the stall")
        check.expect(probe.calls == [], "peer was called")
        return (
            _observed(while_blocked, queue_policy="reject-new"),
            max(latency, emit_latency),
            probe.calls,
        )
    finally:
        gate.set()
        if flush_task is not None:
            await flush_task
        await journal.close()


async def _truncated(
    root: Path, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    run = root / "interrupted"
    run.mkdir()
    (run / "events.jsonl").write_bytes(
        b'{"seq":1,"event":"incident_accepted"}\n{"seq":2,"event":"state_chan'
    )
    journal, probe, _peers = _provider()
    try:
        found = await journal.scan(root)
        check.expect(found.ok is True, "scan failed")
        check.expect(len(found.scan) == 1, "scan did not see the interrupted run")
        row = found.scan[0]
        check.expect(row["partial_tail"] is True, "partial tail was treated as complete")
        check.expect(row["complete_events"] == 1, "partial line was counted")
        check.expect(row["summary_present"] is False, "missing summary looked present")
        check.expect(row["incomplete"] is True, "interrupted run looked complete")
        check.expect(probe.calls == [], "scan called a device")
        return _observed(found), None, probe.calls
    finally:
        await journal.close()


async def _shutdown(
    root: Path, seed: int, check: _Check, *, stall: bool
) -> tuple[dict[str, object], float | None, list[str]]:
    gate = threading.Event()
    gate.set()
    writer = FaultWriter(gate=gate)
    journal, probe, _peers = _provider(
        writer=writer,
        limits=JournalLimits(flush_timeout_s=5, close_timeout_s=0.2),
    )
    flush_task: asyncio.Task[object] | None = None
    try:
        check.expect((await journal.open("run-1", root)).ok is True, "open failed")
        if stall:
            gate.clear()
        check.expect(journal.emit(_record(seed, "incident_accepted")).ok is True, "emit failed")
        if stall:
            flush_task = asyncio.create_task(journal.flush())
            check.expect(
                await asyncio.to_thread(writer.entered.wait, 2) is True, "writer did not block"
            )
            pending = await journal.close()
            check.expect(pending.pending is True, "stalled close was not pending")
            check.expect(pending.saved is False, "stalled close claimed the artifacts were saved")
            gate.set()
            await flush_task
            flush_task = None
            closed = await journal.close()
            check.expect(closed.saved is True, "writer did not finish after release")
            check.expect(closed.pending is False, "finished writer stayed pending")
            check.expect(probe.calls == [], "peer was called")
            return _observed(pending, final_saved=closed.saved), None, probe.calls
        flushed = await journal.flush()
        published = await journal.publish(_summary(seed))
        closed = await journal.close()
        check.expect(getattr(flushed, "durability", None) == "synced", "flush was not synced")
        check.expect(published.published is True, "summary was not published")
        check.expect(closed.saved is True, "normal close did not save")
        check.expect(closed.pending is False, "normal close stayed pending")
        check.expect(probe.calls == [], "peer was called")
        return _observed(closed), None, probe.calls
    finally:
        gate.set()
        if flush_task is not None:
            await flush_task
        await journal.close()


async def _repeat(
    root: Path, seed: int, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    first = await _script(root / "a", seed)
    second = await _script(root / "b", seed)
    check.expect(first == second, "seeded artifacts diverged")
    check.expect(first is not None and b'"seq":1' in first[0], "first event missing")
    return (
        {"equal": first == second, "queued": 2, "flushed": 2, "synced": 2, "published": True},
        None,
        [],
    )


async def _script(root: Path, seed: int) -> tuple[bytes, bytes] | None:
    root.mkdir()
    journal, _probe, _peers = _provider()
    try:
        if not (await journal.open("run-1", root)).ok:
            return None
        journal.emit(_record(seed, "incident_accepted"))
        journal.emit(_record(seed, "state_changed", "INSPECT"))
        await journal.flush()
        await journal.publish(_summary(seed))
        events = (root / "run-1" / "events.jsonl").read_bytes()
        summary = (root / "run-1" / "summary.json").read_bytes()
        return events, summary
    finally:
        await journal.close()


async def _secret(root: Path, check: _Check) -> tuple[dict[str, object], float | None, list[str]]:
    secret = "sk-live-secret"

    def explode(record: Mapping[str, object]) -> Mapping[str, object]:
        del record
        raise RuntimeError(secret)

    journal, probe, _peers = _provider(sanitizer=explode)
    try:
        check.expect((await journal.open("run-1", root)).ok is True, "open failed")
        body = _record(0, "incident_accepted")
        body["data"] = {"api_key": secret}
        failed = journal.emit(body)
        rendered = str(failed.as_dict())
        check.expect(failed.fault_code == "sanitizer_failed", "sanitizer failure was hidden")
        check.expect(secret not in rendered, "secret leaked into the result")
        check.expect(secret not in failed.detail, "secret leaked into the detail")
        check.expect(probe.calls == [], "peer was called")
        return _observed(failed), None, probe.calls
    finally:
        await journal.close()


async def _duplicate(
    root: Path, seed: int, check: _Check
) -> tuple[dict[str, object], float | None, list[str]]:
    first, probe, _peers = _provider()
    second, _probe, _peers = _provider()
    try:
        check.expect((await first.open("run-1", root)).ok is True, "open failed")
        check.expect(first.emit(_record(seed, "incident_accepted")).ok is True, "emit failed")
        await first.flush()
        before = (root / "run-1" / "events.jsonl").read_bytes()
        again = await second.open("run-1", root)
        check.expect(again.fault_code == "run_exists", "second run reused the directory")
        check.expect((root / "run-1" / "events.jsonl").read_bytes() == before, "first log changed")
        check.expect(probe.calls == [], "peer was called")
        return _observed(again), None, probe.calls
    finally:
        await first.close()
        await second.close()


def _read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
