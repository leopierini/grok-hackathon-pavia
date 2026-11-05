from __future__ import annotations

from patrol.ground.operator.policy import LIVE_BLOCKERS, Gate, action_map, next_instruction


def gate(**overrides: object) -> Gate:
    base = dict(
        mode="simulation",
        phase="IDLE",
        armed=False,
        worker="idle",
        closed=False,
        halt_latched=False,
        recovery_required=False,
        goal_reached=False,
        landing_verified=False,
        controlled_motion=None,
        real_modes=False,
        config_ok=True,
    )
    base.update(overrides)
    return Gate(**base)  # type: ignore[arg-type]


def test_halt_is_enabled_without_a_confirmation_requirement() -> None:
    actions = action_map(gate(worker="running", phase="SCOUT"))
    assert actions["halt"]["enabled"] is True
    assert "immediately" in str(actions["halt"]["reason"])


def test_start_requires_arm_and_rejects_a_running_worker() -> None:
    idle = action_map(gate())
    assert idle["start"]["enabled"] is False
    armed = action_map(gate(armed=True))
    assert armed["start"]["enabled"] is True
    running = action_map(gate(armed=True, worker="running", phase="SCOUT"))
    assert running["start"]["enabled"] is False


def test_live_mode_does_not_enable_simulation() -> None:
    actions = action_map(gate(mode="live"))
    assert actions["arm"]["enabled"] is False
    assert actions["start"]["enabled"] is False
    assert LIVE_BLOCKERS[0] in str(actions["start"]["reason"])
    assert "fake" not in str(actions["start"]["reason"]).lower() or "not replaced" in str(actions["start"]["reason"])


def test_reset_requires_recovery_context() -> None:
    assert action_map(gate())["reset"]["enabled"] is False
    done = action_map(gate(phase="DONE", goal_reached=True, landing_verified=True, worker="finished"))
    assert done["reset"]["enabled"] is True
    faulted = action_map(
        gate(phase="FAULT", goal_reached=True, landing_verified=False, recovery_required=True, worker="finished")
    )
    assert faulted["reset"]["enabled"] is True
    assert "token" in str(faulted["reset"]["reason"])


def test_next_instruction_keeps_goal_and_landing_apart() -> None:
    text = next_instruction(
        gate(phase="FAULT", goal_reached=True, landing_verified=False, recovery_required=True, worker="finished")
    )
    assert "unknown landing" in text
