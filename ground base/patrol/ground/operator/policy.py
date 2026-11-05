"""Operator action admission. The UI displays this result; it does not decide it."""

from __future__ import annotations

from dataclasses import dataclass

LIVE_BLOCKERS = (
    "Live operation is refused.",
    "v2 teammate transport and factory bridges have not been supplied.",
    "Physical acceptance has not been performed.",
    "The v1 run_route and inspect APIs are not v2 RSSI or scouting transports.",
    "A failed real device is not replaced with a simulated device.",
)


@dataclass(frozen=True)
class Gate:
    mode: str
    phase: str
    armed: bool
    worker: str
    closed: bool
    halt_latched: bool
    recovery_required: bool
    goal_reached: bool
    landing_verified: bool
    controlled_motion: bool | None
    real_modes: bool
    config_ok: bool


def next_instruction(gate: Gate) -> str:
    if gate.closed:
        return "The operator session is closed. Start the local services again to open a new one."
    if gate.mode == "replay":
        return "This is a read-only replay. Return to simulation before arming another run."
    if gate.mode == "live" or gate.real_modes:
        return " ".join(LIVE_BLOCKERS)
    if gate.halt_latched or gate.recovery_required:
        return (
            "Halt or recovery is latched. Acceptance is not proof the robots stopped. "
            "Reset only after the documented recovery conditions, with a token when landing "
            "or another fault is unresolved. Dismissing this text does not clear an unknown landing."
        )
    if gate.worker == "running":
        return "A mission worker is running. Halt remains immediate. Do not start a second mission."
    if gate.phase == "DONE" and gate.goal_reached and gate.landing_verified:
        return "Goal and landing are both recorded for this run. Reset to open a disarmed session."
    if not gate.config_ok:
        return "Configuration is invalid. Fix it before arming. Invalid values stay rejected."
    if not gate.armed:
        return "Review readiness, then arm this session. Arm does not move the dog or the drone."
    return "Start the armed session. A second start, another tab, or a reload will not create another mission."


def action_map(gate: Gate) -> dict[str, dict[str, object]]:
    return {name: _decision(gate, name) for name in ("status", "arm", "start", "supervised", "halt", "reset", "quit")}


def _decision(gate: Gate, name: str) -> dict[str, object]:
    if name == "status":
        return {"enabled": True, "reason": "Status only reads the current session."}
    if gate.closed and name != "quit":
        return {"enabled": False, "reason": "The operator session is closed."}
    if name == "quit":
        if gate.closed:
            return {"enabled": False, "reason": "The session is already closed."}
        return {"enabled": True, "reason": "Quit latches halt, then closes this operator session."}
    if gate.mode == "replay":
        return {"enabled": False, "reason": "Replay cannot command devices or open a mission."}
    if name == "halt":
        if gate.halt_latched:
            return {
                "enabled": True,
                "reason": "Halt is already latched. Repeating it does not clear recovery or verify a stop.",
            }
        return {
            "enabled": True,
            "reason": "Halt submits immediately. Acceptance is separate from device delivery.",
        }
    if name in {"arm", "start", "supervised"} and (gate.mode == "live" or gate.real_modes):
        return {"enabled": False, "reason": " ".join(LIVE_BLOCKERS)}
    if not gate.config_ok and name in {"arm", "start"}:
        return {"enabled": False, "reason": "Configuration must validate before arm or start."}
    if name == "arm":
        if gate.worker == "running":
            return {"enabled": False, "reason": "A mission worker is already running."}
        if gate.halt_latched or gate.recovery_required:
            return {"enabled": False, "reason": "Reset the latched session before arming again."}
        if gate.armed:
            return {"enabled": False, "reason": "This session is already armed. Arm does not move anything."}
        if gate.phase not in {"IDLE", "DONE", "ABORTED", "FAULT"}:
            return {"enabled": False, "reason": "Arm is only available from an idle or finished session."}
        return {"enabled": True, "reason": "Arm permits this session only. It does not connect hardware or move."}
    if name == "start":
        if gate.worker == "running":
            return {"enabled": False, "reason": "One mission worker is already active."}
        if not gate.armed:
            return {"enabled": False, "reason": "Start requires this session to be armed."}
        if gate.halt_latched or gate.recovery_required:
            return {"enabled": False, "reason": "Halt or recovery is latched. Start stays blocked."}
        return {
            "enabled": True,
            "reason": "Start runs one simulated mission through Ground. It is not physical execution.",
        }
    if name == "supervised":
        if gate.controlled_motion is True:
            return {
                "enabled": False,
                "reason": "Controlled motion is admitted. Supervised mode does not disable it.",
            }
        if gate.worker == "running" and gate.phase not in {"IDLE", "CONNECT", "SCOUT"}:
            return {"enabled": False, "reason": "Supervised search is only available before a drone primitive."}
        if gate.controlled_motion is None:
            reason = (
                "No capability report yet. Supervised withholds an autonomous primitive only "
                "if controlled motion is later denied."
            )
        else:
            reason = "Controlled motion is denied. Supervised search does not enable an autonomous primitive."
        return {"enabled": True, "reason": reason}
    if gate.worker == "running":
        return {"enabled": False, "reason": "Reset waits until the mission worker finishes."}
    if gate.phase == "IDLE" and not gate.halt_latched and not gate.recovery_required:
        return {"enabled": False, "reason": "There is no finished run to reset."}
    if gate.goal_reached and gate.landing_verified and not gate.recovery_required:
        return {"enabled": True, "reason": "Goal and landing are both verified. Reset opens a disarmed session."}
    return {
        "enabled": True,
        "reason": "Recovery is unresolved. Reset requires a recovery token and does not erase the old run.",
    }
