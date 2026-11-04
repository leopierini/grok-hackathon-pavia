"""Ground-internal contracts. These types are not the robot contract."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from patrol.contract import Frame, Incident, RunContext
from patrol.ground.kernel.catalog import SCHEMA_VERSION

__all__ = ["SCHEMA_VERSION"]


@dataclass(frozen=True)
class Ticket:
    mission_id: str
    epoch: int
    stage_id: str


@dataclass(frozen=True)
class GroundError:
    code: str
    detail: str
    recovery_required: bool


@dataclass(frozen=True)
class GroundEvent:
    kind: str
    ticket: Ticket | None
    payload: Mapping[str, object]


@dataclass(frozen=True)
class FeatureRequest:
    kind: str
    name: str
    ticket: Ticket | None
    payload: Mapping[str, object]


@dataclass(frozen=True)
class FeatureResult:
    status: str
    data: Mapping[str, object]
    events: tuple[GroundEvent, ...]
    error: GroundError | None


@dataclass(frozen=True)
class SessionSnapshot:
    phase: str
    incident: Incident | None
    epoch: int
    stage_id: str | None
    modes: Mapping[str, str]
    dog_transport: str
    armed: bool
    arrival_confirmed: bool | None
    arrival_monotonic: float | None
    arrival_method: str | None
    readiness_confirmed: bool | None
    confirmation_method: str | None
    evidence: Mapping[str, object]
    decisions: Mapping[str, object]
    outcome: str | None
    flight_lock: bool
    recovery_required: bool
    halt_latched: bool
    mission_id: str | None


@dataclass(frozen=True)
class GroundSettings:
    zones: tuple[str, ...]
    profile_by_zone: Mapping[str, str]
    launch_tier: str
    dog_transport: str
    profile_identity: str
    arrival_timeout_s: float
    flight_ready_timeout_s: float
    incident_timeout_s: float
    route_limit_s: float
    flight_limit_s: float
    model_limit_s: float
    prepare_limit_s: float
    capture_limit_s: float
    connect_limit_s: float
    output_root: str
    adapter_configs: Mapping[str, Mapping[str, object]]
    modes: Mapping[str, str]
    scenario: str


@dataclass(frozen=True)
class IncidentInput:
    image_path: str
    zone: str
    target: str
    captured_at: str | None
    simulated: bool


@dataclass(frozen=True)
class AdmissionResult:
    accepted: bool
    incident: Incident | None
    error: GroundError | None


@dataclass(frozen=True)
class OperationResult:
    operation: str
    ticket: Ticket
    status: str
    value: object
    error: GroundError | None
    pending: bool
    started_utc: str
    ended_utc: str | None
    started_monotonic: float
    ended_monotonic: float | None


@dataclass(frozen=True)
class EventRecord:
    sequence: int
    timestamp_utc: str
    elapsed_s: float
    mission_id: str | None
    ticket: Ticket | None
    state: str | None
    event: str
    zone: str | None
    target: str | None
    modes: Mapping[str, str]
    data: Mapping[str, object]


@dataclass(frozen=True)
class SimulationCase:
    task_id: str
    case_id: str
    seed: int
    setup: Mapping[str, object]
    stimuli: tuple[Mapping[str, object], ...]
    barriers: tuple[str, ...]
    faults: tuple[str, ...]
    expected: Mapping[str, object]
    forbidden_calls: tuple[str, ...]
    teardown: tuple[str, ...]


@dataclass(frozen=True)
class SimulationReport:
    task_id: str
    seed: int
    clock_mode: str
    cases: tuple[Mapping[str, object], ...]
    failures: tuple[str, ...]
    assertion_count: int
    modes: Mapping[str, str]
    trace: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    live_call_count: int
    skipped: int


@dataclass(frozen=True)
class Command:
    name: str
    args: tuple[str, ...]
    raw: str


@dataclass(frozen=True)
class CaptureInterval:
    started_monotonic: float
    ended_monotonic: float | None
    started_utc: str
    ended_utc: str | None


@dataclass(frozen=True)
class EvidenceResult:
    accepted: bool
    reason: str
    frame: Frame | None
    diagnostics: Mapping[str, object]


@dataclass(frozen=True)
class WaitSpec:
    kind: str
    zone: str
    stage_id: str
    deadline_monotonic: float


@dataclass(frozen=True)
class ConfirmationResult:
    accepted: bool
    method: str | None
    zone: str | None
    detail: str


@dataclass(frozen=True)
class MissionHandle:
    mission_id: str
    ticket: Ticket


@dataclass(frozen=True)
class SafetyHandle:
    ticket: Ticket
    reason: str
    generation: int


@dataclass(frozen=True)
class SafetySnapshot:
    halted: bool
    recovery_required: bool
    pending: bool
    detail: str


OperationFactory = Callable[[RunContext], Awaitable[object]]


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def utc_now(self) -> datetime: ...

    async def sleep(self, seconds: float) -> None: ...

    def is_manual(self) -> bool: ...


class Authority(Protocol):
    @property
    def epoch(self) -> int: ...

    @property
    def cancelled(self) -> bool: ...

    @property
    def cancel_event(self) -> threading.Event: ...

    def issue(self, mission_id: str, stage_id: str) -> Ticket: ...

    def require_current(self, ticket: Ticket) -> None: ...

    def require_action(
        self,
        ticket: Ticket,
        *,
        deadline_monotonic: float,
        clock: Clock,
    ) -> None: ...

    def latch_cancel(self, reason: str) -> None: ...

    def reset_generation(self, reason: str) -> int: ...


class TaskRegistry(Protocol):
    def retain(self, name: str, task: object) -> None: ...

    def pending(self) -> tuple[str, ...]: ...

    async def collect(self, *, deadline: float) -> None: ...


class IOPort(Protocol):
    def read_bytes(self, path: Path, *, limit: int) -> bytes: ...

    def write_bytes(self, path: Path, data: bytes) -> None: ...

    def read_text(self, path: Path, *, limit: int = 1_000_000) -> str: ...

    def fail_next(self, op: str, reason: str) -> None: ...


class BarrierBoard(Protocol):
    def arm(self, name: str) -> None: ...

    def release(self, name: str) -> None: ...

    def release_all(self) -> None: ...

    async def wait(self, name: str) -> None: ...

    def armed(self, name: str) -> bool: ...


class ResultValidation(Protocol):
    def payload(
        self,
        slot: str,
        direction: str,
        data: Mapping[str, object],
    ) -> Mapping[str, object]: ...

    def feature_request(self, slot: str, request: FeatureRequest) -> FeatureRequest: ...

    def feature_result(self, slot: str, result: FeatureResult) -> FeatureResult: ...


class FeatureRegistry(Protocol):
    def get(self, slot: str) -> FeaturePort: ...

    def installed(self) -> Mapping[str, str]: ...


class Simulator(Protocol):
    async def run(
        self,
        case: SimulationCase,
        *,
        providers: Mapping[str, object],
        clock_mode: str,
    ) -> SimulationReport: ...


class ConfigPort(Protocol):
    def load(
        self,
        path: str | Path | None,
        *,
        modes: Mapping[str, str],
        scenario: str | None,
    ) -> GroundSettings: ...

    def redacted(self, settings: GroundSettings) -> Mapping[str, object]: ...


class StatePort(Protocol):
    def open(self, incident: Incident, settings: GroundSettings) -> SessionSnapshot: ...

    def apply(self, event: GroundEvent, *, expected_ticket: Ticket) -> SessionSnapshot: ...

    def snapshot(self) -> SessionSnapshot: ...


class JournalPort(Protocol):
    async def open(self, run_id: str, output_root: str | Path) -> None: ...

    def emit(self, record: EventRecord) -> None: ...

    async def flush(self) -> None: ...

    async def publish(self, summary: Mapping[str, object]) -> None: ...

    async def scan(self, output_root: str | Path) -> tuple[Mapping[str, object], ...]: ...

    async def close(self) -> None: ...


class ExecutorPort(Protocol):
    async def run(
        self,
        name: str,
        ticket: Ticket,
        factory: OperationFactory,
        *,
        limit_s: float,
    ) -> OperationResult: ...

    def pending(self) -> tuple[str, ...]: ...

    async def collect(self, *, deadline: float) -> None: ...


class EvidencePort(Protocol):
    async def validate(
        self,
        frame: Frame,
        *,
        expected_source: str,
        zone: str,
        mode: str,
        output_root: str | Path,
        interval: CaptureInterval,
    ) -> EvidenceResult: ...


class ConsolePort(Protocol):
    def parse(self, text: str) -> Command: ...

    def commands(self) -> AsyncIterator[Command]: ...

    async def confirm(self, wait_spec: WaitSpec) -> ConfirmationResult: ...

    def write(self, message: str) -> None: ...

    async def close(self) -> None: ...


class AdapterPort(Protocol):
    async def build(
        self,
        settings: GroundSettings,
        output_root: str | Path,
        *,
        resolver: Mapping[str, object],
    ) -> None: ...

    async def connect(self, component: str) -> object: ...

    async def status(self, component: str) -> object: ...

    async def invoke(
        self,
        component: str,
        method: str,
        args: tuple[object, ...],
        *,
        ticket: Ticket,
        context: RunContext,
    ) -> object: ...

    async def close(self) -> None: ...


class WorkflowPort(Protocol):
    async def load(self, raw: IncidentInput) -> AdmissionResult: ...

    def start(self, incident: Incident) -> MissionHandle: ...

    def snapshot(self) -> SessionSnapshot: ...

    async def join(self, handle: MissionHandle) -> None: ...


class SafetyPort(Protocol):
    def request(self, reason: str, ticket: Ticket) -> SafetyHandle: ...

    async def observe(self, handle: SafetyHandle, *, deadline: float) -> SafetySnapshot: ...

    async def reset(self, recovery: Mapping[str, object]) -> None: ...

    async def shutdown(self, reason: str) -> None: ...


class FeaturePort(Protocol):
    async def execute(self, request: FeatureRequest) -> FeatureResult: ...


@dataclass
class ServicePorts:
    config: ConfigPort
    state: StatePort
    journal: JournalPort
    executor: ExecutorPort
    evidence: EvidencePort
    console: ConsolePort
    adapters: AdapterPort
    workflow: WorkflowPort
    safety: SafetyPort


@dataclass
class KernelContext:
    clock: Clock
    io: IOPort
    authority: Authority
    tasks: TaskRegistry
    features: FeatureRegistry
    result_validation: ResultValidation
    simulator: Simulator
    barriers: BarrierBoard
    mode: str
    seed: int


@dataclass
class BaseServices:
    kernel: KernelContext
    config: ConfigPort
    state: StatePort
    journal: JournalPort
    executor: ExecutorPort
    evidence: EvidencePort
    console: ConsolePort
    adapters: AdapterPort
    workflow: WorkflowPort
    safety: SafetyPort
