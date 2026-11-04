"""Operator-controlled, sequential steps with separate soft and hard deadlines.

This is an in-process backend API. Use one asyncio loop per session. Operations
and reconciliation callbacks are installed by trusted backend code, never JSON.
An operator timeout does not cancel an operation or repeat a motor command.
"""

from __future__ import annotations

import asyncio
import copy
import json
import math
import re
import threading
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal
from uuid import uuid4

from patrol.contract import RunContext
from patrol.ground.kernel.clock import RealClock
from patrol.ground.kernel.contracts import Clock

RetryMode = Literal["idempotent", "reconcile", "never"]
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class StepControlError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(detail)


class StepRejected(RuntimeError):
    """A policy rejection. Waiting or replaying cannot make invalid evidence valid."""


class SessionStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class StepSpec:
    step_id: str
    label: str
    wait_s: float = 3.0
    hard_limit_s: float = 30.0
    retry_mode: RetryMode = "never"
    max_attempts: int = 3


@dataclass(frozen=True)
class StepAttempt:
    session_id: str
    step_id: str
    attempt_id: str
    number: int
    command_id: str
    deadline_monotonic: float
    cancel: threading.Event

    def run_context(self) -> RunContext:
        return RunContext(self.session_id, self.deadline_monotonic, self.cancel)


@dataclass(frozen=True)
class Reconciliation:
    """Trusted, fresh device evidence: complete, safe to retry, or still unknown."""

    outcome: Literal["completed", "not_executed", "unknown"]
    value: object = None


Operation = Callable[[StepAttempt], Awaitable[object]]
Reconciler = Callable[[StepAttempt], Awaitable[Reconciliation]]
ResultValidator = Callable[[StepAttempt, object], None]


@dataclass
class _Attempt:
    context: StepAttempt
    started: float
    soft_deadline: float
    task: asyncio.Task[None] | None = None
    finished: float | None = None
    value: object = None
    error: str | None = None
    retryable: bool = True
    hard_expired: bool = False


@dataclass
class _Step:
    spec: StepSpec
    status: str = "pending"
    reason: str = ""
    attempts: list[_Attempt] = field(default_factory=list)
    operation: Operation | None = None
    reconcile: Reconciler | None = None
    validate_result: ResultValidator | None = None
    value: object = None


