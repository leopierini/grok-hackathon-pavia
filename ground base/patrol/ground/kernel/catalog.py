"""Frozen names for slots, errors, events, commands, and payload keys.

Later tasks import this module. They do not extend it inside a parallel batch.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "ground-task-v1"

PHASES: frozenset[str] = frozenset(
    {
        "IDLE",
        "ASSESS",
        "PREPARE_DOG",
        "MOVE_DOG",
        "WAIT_ARRIVAL",
        "GROUND_VIEW",
        "PREFLIGHT",
        "INSPECT",
        "RESOLVE",
        "REPORT",
        "DONE",
        "ABORTED",
        "FAULT",
    }
)

OUTCOMES: frozenset[str] = frozenset(
    {"ignored", "cleared", "alerted", "unresolved", "aborted", "failed"}
)

ZONES: frozenset[str] = frozenset({"entrance", "room_2", "display"})

MODES: frozenset[str] = frozenset({"fake", "real"})

DOG_TRANSPORTS: frozenset[str] = frozenset({"ethernet", "wifi"})

LAUNCH_TIERS: frozenset[str] = frozenset({"carried_pad", "stationary_pad", "floor"})

LAUNCH_ORIGINS: frozenset[str] = frozenset({"dog_pad", "floor"})

SCENARIOS: frozenset[str] = frozenset(
    {
        "blocked_resolved",
        "dismiss",
        "ground_clear",
        "ground_confirmed",
        "drone_unavailable",
        "route_blocked",
        "invalid_model",
        "stale_frame",
        "takeoff_timeout",
        "landing_unknown",
        "slow_model",
    }
)

COMMANDS: frozenset[str] = frozenset(
    {"status", "arm", "start", "arrived", "flight-ready", "halt", "reset", "quit"}
)

FEATURE_KINDS: frozenset[str] = frozenset(
    {"stage", "command", "guard", "projection", "diagnostic"}
)

FEATURE_STATUSES: frozenset[str] = frozenset({"ok", "blocked", "failed"})

OPERATION_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "timeout", "cancelled"}
)

ERROR_CODES: frozenset[str] = frozenset(
    {
        "invalid_input",
        "rejected",
        "missing_provider",
        "duplicate_slot",
        "duplicate_task",
        "unknown_slot",
        "schema_mismatch",
        "path_escape",
        "forbidden_command",
        "owner_mismatch",
        "cancelled",
        "stale_ticket",
        "epoch_mismatch",
        "expired_deadline",
        "validation_failed",
        "io_fault",
        "unsafe_state",
        "timeout",
        "unavailable",
        "internal",
        "not_admitted",
        "recovery_required",
        "contract_mismatch",
    }
)

EVENT_KINDS: frozenset[str] = frozenset(
    {
        "incident_loaded",
        "incident_accepted",
        "incident_rejected",
        "permission_granted",
        "permission_consumed",
        "state_changed",
        "operation_started",
        "operation_completed",
        "operation_failed",
        "decision_received",
        "arrival_confirmed",
        "arrival_rejected",
        "flight_ready_confirmed",
        "flight_ready_rejected",
        "frame_validated",
        "frame_rejected",
        "halt_requested",
        "stop_attempted",
        "stop_result",
        "recovery_required",
        "recovery_cleared",
        "report_saved",
        "mission_finished",
        "provider_missing",
        "composition_rejected",
        "clock_advanced",
        "barrier_released",
        "simulation_completed",
        "persistence_fault",
        "link_lost",
        "reset_requested",
        "shutdown_requested",
    }
)

OPERATIONS: frozenset[str] = frozenset(
    {
        "dog.connect",
        "dog.prepare",
        "dog.get_status",
        "dog.run_route",
        "dog.capture_frame",
        "dog.halt",
        "dog.close",
        "drone.connect",
        "drone.get_status",
        "drone.inspect",
        "drone.land",
        "drone.close",
        "reasoner.metadata",
        "reasoner.assess_incident",
        "reasoner.assess_ground_view",
        "reasoner.resolve_incident",
        "reasoner.compose_alert",
        "reasoner.close",
    }
)

LIFECYCLE_GUARDS: frozenset[str] = frozenset(
    {
        "current_epoch",
        "not_cancelled",
        "deadline_open",
        "mandatory_providers",
        "no_hardware_from_optional_absence",
        "single_mission",
        "recovery_latched",
        "flight_lock",
        "manual_clock_isolated",
        "no_live_sdk",
    }
)

COMMON_INPUTS: frozenset[str] = frozenset(
    {
        "incident",
        "settings",
        "snapshot",
        "operation",
        "frame",
        "ground",
        "aerial",
        "command",
        "interval",
    }
)

BOOLEAN_KEYS: frozenset[str] = frozenset(
    {
        "simulated",
        "may_route",
        "may_wait_arrival",
        "arrival_confirmed",
        "may_confirm",
        "may_inspect",
        "ready",
        "may_arm",
        "block_actions",
        "request_safety",
        "recovery_required",
        "within_limit",
        "authorized",
        "retained",
    }
)

NULLABLE_KEYS: frozenset[str] = frozenset(
    {
        "arrival_confirmed",
        "arrival_monotonic",
        "captured_at",
        "readiness",
        "evaluation",
        "resolution",
    }
)


@dataclass(frozen=True)
class SlotSpec:
    slot: str
    owner: str
    group: str
    mandatory_live: bool
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


def _slot(
    slot: str,
    owner: str,
    group: str,
    mandatory_live: bool,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
) -> SlotSpec:
    return SlotSpec(slot, owner, group, mandatory_live, inputs, outputs)


SLOT_SPECS: tuple[SlotSpec, ...] = (
    _slot("kernel.foundation", "01", "foundation", False, ("seed",), (
        "live_call_count",
        "simulated",
        "trace",
        "within_limit",
        "device_calls",
        "cleanup",
        "retained",
        "measurement_clock",
        "slot",
        "schema_version",
        "authorized",
        "detail",
    )),
    _slot("base.config", "02", "service", True, (), ()),
    _slot("base.state", "03", "service", True, (), ()),
    _slot("base.journal", "04", "service", True, (), ()),
    _slot("base.executor", "05", "service", True, (), ()),
    _slot("base.evidence", "06", "service", True, (), ()),
    _slot("base.console", "07", "service", True, (), ()),
    _slot("base.adapters", "08", "service", True, (), ()),
    _slot("base.workflow", "09", "service", True, (), ()),
    _slot("base.safety", "10", "service", True, (), ()),
    _slot(
        "feature.incident_input",
        "11",
        "stage",
        True,
        ("image_path", "zone", "target", "captured_at", "simulated"),
        ("incident", "provenance"),
    ),
    _slot(
        "feature.dispatch",
        "12",
        "stage",
        True,
        ("incident", "operation"),
        ("decision", "continuation"),
    ),
    _slot(
        "feature.prepare",
        "13",
        "stage",
        True,
        ("incident", "settings", "snapshot"),
        ("preparation", "dog_status", "may_route"),
    ),
    _slot(
        "feature.route_result",
        "14",
        "stage",
        True,
        ("incident", "operation", "dog_status"),
        ("route", "may_wait_arrival"),
    ),
    _slot(
        "feature.arrival",
        "15",
        "stage",
        True,
        ("incident", "route", "wait_spec"),
        ("arrival_confirmed", "arrival_monotonic", "arrival_method"),
    ),
    _slot(
        "feature.dog_frame",
        "16",
        "stage",
        True,
        ("incident", "arrival", "snapshot"),
        ("ground", "interval", "validation"),
    ),
    _slot(
        "feature.ground_view",
        "17",
        "stage",
        True,
        ("incident", "ground", "operation"),
        ("decision", "continuation"),
    ),
    _slot(
        "feature.preflight",
        "18",
        "stage",
        True,
        ("check", "incident", "snapshot", "readiness"),
        ("inspection_request", "checks", "may_confirm", "may_inspect"),
    ),
    _slot(
        "feature.flight_ready",
        "19",
        "stage",
        True,
        ("incident", "initial_preflight", "wait_spec"),
        ("readiness", "confirmation_method"),
    ),
    _slot(
        "feature.inspection_result",
        "20",
        "stage",
        True,
        ("incident", "inspection_request", "operation"),
        ("aerial", "flight_state", "continuation", "recovery_required"),
    ),
    _slot(
        "feature.resolution",
        "21",
        "stage",
        True,
        ("incident", "ground", "aerial", "operation"),
        ("resolution", "outcome"),
    ),
    _slot(
        "feature.report",
        "22",
        "stage",
        True,
        ("incident", "resolution", "outcome", "snapshot", "metrics"),
        ("report", "summary", "wording_source", "publication_status"),
    ),
    _slot(
        "feature.status",
        "23",
        "projection",
        False,
        ("snapshot", "pending_operations", "writer_health"),
        ("display", "status_fields"),
    ),
    _slot(
        "feature.transport",
        "24",
        "guard",
        False,
        ("settings", "snapshot", "acceptance", "tether"),
        ("ready", "checks", "profile"),
    ),
    _slot(
        "feature.metrics",
        "25",
        "projection",
        False,
        ("events", "snapshot", "evaluation"),
        ("metrics", "denominators", "unavailable_reasons"),
    ),
    _slot(
        "feature.restart",
        "26",
        "stage",
        True,
        ("prior_runs", "current_device_status", "ownership"),
        ("may_arm", "recovery_required", "incomplete_run"),
    ),
    _slot(
        "feature.redaction",
        "27",
        "stage",
        True,
        ("record", "sensitive_values"),
        ("safe_record", "rejected_fields"),
    ),
    _slot(
        "feature.persistence_fault",
        "28",
        "stage",
        True,
        ("writer_health", "fault_event", "snapshot"),
        ("block_actions", "request_safety", "persistence_status"),
    ),
    _slot(
        "feature.console_shutdown",
        "29",
        "stage",
        True,
        ("command", "input_event", "snapshot"),
        ("shutdown_intent", "cleanup_result"),
    ),
    _slot(
        "feature.adapter_probe",
        "30",
        "diagnostic",
        False,
        ("resolver", "settings", "acceptance_evidence", "probe_mode"),
        ("report",),
    ),
    _slot(
        "feature.network_diagnostics",
        "31",
        "diagnostic",
        False,
        ("settings", "probe", "diagnostic_mode"),
        ("findings",),
    ),
    _slot(
        "feature.rehearsal",
        "32",
        "diagnostic",
        False,
        ("scenario", "seed", "simulation_mode", "output_root"),
        ("report", "simulation_label", "runbook"),
    ),
)

SLOT_BY_NAME: dict[str, SlotSpec] = {spec.slot: spec for spec in SLOT_SPECS}

CONTINUATIONS: dict[str, frozenset[str]] = {
    "feature.dispatch": frozenset({"investigate", "ignored", "unresolved"}),
    "feature.ground_view": frozenset({"resolve", "preflight", "unresolved"}),
    "feature.inspection_result": frozenset(
        {"resolve", "unresolved", "failed", "fault"}
    ),
}


def missing_mandatory(installed: set[str] | frozenset[str]) -> tuple[str, ...]:
    return tuple(
        spec.slot
        for spec in SLOT_SPECS
        if spec.mandatory_live and spec.slot not in installed
    )


def optional_slots() -> tuple[str, ...]:
    return tuple(
        spec.slot
        for spec in SLOT_SPECS
        if not spec.mandatory_live and spec.group != "foundation"
    )


def absence_enables_hardware(slot: str) -> bool:
    """A missing provider never grants motion, including optional diagnostics."""
    if slot not in SLOT_BY_NAME:
        return False
    return False


def live_motion_allowed(installed: set[str] | frozenset[str]) -> bool:
    """Foundation builds refuse live motion.

    Missing mandatory providers are the explicit blocker. A complete install
    still does not authorize hardware from this package; Task 09 owns that gate.
    """
    if missing_mandatory(installed):
        return False
    return False
