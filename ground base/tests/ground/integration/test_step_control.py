from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.paths import repo_root
from patrol.ground.steps import (
    Reconciliation,
    SessionStopped,
    StepAttempt,
    StepControlError,
    StepRejected,
    StepSession,
    StepSpec,
)


async def settle() -> None:
    for _ in range(15):
        await asyncio.sleep(0)


def row(session: StepSession, index: int = -1) -> Any:
    return session.get_snapshot()["steps"][index]  # type: ignore[index]


async def command(session: StepSession, action: str, **kwargs: object) -> dict[str, Any]:
    snapshot = session.get_snapshot()
    request: dict[str, object] = {
        "action": action,
        "request_id": f"request-{snapshot['revision']}-{action}",
        "expected_revision": snapshot["revision"],
        **kwargs,
    }
    if action in {"wait_more", "retry"}:
        request.update(
            step_id=row(session)["step_id"], attempt_id=row(session)["attempts"][-1]["attempt_id"]
        )
    return await session.command(request)


def test_wait_more_preserves_worker_and_does_not_repeat_command() -> None:
    async def scenario() -> None:
        clock = ManualClock()
        session = StepSession([StepSpec("takeoff", "Take off", 3, 30, "reconcile")], clock=clock)
        release = asyncio.Event()
        calls: list[StepAttempt] = []

        async def operation(attempt: StepAttempt) -> str:
            calls.append(attempt)
            assert attempt.run_context().deadline_monotonic == 30
            await release.wait()
            return "airborne"

        runner = asyncio.create_task(session.run_step("takeoff", operation))
        await settle()
        clock.advance(3)
        await settle()
        assert row(session)["status"] == "awaiting_operator"
        assert not calls[0].cancel.is_set()
        assert (await command(session, "retry"))["error"]["code"] == "retry_unavailable"
        response = await command(session, "wait_more", seconds=10)
        assert response["ok"] is True
        assert row(session)["status"] == "running"
        clock.advance(4)
        release.set()
        await settle()
        assert await runner == "airborne"
        assert len(calls) == 1
        assert calls[0].deadline_monotonic == 30
        assert session.get_snapshot()["completed_steps"] == ["takeoff"]
        await session.close()

    asyncio.run(scenario())


def test_late_success_requires_explicit_wait_then_continues_next_step() -> None:
    async def scenario() -> None:
        clock = ManualClock()
        session = StepSession(
            [StepSpec("photo", "Photo"), StepSpec("vision", "Vision")], clock=clock
        )
        release = asyncio.Event()

        async def photo(_: StepAttempt) -> str:
            await release.wait()
            return "frame-1"

        async def vision(_: StepAttempt) -> str:
            return "target"

        runner = asyncio.create_task(session.run_step("photo", photo))
        await settle()
        clock.advance(4)
        release.set()
        await settle()
        assert not runner.done()
        assert row(session, 0)["reason"] == "late_result"
        current = row(session, 0)
        result = await session.command(
            {
                "action": "wait_more",
                "request_id": "extend-photo",
                "expected_revision": session.get_snapshot()["revision"],
                "step_id": "photo",
                "attempt_id": current["attempts"][-1]["attempt_id"],
                "seconds": 2,
            }
        )
        assert result["ok"] is True
        assert await runner == "frame-1"
        assert await session.run_step("vision", vision) == "target"
        assert await session.run_step("photo", photo) == "frame-1"
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("completed", [0, 1, 49, 50])
@pytest.mark.parametrize("seed", [0, 7, 29])
def test_manual_retry_preserves_all_completed_checkpoints(completed: int, seed: int) -> None:
    async def scenario() -> None:
        clock = ManualClock()
        specs = [
            StepSpec(f"step-{i}", f"Stage {i}", retry_mode="idempotent")
            for i in range(completed + 1)
        ]
        session = StepSession(specs, clock=clock, session_id=f"simulation-{seed}-{completed}")
        calls: list[tuple[str, str]] = []

        async def operation(attempt: StepAttempt) -> str:
            calls.append((attempt.step_id, attempt.command_id))
            if attempt.step_id == f"step-{completed}" and attempt.number == 1:
                raise ConnectionError("synthetic dropped reply")
            return attempt.step_id

        for i in range(completed):
            assert await session.run_step(f"step-{i}", operation) == f"step-{i}"
        runner = asyncio.create_task(session.run_step(f"step-{completed}", operation))
        await settle()
        assert row(session)["status"] == "failed"
        response = await command(session, "retry")
        assert response["ok"] is True
        assert await runner == f"step-{completed}"
        assert len(calls) == completed + 2
        assert len({identity for _, identity in calls}) == len(calls)
        assert len(session.get_snapshot()["completed_steps"]) == completed + 1
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["completed", "not_executed", "unknown"])
def test_motion_retry_requires_backend_reconciliation(outcome: str) -> None:
    async def scenario() -> None:
        session = StepSession([StepSpec("takeoff", "Take off", retry_mode="reconcile")])
        calls: list[str] = []
        checks: list[str] = []

        async def takeoff(attempt: StepAttempt) -> str:
            calls.append(attempt.command_id)
            if attempt.number == 1:
                raise ConnectionError("ack missing")
            return "new airborne"

        async def reconcile(attempt: StepAttempt) -> Reconciliation:
            checks.append(attempt.command_id)
            return Reconciliation(outcome, "verified airborne")  # type: ignore[arg-type]

        runner = asyncio.create_task(session.run_step("takeoff", takeoff, reconcile=reconcile))
        await settle()
        response = await command(session, "retry")
        if outcome == "unknown":
            assert response["error"]["code"] == "effect_unknown"
            assert len(calls) == 1
            await command(session, "halt", reason="stop demo")
            with pytest.raises(SessionStopped):
                await runner
        else:
            assert response["ok"] is True
            assert await runner == (
                "verified airborne" if outcome == "completed" else "new airborne"
            )
            assert len(calls) == (1 if outcome == "completed" else 2)
        assert checks == [calls[0]]
        await session.close()

    asyncio.run(scenario())