def _number(value: object, name: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise StepControlError("invalid_input", f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= maximum:
        raise StepControlError("invalid_input", f"{name} must be > 0 and <= {maximum}")
    return number


def _token(value: object, name: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise StepControlError("invalid_input", f"{name} must be a bounded identifier")
    return value


def _validate(spec: StepSpec) -> None:
    _token(spec.step_id, "step_id")
    if not isinstance(spec.label, str) or not 1 <= len(spec.label) <= 200:
        raise StepControlError("invalid_input", "label is required and at most 200 characters")
    wait = _number(spec.wait_s, "wait_s", 300)
    hard = _number(spec.hard_limit_s, "hard_limit_s", 300)
    if wait > hard:
        raise StepControlError("invalid_input", "wait_s cannot exceed hard_limit_s")
    if spec.retry_mode not in {"idempotent", "reconcile", "never"}:
        raise StepControlError("invalid_input", "unknown retry_mode")
    if isinstance(spec.max_attempts, bool) or not isinstance(spec.max_attempts, int):
        raise StepControlError("invalid_input", "max_attempts must be an integer")
    if not 1 <= spec.max_attempts <= 10:
        raise StepControlError("invalid_input", "max_attempts must be between 1 and 10")


class StepSession:
    def __init__(
        self,
        specs: Sequence[StepSpec],
        *,
        session_id: str | None = None,
        mission_limit_s: float = 180.0,
        clock: Clock | None = None,
        is_halted: Callable[[], bool] = lambda: False,
        on_halt: Callable[[str], None] | None = None,
    ) -> None:
        if len(specs) > 4096:
            raise StepControlError("invalid_input", "a session permits at most 4096 steps")
        for spec in specs:
            _validate(spec)
        if len({spec.step_id for spec in specs}) != len(specs):
            raise StepControlError("invalid_input", "duplicate step_id")
        self.session_id = _token(session_id or uuid4().hex, "session_id")
        self.clock = clock or RealClock()
        self.started = self.clock.monotonic()
        self.deadline = self.started + _number(mission_limit_s, "mission_limit_s", 3600)
        self._is_halted = is_halted
        self._on_halt = on_halt
        self._steps = {spec.step_id: _Step(spec) for spec in specs}
        self._active: str | None = None
        self._halted = False
        self._closed = False
        self._revision = 0
        self._signal = asyncio.Event()
        self._events: list[dict[str, object]] = []
        self._requests: dict[str, tuple[str, dict[str, object]]] = {}
        self._inflight: set[str] = set()
        self._queries: set[asyncio.Task[Reconciliation]] = set()
        self._record("session_created")

    def _record(self, event: str, **data: object) -> None:
        self._revision += 1
        self._events.append(
            {"seq": self._revision, "monotonic_s": self.clock.monotonic(), "event": event, **data}
        )
        self._signal.set()

    def _state(self, state: _Step, status: str, reason: str = "") -> None:
        if (state.status, state.reason) != (status, reason):
            state.status, state.reason = status, reason
            self._record("step_state", step_id=state.spec.step_id, status=status, reason=reason)

    def _stop(self, reason: str) -> None:
        if self._halted or self._closed:
            return
        self._halted = True
        for query in self._queries:
            query.cancel()
        if self._on_halt is not None:
            try:
                self._on_halt(reason)
            except Exception as exc:
                self._record("safety_callback_failed", error=type(exc).__name__)
        for state in self._steps.values():
            if state.attempts:
                attempt = state.attempts[-1]
                attempt.context.cancel.set()
                if attempt.task is not None and not attempt.task.done():
                    attempt.task.cancel()
            if state.status != "succeeded":
                self._state(state, "halted", reason)
        self._record("session_halted", reason=reason)

    def _refresh(self) -> None:
        if self._halted or self._closed:
            return
        if self._is_halted():
            self._stop("authority_halted")
            return
        if self.clock.monotonic() >= self.deadline:
            self._stop("mission_deadline")
            return
        if self._active is None:
            return
        state = self._steps[self._active]
        attempt = state.attempts[-1]
        if state.status == "succeeded" or attempt.hard_expired:
            return
        now = self.clock.monotonic()
        if attempt.finished is not None and attempt.finished < attempt.soft_deadline:
            if attempt.error is not None:
                self._state(state, "failed", attempt.error)
            else:
                self._accept(state, attempt.value)
        elif now >= attempt.context.deadline_monotonic:
            attempt.hard_expired = True
            attempt.context.cancel.set()
            if attempt.task is not None and not attempt.task.done():
                attempt.task.cancel()
            self._state(state, "hard_timeout", "hard_deadline")
        elif attempt.finished is not None:
            self._state(
                state,
                "failed" if attempt.error else "awaiting_operator",
                attempt.error or "late_result",
            )
        elif now >= attempt.soft_deadline:
            self._state(state, "awaiting_operator", "wait_budget_exhausted")

    async def _worker(self, state: _Step, attempt: _Attempt) -> None:
        try:
            assert state.operation is not None
            attempt.value = await state.operation(attempt.context)
        except asyncio.CancelledError:
            attempt.error, attempt.retryable = "cancelled", False
        except StepRejected:
            attempt.error, attempt.retryable = "policy_rejected", False
        except Exception as exc:
            # Raw exception text may contain credentials or device addresses.
            attempt.error = type(exc).__name__
        finally:
            attempt.finished = self.clock.monotonic()
            self._record(
                "attempt_finished",
                step_id=state.spec.step_id,
                attempt_id=attempt.context.attempt_id,
                error=attempt.error,
            )

    def _launch(self, state: _Step) -> None:
        now = self.clock.monotonic()
        identity = uuid4().hex
        context = StepAttempt(
            self.session_id,
            state.spec.step_id,
            identity,
            len(state.attempts) + 1,
            f"step-{identity}",
            min(now + state.spec.hard_limit_s, self.deadline),
            threading.Event(),
        )
        attempt = _Attempt(context, now, min(now + state.spec.wait_s, context.deadline_monotonic))
        state.attempts.append(attempt)
        self._state(state, "running")
        attempt.task = asyncio.create_task(self._worker(state, attempt))
        self._record("attempt_started", step_id=state.spec.step_id, attempt_id=identity)

    async def run_step(
        self,
        step_id: str,
        operation: Operation,
        *,
        reconcile: Reconciler | None = None,
        validate_result: ResultValidator | None = None,
    ) -> object:
        """Run one stage. Soft failures park here until an operator acts or halt wins."""
        self._refresh()
        if self._halted or self._closed:
            raise SessionStopped("session stopped")
        if self._active is not None:
            raise StepControlError("step_busy", "another run_step call owns this session")
        state = self._get(step_id)
        if state.status == "succeeded":
            return state.value
        if state.status != "pending":
            raise StepControlError("step_locked", "use the operator controls for a failed step")
        first_pending = next(s for s in self._steps.values() if s.status != "succeeded")
        if first_pending is not state:
            raise StepControlError("step_order", "earlier steps must complete first")
        state.operation, state.reconcile = operation, reconcile
        state.validate_result = validate_result
        self._active = step_id
        self._launch(state)
        try:
            while True:
                self._signal.clear()
                self._refresh()
                if self._halted:
                    raise SessionStopped("session stopped")
                if state.status == "succeeded":
                    return state.value
                if state.status == "failed" and state.reason == "policy_rejected":
                    raise StepRejected("stage policy rejected the input")
                attempt = state.attempts[-1]
                deadlines = [self.deadline]
                if not attempt.hard_expired and state.status != "failed":
                    deadlines.append(attempt.context.deadline_monotonic)
                    if state.status == "running":
                        deadlines.append(attempt.soft_deadline)
                delay = max(0.0, min(deadlines) - self.clock.monotonic())
                timer = asyncio.create_task(self.clock.sleep(delay))
                signal = asyncio.create_task(self._signal.wait())
                try:
                    await asyncio.wait((timer, signal), return_when=asyncio.FIRST_COMPLETED)
                finally:
                    timer.cancel()
                    signal.cancel()
                    await asyncio.gather(timer, signal, return_exceptions=True)
        except asyncio.CancelledError:
            self._stop("runner_cancelled")
            raise
        finally:
            self._active = None

    def _get(self, step_id: object) -> _Step:
        key = _token(step_id, "step_id")
        if key not in self._steps:
            raise StepControlError("unknown_step", "step_id is not in this session")
        return self._steps[key]

    def _accept(self, state: _Step, value: object) -> None:
        try:
            if state.validate_result is not None:
                state.validate_result(state.attempts[-1].context, value)
        except Exception:
            state.attempts[-1].error = "policy_rejected"
            state.attempts[-1].retryable = False
            self._state(state, "failed", "policy_rejected")
            return
        state.value = value
        self._state(state, "succeeded")

    def add_step(self, spec: StepSpec) -> None:
        """Trusted workflow hook for loops whose iteration count is not known upfront."""
        self._refresh()
        _validate(spec)
        if self._halted or self._closed:
            raise SessionStopped("session stopped")
        if spec.step_id in self._steps or len(self._steps) >= 4096:
            raise StepControlError("invalid_input", "duplicate step or step limit reached")
        self._steps[spec.step_id] = _Step(spec)
        self._record("step_added", step_id=spec.step_id)

    def notify_halt(self, reason: str = "authority_halted") -> None:
        """Call immediately alongside the existing physical safety controller."""
        self._stop(reason)

    def bind_safety(self, is_halted: Callable[[], bool], on_halt: Callable[[str], None]) -> None:
        """Bind the existing safety authority before any backend operation starts."""
        if self._active is not None:
            raise StepControlError("step_busy", "safety must be bound before starting")
        self._is_halted, self._on_halt = is_halted, on_halt
        if self._halted:
            on_halt("session_already_halted")

    def _actions(self, state: _Step) -> dict[str, bool]:
        if self._halted or self._closed:
            return {"set_budget": False, "wait_more": False, "retry": False}
        attempt = state.attempts[-1] if state.attempts else None
        can_retry = (
            attempt is not None
            and state.status in {"failed", "hard_timeout", "awaiting_operator"}
            and attempt.task is not None
            and attempt.task.done()
            and (attempt.retryable or attempt.hard_expired)
            and len(state.attempts) < state.spec.max_attempts
            and not any(not query.done() for query in self._queries)
            and (
                state.spec.retry_mode == "idempotent"
                or (state.spec.retry_mode == "reconcile" and state.reconcile is not None)
            )
            # A late success is accepted with wait_more, never repeated.
            and (attempt.error is not None or attempt.hard_expired)
        )
        return {
            "set_budget": state.status == "pending",
            "wait_more": (
                attempt is not None
                and not attempt.hard_expired
                and state.status in {"running", "awaiting_operator"}
                and attempt.error is None
                and self.clock.monotonic() < attempt.context.deadline_monotonic
                and attempt.soft_deadline < attempt.context.deadline_monotonic
            ),
            "retry": can_retry,
        }

    def get_snapshot(self) -> dict[str, object]:
        self._refresh()
        now = self.clock.monotonic()
        rows: list[dict[str, object]] = []
        for state in self._steps.values():
            attempts: list[dict[str, object]] = []
            for attempt in state.attempts:
                attempts.append(
                    {
                        "attempt_id": attempt.context.attempt_id,
                        "number": attempt.context.number,
                        "command_id": attempt.context.command_id,
                        "elapsed_s": max(
                            0.0,
                            (now if attempt.finished is None else attempt.finished)
                            - attempt.started,
                        ),
                        "wait_remaining_s": max(0.0, attempt.soft_deadline - now),
                        "hard_remaining_s": max(0.0, attempt.context.deadline_monotonic - now),
                        "max_extension_s": max(
                            0.0,
                            attempt.context.deadline_monotonic - max(now, attempt.soft_deadline),
                        ),
                        "pending": attempt.task is not None and not attempt.task.done(),
                        "error": attempt.error,
                        "hard_expired": attempt.hard_expired,
                    }
                )
            rows.append(
                {
                    "step_id": state.spec.step_id,
                    "label": state.spec.label,
                    "status": state.status,
                    "reason": state.reason,
                    "wait_s": state.spec.wait_s,
                    "hard_limit_s": state.spec.hard_limit_s,
                    "retry_mode": state.spec.retry_mode,
                    "max_attempts": state.spec.max_attempts,
                    "allowed_actions": self._actions(state),
                    "attempts": attempts,
                }
            )
        return {
            "schema_version": "ground-step-control-v1",
            "session_id": self.session_id,
            "revision": self._revision,
            "halted": self._halted,
            "closed": self._closed,
            "pending_reconciliations": sum(not query.done() for query in self._queries),
            "active_step_id": self._active,
            "mission_remaining_s": max(0.0, self.deadline - now),
            "completed_steps": [
                s.spec.step_id for s in self._steps.values() if s.status == "succeeded"
            ],
            "steps": rows,
        }

    def events(self) -> list[dict[str, object]]:
        return copy.deepcopy(self._events)

    async def command(self, request: Mapping[str, object]) -> dict[str, object]:
        """Strict JSON facade. Mutations need request_id and expected_revision."""
        request_id: str | None = None
        fingerprint = ""
        reserved = False
        try:
            if not isinstance(request, Mapping):
                raise StepControlError("invalid_input", "command must be an object")
            action = request.get("action")
            fields = {
                "snapshot": set(),
                "set_budgets": {"budgets"},
                "wait_more": {"step_id", "attempt_id", "seconds"},
                "retry": {"step_id", "attempt_id"},
                "halt": {"reason"},
            }
            if not isinstance(action, str) or action not in fields:
                raise StepControlError("invalid_input", "unknown action")
            common = (
                {"action"}
                if action == "snapshot"
                else {"action", "request_id", "expected_revision"}
            )
            if set(request) != common | fields[action]:
                raise StepControlError("invalid_input", "command has missing or unknown fields")
            if action == "snapshot":
                return {"ok": True, "snapshot": self.get_snapshot()}
            request_id = _token(request.get("request_id"), "request_id")
            try:
                fingerprint = json.dumps(dict(request), sort_keys=True, allow_nan=False)
            except (ValueError, TypeError) as exc:
                raise StepControlError("invalid_input", "command must contain finite JSON") from exc
            if len(fingerprint) > 65536:
                raise StepControlError("invalid_input", "command exceeds 64 KiB")
            if request_id in self._requests:
                previous, response = self._requests[request_id]
                if fingerprint != previous:
                    raise StepControlError(
                        "request_conflict", "request_id was used for another command"
                    )
                return {**copy.deepcopy(response), "replayed": True}
            if request_id in self._inflight:
                raise StepControlError("request_pending", "this request is still reconciling")
            if len(self._requests) >= 4096:
                raise StepControlError("request_limit", "session request limit reached")
            self._refresh()
            revision = request.get("expected_revision")
            if isinstance(revision, bool) or not isinstance(revision, int):
                raise StepControlError("invalid_input", "expected_revision must be an integer")
            # Halt remains immediate even if the UI's snapshot is slightly stale.
            if action != "halt" and revision != self._revision:
                raise StepControlError("stale_revision", "read a fresh snapshot before changing it")
            if self._halted or self._closed:
                raise StepControlError(
                    "session_stopped", "halt or mission deadline is authoritative"
                )
            self._inflight.add(request_id)
            reserved = True
            if action == "set_budgets":
                self._budgets(request["budgets"])
            elif action == "halt":
                reason = request["reason"]
                if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 200:
                    raise StepControlError(
                        "invalid_input", "halt reason is required (max 200 characters)"
                    )
                self._stop("operator_halt")
            else:
                state = self._get(request["step_id"])
                if (
                    not state.attempts
                    or request["attempt_id"] != state.attempts[-1].context.attempt_id
                ):
                    raise StepControlError(
                        "stale_attempt", "command targets an old or missing attempt"
                    )
                if action == "wait_more":
                    self._extend(state, request["seconds"])
                else:
                    await self._retry(state)
            response = {"ok": True, "snapshot": self.get_snapshot()}
            self._requests[request_id] = (fingerprint, copy.deepcopy(response))
            return response
        except StepControlError as exc:
            return {
                "ok": False,
                "error": {"code": exc.code, "detail": exc.detail},
                "snapshot": self.get_snapshot(),
            }
        finally:
            if reserved and request_id is not None:
                self._inflight.discard(request_id)

    def _budgets(self, raw: object) -> None:
        if not isinstance(raw, list) or not 1 <= len(raw) <= len(self._steps):
            raise StepControlError("invalid_input", "budgets must be a nonempty bounded array")
        changes: dict[str, StepSpec] = {}
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"step_id", "wait_s", "hard_limit_s"}:
                raise StepControlError(
                    "invalid_input", "budget needs step_id, wait_s, hard_limit_s"
                )
            state = self._get(item["step_id"])
            if not self._actions(state)["set_budget"] or state.spec.step_id in changes:
                raise StepControlError(
                    "budget_locked", "only distinct, pending steps can be configured"
                )
            spec = replace(state.spec, wait_s=item["wait_s"], hard_limit_s=item["hard_limit_s"])
            _validate(spec)
            changes[spec.step_id] = spec
        for key, spec in changes.items():
            self._steps[key].spec = spec
        self._record(
            "budgets_changed",
            budgets=[
                {"step_id": spec.step_id, "wait_s": spec.wait_s, "hard_limit_s": spec.hard_limit_s}
                for spec in changes.values()
            ],
        )

    def _extend(self, state: _Step, seconds: object) -> None:
        extra = _number(seconds, "seconds", 300)
        if not self._actions(state)["wait_more"]:
            raise StepControlError("wait_unavailable", "this attempt cannot be extended")
        attempt = state.attempts[-1]
        new_deadline = max(attempt.soft_deadline, self.clock.monotonic()) + extra
        if new_deadline > attempt.context.deadline_monotonic:
            raise StepControlError(
                "hard_limit", "extension exceeds the fixed operation/mission deadline"
            )
        attempt.soft_deadline = new_deadline
        self._record(
            "wait_extended",
            step_id=state.spec.step_id,
            seconds=extra,
            attempt_id=attempt.context.attempt_id,
        )
        self._state(state, "running")
        self._refresh()

    async def _retry(self, state: _Step) -> None:
        if not self._actions(state)["retry"]:
            raise StepControlError(
                "retry_unavailable", "retry requires a stopped worker and a retryable step"
            )
        attempt = state.attempts[-1]
        if state.spec.retry_mode == "reconcile":
            assert state.reconcile is not None
            self._record("reconciliation_started", step_id=state.spec.step_id)
            revision = self._revision

            async def get_proof() -> Reconciliation:
                assert state.reconcile is not None
                return await state.reconcile(attempt.context)

            query = asyncio.create_task(get_proof())
            self._queries.add(query)

            def finished(task: asyncio.Task[Reconciliation]) -> None:
                self._queries.discard(task)
                if not task.cancelled():
                    task.exception()

            query.add_done_callback(finished)
            try:
                done, _ = await asyncio.wait((query,), timeout=3.0)
                if not done:
                    query.cancel()
                    raise StepControlError(
                        "reconciliation_pending",
                        "status query exceeded its wait; retry remains locked",
                    )
                if query.cancelled():
                    raise StepControlError("session_stopped", "status query was cancelled")
                proof = query.result()
            except StepControlError:
                raise
            except asyncio.CancelledError:
                query.cancel()
                raise
            except Exception as exc:
                raise StepControlError(
                    "reconciliation_failed", "backend could not verify device status"
                ) from exc
            self._refresh()
            if self._halted or self._closed:
                raise StepControlError("session_stopped", "halt won during reconciliation")
            if revision != self._revision:
                raise StepControlError("stale_revision", "session changed during reconciliation")
            if not isinstance(proof, Reconciliation) or proof.outcome == "unknown":
                raise StepControlError("effect_unknown", "original command may still have executed")
            if proof.outcome == "completed":
                self._accept(state, proof.value)
                return
            if proof.outcome != "not_executed":
                raise StepControlError("effect_unknown", "unsupported reconciliation evidence")
        self._record(
            "retry_requested",
            step_id=state.spec.step_id,
            previous_attempt_id=attempt.context.attempt_id,
        )
        self._launch(state)

    async def close(self, grace_s: float = 0.2) -> dict[str, object]:
        """Bounded shutdown. A resistant worker remains visible as pending."""
        _number(grace_s, "grace_s", 3)
        if not self._closed:
            if any(state.status != "succeeded" for state in self._steps.values()):
                self._stop("session_closed")
            self._closed = True
            self._record("session_closed")
        tasks = [
            attempt.task
            for state in self._steps.values()
            for attempt in state.attempts
            if attempt.task is not None and not attempt.task.done()
        ]
        if tasks:
            await asyncio.wait(tasks, timeout=grace_s)
        if self._queries:
            await asyncio.wait(self._queries, timeout=grace_s)
        return self.get_snapshot()
