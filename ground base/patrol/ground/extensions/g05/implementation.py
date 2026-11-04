"""Stage executor. It bounds one operation; it does not choose the next mission step.

Acceptance precedence is ``halt-over-deadline-over-success``. A latched halt
rejects a returned value. If the halt is clear and the injected clock is at or
past the deadline, the result is ``timeout``, including when the clock lands
exactly on the deadline. Only a current ticket, an open deadline, and a
finished awaitable become ``completed``. Cancelling a task does not mean the
device stopped; unfinished work stays pending and blocks replacement.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from patrol.contract import AdapterError, RunContext
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    KernelContext,
    OperationResult,
    ServicePorts,
    Ticket,
)
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map

ACCEPTANCE_PRECEDENCE = "halt-over-deadline-over-success"
Mode = Literal["ordinary", "recovery"]
Wake = Literal["finished", "cancel", "deadline"]


class OperationExecutor:
    """Owns stage tasks for one kernel. Construction does not call peers."""

    def __init__(self, kernel: KernelContext, peers: ServicePorts) -> None:
        self.kernel = kernel
        self.peers = peers
        self.factory_calls: list[str] = []
        self.events: list[GroundEvent] = []
        self.cleanup_errors: list[GroundError] = []
        self.history: list[OperationResult] = []
        self._owned: list[tuple[str, asyncio.Task[object]]] = []
        self._mission_deadline: float | None = None
        self._mission_id: str | None = None

    @property
    def mission_deadline(self) -> float | None:
        return self._mission_deadline

    def bind_mission(self, mission_id: str, budget_s: float) -> float:
        """Record the original incident deadline. Later calls cannot extend it."""
        if not isinstance(mission_id, str) or not mission_id:
            raise fault("invalid_input", "mission id is required")
        budget = _finite(budget_s, "mission budget")
        if budget <= 0:
            raise fault("invalid_input", "mission budget must be positive")
        if self._mission_deadline is None:
            self._mission_id = mission_id
            self._mission_deadline = self.kernel.clock.monotonic() + budget
        return self._mission_deadline

    async def run(
        self,
        name: str,
        ticket: Ticket,
        factory: Callable[[RunContext], Awaitable[object]],
        *,
        limit_s: float,
    ) -> OperationResult:
        return await self._execute(name, ticket, factory, limit_s=limit_s, mode="ordinary")

    async def run_recovery(
        self,
        name: str,
        ticket: Ticket,
        factory: Callable[[RunContext], Awaitable[object]],
        *,
        limit_s: float,
    ) -> OperationResult:
        """Run cleanup on a fresh event and budget. This does not retry motion."""
        return await self._execute(name, ticket, factory, limit_s=limit_s, mode="recovery")

    async def run_cleanup(
        self,
        primary: OperationResult,
        name: str,
        factory: Callable[[RunContext], Awaitable[object]],
        *,
        limit_s: float,
    ) -> OperationResult:
        """Run cleanup and keep the first device/timeout error if cleanup fails."""
        if not isinstance(primary, OperationResult):
            raise fault("invalid_input", "cleanup requires the primary OperationResult")
        outcome = await self.run_recovery(name, primary.ticket, factory, limit_s=limit_s)
        if outcome.status != "completed" and outcome.error is not None:
            self.cleanup_errors.append(outcome.error)
        return primary

    def pending(self) -> tuple[str, ...]:
        return tuple(name for name, task in self._owned if not task.done())

    async def collect(self, *, deadline: float) -> None:
        self._consume_finished()
        await self.kernel.tasks.collect(deadline=deadline)
        self._consume_finished()

    def authorizes_next(self, result: OperationResult) -> bool:
        if result.status != "completed" or result.pending or result.error is not None:
            return False
        if self.kernel.authority.cancelled or result.ticket.epoch != self.kernel.authority.epoch:
            return False
        return not self.pending()

    async def inspect_late(self, name: str) -> object:
        """Read a tracked awaitable without changing the recorded operation status."""
        for owned, task in self._owned:
            if owned == name:
                return await task
        raise fault("invalid_input", "operation is not tracked")

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        """Simulation entry. The harness passes one case name per call."""
        cases = {
            "completed_operation": self._case_completed,
            "barrier_console_pulse": self._case_pulse,
            "deadline_before_start": self._case_deadline_before,
            "deadline_during_execution": self._case_deadline_during,
            "release_before_halt": self._case_before_halt,
            "release_after_halt": self._case_after_halt,
            "same_turn_halt": self._case_same_turn,
            "cancellation_resistant": self._case_resistant,
            "recovery_budget": self._case_recovery,
            "no_retry_timeout": self._case_no_retry,
            "cleanup_preserves_primary": self._case_cleanup,
            "cancelled_error_distinct": self._case_cancelled_error,
            "exact_deadline": self._case_exact_deadline,
            "mission_deadline_frozen": self._case_mission_frozen,
            "zero_budget": self._case_zero_budget,
            "responsiveness": self._case_responsive,
        }
        handler = cases.get(request.name)
        if handler is None:
            return _failed("invalid_input", "unknown executor case")
        try:
            return await handler()
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail)
        finally:
            self._consume_finished()

    async def _execute(
        self,
        name: str,
        ticket: Ticket,
        factory: Callable[[RunContext], Awaitable[object]],
        *,
        limit_s: float,
        mode: Mode,
    ) -> OperationResult:
        self._require_shape(name, ticket, factory)
        started = self.kernel.clock.monotonic()
        started_utc = self.kernel.clock.utc_now().isoformat()
        blocked = self._blocked_before_start(name, ticket, limit_s, mode, started)
        if blocked is not None:
            result = self._finish(
                name,
                ticket,
                blocked[0],
                None,
                blocked[1],
                False,
                started,
                started_utc,
            )
            self._emit("operation_failed", ticket, result)
            return result
        context = self._context(ticket, limit_s, mode, started)
        task = asyncio.create_task(
            self._work(name, ticket, factory, context, mode),
            name=name,
        )
        self._owned.append((name, task))
        self.kernel.tasks.retain(name, task)
        self._emit_started(name, ticket, started, started_utc, context.deadline_monotonic)
        wake = await self._race(
            task,
            context.deadline_monotonic,
            context.cancel,
            honor_authority=mode == "ordinary",
        )
        if wake in {"cancel", "deadline"} and not task.done():
            task.cancel()
            for _ in range(5):
                if task.done():
                    break
                await asyncio.sleep(0)
        status, value, error, pending = self._classify(
            task,
            ticket,
            context.deadline_monotonic,
            wake,
            mode,
        )
        if task.done():
            self._consume_finished()
        result = self._finish(
            name,
            ticket,
            status,
            value,
            error,
            pending,
            started,
            started_utc,
        )
        kind = "operation_completed" if status == "completed" else "operation_failed"
        self._emit(kind, ticket, result)
        return result

    async def _work(
        self,
        name: str,
        ticket: Ticket,
        factory: Callable[[RunContext], Awaitable[object]],
        context: RunContext,
        mode: Mode,
    ) -> object:
        if self._factory_closed(ticket, context.deadline_monotonic, mode):
            raise fault("cancelled", "halted before the operation factory", recovery_required=True)
        self.factory_calls.append(name)
        produced = factory(context)
        if not asyncio.iscoroutine(produced) and not _is_awaitable(produced):
            raise fault("invalid_input", "operation factory must return an awaitable")
        return await produced

    def _require_shape(
        self,
        name: str,
        ticket: Ticket,
        factory: Callable[[RunContext], Awaitable[object]],
    ) -> None:
        if not isinstance(name, str) or not name:
            raise fault("invalid_input", "operation name is required")
        if not isinstance(ticket, Ticket):
            raise fault("invalid_input", "expected a Ticket")
        if not callable(factory):
            raise fault("invalid_input", "operation factory must be callable")

    def _blocked_before_start(
        self,
        name: str,
        ticket: Ticket,
        limit_s: float,
        mode: Mode,
        now: float,
    ) -> tuple[str, GroundError] | None:
        del name
        if self.pending():
            return (
                "failed",
                GroundError(
                    "unsafe_state",
                    "pending work blocks replacement",
                    True,
                ),
            )
        number = _limit(limit_s)
        if isinstance(number, GroundError):
            status = "timeout" if number.code == "expired_deadline" else "failed"
            return status, number
        if mode == "ordinary" and self.kernel.authority.cancelled:
            return (
                "cancelled",
                GroundError("cancelled", "cancellation is latched", True),
            )
        if mode == "ordinary" and ticket.epoch != self.kernel.authority.epoch:
            return ("failed", GroundError("stale_ticket", "ticket epoch is not current", True))
        mission = self._mission_deadline
        if mode == "ordinary" and mission is not None and now >= mission:
            return (
                "timeout",
                GroundError("expired_deadline", "mission deadline has passed", True),
            )
        if mission is not None and mode == "ordinary":
            deadline = min(mission, now + number)
        else:
            deadline = now + number
        if now >= deadline:
            return (
                "timeout",
                GroundError("expired_deadline", "stage deadline has passed", True),
            )
        return None

    def _factory_closed(self, ticket: Ticket, deadline: float, mode: Mode) -> bool:
        if self.kernel.clock.monotonic() >= deadline:
            return True
        if mode == "recovery":
            return False
        if self.kernel.authority.cancelled or ticket.epoch != self.kernel.authority.epoch:
            return True
        return False

    def _context(self, ticket: Ticket, limit_s: float, mode: Mode, now: float) -> RunContext:
        if mode == "recovery":
            return RunContext(
                mission_id=ticket.mission_id,
                deadline_monotonic=now + float(limit_s),
                cancel=threading.Event(),
            )
        mission = self._mission_deadline
        if mission is None:
            mission = now + float(limit_s)
        return context_for_stage(
            ticket.mission_id,
            mission,
            float(limit_s),
            self.kernel.authority.cancel_event,
            self.kernel.clock,
            real_adapter=False,
        )

    async def _race(
        self,
        task: asyncio.Task[object],
        deadline: float,
        event: threading.Event,
        *,
        honor_authority: bool,
    ) -> Wake:
        if task.done():
            await asyncio.sleep(0)
            return self._wake(deadline, event, honor_authority=honor_authority)
        cancel_waiter = asyncio.create_task(self._wait_flag(event), name="executor-cancel")
        deadline_waiter = asyncio.create_task(self._sleep_until(deadline), name="executor-deadline")
        try:
            done, _pending = await asyncio.wait(
                {task, cancel_waiter, deadline_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for waiter in (cancel_waiter, deadline_waiter):
                if not waiter.done():
                    waiter.cancel()
            await asyncio.gather(cancel_waiter, deadline_waiter, return_exceptions=True)
        await asyncio.sleep(0)
        if task in done:
            return self._wake(deadline, event, honor_authority=honor_authority)
        if event.is_set() or (honor_authority and self.kernel.authority.cancelled):
            return "cancel"
        return "deadline"

    def _wake(self, deadline: float, event: threading.Event, *, honor_authority: bool) -> Wake:
        if event.is_set() or (honor_authority and self.kernel.authority.cancelled):
            return "cancel"
        if self.kernel.clock.monotonic() >= deadline:
            return "deadline"
        return "finished"

    async def _wait_flag(self, event: threading.Event) -> None:
        while not event.is_set():
            delay = 0 if self.kernel.clock.is_manual() else 0.01
            await asyncio.sleep(delay)

    async def _sleep_until(self, deadline: float) -> None:
        remaining = deadline - self.kernel.clock.monotonic()
        if remaining <= 0:
            return
        await self.kernel.clock.sleep(remaining)

    def _classify(
        self,
        task: asyncio.Task[object],
        ticket: Ticket,
        deadline: float,
        wake: Wake,
        mode: Mode,
    ) -> tuple[str, object, GroundError | None, bool]:
        pending = not task.done()
        value, exc = _read_task(task)
        halted = mode == "ordinary" and (
            self.kernel.authority.cancelled or ticket.epoch != self.kernel.authority.epoch
        )
        if halted or wake == "cancel":
            code = "cancelled"
            detail = "result arrived after halt and does not authorize the next action"
            if (
                mode == "ordinary"
                and not self.kernel.authority.cancelled
                and ticket.epoch != self.kernel.authority.epoch
            ):
                code = "stale_ticket"
                detail = "ticket epoch changed before the result was accepted"
            if pending:
                detail = (
                    "cancellation is latched and work is still pending; "
                    "cancelling the coroutine does not prove the device stopped"
                )
            status = "cancelled" if code == "cancelled" else "failed"
            return status, value, GroundError(code, detail, True), pending
        if wake == "deadline" or self.kernel.clock.monotonic() >= deadline:
            detail = "deadline equality is timeout and does not authorize the next action"
            if pending:
                detail = (
                    "timed out with work still pending; "
                    "cancelling the coroutine does not prove the device stopped"
                )
            return "timeout", value, GroundError("timeout", detail, True), pending
        if isinstance(exc, AdapterError):
            return "failed", None, GroundError("unavailable", exc.detail, True), False
        if isinstance(exc, GroundFault):
            return _fault_status(exc), None, exc.error, False
        if isinstance(exc, asyncio.CancelledError):
            return (
                "cancelled",
                None,
                GroundError("cancelled", "the operation raised CancelledError", True),
                False,
            )
        if exc is not None:
            text = str(exc) or type(exc).__name__
            return "failed", None, GroundError("internal", text, True), False
        return "completed", value, None, False

    def _finish(
        self,
        name: str,
        ticket: Ticket,
        status: str,
        value: object,
        error: GroundError | None,
        pending: bool,
        started: float,
        started_utc: str,
    ) -> OperationResult:
        result = OperationResult(
            operation=name,
            ticket=ticket,
            status=status,
            value=value,
            error=error,
            pending=pending,
            started_utc=started_utc,
            ended_utc=self.kernel.clock.utc_now().isoformat(),
            started_monotonic=started,
            ended_monotonic=self.kernel.clock.monotonic(),
        )
        self.history.append(result)
        return result

    def _emit_started(
        self,
        name: str,
        ticket: Ticket,
        started: float,
        started_utc: str,
        deadline: float,
    ) -> None:
        self.events.append(
            GroundEvent(
                "operation_started",
                ticket,
                {
                    "operation": name,
                    "started_monotonic": started,
                    "started_utc": started_utc,
                    "deadline_monotonic": deadline,
                },
            )
        )

    def _emit(self, kind: str, ticket: Ticket, result: OperationResult) -> None:
        self.events.append(
            GroundEvent(
                kind,
                ticket,
                {
                    "operation": result.operation,
                    "status": result.status,
                    "pending": result.pending,
                    "started_monotonic": result.started_monotonic,
                    "ended_monotonic": result.ended_monotonic,
                    "started_utc": result.started_utc,
                    "ended_utc": result.ended_utc,
                },
            )
        )

    def _consume_finished(self) -> None:
        still: list[tuple[str, asyncio.Task[object]]] = []
        for name, task in self._owned:
            if task.done():
                _drain(task)
            else:
                still.append((name, task))
        self._owned = still

    def _manual(self) -> ManualClock:
        clock = self.kernel.clock
        if not isinstance(clock, ManualClock):
            raise fault("invalid_input", "case requires the manual clock")
        return clock

    async def _case_completed(self) -> FeatureResult:
        ticket = self.kernel.authority.issue("mission", "prepare")
        self.bind_mission("mission", 30)

        async def factory(_context: RunContext) -> str:
            return "ready"

        result = await self.run("dog.prepare", ticket, factory, limit_s=5)
        accepted = result.status == "completed" and result.value == "ready"
        if not accepted or not self.authorizes_next(result):
            return _failed("validation_failed", "completed operation was not accepted")
        if not result.started_utc or result.ended_monotonic is None:
            return _failed("validation_failed", "timing was not recorded")
        if not self.events or self.events[0].ticket != ticket:
            return _failed("validation_failed", "event lost the original ticket")
        return _view(
            authorized=True,
            trace=("started", "completed", "authorizes"),
            retained=False,
            detail="current ticket completed inside the deadline",
        )

    async def _case_pulse(self) -> FeatureResult:
        barriers = self.kernel.barriers
        barriers.arm("hold")
        pulses = 0
        stop = asyncio.Event()

        async def pulse() -> None:
            nonlocal pulses
            while not stop.is_set():
                pulses += 1
                await asyncio.sleep(0)

        pulse_task = asyncio.create_task(pulse(), name="console-pulse")
        entered = asyncio.Event()
        try:
            ticket = self.kernel.authority.issue("mission", "route")
            self.bind_mission("mission", 30)

            async def factory(_context: RunContext) -> str:
                entered.set()
                await barriers.wait("hold")
                return "moved"

            run_task = asyncio.create_task(
                self.run("dog.run_route", ticket, factory, limit_s=10),
                name="run-route",
            )
            await entered.wait()
            await asyncio.sleep(0)
            if pulses < 1:
                run_task.cancel()
                return _failed("validation_failed", "console pulse did not run")
            barriers.release("hold")
            result = await run_task
        finally:
            stop.set()
            await pulse_task
        if result.status != "completed" or not self.authorizes_next(result):
            return _failed("validation_failed", "pulsed operation did not complete")
        return _view(
            authorized=True,
            trace=("pulse", "completed"),
            retained=False,
            detail="console pulse advanced while the route waited",
        )

    async def _case_deadline_before(self) -> FeatureResult:
        self.bind_mission("mission", 5)
        self._manual().advance(5)
        ticket = self.kernel.authority.issue("mission", "route")

        async def factory(_context: RunContext) -> str:
            return "ran"

        result = await self.run("dog.run_route", ticket, factory, limit_s=5)
        if self.factory_calls or result.status != "timeout":
            return _failed("validation_failed", "expired mission invoked the factory")
        return _view(
            authorized=False,
            trace=("rejected", "factory:0"),
            retained=False,
            detail="expired before factory",
        )

    async def _case_deadline_during(self) -> FeatureResult:
        return await self._timeout_once("dog.run_route", ("factory", "timeout", "invocations:1"))

    async def _case_before_halt(self) -> FeatureResult:
        barriers = self.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        ticket = self.kernel.authority.issue("mission", "route")
        self.bind_mission("mission", 30)

        async def factory(_context: RunContext) -> str:
            entered.set()
            await barriers.wait("hold")
            return "arrived"

        run_task = asyncio.create_task(self.run("dog.run_route", ticket, factory, limit_s=10))
        await entered.wait()
        barriers.release("hold")
        result = await run_task
        if result.status != "completed":
            return _failed("validation_failed", "route did not finish before halt")
        self.kernel.authority.latch_cancel("halt")
        calls = len(self.factory_calls)

        async def again(_context: RunContext) -> str:
            return "again"

        follow = await self.run("dog.run_route", ticket, again, limit_s=10)
        if len(self.factory_calls) != calls or follow.status == "completed":
            return _failed("validation_failed", "halt authorized another route")
        return _view(
            authorized=False,
            trace=("completed", "next-rejected", "factory-next:0"),
            retained=False,
            detail="completion before halt does not authorize the next action",
        )

    async def _case_after_halt(self) -> FeatureResult:
        barriers = self.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        ticket = self.kernel.authority.issue("mission", "route")
        self.bind_mission("mission", 30)

        async def factory(_context: RunContext) -> str:
            entered.set()
            try:
                await barriers.wait("hold")
            except asyncio.CancelledError:
                return "late"
            return "early"

        run_task = asyncio.create_task(self.run("dog.run_route", ticket, factory, limit_s=10))
        await entered.wait()
        self.kernel.authority.latch_cancel("halt")
        result = await run_task
        follow = await self.run("dog.run_route", ticket, factory, limit_s=10)
        if result.status != "cancelled" or result.value != "late" or follow.status == "completed":
            return _failed("validation_failed", "late result authorized the mission")
        if self.authorizes_next(result) or self.history[0].status != "cancelled":
            return _failed("validation_failed", "late value upgraded the recorded result")
        return _view(
            authorized=False,
            trace=("cancelled", "late-value", "not-authorized"),
            retained=False,
            detail="late result stayed inspectable and did not authorize motion",
        )

    async def _case_same_turn(self) -> FeatureResult:
        barriers = self.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        ticket = self.kernel.authority.issue("mission", "route")
        self.bind_mission("mission", 30)

        async def factory(_context: RunContext) -> str:
            entered.set()
            await barriers.wait("hold")
            return "value"

        run_task = asyncio.create_task(self.run("dog.run_route", ticket, factory, limit_s=10))
        await entered.wait()

        def both() -> None:
            barriers.release("hold")
            self.kernel.authority.latch_cancel("halt")

        asyncio.get_running_loop().call_soon(both)
        result = await run_task
        if result.status == "completed" or self.authorizes_next(result):
            return _failed("validation_failed", "same-turn halt authorized the result")
        return _view(
            authorized=False,
            trace=("same-turn", "not-authorized"),
            retained=False,
            detail="halt in the completion turn wins",
        )

    async def _case_resistant(self) -> FeatureResult:
        barriers = self.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        ticket = self.kernel.authority.issue("mission", "inspect")
        self.bind_mission("mission", 5)

        async def factory(_context: RunContext) -> str:
            entered.set()
            while True:
                try:
                    await barriers.wait("hold")
                except asyncio.CancelledError:
                    continue
                return "finished"

        run_task = asyncio.create_task(self.run("drone.inspect", ticket, factory, limit_s=5))
        await entered.wait()
        self._manual().advance(5)
        result = await run_task
        calls = len(self.factory_calls)

        async def replacement(_context: RunContext) -> str:
            return "replacement"

        blocked = await self.run("drone.inspect", ticket, replacement, limit_s=5)
        still_pending = result.pending and "drone.inspect" in self.pending()
        if not still_pending or len(self.factory_calls) != calls:
            return _failed("validation_failed", "resistant work did not stay pending")
        blocked_code = None if blocked.error is None else blocked.error.code
        if blocked.status == "completed" or blocked_code != "unsafe_state":
            return _failed("validation_failed", "replacement was not blocked")
        return _view(
            authorized=False,
            trace=("pending", "replacement-blocked", "factory-next:0"),
            retained=True,
            detail="cancellation-resistant work blocks replacement",
        )

    async def _case_recovery(self) -> FeatureResult:
        ticket = self.kernel.authority.issue("mission", "route")
        self.bind_mission("mission", 30)
        frozen = self.mission_deadline

        async def ordinary(context: RunContext) -> str:
            if context.cancel is not self.kernel.authority.cancel_event:
                raise fault("validation_failed", "ordinary context left the mission event")
            return "done"

        first = await self.run("dog.run_route", ticket, ordinary, limit_s=5)
        if first.status != "completed":
            return _failed("validation_failed", "recovery setup did not complete")
        self.kernel.authority.latch_cancel("halt")
        seen: dict[str, bool] = {}

        async def recovery(context: RunContext) -> str:
            seen["same"] = context.cancel is self.kernel.authority.cancel_event
            seen["set"] = context.cancel.is_set()
            return "stopped"

        outcome = await self.run_recovery("dog.halt", ticket, recovery, limit_s=3)

        async def ordinary_again(_context: RunContext) -> str:
            return "walk"

        follow = await self.run("dog.run_route", ticket, ordinary_again, limit_s=5)
        if (
            outcome.status != "completed"
            or seen.get("same") is not False
            or seen.get("set") is not False
            or self.mission_deadline != frozen
            or follow.status == "completed"
        ):
            return _failed("validation_failed", "recovery reused the cancelled context")
        return _view(
            authorized=False,
            trace=("recovery-completed", "separate-context", "ordinary-blocked"),
            retained=False,
            detail="recovery used a fresh event without extending the mission",
        )

    async def _case_no_retry(self) -> FeatureResult:
        view = await self._timeout_once("drone.inspect", ("timeout", "invocations:1", "no-retry"))
        if view.status != "ok":
            return view
        if self.factory_calls != ["drone.inspect"]:
            return _failed("validation_failed", "timeout invoked the factory more than once")
        return view

    async def _case_cleanup(self) -> FeatureResult:
        timed = await self._hold_timeout("drone.inspect", 5)
        if timed.status != "timeout" or timed.error is None:
            return _failed("validation_failed", "cleanup setup did not time out")
        primary = timed.error

        async def cleanup(_context: RunContext) -> str:
            raise RuntimeError("disk full")

        returned = await self.run_cleanup(timed, "journal.flush", cleanup, limit_s=2)
        if returned.error is not primary or returned.status != "timeout" or not self.cleanup_errors:
            return _failed("validation_failed", "cleanup replaced the primary error")
        if self.cleanup_errors[0].detail != "disk full":
            return _failed("validation_failed", "cleanup diagnostic was dropped")
        return _view(
            authorized=False,
            trace=("timeout", "primary-kept", "cleanup-separate"),
            retained=False,
            detail="primary timeout kept",
        )

    async def _case_cancelled_error(self) -> FeatureResult:
        ticket = self.kernel.authority.issue("mission", "model")
        self.bind_mission("mission", 10)

        async def factory(_context: RunContext) -> str:
            raise asyncio.CancelledError

        result = await self.run("reasoner.assess_incident", ticket, factory, limit_s=5)
        if result.status != "cancelled" or result.value is not None or result.error is None:
            return _failed("validation_failed", "CancelledError looked like success")
        if result.error.detail != "the operation raised CancelledError":
            return _failed("validation_failed", "CancelledError was not distinguished")
        return _view(
            authorized=False,
            trace=("cancelled-error", "not-completed"),
            retained=False,
            detail="CancelledError is not a successful result",
        )

    async def _case_exact_deadline(self) -> FeatureResult:
        clock = self._manual()
        entered = asyncio.Event()
        ticket = self.kernel.authority.issue("mission", "model")
        self.bind_mission("mission", 5)

        async def factory(context: RunContext) -> str:
            entered.set()
            remaining = context.deadline_monotonic - clock.monotonic()
            await clock.sleep(remaining)
            return "edge"

        run_task = asyncio.create_task(
            self.run("reasoner.assess_incident", ticket, factory, limit_s=5)
        )
        await entered.wait()
        clock.advance(5)
        result = await run_task
        if result.status != "timeout" or self.authorizes_next(result):
            return _failed("validation_failed", "exact deadline was accepted as success")
        return _view(
            authorized=False,
            trace=("exact-deadline", "timeout"),
            retained=False,
            detail="deadline equality is timeout",
        )

    async def _case_mission_frozen(self) -> FeatureResult:
        clock = self._manual()
        self.bind_mission("mission", 10)
        clock.advance(4)
        seen: dict[str, float] = {}
        ticket = self.kernel.authority.issue("mission", "prepare")

        async def factory(context: RunContext) -> str:
            seen["deadline"] = context.deadline_monotonic
            return "ok"

        result = await self.run("dog.prepare", ticket, factory, limit_s=30)
        again = self.bind_mission("mission", 100)
        if result.status != "completed" or seen.get("deadline") != 10 or again != 10:
            return _failed("validation_failed", "a later stage extended the mission deadline")
        return _view(
            authorized=True,
            trace=("deadline-frozen", "not-extended"),
            retained=False,
            detail="10",
        )

    async def _case_zero_budget(self) -> FeatureResult:
        ticket = self.kernel.authority.issue("mission", "route")

        async def factory(_context: RunContext) -> str:
            return "ran"

        result = await self.run("dog.run_route", ticket, factory, limit_s=0)
        if self.factory_calls or result.status != "timeout":
            return _failed("validation_failed", "zero budget invoked the factory")
        return _view(
            authorized=False,
            trace=("rejected", "factory:0", "zero-budget"),
            retained=False,
            detail="zero budget rejected before factory",
        )

    async def _case_responsive(self) -> FeatureResult:
        ticket = self.kernel.authority.issue("mission", "model")
        self.bind_mission("mission", 30)

        async def factory(context: RunContext) -> str:
            while not context.cancel.is_set():
                await asyncio.sleep(0.01)
            return "late"

        run_task = asyncio.create_task(
            self.run("reasoner.assess_incident", ticket, factory, limit_s=10)
        )
        await self._until_pending("reasoner.assess_incident")
        await asyncio.sleep(0.02)
        started = time.monotonic()
        self.kernel.authority.latch_cancel("halt")
        result = await asyncio.wait_for(run_task, timeout=0.5)
        elapsed = time.monotonic() - started
        if result.status != "cancelled" or elapsed >= 0.5:
            return _failed("validation_failed", "halt recognition missed the 0.5s bound")
        return _view(
            authorized=False,
            trace=("halt", "responsive"),
            retained=False,
            within_limit=True,
            measurement_clock="real",
            detail="halt latch observed on the real clock",
        )

    async def _timeout_once(self, name: str, trace: tuple[str, ...]) -> FeatureResult:
        result = await self._hold_timeout(name, 5)
        if result.status != "timeout" or self.factory_calls != [name]:
            return _failed("validation_failed", "timeout did not stay a single attempt")
        ticket = result.ticket

        async def again(_context: RunContext) -> str:
            return "retry"

        follow = await self.run(name, ticket, again, limit_s=30)
        if follow.status == "completed" or self.factory_calls != [name]:
            return _failed("validation_failed", "timeout started another attempt")
        return _view(authorized=False, trace=trace, retained=False, detail="single attempt")

    async def _hold_timeout(self, name: str, limit_s: float) -> OperationResult:
        barriers = self.kernel.barriers
        barriers.arm("hold")
        entered = asyncio.Event()
        self.bind_mission("mission", limit_s)
        ticket = self.kernel.authority.issue("mission", name)

        async def factory(_context: RunContext) -> str:
            entered.set()
            await barriers.wait("hold")
            return "ran"

        run_task = asyncio.create_task(self.run(name, ticket, factory, limit_s=limit_s))
        await entered.wait()
        self._manual().advance(limit_s)
        return await run_task

    async def _until_pending(self, name: str) -> None:
        for _ in range(50):
            if name in self.pending():
                return
            await asyncio.sleep(0)
        raise fault("internal", f"{name} did not start")


def create(
    kernel: KernelContext | BaseServices,
    peers: ServicePorts | None = None,
) -> OperationExecutor:
    """Build an executor. The simulator passes BaseServices; callers pass kernel and peers."""
    if isinstance(kernel, BaseServices):
        return OperationExecutor(kernel.kernel, _ports(kernel))
    if not isinstance(kernel, KernelContext) or peers is None:
        raise fault("invalid_input", "executor create requires a kernel and peers")
    return OperationExecutor(kernel, peers)


def _ports(services: BaseServices) -> ServicePorts:
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


def _view(
    *,
    authorized: bool,
    trace: tuple[str, ...],
    retained: bool,
    detail: str,
    within_limit: bool | None = None,
    measurement_clock: str | None = None,
) -> FeatureResult:
    payload: dict[str, object] = {
        "authorized": authorized,
        "simulated": True,
        "trace": trace,
        "device_calls": 0,
        "live_call_count": 0,
        "slot": "base.executor",
        "schema_version": SCHEMA_VERSION,
        "retained": retained,
        "detail": detail,
    }
    if within_limit is not None:
        payload["within_limit"] = within_limit
    if measurement_clock is not None:
        payload["measurement_clock"] = measurement_clock
    return FeatureResult("ok", freeze_map(payload), (), None)


def _failed(code: str, detail: str) -> FeatureResult:
    recovery = code in {"cancelled", "expired_deadline", "io_fault", "timeout", "unsafe_state"}
    return FeatureResult(
        "failed",
        freeze_map({"device_calls": 0, "detail": detail, "live_call_count": 0}),
        (),
        GroundError(code, detail, recovery),
    )


def _limit(value: float) -> float | GroundError:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return GroundError("invalid_input", "stage limit must be a real number", False)
    number = float(value)
    if not math.isfinite(number):
        return GroundError("invalid_input", "stage limit must be finite", False)
    if number < 0:
        return GroundError("invalid_input", "stage limit must be non-negative", False)
    if number == 0:
        return GroundError("expired_deadline", "stage budget is zero", False)
    return number


def _finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", f"{label} must be a real number")
    number = float(value)
    if not math.isfinite(number):
        raise fault("invalid_input", f"{label} must be finite")
    return number


def _fault_status(exc: GroundFault) -> str:
    if exc.error.code == "cancelled":
        return "cancelled"
    if exc.error.code in {"expired_deadline", "timeout"}:
        return "timeout"
    return "failed"


def _read_task(task: asyncio.Task[object]) -> tuple[object, BaseException | None]:
    if not task.done():
        return None, None
    if task.cancelled():
        return None, asyncio.CancelledError()
    try:
        return task.result(), None
    except Exception as exc:
        return None, exc


def _drain(task: asyncio.Task[object]) -> None:
    if not task.done():
        return
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        return


def _is_awaitable(value: object) -> bool:
    return isinstance(value, Awaitable)
