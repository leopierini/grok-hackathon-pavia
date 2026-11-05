"""Console transport: parsing, scripted or prompt input, and scoped confirmations.

Phase policy stays in later features. This service does not move a robot.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Mapping

from prompt_toolkit.input import PipeInput
from prompt_toolkit.output import Output
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import PromptSession

from patrol.contract import Frame, Incident
from patrol.ground.extensions.g07.parser import parse_operator_text
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import (
    BaseServices,
    Command,
    ConfirmationResult,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    KernelContext,
    ServicePorts,
    WaitSpec,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.validation import freeze_map

_ARRIVAL = frozenset({"arrival", "arrived"})
_READINESS = frozenset({"flight_ready", "flight-ready", "readiness"})
_CONFIRMATION = frozenset({"arrived", "flight-ready"})


class _Waiter:
    """One confirmation wait. A plain class so the foundation loader can import it."""

    def __init__(
        self,
        identity: str,
        mission_id: str,
        epoch: int,
        stage_id: str,
        kind: str,
        group: str,
        zone: str,
        future: asyncio.Future[ConfirmationResult],
        timer: asyncio.Task[None] | None = None,
        done: bool = False,
    ) -> None:
        self.identity = identity
        self.mission_id = mission_id
        self.epoch = epoch
        self.stage_id = stage_id
        self.kind = kind
        self.group = group
        self.zone = zone
        self.future = future
        self.timer = timer
        self.done = done


class ConsoleService:
    """ConsolePort plus the simulation entry the Task 01 harness calls."""

    def __init__(self, kernel: KernelContext, peers: ServicePorts) -> None:
        self.kernel = kernel
        self.peers = peers
        self.events: list[GroundEvent] = []
        self._trace: list[str] = []
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()
        self.renderer_errors = 0
        self.input_errors = 0
        self._output: list[str] = []
        self._writer: Callable[[str], None] | None = None
        self._commands: asyncio.Queue[Command | None] = asyncio.Queue()
        self._turns: list[tuple[tuple[str, ...], asyncio.Future[None]]] = []
        self._signals: list[tuple[str, asyncio.Future[None]]] = []
        self._wake = asyncio.Event()
        self._waiters: dict[str, _Waiter] = {}
        self._accepted: set[tuple[str, str, str]] = set()
        self._owned: list[asyncio.Task[None]] = []
        self._dispatcher: asyncio.Task[None] | None = None
        self._prompt: asyncio.Task[None] | None = None
        self._closed = False
        self._commands_stopped = False
        self._close_gate: asyncio.Future[None] | None = None
        self._ids = 0
        self._last_rejection = ""

    def parse(self, text: str) -> Command:
        return parse_operator_text(text)

    def commands(self) -> AsyncIterator[Command]:
        return self._iterate_commands()

    def write(self, message: str) -> None:
        if not isinstance(message, str):
            raise fault("invalid_input", "console message must be a string")
        if self._writer is not None:
            self._writer(message)
            return
        self._output.append(message)

    def set_writer(self, writer: Callable[[str], None] | None) -> None:
        self._writer = writer

    @property
    def messages(self) -> tuple[str, ...]:
        return tuple(self._output)

    @property
    def trace(self) -> list[str]:
        return self._trace

    def lifecycle_events(self) -> tuple[GroundEvent, ...]:
        return tuple(self.events)

    def submit_interrupt(self) -> None:
        """Latch halt immediately. Ctrl+C must not wait for the dispatcher."""
        self._remember("shutdown_requested", "ctrl-c")
        self._trace.append("event:shutdown_requested")
        self._latch_halt("console interrupt", event_source="ctrl-c")

    def submit_eof(self) -> None:
        """Record EOF and latch halt without a second halt event."""
        self._remember("shutdown_requested", "eof")
        self._trace.append("event:shutdown_requested")
        self._latch_halt("console eof", event_source=None)

    async def confirm(self, wait_spec: WaitSpec) -> ConfirmationResult:
        self._check_spec(wait_spec)
        if self._closed:
            return ConfirmationResult(False, None, wait_spec.zone, "closed")
        if self.kernel.authority.cancelled:
            return ConfirmationResult(False, None, wait_spec.zone, "cancelled")
        stale = self._staleness(wait_spec)
        if stale is not None:
            return ConfirmationResult(False, None, wait_spec.zone, stale)
        if self._deadline_passed(wait_spec):
            return ConfirmationResult(False, None, wait_spec.zone, "expired")
        waiter = self._register(wait_spec)
        waiter.timer = self._start_task(
            f"console.confirm.{waiter.identity}",
            self._watch_deadline(waiter, wait_spec),
        )
        try:
            return await waiter.future
        finally:
            self._waiters.pop(waiter.identity, None)

    def submit_turn(self, lines: tuple[str, ...] | list[str]) -> asyncio.Future[None]:
        """Queue one logical turn. A halt anywhere in the turn is applied first."""
        if self._closed:
            raise fault("cancelled", "console is closed")
        done = self._future()
        self._turns.append((tuple(lines), done))
        self._wake.set()
        self._ensure_dispatcher()
        return done

    def submit_signal(self, name: str) -> asyncio.Future[None]:
        """Deliver ctrl-c, eof, or an input-error without a background input thread."""
        if name == "interrupt":
            self.submit_interrupt()
        elif name == "eof":
            self.submit_eof()
        elif name == "input-error":
            self.input_errors += 1
            self._trace.append("input:error")
        else:
            raise fault("invalid_input", "unknown console signal")
        done = self._future()
        done.set_result(None)
        return done

    async def attach_prompt(
        self,
        pipe: PipeInput,
        output: Output,
        *,
        patch: bool = False,
    ) -> None:
        if self._closed:
            raise fault("cancelled", "console is closed")
        if self._prompt is not None and not self._prompt.done():
            raise fault("rejected", "prompt is already attached")
        self._prompt = self._start_task(
            "console.prompt",
            self._prompt_loop(pipe, output, patch=patch),
        )
        # The Windows pipe reader arms on a helper thread. Wait until it can
        # observe keys that the caller sends immediately after attach returns.
        await asyncio.sleep(0.05)
        if self._prompt.done():
            error = self._prompt.exception()
            if error is not None:
                raise fault("internal", f"prompt failed to start: {error}")

    async def close(self) -> None:
        if self._close_gate is not None:
            await self._close_gate
            return
        loop = asyncio.get_running_loop()
        gate: asyncio.Future[None] = loop.create_future()
        self._close_gate = gate
        self._closed = True
        self._resolve_all("closed")
        self._drop_pending_inputs()
        self._stop_commands()
        self._wake.set()
        current = asyncio.current_task()
        pending = [task for task in self._owned if task is not current and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if not gate.done():
            gate.set_result(None)

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        handler = _CASES.get(request.name)
        if handler is None:
            return _failed("invalid_input", "unknown console case")
        try:
            data = await handler(self)
            return FeatureResult("ok", freeze_map(data), (), None)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail)
        finally:
            await self.close()

    async def _iterate_commands(self) -> AsyncIterator[Command]:
        while True:
            item = await self._commands.get()
            if item is None:
                return
            yield item

    async def _prompt_loop(self, pipe: PipeInput, output: Output, *, patch: bool) -> None:
        session: PromptSession[str] = PromptSession(input=pipe, output=output)

        use_patch = patch

        async def _read_line() -> str:
            nonlocal use_patch
            if not use_patch:
                return await session.prompt_async("")
            try:
                with patch_stdout():
                    return await session.prompt_async("")
            except Exception as exc:
                if exc.__class__.__name__ != "NoConsoleScreenBufferError":
                    raise
                use_patch = False
                self._trace.append("patch_stdout:unavailable")
                return await session.prompt_async("")

        async def _run() -> None:
            while not self._closed:
                try:
                    line = await _read_line()
                except EOFError:
                    self.submit_eof()
                    return
                except KeyboardInterrupt:
                    self.submit_interrupt()
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.input_errors += 1
                    self._trace.append("input:error")
                    return
                await self.submit_turn((line,))

        await _run()

    async def _run_dispatcher(self) -> None:
        try:
            while not self._closed:
                if not self._turns and not self._signals:
                    await self._wake.wait()
                self._wake.clear()
                self._drain()
        except asyncio.CancelledError:
            self._drop_pending_inputs()
            raise

    async def _watch_deadline(self, waiter: _Waiter, spec: WaitSpec) -> None:
        try:
            remaining = float(spec.deadline_monotonic) - self.kernel.clock.monotonic()
            if remaining <= 0:
                self._resolve(waiter, False, None, spec.zone, "expired")
                return
            await self.kernel.clock.sleep(remaining)
            self._resolve(waiter, False, None, spec.zone, "expired")
        except asyncio.CancelledError:
            return

    def _future(self) -> asyncio.Future[None]:
        loop = asyncio.get_running_loop()
        return loop.create_future()

    def _ensure_dispatcher(self) -> None:
        if self._closed:
            return
        if self._dispatcher is not None and not self._dispatcher.done():
            return
        self._dispatcher = self._start_task("console.dispatch", self._run_dispatcher())

    def _start_task(self, name: str, work: Coroutine[None, None, None]) -> asyncio.Task[None]:
        task: asyncio.Task[None] = asyncio.create_task(work, name=name)
        self._owned.append(task)
        self.kernel.tasks.retain(name, task)
        return task

    def _drain(self) -> None:
        while self._signals:
            name, done = self._signals.pop(0)
            try:
                self._apply_signal(name)
            finally:
                if not done.done():
                    done.set_result(None)
        while self._turns:
            lines, done = self._turns.pop(0)
            try:
                self._apply_turn(lines)
            finally:
                if not done.done():
                    done.set_result(None)

    def _apply_signal(self, name: str) -> None:
        if name == "interrupt":
            self.submit_interrupt()
            return
        if name == "eof":
            self.submit_eof()
            return
        if name == "input-error":
            self.input_errors += 1
            self._trace.append("input:error")
            return
        raise fault("invalid_input", "unknown console signal")

    def _apply_turn(self, lines: tuple[str, ...]) -> None:
        parsed: list[Command] = []
        for line in lines:
            try:
                parsed.append(self.parse(line))
            except GroundFault as exc:
                self._last_rejection = exc.error.detail
                self._trace.append(f"rejected:{exc.error.detail}")
        halt_in_turn = any(command.name == "halt" for command in parsed)
        if halt_in_turn:
            self._latch_halt("operator halt", event_source="command")
        for command in parsed:
            self._dispatch_command(command, halt_in_turn=halt_in_turn)

    def _dispatch_command(self, command: Command, *, halt_in_turn: bool) -> None:
        if command.name == "halt":
            self._trace.append("parsed:halt")
            self._enqueue(command)
            return
        if command.name in _CONFIRMATION:
            if halt_in_turn or self.kernel.authority.cancelled:
                self._reject_confirmation(command, "invalidated by halt")
                return
            self._offer(command)
            return
        if command.name == "quit":
            self._trace.append("parsed:quit")
            self._trace.append("event:shutdown_requested")
            self._remember("shutdown_requested", "quit")
            self._enqueue(command)
            return
        if command.name == "reset":
            self._trace.append("parsed:reset")
            self._trace.append("event:reset_requested")
            self._remember("reset_requested", "reset")
            self._enqueue(command)
            return
        self._trace.append(f"parsed:{command.name}")
        self._enqueue(command)

    def _offer(self, command: Command) -> None:
        group = "arrival" if command.name == "arrived" else "readiness"
        zone = command.args[0] if command.name == "arrived" else ""
        if self.kernel.authority.cancelled:
            self._reject_confirmation(command, "invalidated by halt")
            return
        current = [
            waiter
            for waiter in self._waiters.values()
            if not waiter.done and waiter.group == group and self._waiter_current(waiter)
        ]
        if group == "arrival":
            matched = [waiter for waiter in current if waiter.zone == zone]
            if current and not matched:
                self._reject_confirmation(command, "wrong zone")
                return
            current = matched
        if not current:
            if self._was_accepted(group, zone):
                self._reject_confirmation(command, "duplicate")
                return
            self._reject_confirmation(command, "no active wait")
            return
        self._accept(current[0], command, zone)

    def _accept(self, waiter: _Waiter, command: Command, zone: str) -> None:
        chosen = zone or waiter.zone
        self._accepted.add((waiter.group, chosen, waiter.stage_id))
        self._resolve(waiter, True, "operator", chosen, "confirmed")
        label = "arrived" if command.name == "arrived" else "flight-ready"
        self._trace.append(f"confirmation:{label}:accepted")
        kind = "arrival_confirmed" if command.name == "arrived" else "flight_ready_confirmed"
        self._remember(kind, "operator")

    def _reject_confirmation(self, command: Command, detail: str) -> None:
        self._last_rejection = detail
        label = "arrived" if command.name == "arrived" else "flight-ready"
        self._trace.append(f"confirmation:{label}:{_rejection_token(detail)}")
        kind = "arrival_rejected" if command.name == "arrived" else "flight_ready_rejected"
        self._remember(kind, detail)

    def _register(self, spec: WaitSpec) -> _Waiter:
        group = _group(spec.kind)
        if group is None:
            raise fault("invalid_input", "unknown confirmation kind")
        for existing in list(self._waiters.values()):
            if not existing.done and existing.group == group:
                self._resolve(existing, False, None, existing.zone, "stale")
        self._ids += 1
        loop = asyncio.get_running_loop()
        waiter = _Waiter(
            identity=f"w{self._ids}",
            mission_id=self._mission_id(),
            epoch=self.kernel.authority.epoch,
            stage_id=spec.stage_id,
            kind=spec.kind,
            group=group,
            zone=spec.zone,
            future=loop.create_future(),
        )
        self._waiters[waiter.identity] = waiter
        return waiter

    def _resolve(
        self,
        waiter: _Waiter,
        accepted: bool,
        method: str | None,
        zone: str | None,
        detail: str,
    ) -> None:
        if waiter.done:
            return
        waiter.done = True
        if not waiter.future.done():
            waiter.future.set_result(ConfirmationResult(accepted, method, zone, detail))
        timer = waiter.timer
        current = asyncio.current_task()
        if timer is not None and timer is not current and not timer.done():
            timer.cancel()

    def _resolve_all(self, detail: str) -> None:
        for waiter in list(self._waiters.values()):
            self._resolve(waiter, False, None, waiter.zone, detail)

    def _latch_halt(self, reason: str, *, event_source: str | None) -> None:
        if not self.kernel.authority.cancelled:
            self.kernel.authority.latch_cancel(reason)
            if event_source is not None:
                self._trace.append("event:halt_requested")
                self._remember("halt_requested", event_source)
        self._resolve_all("cancelled")
        try:
            self.write("halt")
        except Exception:
            self.renderer_errors += 1
            self._trace.append("renderer:isolated")

    def _waiter_current(self, waiter: _Waiter) -> bool:
        return (
            not waiter.done
            and not self._closed
            and not self.kernel.authority.cancelled
            and waiter.epoch == self.kernel.authority.epoch
        )

    def _was_accepted(self, group: str, zone: str) -> bool:
        return any(item[0] == group and item[1] == zone for item in self._accepted)

    def _staleness(self, spec: WaitSpec) -> str | None:
        if _group(spec.kind) is None:
            return "stale"
        try:
            snapshot = self.peers.state.snapshot()
        except GroundFault:
            return None
        if snapshot.epoch != self.kernel.authority.epoch:
            return "stale"
        if snapshot.stage_id is not None and snapshot.stage_id != spec.stage_id:
            return "stale"
        return None

    def _deadline_passed(self, spec: WaitSpec) -> bool:
        return self.kernel.clock.monotonic() >= float(spec.deadline_monotonic)

    def _check_spec(self, spec: WaitSpec) -> None:
        if not isinstance(spec, WaitSpec):
            raise fault("invalid_input", "expected a WaitSpec")
        deadline = spec.deadline_monotonic
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise fault("invalid_input", "deadline must be a real number")
        if spec.zone not in {"entrance", "room_2", "display"}:
            raise fault("invalid_input", "confirmation zone is unknown")
        if not isinstance(spec.stage_id, str) or not spec.stage_id:
            raise fault("invalid_input", "confirmation stage is required")
        if _group(spec.kind) is None:
            raise fault("invalid_input", "unknown confirmation kind")

    def _mission_id(self) -> str:
        try:
            snapshot = self.peers.state.snapshot()
        except GroundFault:
            return ""
        return snapshot.mission_id or ""

    def _enqueue(self, command: Command) -> None:
        if self._closed:
            return
        self._commands.put_nowait(command)

    def _remember(self, kind: str, source: str) -> None:
        self.events.append(GroundEvent(kind, None, freeze_map({"source": source})))

    def _drop_pending_inputs(self) -> None:
        while self._turns:
            _lines, done = self._turns.pop(0)
            if not done.done():
                done.set_result(None)
        while self._signals:
            _name, done = self._signals.pop(0)
            if not done.done():
                done.set_result(None)

    def _stop_commands(self) -> None:
        if self._commands_stopped:
            return
        self._commands_stopped = True
        self._commands.put_nowait(None)

    def _device_calls(self) -> int:
        devices = getattr(self.peers.adapters, "devices", None)
        calls = getattr(devices, "calls", ())
        if isinstance(calls, list):
            return len(calls)
        return 0

    def _payload(
        self,
        *,
        trace: tuple[str, ...],
        detail: str,
        authorized: bool,
        within_limit: bool | None = None,
        retained: bool | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "live_call_count": 0,
            "device_calls": self._device_calls(),
            "simulated": True,
            "trace": trace,
            "slot": "base.console",
            "schema_version": SCHEMA_VERSION,
            "authorized": authorized,
            "detail": detail,
        }
        if within_limit is not None:
            payload["within_limit"] = within_limit
        if retained is not None:
            payload["retained"] = retained
        return payload


def _group(kind: str) -> str | None:
    if kind in _ARRIVAL:
        return "arrival"
    if kind in _READINESS:
        return "readiness"
    return None


def _rejection_token(detail: str) -> str:
    return {
        "no active wait": "early",
        "wrong zone": "wrong-zone",
        "duplicate": "duplicate",
        "invalidated by halt": "invalidated",
    }.get(detail, detail)


def _peers_from(services: BaseServices) -> ServicePorts:
    return ServicePorts(
        config=services.config,
        state=services.state,
        journal=services.journal,
        executor=services.executor,
        evidence=services.evidence,
        console=services.console,
        adapters=services.adapters,
        workflow=services.workflow,
        safety=services.safety,
    )


def create(
    kernel: KernelContext | BaseServices,
    peers: ServicePorts | None = None,
) -> ConsoleService:
    if isinstance(kernel, BaseServices):
        if peers is not None:
            raise fault("invalid_input", "pass either services or kernel and peers")
        return ConsoleService(kernel.kernel, _peers_from(kernel))
    if peers is None:
        raise fault("invalid_input", "console peers are required")
    return ConsoleService(kernel, peers)


def _failed(code: str, detail: str) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "live_call_count": 0,
                "device_calls": 0,
                "simulated": True,
                "trace": (),
                "slot": "base.console",
                "schema_version": SCHEMA_VERSION,
                "authorized": False,
                "detail": detail,
            }
        ),
        (),
        GroundError(code, detail, code in {"cancelled", "recovery_required"}),
    )


async def _case_stream(console: ConsoleService) -> Mapping[str, object]:
    lines = ("status", "arm", "start", "reset", "quit")
    iterator = console.commands()
    names: list[str] = []
    for line in lines:
        await console.submit_turn((line,))
        command = await _next_command(iterator)
        names.append(command.name)
    kinds = [event.kind for event in console.events]
    ok = names == ["status", "arm", "start", "reset", "quit"]
    ok = ok and "reset_requested" in kinds and "shutdown_requested" in kinds
    trace = tuple(f"parsed:{name}" for name in names) + (
        "event:reset_requested" if "reset_requested" in kinds else "event:missing-reset",
        "event:shutdown_requested" if "shutdown_requested" in kinds else "event:missing-quit",
    )
    return console._payload(
        trace=trace,
        detail="scripted stream accepted" if ok else "stream mismatch",
        authorized=False,
    )


async def _case_arrival(console: ConsoleService) -> Mapping[str, object]:
    spec = WaitSpec("arrival", "room_2", "arrive-1", 30.0)
    await console.submit_turn(("arrived room_2",))
    early = _rejection_token(console._last_rejection)
    pending = asyncio.create_task(console.confirm(spec))
    await asyncio.sleep(0)
    await console.submit_turn(("arrived display",))
    wrong = _rejection_token(console._last_rejection)
    await console.submit_turn(("arrived room_2",))
    result = await pending
    accepted = "accepted" if result.accepted and result.zone == "room_2" else result.detail
    await console.submit_turn(("arrived room_2",))
    duplicate = _rejection_token(console._last_rejection)
    return console._payload(
        trace=(
            f"confirmation:arrived:{early}",
            f"confirmation:arrived:{wrong}",
            f"confirmation:arrived:{accepted}",
            f"confirmation:arrived:{duplicate}",
        ),
        detail="single arrival resolution",
        authorized=False,
    )


async def _case_pending(console: ConsoleService) -> Mapping[str, object]:
    console.kernel.barriers.arm("model")
    ticket = console.kernel.authority.issue("pending-mission", "assess")

    async def factory(_context: object) -> str:
        await console.kernel.barriers.wait("model")
        return "done"

    operation = asyncio.create_task(
        console.peers.executor.run(
            "reasoner.assess_incident",
            ticket,
            factory,
            limit_s=30,
        )
    )
    console.kernel.tasks.retain("model-op", operation)
    await asyncio.sleep(0)
    iterator = console.commands()
    started = time.perf_counter()
    await console.submit_turn(("status",))
    status = await _next_command(iterator)
    await console.submit_turn(("halt",))
    halt = await _next_command(iterator)
    elapsed = time.perf_counter() - started
    still_open = not operation.done()
    within = elapsed < 0.5 and still_open and status.name == "status" and halt.name == "halt"
    return console._payload(
        trace=(
            "pending:reasoner.assess_incident",
            "parsed:status",
            "parsed:halt",
            "pending:still-open" if still_open else "pending:finished",
        ),
        detail="commands progressed during pending work" if within else "commands blocked",
        authorized=False,
        within_limit=within,
    )


async def _case_race(console: ConsoleService) -> Mapping[str, object]:
    first = await _race_turn(console, ("halt", "flight-ready"), "pre-halt-first")
    console.kernel.authority.reset_generation("same-turn recovery")
    second = await _race_turn(console, ("flight-ready", "halt"), "pre-ready-first")
    return console._payload(
        trace=(
            (
                "same-turn:halt,flight-ready:rejected"
                if not first
                else "same-turn:halt,flight-ready:accepted"
            ),
            (
                "same-turn:flight-ready,halt:rejected"
                if not second
                else "same-turn:flight-ready,halt:accepted"
            ),
        ),
        detail="readiness invalidated",
        authorized=False,
    )


async def _race_turn(console: ConsoleService, lines: tuple[str, ...], stage: str) -> bool:
    spec = WaitSpec("flight_ready", "room_2", stage, 100.0)
    pending = asyncio.create_task(console.confirm(spec))
    await asyncio.sleep(0)
    await console.submit_turn(lines)
    result = await pending
    return result.accepted


async def _case_lifecycle(console: ConsoleService) -> Mapping[str, object]:
    console.kernel.barriers.arm("model")
    ticket = console.kernel.authority.issue("life", "assess")

    async def factory(_context: object) -> str:
        await console.kernel.barriers.wait("model")
        return "done"

    operation = asyncio.create_task(
        console.peers.executor.run("reasoner.assess_incident", ticket, factory, limit_s=30)
    )
    console.kernel.tasks.retain("life-op", operation)
    await asyncio.sleep(0)

    def boom(_message: str) -> None:
        raise RuntimeError("renderer down")

    console.set_writer(boom)
    await console.submit_signal("interrupt")
    interrupted = console.kernel.authority.cancelled and console.renderer_errors > 0
    console.kernel.authority.reset_generation("after interrupt")
    console.set_writer(None)
    await console.submit_signal("eof")
    ended = console.kernel.authority.cancelled
    console.kernel.authority.reset_generation("after eof")
    await console.submit_signal("input-error")
    saw_input = console.input_errors > 0
    if interrupted and ended and saw_input:
        detail = "lifecycle events delivered"
    else:
        detail = "lifecycle incomplete"
    return console._payload(
        trace=(
            "event:halt_requested" if interrupted else "event:missing-interrupt",
            "renderer:isolated" if console.renderer_errors else "renderer:missed",
            "event:shutdown_requested" if ended else "event:missing-eof",
            "input:error" if saw_input else "input:missed",
        ),
        detail=detail,
        authorized=False,
    )


async def _case_parity(console: ConsoleService) -> Mapping[str, object]:
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    lines = ("status", "arm", "quit")
    iterator = console.commands()
    scripted: list[str] = []
    for line in lines:
        await console.submit_turn((line,))
        scripted.append((await _next_command(iterator)).name)
    piped: list[str] = []
    with create_pipe_input() as pipe:
        output = DummyOutput()
        await console.attach_prompt(pipe, output, patch=False)
        await asyncio.sleep(0)
        pipe.send_text("status\narm\nquit\n")
        for _line in lines:
            command = await asyncio.wait_for(_next_command(iterator), timeout=2)
            piped.append(command.name)
    match = tuple(scripted) == tuple(piped) == lines
    return console._payload(
        trace=(
            "scripted:" + ",".join(scripted),
            "prompt:" + ",".join(piped),
            "parity:match" if match else "parity:differ",
        ),
        detail="scripted and pipe input match" if match else "input backends differ",
        authorized=False,
    )


async def _case_rejected(console: ConsoleService) -> Mapping[str, object]:
    frame = Frame("C:/simulated/phone.jpg", "phone", "room_2", None, True)
    incident = Incident(
        "m-reject",
        "room_2",
        "a person or an object left in a marked closed area",
        frame,
    )
    console.peers.state.open(incident, make_settings())
    before = console.peers.state.snapshot().incident
    await console.submit_turn(("launch now",))
    await console.submit_turn(("   ",))
    await console.submit_turn(("status extra",))
    await console.submit_turn(("status\x00",))
    after = console.peers.state.snapshot()
    zone = "" if after.incident is None else after.incident.zone
    state_trace = getattr(console.peers.state, "trace", [])
    applied = isinstance(state_trace, list) and "state.apply" in state_trace
    notes = tuple(item for item in console.trace if item.startswith("rejected:"))
    unchanged = (
        before is not None
        and before.zone == "room_2"
        and zone == "room_2"
        and not applied
        and console._device_calls() == 0
    )
    state_note = "state.apply:absent" if not applied else "state.apply:present"
    detail = "trusted zone unchanged" if unchanged else "state drifted"
    return console._payload(
        trace=notes + (f"zone:{zone}", state_note),
        detail=detail,
        authorized=False,
    )


async def _case_close(console: ConsoleService) -> Mapping[str, object]:
    spec = WaitSpec("arrival", "room_2", "close-stage", 100.0)
    pending = asyncio.create_task(console.confirm(spec))
    await asyncio.sleep(0)
    await console.close()
    result = await pending
    await console.close()
    pending_tasks = len(console.kernel.tasks.pending())
    clean = result.detail == "closed" and not result.accepted and pending_tasks == 0
    return console._payload(
        trace=(
            "closed:once" if result.detail == "closed" else f"closed:{result.detail}",
            "closed:idempotent",
            f"tasks:{pending_tasks}",
        ),
        detail="input tasks collected" if clean else "tasks leaked",
        authorized=False,
        retained=pending_tasks > 0,
    )


async def _case_expired(console: ConsoleService) -> Mapping[str, object]:
    spec = WaitSpec("arrival", "room_2", "expire", 5.0)
    pending = asyncio.create_task(console.confirm(spec))
    await asyncio.sleep(0)
    clock = console.kernel.clock
    if not isinstance(clock, ManualClock):
        raise fault("invalid_input", "expiry case requires the manual clock")
    clock.advance(5)
    await asyncio.sleep(0)
    result = await pending
    expired = (not result.accepted) and result.detail == "expired"
    return console._payload(
        trace=(f"confirmation:arrived:{result.detail}",),
        detail="deadline rejected" if expired else "deadline accepted",
        authorized=False,
    )


async def _case_stale(console: ConsoleService) -> Mapping[str, object]:
    frame = Frame("C:/simulated/phone.jpg", "phone", "room_2", None, True)
    incident = Incident(
        "m-stale",
        "room_2",
        "a person or an object left in a marked closed area",
        frame,
    )
    console.peers.state.open(incident, make_settings())
    console.kernel.authority.reset_generation("newer epoch")
    result = await console.confirm(WaitSpec("flight_ready", "room_2", "preflight", 20.0))
    stale = (not result.accepted) and result.detail == "stale"
    return console._payload(
        trace=(f"confirmation:flight-ready:{result.detail}",),
        detail="epoch rejected" if stale else "stale accepted",
        authorized=False,
    )


async def _next_command(iterator: AsyncIterator[Command]) -> Command:
    return await anext(iterator)


_CASES: dict[str, Callable[[ConsoleService], Awaitable[Mapping[str, object]]]] = {
    "command_stream": _case_stream,
    "arrival_confirmations": _case_arrival,
    "pending_halt": _case_pending,
    "readiness_race": _case_race,
    "lifecycle_faults": _case_lifecycle,
    "scripted_parity": _case_parity,
    "rejected_commands": _case_rejected,
    "close_collect": _case_close,
    "expired_confirmation": _case_expired,
    "stale_epoch": _case_stale,
}