def test_hard_timeout_never_accepts_late_result_or_overlaps_workers() -> None:
    async def scenario() -> None:
        clock = ManualClock()
        session = StepSession([StepSpec("capture", "Capture", 3, 8, "idempotent")], clock=clock)
        release = asyncio.Event()
        calls: list[StepAttempt] = []

        async def resistant(attempt: StepAttempt) -> str:
            calls.append(attempt)
            if attempt.number == 1:
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
            return "new" if attempt.number == 2 else "expired"

        runner = asyncio.create_task(session.run_step("capture", resistant))
        await settle()
        assert (await command(session, "wait_more", seconds=9))["error"]["code"] == "hard_limit"
        clock.advance(8)
        await settle()
        assert row(session)["status"] == "hard_timeout"
        assert calls[0].cancel.is_set()
        assert row(session)["attempts"][-1]["pending"] is True
        assert (await command(session, "retry"))["ok"] is False
        release.set()
        await settle()
        assert row(session)["status"] == "hard_timeout"
        assert (await command(session, "wait_more", seconds=1))["ok"] is False
        assert (await command(session, "retry"))["ok"] is True
        assert await runner == "new"
        assert len(calls) == 2
        await session.close()

    asyncio.run(scenario())


def test_double_click_stale_revision_and_old_attempt_are_rejected() -> None:
    async def scenario() -> None:
        session = StepSession([StepSpec("network", "Network", retry_mode="idempotent")])
        release = asyncio.Event()

        async def operation(attempt: StepAttempt) -> str:
            if attempt.number == 1:
                raise ConnectionError()
            await release.wait()
            return "connected"

        runner = asyncio.create_task(session.run_step("network", operation))
        await settle()
        snapshot = session.get_snapshot()
        old = row(session)["attempts"][-1]["attempt_id"]
        request = {
            "action": "retry",
            "request_id": "double-click",
            "expected_revision": snapshot["revision"],
            "step_id": "network",
            "attempt_id": old,
        }
        assert (await session.command(request))["ok"] is True
        assert (await session.command(request))["replayed"] is True
        assert (await session.command({**request, "action": "wait_more", "seconds": 1}))["error"][
            "code"
        ] == "request_conflict"
        assert (await session.command({**request, "request_id": "another"}))["error"][
            "code"
        ] == "stale_revision"
        assert (
            await session.command(
                {
                    **request,
                    "request_id": "old-attempt",
                    "expected_revision": session.get_snapshot()["revision"],
                }
            )
        )["error"]["code"] == "stale_attempt"
        release.set()
        assert await runner == "connected"
        assert len(row(session)["attempts"]) == 2
        json.dumps(session.get_snapshot(), allow_nan=False)
        await session.close()

    asyncio.run(scenario())


