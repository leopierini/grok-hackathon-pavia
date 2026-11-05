"""One local operator session. It does not start a worker per request."""

from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from patrol.ground.demo import MISSION
from patrol.ground.dog_limits import clamp_limits, default_limits, direction_steps
from patrol.ground.dog_link import EthernetDogLink
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.operator.artifacts import ArtifactError
from patrol.ground.operator.config import ConfigError, default_config, validate_config
from patrol.ground.operator.describe import journal_row, phase_row
from patrol.ground.operator.mission import OPERATOR_SCENARIOS, SCENARIO_TEXT, execute_simulation
from patrol.ground.operator.policy import LIVE_BLOCKERS, Gate, action_map, next_instruction
from patrol.ground.operator.public_patrol import PatrolBoard, PatrolRejected
from patrol.ground.operator.snapshot import build_snapshot
from patrol.ground.radio import ethernet_now, probe_dog_ethernet

Json = dict[str, Any]
_RUN = re.compile(r"run-[a-f0-9]{12}")


class Host:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.config = default_config()
        self.mode = "simulation"
        self.session_epoch = 1
        self.armed = False
        self.supervised = False
        self.halt_latched = False
        self.halt_accepted = False
        self.halt_delivered: bool | None = None
        self.closed = False
        self.recovery_required = False
        self.goal_reached = False
        self.landing_verified = False
        self.phase = "IDLE"
        self.reason = ""
        self.outcome: str | None = None
        self.worker: asyncio.Task[None] | None = None
        self.demo: Any = None
        self.services: Any = None
        self.controls: Any = None
        self.run_id: str | None = None
        self.scenario: str | None = None
        self.seed: int | None = None
        self.messages: list[Json] = []
        self.trace: list[Json] = []
        self.commands: list[Json] = []
        self.phase_history: list[Json] = []
        self.notes: list[Json] = []
        self.activity: list[Json] = []
        self.provider_journal: list[Json] = []
        self.metrics: Json | None = None
        self.writer_state = "idle"
        self.step_control: Json | None = None
        self.foundation_phase: str | None = None
        self.mission_epoch: int | None = None
        self.live_call_count = 0
        self.cursor = 0
        self.events: deque[Json] = deque(maxlen=2000)
        self.subscribers: list[asyncio.Queue[Json]] = []
        self.idempotency: dict[str, Json] = {}
        self.runs: list[Json] = []
        self.connection = "connected"
        self.dog_link: EthernetDogLink | None = None
        self.dog_motion: Json | None = None
        self.dog_target = "fake"
        self.dog_limits = default_limits()
        self.dog_view = False
        self.dog_view_ready = False
        self.dog_view_owns = False
        self.dog_view_stop = False
        self.dog_view_detail = "Camera and LiDAR are closed."
        self.view_task: asyncio.Task[None] | None = None
        self.patrol = PatrolBoard()
        self.providers, self.missing = _inventory()
        self.snapshot: Json = {}
        self._lock = asyncio.Lock()
        self._probe_task: asyncio.Task[dict[str, Any]] | None = None
        self._scan_runs()
        self._refresh()

    async def act(self, name: str, body: Mapping[str, Any], key: str | None) -> Json:
        async with self._lock:
            if key and key in self.idempotency:
                return self.idempotency[key]
            if name not in {
                "status",
                "arm",
                "start",
                "supervised",
                "halt",
                "reset",
                "quit",
                "probe",
                "dog_test",
                "dog_view",
                "start_patrol",
                "stop_patrol",
            }:
                return _error(404, "unknown_action", "unknown operator action")
            probe_first = _wants_ethernet_probe(name, body)
            epoch = self.session_epoch
        route: dict[str, Any] | None = None
        if probe_first:
            route = await self._coalesced_probe()
        async with self._lock:
            if key and key in self.idempotency:
                return self.idempotency[key]
            if probe_first and (
                self.closed or self.halt_latched or self.session_epoch != epoch
            ):
                return _error(
                    409,
                    "rejected",
                    "probe result was dropped because the session changed",
                )
            if name == "probe":
                result = self._probe(route)
                self._remember(key, result)
                return result
            if name not in {"halt", "status", "quit"}:
                sent = body.get("session_epoch")
                if isinstance(sent, bool) or not isinstance(sent, int) or sent != self.session_epoch:
                    return _error(409, "stale_epoch", "session epoch is stale; read the session again")
            if name == "dog_test":
                result = self._begin_dog_test(body, route)
                self._remember(key, result)
                return result
            if name == "dog_view":
                result = self._begin_dog_view(body, route)
                self._remember(key, result)
                return result
            if name in {"start_patrol", "stop_patrol"}:
                result = self._patrol(name)
                self._remember(key, result)
                return result
            decision = action_map(self._gate())[name]
            if name != "status" and decision["enabled"] is not True:
                return _error(409, "rejected", str(decision["reason"]))
            result = await self._apply(name, body, route)
            self._remember(key, result)
            return result

    async def update_config(self, raw: object) -> Json:
        async with self._lock:
            if self._worker_state() == "running":
                return _error(409, "rejected", "configuration applies to an idle or new session")
            try:
                self.config = validate_config(raw)
            except ConfigError as exc:
                return _error(422, exc.code, exc.detail)
            self._refresh()
            return _ok(200, "Configuration accepted for the next idle session.", self.snapshot)

    async def set_mode(self, mode: str) -> Json:
        async with self._lock:
            if mode not in {"simulation", "live"}:
                return _error(422, "invalid_input", "mode must be simulation or live")
            if self._worker_state() == "running":
                return _error(409, "rejected", "mode cannot change while a mission worker is running")
            self.mode = mode
            if mode == "live":
                self.armed = False
            self._refresh()
            return _ok(200, f"Transport is {mode}.", self.snapshot)

    async def open_replay(self, run_id: str) -> Json:
        async with self._lock:
            if self._worker_state() == "running":
                return _error(409, "rejected", "replay waits until the mission worker finishes")
            try:
                report = json.loads(self._report_path(run_id).read_text(encoding="utf-8"))
            except (ArtifactError, OSError, ValueError, json.JSONDecodeError):
                return _error(404, "not_found", "run report was not found")
            if not isinstance(report, dict):
                return _error(422, "invalid_input", "run report is not an object")
            self.mode = "replay"
            self._view_from_report(report)
            self._refresh()
            return _ok(200, "Replay loaded. It cannot command devices.", self.snapshot)

    async def step_command(self, body: Mapping[str, Any]) -> Json:
        async with self._lock:
            action = body.get("action")
            if action != "halt":
                sent = body.get("session_epoch")
                if isinstance(sent, bool) or not isinstance(sent, int) or sent != self.session_epoch:
                    return _error(409, "stale_epoch", "session epoch is stale; read the session again")
            if self.controls is None:
                return _error(409, "rejected", "no step session is active")
            payload = {key: value for key, value in body.items() if key != "session_epoch"}
            result = await self.controls.command(payload)
            if isinstance(result, dict) and isinstance(result.get("snapshot"), dict):
                self.step_control = result["snapshot"]
            self._refresh()
            ok = isinstance(result, dict) and result.get("ok") is True
            detail = "Step command accepted." if ok else "Step command was rejected."
            if isinstance(result, dict) and isinstance(result.get("error"), dict):
                detail = str(result["error"].get("detail") or detail)
            return {
                "ok": ok,
                "status": 200 if ok else 409,
                "detail": detail,
                "step": result,
                "snapshot": self.snapshot,
            }

    def journal(self, *, cursor: int, limit: int, filters: Mapping[str, str]) -> Json:
        rows = [row for row in self.activity if row.get("cursor", 0) > cursor and _match(row, filters)]
        page = rows[:limit]
        return {
            "cursor": cursor,
            "next_cursor": page[-1]["cursor"] if page else cursor,
            "count": len(self.activity),
            "rows": page,
        }

    def since(self, cursor: int) -> tuple[str, list[Json]]:
        if not self.events:
            return "ok", []
        oldest = int(self.events[0]["cursor"])
        if cursor != 0 and cursor < oldest - 1:
            return "gap", []
        return "ok", [item for item in self.events if int(item["cursor"]) > cursor]

    def subscribe(self) -> asyncio.Queue[Json]:
        queue: asyncio.Queue[Json] = asyncio.Queue(maxsize=100)
        self.subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Json]) -> None:
        if queue in self.subscribers:
            self.subscribers.remove(queue)

    def _remember(self, key: str | None, result: Json) -> None:
        if not key:
            return
        self.idempotency[key] = result
        while len(self.idempotency) > 64:
            self.idempotency.pop(next(iter(self.idempotency)))

    async def _release_link(self, link: EthernetDogLink) -> None:
        try:
            await link.halt()
        except Exception:
            pass
        try:
            await link.close()
        except Exception:
            pass
        if self.dog_link is link:
            self.dog_link = None
            self.dog_view = False
            self.dog_view_ready = False
            self.dog_view_owns = False

    async def _coalesced_probe(self) -> dict[str, Any]:
        task = self._probe_task
        if task is None or task.done():
            task = asyncio.create_task(asyncio.to_thread(probe_dog_ethernet))
            self._probe_task = task
        try:
            return await task
        finally:
            if self._probe_task is task and task.done():
                self._probe_task = None

    async def _apply(self, name: str, body: Mapping[str, Any], route: dict[str, Any] | None = None) -> Json:
        if name == "status":
            self._refresh()
            return _ok(200, "Status is a read of the current session.", self.snapshot)
        if name == "arm":
            self.armed = True
            self._refresh()
            return _ok(200, "Session armed. Nothing moved.", self.snapshot)
        if name == "supervised":
            self.supervised = True
            self._refresh()
            return _ok(200, "Supervised search is selected. It does not enable motion.", self.snapshot)
        if name == "start":
            return self._start(body, route)
        if name == "halt":
            return self._halt()
        if name == "reset":
            return self._reset(body)
        self._halt()
        self.dog_view_stop = True
        link = self.dog_link
        if link is not None:
            asyncio.create_task(self._release_link(link))
        self.closed = True
        self._refresh()
        return _ok(200, "Quit latched halt and closed the operator session.", self.snapshot)

    def _start(self, body: Mapping[str, Any], route: dict[str, Any] | None = None) -> Json:
        scenario = body.get("scenario") or "happy_path"
        if scenario not in OPERATOR_SCENARIOS:
            return _error(422, "invalid_input", "unknown scenario")
        seed = body.get("seed", 0)
        if isinstance(seed, bool) or not isinstance(seed, int):
            return _error(422, "invalid_input", "seed must be an integer")
        pace = body.get("pace_s", self.config.get("pace_s", 0))
        if isinstance(pace, bool) or not isinstance(pace, (int, float)) or not 0 <= float(pace) <= 1:
            return _error(422, "invalid_input", "pace_s must be from 0 to 1")
        if body.get("supervised") is True:
            self.supervised = True
        dog = body.get("dog") or "fake"
        if "limits" in body:
            self.dog_limits = clamp_limits(body.get("limits"))
        if dog not in {"fake", "ethernet", "sim"}:
            return _error(422, "invalid_input", "dog must be fake, ethernet, or sim")
        if dog == "ethernet":
            if route is None:
                route = probe_dog_ethernet()
            self.dog_motion = {"probe": route, "sent": False}
            if route.get("reachable") is not True:
                return self._fail(
                    409,
                    "dog_unreachable",
                    "The dog Ethernet port 8081 did not answer. "
                    "Set this laptop's adapter to 192.168.123.222/24 and plug in the dog cable. "
                    "No WebRTC session was opened.",
                )
            if route.get("laptop_on_dog_subnet") is not True:
                return self._fail(
                    409,
                    "dog_unreachable",
                    "The dog answered on an address outside 192.168.123.222/24. "
                    "No WebRTC session was opened.",
                )
        self.dog_target = str(dog)
        self.run_id = f"run-{uuid4().hex[:12]}"
        self.scenario = str(scenario)
        self.seed = seed
        self.mode = "simulation"
        self.outcome = None
        self.reason = ""
        self.messages = []
        self.trace = []
        self.commands = []
        self.activity = []
        self.phase_history = []
        self.provider_journal = []
        self.metrics = None
        self.writer_state = "queued"
        self.phase = "IDLE"
        run_id = self.run_id
        self.worker = asyncio.create_task(self._worker(run_id, str(scenario), seed, float(pace)))
        self._refresh()
        if dog == "fake":
            detail = "Mission worker started. The dog and the drone stay simulated."
        elif dog == "sim":
            detail = "Mission worker started against the simulated dog body. The drone stays a script."
        else:
            detail = "Mission worker started. The approved dog step goes out on Ethernet. The drone stays a script."
        return _ok(202, detail, self.snapshot)

    def _halt(self) -> Json:
        self.halt_latched = True
        self.halt_accepted = True
        self.halt_delivered = None
        self.armed = False
        self.recovery_required = True
        self.session_epoch += 1
        if self.services is not None and self.demo is not None:
            try:
                self.services.safety.request("operator_halt", self.demo.ticket)
                self.halt_delivered = False
            except GroundFault as exc:
                self.reason = exc.error.detail
        if self.controls is not None:
            self.controls.notify_halt("operator_halt")
        link = self.dog_link
        if link is not None:
            asyncio.get_running_loop().create_task(self._halt_dog(link))
        self._refresh()
        self._broadcast("halt", "Halt accepted. Device delivery is not verified.")
        return _ok(202, "Halt accepted. Device delivery is not verified.", self.snapshot)

    def _reset(self, body: Mapping[str, Any]) -> Json:
        clean = self.goal_reached and self.landing_verified and not self.recovery_required
        token = body.get("recovery_token")
        if not clean and (not isinstance(token, str) or len(token.strip()) < 8):
            return _error(409, "recovery_required", "reset requires a recovery token while a fault is unresolved")
        self.session_epoch += 1
        self.idempotency.clear()
        self.armed = False
        self.supervised = False
        self.halt_latched = False
        self.halt_accepted = False
        self.halt_delivered = None
        self.recovery_required = False
        self.goal_reached = False
        self.landing_verified = False
        self.phase = "IDLE"
        self.reason = ""
        self.outcome = None
        self.run_id = None
        self.scenario = None
        self.messages = []
        self.trace = []
        self.commands = []
        self.activity = []
        self.phase_history = []
        self.notes = []
        self.provider_journal = []
        self.metrics = None
        self.step_control = None
        self.writer_state = "idle"
        self.mission_epoch = None
        self.patrol = PatrolBoard()
        if self.mode == "replay":
            self.mode = "simulation"
        self._refresh()
        return _ok(200, "Session reset and disarmed. The previous run record was kept.", self.snapshot)

    async def _worker(self, run_id: str, scenario: str, seed: int, pace: float) -> None:
        output = self.runs_root / run_id
        report: Json | None = None
        link: EthernetDogLink | None = None
        radio = None
        if getattr(self, "dog_target", "fake") in {"ethernet", "sim"}:
            link = EthernetDogLink(
                output / "dog",
                armed=True,
                fake=self.dog_target == "sim",
                limits=self.dog_limits,
            )
            radio = ethernet_now()
            self.dog_link = link
        try:
            report = await execute_simulation(
                output,
                scenario=scenario,
                seed=seed,
                transport=str(self.config.get("dog_transport") or "ethernet"),
                pace_s=pace,
                supervised=self.supervised,
                run_id=run_id,
                should_halt=lambda: self.halt_latched,
                on_event=self._on_event,
                on_ready=self._ready,
                dog_link=link,
                radio=radio,
            )
        except Exception:
            self.reason = self.reason or "mission worker failed"
            self.phase = "FAULT"
            self.recovery_required = True
        if report is not None:
            self._view_from_report(report)
            self.runs.append(_summary(report))
        self.demo = None
        self.services = None
        self.controls = None
        self.dog_link = None
        self.dog_target = "fake"
        self.armed = False
        self._refresh()
        self._broadcast("mission", "Mission worker finished")

    def _ready(self, demo: Any, services: Any, controls: Any) -> None:
        self.demo = demo
        self.services = services
        self.controls = controls
        self.mission_epoch = demo.ticket.epoch

    def _on_event(self, kind: str, payload: Json) -> None:
        demo = self.demo
        if demo is None:
            return
        self.messages = list(demo.messages)
        self.trace = list(demo.trace)
        self.commands = list(demo.commands)
        self.phase = str(demo.phase)
        self.phase_history = list(demo.phase_history)
        self.notes = list(demo.operator_notes)
        self.goal_reached = bool(demo.goal_reached)
        self.landing_verified = bool(demo.landing_verified)
        self.recovery_required = bool(demo.recovery_required) or self.halt_latched
        if demo.reason:
            self.reason = str(demo.reason)
        if isinstance(demo.dog_motion_log, dict):
            self.dog_motion = demo.dog_motion_log
        self.mission_epoch = demo.ticket.epoch
        if self.controls is not None:
            try:
                snapshot = self.controls.get_snapshot()
                if isinstance(snapshot, dict):
                    self.step_control = snapshot
            except Exception:
                self.step_control = self.step_control
        feature = demo.providers.get(29)
        if feature is not None:
            records = getattr(feature, "records", [])
            self.provider_journal = [dict(item) for item in records if isinstance(item, dict)]
            self.writer_state = _writer(self.provider_journal)
        if self.services is not None:
            try:
                self.foundation_phase = str(self.services.state.snapshot().phase)
            except Exception:
                self.foundation_phase = self.foundation_phase
        self._append_activity(kind, payload)
        self._refresh()
        self._broadcast(kind, _summary_text(kind, payload))

    def _append_activity(self, kind: str, payload: Json) -> None:
        row: Json | None = None
        if kind == "message" and self.messages:
            row = journal_row(self.messages[-1])
            if any(item.get("message_id") == row.get("message_id") for item in self.activity):
                row = None
        elif kind == "phase":
            row = phase_row(payload)
        elif kind in {"vision_wait", "late_model", "halt", "provider"}:
            row = {
                "kind": kind,
                "source": "ground",
                "category": "safety" if kind in {"halt", "late_model"} else "session",
                "severity": "warn" if kind in {"halt", "late_model"} else "info",
                "summary": _summary_text(kind, payload),
                "writer_state": "enqueued",
                "published": False,
                "ledger": "operator_feed",
                "payload": payload,
            }
        if row is None:
            return
        self.cursor += 1
        row["cursor"] = self.cursor
        self.activity.append(row)
        if len(self.activity) > 5000:
            del self.activity[: len(self.activity) - 5000]

    def _refresh(self) -> None:
        gate = self._gate()
        observed = None
        if self.demo is not None:
            observed = self.demo.now
        self.snapshot = build_snapshot(
            {
                "mode": self.mode,
                "connection": self.connection,
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "cursor": self.cursor,
                "session_epoch": self.session_epoch,
                "phase": self.phase,
                "phase_history": self.phase_history,
                "foundation_phase": self.foundation_phase,
                "armed": self.armed,
                "worker": gate.worker,
                "scenario": self.scenario,
                "seed": self.seed,
                "goal_reached": self.goal_reached,
                "landing_verified": self.landing_verified,
                "recovery_required": self.recovery_required,
                "outcome": self.outcome,
                "reason": self.reason,
                "halt_latched": self.halt_latched,
                "halt_accepted": self.halt_accepted,
                "halt_delivered": self.halt_delivered,
                "supervised": self.supervised,
                "waiting_for_model": bool(self.demo and self.demo.waiting_for_model),
                "run_id": self.run_id,
                "mission_id": None if self.run_id is None and self.mode != "replay" else MISSION,
                "mission_epoch": self.mission_epoch,
                "live_call_count": self.live_call_count,
                "observed_at": observed,
                "messages": self.messages,
                "trace": self.trace,
                "commands": self.commands,
                "notes": self.notes,
                "config": self.config,
                "providers": self.providers,
                "missing_providers": self.missing,
                "writer_state": self.writer_state,
                "provider_journal": self.provider_journal[-40:],
                "metrics": self.metrics,
                "step_control": self.step_control,
                "activity": self.activity[-40:],
                "journal_count": len(self.activity),
                "actions": action_map(gate),
                "next_action": next_instruction(gate),
                "live_blockers": list(LIVE_BLOCKERS) if gate.mode == "live" or gate.real_modes else [],
                "scenarios": [{"id": key, "detail": SCENARIO_TEXT[key]} for key in OPERATOR_SCENARIOS],
                "real_modes": gate.real_modes,
                "dog_demo": self._dog_demo(),
                "patrol": self.patrol.view(),
                "active_operation": None
                if not isinstance(self.step_control, dict)
                else self.step_control.get("active_step_id"),
            }
        )

    def _broadcast(self, kind: str, summary: str) -> None:
        event = {"cursor": self.cursor, "kind": kind, "summary": summary, "snapshot": self.snapshot}
        self.events.append({"cursor": self.cursor, "kind": kind, "summary": summary})
        for queue in tuple(self.subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _gate(self) -> Gate:
        modes = self.config.get("modes")
        real = isinstance(modes, dict) and any(value == "real" for value in modes.values())
        return Gate(
            mode=self.mode,
            phase=self.phase,
            armed=self.armed,
            worker=self._worker_state(),
            closed=self.closed,
            halt_latched=self.halt_latched,
            recovery_required=self.recovery_required,
            goal_reached=self.goal_reached,
            landing_verified=self.landing_verified,
            controlled_motion=self._motion(),
            real_modes=real,
            config_ok=True,
        )

    def _begin_dog_test(self, body: Mapping[str, Any], route: dict[str, Any] | None = None) -> Json:
        if self.closed:
            return _error(409, "rejected", "The operator session is closed.")
        if self.mode == "replay":
            return _error(409, "rejected", "Replay cannot move the dog.")
        if not self.armed:
            return _error(409, "rejected", "Arm this session before the direction test. Arm does not move the dog.")
        if self.halt_latched or self.recovery_required:
            return _error(409, "rejected", "Reset the latched session before testing the dog.")
        if self._worker_state() == "running" or self.dog_link is not None:
            if self.dog_view_owns:
                return _error(
                    409,
                    "rejected",
                    "Close the camera and LiDAR view first. The dog allows one connection.",
                )
            return _error(409, "rejected", "A dog session is already running.")
        dog = body.get("dog") or "ethernet"
        if dog not in {"ethernet", "sim"}:
            return _error(422, "invalid_input", "dog test must use ethernet or sim")
        self.dog_limits = clamp_limits(body.get("limits"))
        if dog == "ethernet":
            if route is None:
                route = probe_dog_ethernet()
            self.dog_motion = {"probe": route, "sent": False, "steps": []}
            if route.get("reachable") is not True or route.get("laptop_on_dog_subnet") is not True:
                return self._fail(
                    409,
                    "dog_unreachable",
                    "The dog Ethernet cable is not ready. No step was sent.",
                )
        run_id = f"run-{uuid4().hex[:12]}"
        self.run_id = run_id
        self.scenario = "dog_test"
        self.dog_target = str(dog)
        link = EthernetDogLink(
            self.runs_root / run_id / "dog",
            armed=True,
            fake=dog == "sim",
            limits=self.dog_limits,
        )
        self.dog_link = link
        self.dog_motion = {
            "sent": False,
            "detail": "Direction test is starting. Each step stops before the next one.",
            "steps": [],
        }
        self.worker = asyncio.create_task(self._direction_test(link))
        self._refresh()
        return _ok(
            202,
            "Direction test started: forward, back, right, then left.",
            self.snapshot,
        )

    def _patrol(self, name: str) -> Json:
        try:
            detail = self.patrol.start() if name == "start_patrol" else self.patrol.stop()
        except PatrolRejected as exc:
            self._refresh()
            return _error(409, "rejected", exc.detail)
        self._refresh()
        self._broadcast("patrol", detail)
        return _ok(200, detail, self.snapshot)

    async def _direction_test(self, link: EthernetDogLink) -> None:
        steps: list[Json] = []
        try:
            await link.connect()
            for segment in direction_steps(self.dog_limits):
                if self.halt_latched:
                    break
                result = await link.move_segment(segment)
                steps.append(result)
                self.dog_motion = {
                    "sent": result.get("sent") is True,
                    "detail": str(result.get("detail") or ""),
                    "steps": steps,
                }
                self._refresh()
                self._broadcast("dog_test", str(result.get("detail") or "step finished"))
                if result.get("sent") is True and result.get("stopped") is not True:
                    break
        except Exception as exc:
            self.reason = f"{type(exc).__name__}: {exc}"
            self.phase = "FAULT"
            self.recovery_required = True
        finally:
            if self.halt_latched:
                try:
                    await link.halt()
                except Exception:
                    self.halt_delivered = False
            try:
                await link.close()
            except Exception:
                pass
            self.dog_link = None
            self.dog_target = "fake"
            self.armed = False
            if self.dog_motion is None:
                self.dog_motion = {}
            self.dog_motion["steps"] = steps
            self.dog_motion["detail"] = self.dog_motion.get("detail") or "Direction test finished."
            self._refresh()
            self._broadcast("dog_test", "Direction test finished.")

    def _begin_dog_view(self, body: Mapping[str, Any], route: dict[str, Any] | None = None) -> Json:
        if self.closed or self.mode == "replay":
            return _error(409, "rejected", "This session cannot open the dog camera.")
        if body.get("open") is False:
            self.dog_view_stop = True
            if not self.dog_view_owns:
                self.dog_view = False
                self.dog_view_ready = False
                self.dog_view_detail = "Camera display closed. The dog session stays open."
                self._refresh()
                return _ok(200, self.dog_view_detail, self.snapshot)
            self.dog_view_detail = "Closing the camera and LiDAR."
            self._refresh()
            return _ok(202, self.dog_view_detail, self.snapshot)
        if self.dog_view and self.dog_link is not None:
            return _ok(200, "Camera and LiDAR are already open.", self.snapshot)
        if self.dog_link is not None or self._worker_state() == "running":
            self.dog_view = True
            self.dog_view_owns = False
            self.dog_view_ready = self.dog_link is not None and self.dog_link.ready is not None
            self.dog_view_detail = "Showing the dog session that is already open."
            self._refresh()
            return _ok(200, self.dog_view_detail, self.snapshot)
        dog = body.get("dog") or "ethernet"
        if dog not in {"ethernet", "sim"}:
            return _error(422, "invalid_input", "dog view must use ethernet or sim")
        if dog == "ethernet":
            if route is None:
                route = probe_dog_ethernet()
            if route.get("reachable") is not True or route.get("laptop_on_dog_subnet") is not True:
                return self._fail(
                    409,
                    "dog_unreachable",
                    "The dog Ethernet cable is not ready. No camera was opened.",
                )
        link = EthernetDogLink(
            self.runs_root / f"view-{uuid4().hex[:12]}" / "dog",
            armed=False,
            fake=dog == "sim",
        )
        self.dog_link = link
        self.dog_target = str(dog)
        self.dog_view = True
        self.dog_view_ready = False
        self.dog_view_owns = True
        self.dog_view_stop = False
        self.dog_view_detail = "Opening the camera and LiDAR. No motion is sent."
        self.view_task = asyncio.create_task(self._hold_view(link))
        self._refresh()
        return _ok(202, self.dog_view_detail, self.snapshot)

    async def _hold_view(self, link: EthernetDogLink) -> None:
        failed = ""
        try:
            await link.connect()
            self.dog_view_ready = True
            self.dog_view_detail = "Camera and LiDAR are open. This view does not move the dog."
            self._refresh()
            self._broadcast("dog_view", self.dog_view_detail)
            while not self.dog_view_stop:
                await asyncio.sleep(0.2)
        except Exception as exc:
            failed = f"{type(exc).__name__}: {exc}"
        finally:
            self.dog_view_ready = False
            self.dog_view = False
            self.dog_view_owns = False
            self.dog_view_stop = False
            if self.dog_link is link:
                self.dog_link = None
                self.dog_target = "fake"
            try:
                await link.close()
            except Exception:
                pass
            self.dog_view_detail = failed or "Camera and LiDAR are closed."
            self._refresh()
            self._broadcast("dog_view", self.dog_view_detail)

    async def dog_frame_jpeg(self) -> bytes | None:
        link = self.dog_link
        if link is None or link.ready is None:
            return None
        parsed = await link.frame()
        jpeg = parsed.get("jpeg")
        return jpeg if isinstance(jpeg, bytes) else None

    async def dog_lidar_view(self) -> Json | None:
        link = self.dog_link
        if link is None or link.ready is None:
            return None
        parsed = await link.lidar()
        if parsed.get("ok") is not True:
            return {"ok": False, "detail": str(parsed.get("detail") or "LiDAR did not answer")}
        return {"ok": True, "view": parsed.get("view"), "status": parsed.get("status")}

    def _probe(self, route: dict[str, Any] | None = None) -> Json:
        if route is None:
            route = probe_dog_ethernet()
        self.dog_motion = {"probe": route, "sent": False}
        if route.get("reachable") is True and route.get("laptop_on_dog_subnet") is True:
            self._refresh()
            return _ok(200, "Dog Ethernet answered on 192.168.123.161:8081. No motion was sent.", self.snapshot)
        if route.get("reachable") is True:
            return self._fail(
                409,
                "dog_unreachable",
                "The dog answered on an address outside 192.168.123.222/24.",
            )
        return self._fail(
            409,
            "dog_unreachable",
            "The dog Ethernet port 8081 did not answer. Plug in the cable and set this laptop to 192.168.123.222/24.",
        )

    def _fail(self, status: int, code: str, detail: str) -> Json:
        self._refresh()
        body = _error(status, code, detail)
        body["snapshot"] = self.snapshot
        return body

    async def _halt_dog(self, link: EthernetDogLink) -> None:
        try:
            result = await link.halt()
        except Exception as exc:
            result = {"ok": False, "detail": type(exc).__name__}
        self.dog_motion = {"halt": result, "sent": result.get("sent") is True}
        self.halt_delivered = result.get("sent") is True
        self._refresh()
        self._broadcast("halt", "Dog halt finished. Delivery is recorded separately from acceptance.")

    def _dog_demo(self) -> Json:
        return {
            "profile": "ethernet-now",
            "dog": "192.168.123.161",
            "laptop": "192.168.123.222",
            "drone": "simulated script",
            "pi": "not mounted; later this laptop Wi-Fi joins only the ground AP",
            "active": self.dog_link is not None,
            "view": {
                "open": self.dog_view,
                "ready": self.dog_view_ready,
                "owns": self.dog_view_owns,
                "detail": self.dog_view_detail,
            },
            "last": self.dog_motion,
            "limits": self.dog_limits,
            "ceiling": {
                "forward_m_s": 0.3,
                "side_m_s": 0.2,
                "yaw_rad_s": 0.6,
                "step_s": 1.0,
            },
        }

    def _worker_state(self) -> str:
        if self.worker is not None and not self.worker.done():
            return "running"
        if self.run_id is not None or self.phase not in {"IDLE"}:
            return "finished"
        return "idle"

    def _motion(self) -> bool | None:
        for message in reversed(self.messages):
            if message.get("kind") != "capabilities.report" or message.get("source") != "drone":
                continue
            payload = message.get("payload")
            if isinstance(payload, dict) and isinstance(payload.get("features"), dict):
                value = payload["features"].get("controlled_motion")
                if isinstance(value, bool):
                    return value
        return None

    def _view_from_report(self, report: Mapping[str, Any]) -> None:
        self.run_id = str(report.get("run_id") or self.run_id or "")
        self.scenario = str(report.get("scenario") or "")
        self.phase = str(report.get("phase") or "IDLE")
        self.phase_history = list(report.get("phase_history") or [])
        self.goal_reached = report.get("goal_reached") is True
        self.landing_verified = report.get("landing_verified") is True
        self.recovery_required = report.get("recovery_required") is True
        self.outcome = str(report.get("outcome") or "")
        self.reason = str(report.get("reason") or "")
        self.messages = [item for item in report.get("messages", []) if isinstance(item, dict)]
        self.trace = [item for item in report.get("trace", []) if isinstance(item, dict)]
        self.commands = [item for item in report.get("commands", []) if isinstance(item, dict)]
        self.notes = [item for item in report.get("notes", []) if isinstance(item, dict)]
        self.metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else None
        journal = report.get("provider_journal")
        self.provider_journal = [item for item in journal if isinstance(item, dict)] if isinstance(journal, list) else []
        self.writer_state = "failed" if report.get("writer_failed") is True else _writer(self.provider_journal)
        self.step_control = report.get("step_control") if isinstance(report.get("step_control"), dict) else None
        motion = report.get("dog_ethernet")
        if isinstance(motion, dict):
            self.dog_motion = motion
        self.mission_epoch = report.get("mission_epoch") if isinstance(report.get("mission_epoch"), int) else None
        self.live_call_count = 0
        if not self.activity:
            for message in self.messages:
                self.cursor += 1
                row = journal_row(message)
                row["cursor"] = self.cursor
                self.activity.append(row)

    def _scan_runs(self) -> None:
        for path in sorted(self.runs_root.glob("run-*")):
            report_path = path / "report.json"
            if not report_path.is_file():
                continue
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(report, dict):
                self.runs.append(_summary(report))

    def _report_path(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
            raise ArtifactError("rejected", "run id is not an operator run")
        path = (self.runs_root / run_id).resolve()
        path.relative_to(self.runs_root.resolve())
        return path / "report.json"


def _inventory() -> tuple[list[Json], list[str]]:
    manifests = discover(repo_root() / "patrol" / "ground" / "extensions")
    rows = [{"task_id": manifest.task_id, "slot": manifest.slot} for manifest in manifests]
    found = {str(row["task_id"]) for row in rows}
    missing = [f"GROUND-{number:02d}" for number in range(1, 33) if f"GROUND-{number:02d}" not in found]
    return rows, missing


def _writer(records: list[Json]) -> str:
    if not records:
        return "idle"
    states = {str(item.get("writer_state")) for item in records}
    if "failed" in states:
        return "failed"
    if all(item.get("published") is True for item in records):
        return "published"
    if "flushed" in states:
        return "flushed"
    return "queued"


def _wants_ethernet_probe(name: str, body: Mapping[str, Any]) -> bool:
    if name == "probe":
        return True
    if name == "dog_view" and body.get("open") is False:
        return False
    if name == "start":
        return (body.get("dog") or "fake") == "ethernet"
    if name in {"dog_test", "dog_view"}:
        return (body.get("dog") or "ethernet") == "ethernet"
    return False


def _summary(report: Mapping[str, Any]) -> Json:
    return {
        "run_id": report.get("run_id"),
        "mission_id": report.get("mission_id"),
        "scenario": report.get("scenario"),
        "outcome": report.get("outcome"),
        "phase": report.get("phase"),
        "goal_reached": report.get("goal_reached") is True,
        "landing_verified": report.get("landing_verified") is True,
        "recovery_required": report.get("recovery_required") is True,
        "reason": report.get("reason") or "",
        "evidence": report.get("evidence"),
    }


def _summary_text(kind: str, payload: Json) -> str:
    if isinstance(payload, str):
        return payload
    detail = payload.get("detail") or payload.get("reason") or payload.get("error")
    if isinstance(detail, str) and detail:
        return detail
    phase = payload.get("phase")
    if isinstance(phase, str):
        return f"Phase {phase}"
    return kind


def _match(row: Mapping[str, Any], filters: Mapping[str, str]) -> bool:
    for key, value in filters.items():
        if not value:
            continue
        if str(row.get(key) or "") != value:
            return False
    return True


def _ok(status: int, detail: str, snapshot: Json) -> Json:
    return {"ok": True, "status": status, "detail": detail, "snapshot": snapshot}


def _error(status: int, code: str, detail: str) -> Json:
    return {"ok": False, "status": status, "error": {"code": code, "detail": detail}}
