"""Public kernel surface. Importing it does not open sockets or load device SDKs."""

from patrol.ground.kernel.authority import SessionAuthority
from patrol.ground.kernel.barriers import BarrierSet
from patrol.ground.kernel.build import build_kernel
from patrol.ground.kernel.catalog import (
    COMMANDS,
    ERROR_CODES,
    EVENT_KINDS,
    LIFECYCLE_GUARDS,
    OPERATIONS,
    PHASES,
    SCHEMA_VERSION,
    SLOT_BY_NAME,
    SLOT_SPECS,
    absence_enables_hardware,
    live_motion_allowed,
    missing_mandatory,
)
from patrol.ground.kernel.clock import ManualClock, RealClock
from patrol.ground.kernel.commands import parse_command
from patrol.ground.kernel.contracts import (
    AdmissionResult,
    BaseServices,
    Command,
    EventRecord,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    GroundSettings,
    IncidentInput,
    KernelContext,
    OperationResult,
    ServicePorts,
    SessionSnapshot,
    SimulationCase,
    SimulationReport,
    Ticket,
)
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.jpeg import tiny_jpeg_bytes
from patrol.ground.kernel.loader import discover, load_callable, normalize_task
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings, redact
from patrol.ground.kernel.validation import freeze_map, require_bool

__all__ = [
    "COMMANDS",
    "ERROR_CODES",
    "EVENT_KINDS",
    "LIFECYCLE_GUARDS",
    "OPERATIONS",
    "PHASES",
    "SCHEMA_VERSION",
    "SLOT_BY_NAME",
    "SLOT_SPECS",
    "AdmissionResult",
    "BaseServices",
    "Command",
    "EventRecord",
    "FeatureRequest",
    "FeatureResult",
    "GroundError",
    "GroundEvent",
    "GroundFault",
    "GroundSettings",
    "IncidentInput",
    "KernelContext",
    "ManualClock",
    "OperationResult",
    "RealClock",
    "ServicePorts",
    "SessionAuthority",
    "SessionSnapshot",
    "SimulationCase",
    "SimulationReport",
    "Ticket",
    "absence_enables_hardware",
    "build_kernel",
    "context_for_stage",
    "discover",
    "fault",
    "freeze_map",
    "live_motion_allowed",
    "load_callable",
    "make_settings",
    "missing_mandatory",
    "normalize_task",
    "parse_command",
    "redact",
    "repo_root",
    "require_bool",
    "tiny_jpeg_bytes",
    "BarrierSet",
]