def test_halt_wins_during_reconciliation_and_cannot_be_reset_by_retry() -> None:
    async def scenario() -> None:
        session = StepSession([StepSpec("move", "Move", retry_mode="reconcile")])
        entered, release = asyncio.Event(), asyncio.Event()
        calls: list[str] = []

        async def operation(attempt: StepAttempt) -> None:
            calls.append(attempt.command_id)
            raise ConnectionError()

        async def reconcile(_: StepAttempt) -> Reconciliation:
            entered.set()
            await release.wait()
            return Reconciliation("not_executed")

        runner = asyncio.create_task(session.run_step("move", operation, reconcile=reconcile))
        await settle()
        retry = asyncio.create_task(command(session, "retry"))
        await entered.wait()
        assert (await command(session, "halt", reason="emergency"))["ok"] is True
        release.set()
        assert (await retry)["error"]["code"] == "session_stopped"
        with pytest.raises(SessionStopped):
            await runner
        assert len(calls) == 1
        assert (await command(session, "retry"))["ok"] is False
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("cause", ["mission", "authority", "notify", "cancel"])
def test_shutdown_paths_keep_checkpoint_and_cancel_current_attempt(cause: str) -> None:
    async def scenario() -> None:
        clock = ManualClock()
        authority = [False]
        session = StepSession(
            [StepSpec("wait", "Wait")],
            clock=clock,
            mission_limit_s=5,
            is_halted=lambda: authority[0],
        )

        async def operation(_: StepAttempt) -> None:
            await asyncio.Event().wait()

        runner = asyncio.create_task(session.run_step("wait", operation))
        await settle()
        if cause == "mission":
            clock.advance(5)
        elif cause == "authority":
            authority[0] = True
            session.get_snapshot()
        elif cause == "notify":
            session.notify_halt()
        else:
            runner.cancel()
        await settle()
        with pytest.raises((SessionStopped, asyncio.CancelledError)):
            await runner
        assert session.get_snapshot()["halted"] is True
        assert row(session)["allowed_actions"] == {
            "wait_more": False,
            "retry": False,
            "set_budget": False,
        }
        await session.close()

    asyncio.run(scenario())


def test_budget_updates_are_atomic_and_policy_failures_are_not_retryable() -> None:
    async def scenario() -> None:
        session = StepSession([StepSpec("a", "A", retry_mode="idempotent"), StepSpec("b", "B")])
        bad = await command(
            session,
            "set_budgets",
            budgets=[
                {"step_id": "a", "wait_s": 5, "hard_limit_s": 10},
                {"step_id": "b", "wait_s": 20, "hard_limit_s": 10},
            ],
        )
        assert bad["ok"] is False
        assert row(session, 0)["wait_s"] == 3
        assert (
            await command(
                session,
                "set_budgets",
                budgets=[
                    {"step_id": "a", "wait_s": 5, "hard_limit_s": 10},
                ],
            )
        )["ok"] is True

        async def reject(_: StepAttempt) -> None:
            raise StepRejected("invalid evidence")

        runner = asyncio.create_task(session.run_step("a", reject))
        await settle()
        assert row(session, 0)["reason"] == "policy_rejected"
        assert row(session, 0)["allowed_actions"]["retry"] is False
        await command(session, "halt", reason="invalid evidence")
        with pytest.raises(StepRejected):
            await runner
        await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change",
    [
        {"wait_s": 0},
        {"wait_s": True},
        {"wait_s": float("nan")},
        {"hard_limit_s": float("inf")},
        {"hard_limit_s": 301},
        {"retry_mode": "always"},
        {"max_attempts": 0},
        {"max_attempts": True},
        {"step_id": "../motor"},
        {"label": ""},
    ],
)
def test_invalid_specs(change: dict[str, Any]) -> None:
    with pytest.raises(StepControlError):
        StepSession([replace(StepSpec("safe", "Safe"), **change)])


