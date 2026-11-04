"""Expected simulation traces. The provider rebuilds these from live lifecycle data."""

from __future__ import annotations

SUCCESS_TRACE: tuple[str, ...] = (
    "state:completed",
    "stopped:true",
    "verified:true",
    "motion:stationary",
    "motion_occurred:true",
    "active_command:false",
    "block_next_step:false",
    "proposed_command:none",
    "commands_issued:0",
    "demo_goal:false",
    "target_arrival:false",
    "halt_cleared:false",
)

ACCEPTED_TRACE: tuple[str, ...] = (
    "state:accepted",
    "stopped:false",
    "verified:false",
    "motion:unknown",
    "motion_occurred:false",
    "active_command:true",
    "block_next_step:true",
    "proposed_command:none",
    "commands_issued:0",
)

EXPIRED_TRACE: tuple[str, ...] = (
    "state:rejected",
    "reason:expired_command",
    "stopped:false",
    "motion_occurred:false",
    "active_command:false",
    "proposed_command:none",
    "commands_issued:0",
    "replacement:none",
)

TIMEOUT_TRACE: tuple[str, ...] = (
    "state:pending",
    "timed_out:true",
    "query_command:cmd-dog-001",
    "replacement:none",
    "issued:cmd-dog-002:false",
    "proposed_command:none",
    "commands_issued:0",
    "motion_occurred:false",
    "stopped:false",
)

UNVERIFIED_TRACE: tuple[str, ...] = (
    "state:completed",
    "verified:false",
    "stopped:false",
    "motion:stationary",
    "active_command:true",
    "proposed_command:none",
    "commands_issued:0",
)

HALT_TRACE: tuple[str, ...] = (
    "move:cmd-dog-001:running",
    "move_complete:false",
    "move_stopped:false",
    "halt:cmd-dog-halt-001:completed",
    "halt_terminal:true",
    "halt_stopped:true",
    "halt_cleared:false",
    "block_next_step:true",
    "proposed_command:none",
    "commands_issued:0",
    "demo_goal:false",
)

REPLAY_TRACE: tuple[str, ...] = (
    "state:completed",
    "stopped:true",
    "terminal_events:1",
    "replay_events:0",
    "event_count:3",
    "proposed_command:none",
    "commands_issued:0",
)

LIFECYCLE_REPORT_TRACE: tuple[str, ...] = SUCCESS_TRACE + (
    "report:cmd-dog-001:completed:stopped:true",
)

CONFLICT_TRACE: tuple[str, ...] = (
    "conflict:completed/failed",
    "stopped:false",
    "faulted:true",
    "block_next_step:true",
    "proposed_command:none",
    "commands_issued:0",
    "demo_goal:false",
    "halt_cleared:false",
)

STALE_TRACE: tuple[str, ...] = (
    "state:none",
    "bound:false",
    "motion_occurred:false",
    "proposed_command:none",
    "commands_issued:0",
    "stopped:false",
)

LIDAR_TRACE: tuple[str, ...] = (
    "state:completed",
    "stopped:true",
    "stop_cause:lidar",
    "target_arrival:false",
    "demo_goal:false",
    "verified:true",
    "motion:stationary",
    "proposed_command:none",
)

FOREIGN_TRACE: tuple[str, ...] = (
    "state:none",
    "bound:false",
    "command_id:cmd-dog-999",
    "motion_occurred:false",
    "proposed_command:none",
    "commands_issued:0",
)

REPEATED_TRACE: tuple[str, ...] = (
    "repeated:true",
    "state:completed",
    "stopped:true",
    "motion_allowed:false",
    "faulted:false",
    "proposed_command:none",
    "commands_issued:0",
)

READINESS_TRACE: tuple[str, ...] = (
    "state:completed",
    "stopped:false",
    "stop_cause:readiness_disagrees",
    "verified:true",
    "motion:stationary",
    "proposed_command:none",
    "commands_issued:0",
    "demo_goal:false",
    "target_arrival:false",
)