def test_json_schema_matches_operator_commands_and_rejects_client_safety_claims() -> None:
    schema = json.loads((repo_root() / "contracts/step-control.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    common = {"request_id": "unique-click", "expected_revision": 42}
    requests = [
        {"action": "snapshot"},
        {
            "action": "wait_more",
            **common,
            "step_id": "photo",
            "attempt_id": "attempt-1",
            "seconds": 5,
        },
        {"action": "retry", **common, "step_id": "photo", "attempt_id": "attempt-1"},
        {"action": "halt", **common, "reason": "operator halt"},
        {
            "action": "set_budgets",
            **common,
            "budgets": [
                {"step_id": "photo", "wait_s": 5, "hard_limit_s": 10},
            ],
        },
    ]
    for payload in requests:
        assert list(validator.iter_errors(payload)) == []
        assert list(validator.iter_errors({**payload, "safe_to_retry": True}))


def test_late_evidence_is_revalidated_before_checkpoint_acceptance() -> None:
    async def scenario() -> None:
        clock = ManualClock()
        session = StepSession([StepSpec("photo", "Photo", 1, 10)], clock=clock)
        release = asyncio.Event()
        checked: list[float] = []

        async def operation(_: StepAttempt) -> str:
            await release.wait()
            return "expired frame"

        def validate(_: StepAttempt, value: object) -> None:
            checked.append(clock.monotonic())
            if clock.monotonic() >= 3:
                raise StepRejected("frame expired")

        runner = asyncio.create_task(session.run_step("photo", operation, validate_result=validate))
        await settle()
        clock.advance(2)
        release.set()
        await settle()
        assert row(session)["status"] == "awaiting_operator"
        clock.advance(2)
        assert (await command(session, "wait_more", seconds=1))["ok"] is True
        with pytest.raises(StepRejected):
            await runner
        assert checked == [4]
        assert session.get_snapshot()["completed_steps"] == []
        with pytest.raises(StepControlError):
            await session.run_step("photo", operation)
        await session.close()

    asyncio.run(scenario())


def test_attempt_limit_and_step_order_prevent_unbounded_replays() -> None:
    async def scenario() -> None:
        session = StepSession(
            [
                StepSpec("network", "Network", retry_mode="idempotent", max_attempts=2),
                StepSpec("photo", "Photo"),
            ]
        )

        async def fail(_: StepAttempt) -> None:
            raise ConnectionError()

        with pytest.raises(StepControlError):
            await session.run_step("photo", fail)
        runner = asyncio.create_task(session.run_step("network", fail))
        await settle()
        with pytest.raises(StepControlError):
            await session.run_step("network", fail)
        state = row(session, 0)
        response = await session.command(
            {
                "action": "retry",
                "request_id": "second",
                "expected_revision": session.get_snapshot()["revision"],
                "step_id": "network",
                "attempt_id": state["attempts"][-1]["attempt_id"],
            }
        )
        assert response["ok"] is True
        await settle()
        assert len(row(session, 0)["attempts"]) == 2
        assert row(session, 0)["allowed_actions"]["retry"] is False
        session.notify_halt()
        with pytest.raises(SessionStopped):
            await runner
        await session.close()

    asyncio.run(scenario())


def test_dynamic_steps_safety_binding_and_snapshot_are_detached() -> None:
    async def scenario() -> None:
        clock = ManualClock()
        safety: list[str] = []
        session = StepSession([], clock=clock)
        session.bind_safety(lambda: False, safety.append)
        session.add_step(StepSpec("connect", "Connect"))

        async def operation(_: StepAttempt) -> str:
            return "connected"

        assert await session.run_step("connect", operation) == "connected"
        events = session.events()
        events[0]["event"] = "tampered"
        assert session.events()[0]["event"] == "session_created"
        assert (await session.close())["closed"] is True
        clock.advance(500)
        assert session.get_snapshot()["halted"] is False
        assert safety == []
        with pytest.raises(SessionStopped):
            session.add_step(StepSpec("late", "Late"))

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"action": "execute", "code": "takeoff"},
        {"action": "snapshot", "extra": True},
        {"action": "retry"},
        {"action": "snapshot", "safe_to_retry": True},
    ],
)
def test_json_rejects_unknown_or_incomplete_commands(payload: dict[str, object]) -> None:
    async def scenario() -> None:
        session = StepSession([StepSpec("a", "A")])
        assert (await session.command(payload))["ok"] is False
        assert (await session.command({"action": "snapshot"}))["ok"] is True
        await session.close()

    asyncio.run(scenario())
