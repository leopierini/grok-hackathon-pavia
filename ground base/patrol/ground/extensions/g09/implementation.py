"""Fixed mission workflow. Later policies are resolved by slot, never imported."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from patrol.contract import Frame, Incident, InspectionRequest, RouteResult
from patrol.ground.extensions.g09.synthetic import StageScript, install_stage_pack
from patrol.ground.kernel.catalog import CONTINUATIONS, OUTCOMES, SCHEMA_VERSION
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
    MissionHandle,
    OperationResult,
    ServicePorts,
    SessionSnapshot,
    Ticket,
    WaitSpec,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.jpeg import tiny_jpeg_bytes
from patrol.ground.kernel.loader import discover, load_callable
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.snapshots import idle_snapshot
from patrol.ground.kernel.validation import freeze_map

_TARGET = "a person or an object left in a marked closed area"
_HOLD_ROUTES = frozenset(
    {"halt_during_route", "persistence_during_route", "link_loss_during_route"}
)


def create(
    kernel: KernelContext | BaseServices,
    peers: ServicePorts | None = None,
) -> Workflow:
    """Build a workflow. The harness passes BaseServices; callers may pass ports."""

    if isinstance(kernel, BaseServices):
        ports = ServicePorts(
            config=kernel.config,
            state=kernel.state,
            journal=kernel.journal,
            executor=kernel.executor,
            evidence=kernel.evidence,
            console=kernel.console,
            adapters=kernel.adapters,
            workflow=kernel.workflow,
            safety=kernel.safety,
        )
        return Workflow(kernel.kernel, ports, kernel)
    if peers is None:
        raise fault("invalid_input", "workflow peers are required")
    return Workflow(kernel, peers, None)


class Workflow:
    """One mission coroutine plus independent input and health supervision."""

    def __init__(
        self,
        kernel: KernelContext,
        peers: ServicePorts,
        services: BaseServices | None,
    ) -> None:
        self.kernel = kernel
        self.config = peers.config
        self.state = peers.state
        self.journal = peers.journal
        self.executor = peers.executor
        self.evidence = peers.evidence
        self.console = peers.console
        self.adapters = peers.adapters
        self.safety = peers.safety
        self.services = services
        self.stage_trace: list[str] = []
        self.command_log: list[str] = []
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()
        self.outcome = ""
        self.failure_code: str | None = None
        self.wording_source: str | None = None
        self.health_ran = False
        self.input_ran = False
        self._settings: GroundSettings | None = None
        self._snapshot = idle_snapshot(
            epoch=kernel.authority.epoch,
            modes={"dog": "fake", "drone": "fake", "grok": "fake"},
            dog_transport="ethernet",
        )
        self._admitted: Incident | None = None
        self._ticket: Ticket | None = None
        self._handle: MissionHandle | None = None
        self._mission_task: asyncio.Task[None] | None = None
        self._input_task: asyncio.Task[None] | None = None
        self._health_task: asyncio.Task[None] | None = None
        self._persistence_task: asyncio.Task[None] | None = None
        self._done = asyncio.Event()
        self._can_start = False
        self._started = False
        self._active = False
        self._closed = False
        self._reported = False
        self._startup_done = False
        self._may_arm = False
        self._motion_gate = False
        self._armed = False
        self._route_used = False
        self._flight_lock = False
        self._recovery = False
        self._halted = False
        self._physical_recovery = False
        self._emitting = False
        self._sequence = 0
        self._started_mono: float | None = None
        self._ground: Frame | None = None
        self._aerial: Frame | None = None
        self._resolution: object = None
        self._arrived_zone: str | None = None

    def bind_settings(self, settings: GroundSettings) -> None:
        self._settings = settings
        if self._admitted is None:
            self._snapshot = idle_snapshot(
                epoch=self.kernel.authority.epoch,
                modes=settings.modes,
                dog_transport=settings.dog_transport,
            )

    def snapshot(self) -> SessionSnapshot:
        return self._snapshot

    async def load(self, raw: IncidentInput) -> AdmissionResult:
        if self._admitted is not None or self._started:
            return _reject("rejected", "a mission is already open")
        if self._settings is None:
            self._settings = self.config.load(
                None,
                modes={"dog": "fake", "drone": "fake", "grok": "fake"},
                scenario="blocked_resolved",
            )
        try:
            if not self._startup_done:
                await self._startup()
                self._startup_done = True
            epoch = self.kernel.authority.epoch
            result = await self._call(
                "feature.incident_input",
                kind="stage",
                name="incident_input",
                ticket=None,
                payload={
                    "image_path": raw.image_path,
                    "zone": raw.zone,
                    "target": raw.target,
                    "captured_at": raw.captured_at,
                    "simulated": raw.simulated,
                },
            )
        except GroundFault as exc:
            return AdmissionResult(False, None, exc.error)
        if (
            self.kernel.authority.cancelled
            or self.kernel.authority.epoch != epoch
            or self._admitted is not None
            or self._started
        ):
            return _reject("stale_ticket", "admission is no longer current")
        incident = result.data.get("incident")
        if not isinstance(incident, Incident):
            return _reject("validation_failed", "incident payload is not an Incident")
        if incident.zone != raw.zone or incident.target != raw.target.strip():
            return _reject("validation_failed", "incident does not match the supplied input")
        try:
            self._snapshot = self.state.open(incident, self._require_settings())
        except GroundFault as exc:
            return AdmissionResult(False, None, exc.error)
        self._admitted = incident
        self._can_start = True
        self._note("load")
        return AdmissionResult(True, incident, None)

    def start(self, incident: Incident) -> MissionHandle:
        if self._started or self._active:
            raise fault("rejected", "a mission is already active")
        if self._admitted is None or not self._can_start:
            raise fault("not_admitted", "start requires one loaded incident")
        if incident.mission_id != self._admitted.mission_id:
            raise fault("rejected", "incident does not match the loaded admission")
        ticket = self.kernel.authority.issue(incident.mission_id, "mission")
        self._can_start = False
        self._started = True
        self._active = True
        self._ticket = ticket
        self._handle = MissionHandle(incident.mission_id, ticket)
        self._mission_task = asyncio.create_task(self._mission(), name="workflow.mission")
        self._input_task = asyncio.create_task(self._input_loop(), name="workflow.input")
        self._health_task = asyncio.create_task(self._health(), name="workflow.health")
        self.kernel.tasks.retain("workflow.mission", self._mission_task)
        self.kernel.tasks.retain("workflow.input", self._input_task)
        self.kernel.tasks.retain("workflow.health", self._health_task)
        return self._handle

    async def join(self, handle: MissionHandle) -> None:
        if self._handle is None or self._mission_task is None:
            raise fault("not_admitted", "mission is not running")
        if handle.mission_id != self._handle.mission_id or handle.ticket != self._handle.ticket:
            raise fault("stale_ticket", "mission handle does not match")
        await self._mission_task
        self._done.set()
        await self.console.close()
        if self._health_task is not None:
            await self._health_task
        if self._input_task is not None:
            await self._input_task
        if self._persistence_task is not None:
            await self._persistence_task

    def request_halt(self, reason: str) -> None:
        """Latch cancellation before any device or disk await."""

        if self._halted:
            return
        self._halted = True
        ticket = self._ticket
        if ticket is None:
            try:
                ticket = self.kernel.authority.issue("workflow", "halt")
            except GroundFault:
                self.kernel.authority.latch_cancel(reason)
                return
        self.safety.request(reason, ticket)

    def notify_persistence_fault(self, detail: str) -> None:
        self._note("persistence_fault")
        self.request_halt(f"persistence:{detail}")
        self._schedule_fault("persistence_fault", detail)

    def notify_link_lost(self, detail: str) -> None:
        self._note("link_lost")
        self.request_halt(f"link:{detail}")
        self._schedule_fault("link_lost", detail)

    def note_physical_recovery(self) -> None:
        if self.kernel.tasks.pending():
            raise fault("unsafe_state", "a worker is still pending", recovery_required=True)
        self._physical_recovery = True

    async def route_command(self, command: Command) -> None:
        if command.name == "halt":
            self.request_halt("operator halt")
            self.command_log.append("halt:latched")
            return
        if command.name == "arm":
            if self._admitted is None or self._started or self._may_arm is not True:
                self.command_log.append("arm:rejected")
                return
            self._armed = True
            self._snapshot = replace(self._snapshot, armed=True)
            self.command_log.append("arm:accepted")
            return
        if command.name == "start":
            self.command_log.append("start:rejected")
            return
        if command.name == "arrived":
            zone = command.args[0] if command.args else ""
            current = self._admitted.zone if self._admitted is not None else ""
            if self._snapshot.phase != "WAIT_ARRIVAL" or zone != current:
                self.command_log.append("arrival:rejected")
                return
            self._arrived_zone = zone
            self.command_log.append("arrival:accepted")
            return
        if command.name == "flight-ready":
            if self._snapshot.phase != "PREFLIGHT":
                self.command_log.append("flight-ready:rejected")
                return
            self.command_log.append("flight-ready:accepted")
            return
        if command.name == "status":
            await self._status_command()
            return
        if command.name == "reset":
            await self._reset_command()
            return
        if command.name == "quit":
            self.command_log.append("quit")
            await self._shutdown_command(command)
            return
        self.command_log.append(f"{command.name}:ignored")

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        """Simulation entry. The foundation harness calls this with the case id."""

        if request.name == "synthetic_manifest":
            return await self._synthetic_manifest()
        script = _script_for(request.name)
        if script is None:
            return _sim_failed("invalid_input", "unknown workflow case", self)
        services = self._as_services()
        install_stage_pack(services, script)
        output = _output_dir(self.adapters)
        self.bind_settings(make_settings(output_root=str(output)))
        image = output / "phone.jpg"
        self.kernel.io.write_bytes(image, tiny_jpeg_bytes())
        if request.name in _HOLD_ROUTES:
            self.kernel.barriers.arm("dog.run_route")
        try:
            admitted = await self.load(
                IncidentInput(str(image.resolve()), "room_2", _TARGET, None, True)
            )
        except GroundFault as exc:
            return _sim_failed(exc.error.code, exc.error.detail, self)
        if not admitted.accepted or admitted.incident is None:
            code = "invalid_input" if admitted.error is None else admitted.error.code
            detail = "admission failed" if admitted.error is None else admitted.error.detail
            return _sim_failed(code, detail, self)
        handle = self.start(admitted.incident)
        if request.name in _HOLD_ROUTES:
            parked = await self._wait_until_pending("dog.run_route")
            if not parked:
                self.kernel.barriers.release("dog.run_route")
                await self.join(handle)
                return _sim_failed("timeout", "route did not park", self)
            if request.name == "halt_during_route":
                self.request_halt("operator halt")
            elif request.name == "persistence_during_route":
                self.notify_persistence_fault("disk")
                if "safety.request" not in _trace_of(self.safety):
                    self.kernel.barriers.release("dog.run_route")
                    await self.join(handle)
                    return _sim_failed("internal", "persistence did not request safety", self)
            else:
                self.notify_link_lost("radio")
                if "safety.request" not in _trace_of(self.safety):
                    self.kernel.barriers.release("dog.run_route")
                    await self.join(handle)
                    return _sim_failed("internal", "link loss did not request safety", self)
            self.kernel.barriers.release("dog.run_route")
        await self.join(handle)
        return _sim_result(self)

    async def _mission(self) -> None:
        ticket = self._ticket
        try:
            if ticket is None:
                raise fault("not_admitted", "mission has no ticket")
            await self._body(ticket)
        except GroundFault as exc:
            if not self._closed and ticket is not None:
                self.failure_code = exc.error.code
                await self._terminal(
                    self._fault_outcome(exc), ticket, faulted=exc.error.recovery_required
                )
        finally:
            self._active = False
            self._done.set()

    async def _body(self, ticket: Ticket) -> None:
        incident = self._admitted
        if incident is None:
            raise fault("not_admitted", "mission has no incident")
        self._started_mono = self.kernel.clock.monotonic()
        self._note("assess")
        assess = await self._operate(
            "reasoner.assess_incident",
            ticket,
            "reasoner",
            "assess_incident",
            (incident,),
            limit=self._require_settings().model_limit_s,
            real=self._require_settings().modes["grok"] == "real",
        )
        if assess.status != "completed":
            await self._terminal(
                "aborted" if assess.status == "cancelled" else "unresolved",
                ticket,
                faulted=assess.status == "cancelled",
            )
            return
        self._note("dispatch")
        decision = await self._call(
            "feature.dispatch",
            kind="stage",
            name="dispatch",
            ticket=ticket,
            payload={"incident": incident, "operation": assess},
        )
        continuation = _text(decision.data, "continuation")
        if continuation == "ignored":
            await self._terminal("ignored", ticket)
            return
        if continuation == "unresolved":
            await self._terminal("unresolved", ticket)
            return
        if continuation != "investigate":
            raise fault("validation_failed", "dispatch continuation is not allowed")
        if not await self._transport_ok(ticket) or not self._motion_permitted():
            await self._terminal("unresolved", ticket)
            return
        self._note("prepare")
        prepared = await self._call(
            "feature.prepare",
            kind="stage",
            name="prepare",
            ticket=ticket,
            payload={
                "incident": incident,
                "settings": self._require_settings(),
                "snapshot": self._snapshot,
            },
        )
        if prepared.data.get("may_route") is not True:
            await self._terminal("failed", ticket)
            return
        if not self._fence(ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        if self._route_used:
            raise fault("unsafe_state", "a route is already active", recovery_required=True)
        self._route_used = True
        if not self._commit_phase("MOVE_DOG", ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        self._note("route")
        route = await self._operate(
            "dog.run_route",
            ticket,
            "dog",
            "run_route",
            (incident.zone,),
            limit=self._require_settings().route_limit_s,
            real=self._require_settings().modes["dog"] == "real",
        )
        if route.status != "completed":
            await self._terminal(
                "aborted" if route.status == "cancelled" else "failed",
                ticket,
                faulted=True,
            )
            return
        if not self._fence(ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        dog_status = await self.adapters.status("dog")
        self._note("route_result")
        classified = await self._call(
            "feature.route_result",
            kind="stage",
            name="route_result",
            ticket=ticket,
            payload={"incident": incident, "operation": route, "dog_status": dog_status},
        )
        route_value = classified.data.get("route")
        if isinstance(route_value, RouteResult) and route_value.stopped is not True:
            await self._terminal("failed", ticket, faulted=True)
            return
        if classified.data.get("may_wait_arrival") is not True:
            await self._terminal("failed", ticket)
            return
        if not self._commit_phase("WAIT_ARRIVAL", ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        wait = WaitSpec(
            "arrived",
            incident.zone,
            ticket.stage_id,
            self.kernel.clock.monotonic() + self._require_settings().arrival_timeout_s,
        )
        self._note("arrival")
        arrived = await self._call(
            "feature.arrival",
            kind="stage",
            name="arrival",
            ticket=ticket,
            payload={"incident": incident, "route": route_value, "wait_spec": wait},
        )
        if arrived.data.get("arrival_confirmed") is not True:
            self._snapshot = replace(
                self._snapshot,
                arrival_confirmed=False,
                arrival_monotonic=None,
                arrival_method=None,
            )
            await self._terminal("unresolved", ticket)
            return
        mono = arrived.data.get("arrival_monotonic")
        method = arrived.data.get("arrival_method")
        if (
            isinstance(mono, bool)
            or not isinstance(mono, (int, float))
            or not isinstance(method, str)
        ):
            raise fault("validation_failed", "arrival confirmation is incomplete")
        self._snapshot = replace(
            self._snapshot,
            arrival_confirmed=True,
            arrival_monotonic=float(mono),
            arrival_method=method,
        )
        if not self._commit_phase("GROUND_VIEW", ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        self._note("dog_frame")
        framed = await self._call(
            "feature.dog_frame",
            kind="stage",
            name="dog_frame",
            ticket=ticket,
            payload={
                "incident": incident,
                "arrival": self._arrival_payload(),
                "snapshot": self._snapshot,
            },
        )
        ground = framed.data.get("ground")
        if not isinstance(ground, Frame):
            raise fault("validation_failed", "dog frame is missing")
        self._ground = ground
        if not self._fence(ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        self._note("ground_view")
        viewed = await self._operate(
            "reasoner.assess_ground_view",
            ticket,
            "reasoner",
            "assess_ground_view",
            (incident, ground),
            limit=self._require_settings().model_limit_s,
            real=self._require_settings().modes["grok"] == "real",
        )
        if viewed.status != "completed":
            await self._terminal(
                "aborted" if viewed.status == "cancelled" else "unresolved",
                ticket,
                faulted=viewed.status == "cancelled",
            )
            return
        decision = await self._call(
            "feature.ground_view",
            kind="stage",
            name="ground_view",
            ticket=ticket,
            payload={"incident": incident, "ground": ground, "operation": viewed},
        )
        view_continuation = _text(decision.data, "continuation")
        if view_continuation == "unresolved":
            await self._terminal("unresolved", ticket)
            return
        if view_continuation == "preflight":
            await self._inspect(incident, ticket)
            if self._closed:
                return
        elif view_continuation != "resolve":
            raise fault("validation_failed", "ground continuation is not allowed")
        if self._ground is None or not self._fence(ticket):
            await self._terminal("aborted", ticket, faulted=self._flight_lock)
            return
        if not self._commit_phase("RESOLVE", ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        self._note("resolve")
        resolved = await self._operate(
            "reasoner.resolve_incident",
            ticket,
            "reasoner",
            "resolve_incident",
            (incident, self._ground, self._aerial),
            limit=self._require_settings().model_limit_s,
            real=self._require_settings().modes["grok"] == "real",
        )
        if resolved.status != "completed":
            await self._terminal(
                "aborted" if resolved.status == "cancelled" else "unresolved",
                ticket,
                faulted=self._flight_lock or resolved.status == "cancelled",
            )
            return
        self._note("resolution")
        resolution = await self._call(
            "feature.resolution",
            kind="stage",
            name="resolution",
            ticket=ticket,
            payload={
                "incident": incident,
                "ground": self._ground,
                "aerial": self._aerial,
                "operation": resolved,
            },
        )
        outcome = resolution.data.get("outcome")
        if not isinstance(outcome, str) or outcome not in OUTCOMES:
            raise fault("validation_failed", "resolution outcome is not allowed")
        self._resolution = resolution.data.get("resolution")
        await self._terminal(outcome, ticket)

    async def _inspect(self, incident: Incident, ticket: Ticket) -> None:
        if not await self._transport_ok(ticket):
            await self._terminal("unresolved", ticket)
            return
        if not self._commit_phase("PREFLIGHT", ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        self._flight_lock = True
        self._snapshot = replace(self._snapshot, flight_lock=True)
        self._note("preflight_initial")
        initial = await self._call(
            "feature.preflight",
            kind="stage",
            name="preflight_initial",
            ticket=ticket,
            payload={
                "check": "initial",
                "incident": incident,
                "snapshot": self._snapshot,
                "readiness": None,
                "settings": self._require_settings(),
            },
        )
        if (
            initial.data.get("may_confirm") is not True
            or initial.data.get("may_inspect") is not False
        ):
            await self._terminal("unresolved", ticket)
            return
        self._note("flight_ready")
        ready = await self._call(
            "feature.flight_ready",
            kind="stage",
            name="flight_ready",
            ticket=ticket,
            payload={
                "incident": incident,
                "initial_preflight": initial.data.get("checks"),
                "wait_spec": WaitSpec(
                    "flight-ready",
                    incident.zone,
                    ticket.stage_id,
                    self.kernel.clock.monotonic() + self._require_settings().flight_ready_timeout_s,
                ),
            },
        )
        readiness = ready.data.get("readiness")
        if not isinstance(readiness, str) or not readiness:
            await self._terminal("unresolved", ticket)
            return
        self._note("preflight_final")
        final = await self._call(
            "feature.preflight",
            kind="stage",
            name="preflight_final",
            ticket=ticket,
            payload={
                "check": "final",
                "incident": incident,
                "snapshot": self._snapshot,
                "readiness": readiness,
                "settings": self._require_settings(),
            },
        )
        if final.data.get("may_inspect") is not True:
            await self._terminal("unresolved", ticket)
            return
        request = final.data.get("inspection_request")
        if not isinstance(request, InspectionRequest):
            raise fault("validation_failed", "inspection request is missing")
        if not self._inspection_permitted(request) or not self._fence(ticket):
            await self._terminal(
                "unresolved" if self._fence(ticket) else "aborted",
                ticket,
                faulted=not self._fence(ticket),
            )
            return
        if not self._commit_phase("INSPECT", ticket):
            await self._terminal("aborted", ticket, faulted=True)
            return
        self._note("inspect")
        inspected = await self._operate(
            "drone.inspect",
            ticket,
            "drone",
            "inspect",
            (request,),
            limit=self._require_settings().flight_limit_s,
            real=self._require_settings().modes["drone"] == "real",
        )
        if inspected.status != "completed":
            await self._terminal(
                "aborted" if inspected.status == "cancelled" else "failed",
                ticket,
                faulted=True,
            )
            return
        self._note("inspection_result")
        classified = await self._call(
            "feature.inspection_result",
            kind="stage",
            name="inspection_result",
            ticket=ticket,
            payload={"incident": incident, "inspection_request": request, "operation": inspected},
        )
        flight_state = classified.data.get("flight_state")
        follow = _text(classified.data, "continuation")
        if (
            flight_state == "unknown"
            or classified.data.get("recovery_required") is True
            or follow == "fault"
        ):
            await self._terminal("failed", ticket, faulted=True)
            return
        if follow == "unresolved":
            await self._terminal("unresolved", ticket)
            return
        if follow == "failed":
            await self._terminal("failed", ticket, faulted=True)
            return
        if follow != "resolve":
            raise fault("validation_failed", "inspection continuation is not allowed")
        aerial = classified.data.get("aerial")
        if not isinstance(aerial, Frame):
            await self._terminal("unresolved", ticket, faulted=True)
            return
        self._aerial = aerial

    async def _terminal(self, outcome: str, ticket: Ticket, *, faulted: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        self.outcome = outcome
        recovery = faulted or self._recovery or self._snapshot.recovery_required
        self._recovery = recovery
        if recovery or (self._flight_lock and outcome not in {"alerted", "cleared"}):
            phase = "FAULT"
        elif outcome == "aborted":
            phase = "ABORTED"
        else:
            phase = "DONE"
        if recovery and self._fence(ticket):
            self._apply_recovery(ticket)
        self._commit_phase(phase, ticket)
        self._snapshot = replace(
            self._snapshot,
            phase=phase,
            outcome=outcome,
            recovery_required=recovery or self._snapshot.recovery_required,
            flight_lock=self._flight_lock or self._snapshot.flight_lock,
            halt_latched=self._snapshot.halt_latched or self.kernel.authority.cancelled,
            epoch=self.kernel.authority.epoch,
        )
        try:
            if self._fence(ticket):
                await self._publish(ticket, outcome)
        except GroundFault as exc:
            self.failure_code = self.failure_code or exc.error.code
        await self._emit("mission_finished", ticket, {"outcome": outcome})
        self._note("terminal")

    async def _publish(self, ticket: Ticket, outcome: str) -> None:
        if self._reported:
            return
        self._reported = True
        incident = self._admitted
        if incident is None:
            return
        metrics: object = {}
        if self._installed("feature.metrics"):
            self._note("metrics")
            try:
                measured = await self._call(
                    "feature.metrics",
                    kind="projection",
                    name="metrics",
                    ticket=ticket,
                    payload={
                        "events": tuple(self.stage_trace),
                        "snapshot": self._snapshot,
                        "evaluation": None,
                    },
                )
                metrics = measured.data.get("metrics", {})
            except GroundFault:
                metrics = {}
        if not self._installed("feature.report"):
            self.failure_code = self.failure_code or "missing_provider"
            return
        self._note("report")
        published = await self._call(
            "feature.report",
            kind="stage",
            name="report",
            ticket=ticket,
            payload={
                "incident": incident,
                "resolution": self._resolution,
                "outcome": outcome,
                "snapshot": self._snapshot,
                "metrics": metrics if isinstance(metrics, Mapping) else {},
            },
        )
        source = published.data.get("wording_source")
        self.wording_source = source if isinstance(source, str) else None
        if self._installed("feature.status"):
            self._note("status")
            try:
                await self._project_status(ticket)
            except GroundFault:
                return

    async def _startup(self) -> None:
        self._note("startup")
        settings = self._require_settings()
        prior = await self.journal.scan(settings.output_root)
        if not self._installed("feature.restart"):
            self._may_arm = False
            self._motion_gate = False
            return
        result = await self._call(
            "feature.restart",
            kind="stage",
            name="restart",
            ticket=None,
            payload={
                "prior_runs": prior,
                "current_device_status": "not-connected",
                "ownership": "single-laptop",
            },
        )
        may_arm = result.data.get("may_arm") is True
        blocked = result.data.get("recovery_required") is True
        self._may_arm = may_arm and not blocked
        self._motion_gate = self._may_arm

    async def _transport_ok(self, ticket: Ticket) -> bool:
        self._note("transport")
        if not self._fence(ticket):
            return False
        if not self._installed("feature.transport"):
            settings = self._require_settings()
            real = settings.modes["dog"] == "real" or settings.modes["drone"] == "real"
            return not (real and not self._armed)
        result = await self._call(
            "feature.transport",
            kind="guard",
            name="transport",
            ticket=ticket,
            payload={
                "settings": self._require_settings(),
                "snapshot": self._snapshot,
                "acceptance": "operator",
                "tether": self._require_settings().dog_transport,
            },
        )
        return result.data.get("ready") is True

    async def _operate(
        self,
        name: str,
        ticket: Ticket,
        component: str,
        method: str,
        args: tuple[object, ...],
        *,
        limit: float,
        real: bool,
    ) -> OperationResult:
        if not self._fence(ticket):
            raise fault("cancelled", "action fence closed", recovery_required=True)
        if real and self.kernel.clock.is_manual():
            raise fault("invalid_input", "a manual clock cannot drive a real adapter")

        async def factory(context: object) -> object:
            from patrol.contract import RunContext

            if not isinstance(context, RunContext):
                raise fault("invalid_input", "operation context is missing")
            if context.cancel.is_set() or not self._fence(ticket):
                raise fault("cancelled", "action fence closed", recovery_required=True)
            return await self.adapters.invoke(
                component,
                method,
                (*args, context),
                ticket=ticket,
                context=context,
            )

        return await self.executor.run(name, ticket, factory, limit_s=limit)

    async def _call(
        self,
        slot: str,
        *,
        kind: str,
        name: str,
        ticket: Ticket | None,
        payload: Mapping[str, object],
    ) -> FeatureResult:
        if ticket is not None and not self._fence(ticket):
            raise fault("cancelled", "stage ticket is no longer current", recovery_required=True)
        try:
            feature = self.kernel.features.get(slot)
        except GroundFault:
            self._note(f"missing:{slot}")
            raise
        request = self.kernel.result_validation.feature_request(
            slot,
            FeatureRequest(kind, name, ticket, freeze_map(dict(payload))),
        )
        raw = await feature.execute(request)
        if ticket is not None and not self._fence(ticket):
            raise fault(
                "cancelled", "feature result arrived after cancellation", recovery_required=True
            )
        result = self.kernel.result_validation.feature_result(slot, raw)
        if result.status != "ok":
            code = "unavailable" if result.error is None else result.error.code
            detail = "feature failed" if result.error is None else result.error.detail
            recovery = False if result.error is None else result.error.recovery_required
            raise fault(code, detail, recovery_required=recovery)
        self._check_output(slot, result.data)
        if ticket is not None:
            for event in result.events:
                if event.kind == "state_changed":
                    raise fault("validation_failed", "a feature cannot change the phase")
                self.state.apply(event, expected_ticket=ticket)
        return result

    def _check_output(self, slot: str, data: Mapping[str, object]) -> None:
        allowed = CONTINUATIONS.get(slot)
        if allowed is not None:
            value = data.get("continuation")
            if not isinstance(value, str) or value not in allowed:
                raise fault("validation_failed", "continuation is not allowed")
        if slot == "feature.prepare" and not isinstance(data.get("may_route"), bool):
            raise fault("validation_failed", "may_route must be a boolean")
        if slot == "feature.incident_input" and not isinstance(data.get("incident"), Incident):
            raise fault("validation_failed", "incident payload is not an Incident")
        if slot == "feature.restart":
            if not isinstance(data.get("may_arm"), bool) or not isinstance(
                data.get("recovery_required"), bool
            ):
                raise fault("validation_failed", "restart flags must be booleans")
        if slot == "feature.preflight":
            if not isinstance(data.get("may_confirm"), bool) or not isinstance(
                data.get("may_inspect"), bool
            ):
                raise fault("validation_failed", "preflight flags must be booleans")

    def _commit_phase(self, phase: str, ticket: Ticket) -> bool:
        payload: dict[str, object] = {"phase": phase}
        if self.outcome:
            payload["outcome"] = self.outcome
        event = GroundEvent("state_changed", ticket, freeze_map(payload))
        if not self._fence(ticket):
            self._snapshot = replace(
                self._snapshot,
                phase=phase,
                halt_latched=True,
                epoch=self.kernel.authority.epoch,
            )
            return False
        try:
            updated = self.state.apply(event, expected_ticket=ticket)
        except GroundFault:
            self._recovery = True
            self._snapshot = replace(
                self._snapshot,
                phase="FAULT",
                recovery_required=True,
                epoch=self.kernel.authority.epoch,
            )
            return False
        self._snapshot = replace(
            self._snapshot,
            phase=updated.phase,
            epoch=updated.epoch,
            halt_latched=updated.halt_latched,
            recovery_required=updated.recovery_required or self._recovery,
        )
        return True

    def _apply_recovery(self, ticket: Ticket) -> None:
        event = GroundEvent("recovery_required", ticket, freeze_map({}))
        try:
            updated = self.state.apply(event, expected_ticket=ticket)
        except GroundFault:
            self._snapshot = replace(self._snapshot, recovery_required=True)
            return
        self._snapshot = replace(
            self._snapshot,
            recovery_required=True,
            epoch=updated.epoch,
            halt_latched=updated.halt_latched,
        )

    async def _project_status(self, ticket: Ticket) -> None:
        await self._call(
            "feature.status",
            kind="projection",
            name="status",
            ticket=ticket,
            payload={
                "snapshot": self._snapshot,
                "pending_operations": self.executor.pending(),
                "writer_health": "ok",
            },
        )

    async def _status_command(self) -> None:
        ticket = self._ticket
        if ticket is not None and self._fence(ticket) and self._installed("feature.status"):
            try:
                await self._project_status(ticket)
            except GroundFault:
                self.console.write(self.snapshot().phase)
                self.command_log.append("status:builtin")
                return
            self.command_log.append("status:feature")
            return
        self.console.write(self.snapshot().phase)
        self.command_log.append("status:builtin")

    async def _reset_command(self) -> None:
        if self._physical_recovery is not True or bool(self.kernel.tasks.pending()):
            self.command_log.append("reset:rejected")
            return
        await self.safety.reset({"verified": True})
        self._flight_lock = False
        self._recovery = False
        self._armed = False
        self._snapshot = replace(
            self._snapshot,
            phase="IDLE",
            flight_lock=False,
            recovery_required=False,
            armed=False,
            halt_latched=False,
            epoch=self.kernel.authority.epoch,
        )
        self.command_log.append("reset:accepted")

    async def _shutdown_command(self, command: Command) -> None:
        ticket = self._ticket if self._ticket is not None and self._fence(self._ticket) else None
        if self._installed("feature.console_shutdown"):
            try:
                await self._call(
                    "feature.console_shutdown",
                    kind="stage",
                    name="console_shutdown",
                    ticket=ticket,
                    payload={"command": command, "input_event": "quit", "snapshot": self._snapshot},
                )
            except GroundFault:
                self.command_log.append("quit:policy-failed")
        await self.safety.shutdown("operator quit")

    def _schedule_fault(self, name: str, detail: str) -> None:
        if self._persistence_task is not None:
            return

        async def body() -> None:
            if not self._installed("feature.persistence_fault"):
                return
            try:
                await self._call(
                    "feature.persistence_fault",
                    kind="stage",
                    name=name,
                    ticket=None,
                    payload={
                        "writer_health": "fault",
                        "fault_event": detail,
                        "snapshot": self._snapshot,
                    },
                )
            except GroundFault:
                return

        task = asyncio.create_task(body(), name="workflow.persistence")
        self._persistence_task = task
        self.kernel.tasks.retain("workflow.persistence", task)

    async def _health(self) -> None:
        self.health_ran = True
        self.observations["health_phase"] = self.snapshot().phase
        await self._done.wait()

    async def _input_loop(self) -> None:
        self.input_ran = True
        async for command in self.console.commands():
            if command.name == "halt":
                self.request_halt("operator halt")
                self.command_log.append("halt:latched")
                continue
            try:
                await self.route_command(command)
            except GroundFault:
                self.command_log.append(f"{command.name}:error")

    async def _emit(self, event: str, ticket: Ticket | None, data: Mapping[str, object]) -> None:
        if self._emitting:
            return
        self._emitting = True
        try:
            record = self._record(event, ticket, data)
            if self._installed("feature.redaction"):
                try:
                    result = await self._call(
                        "feature.redaction",
                        kind="stage",
                        name="redaction",
                        ticket=None,
                        payload={"record": record, "sensitive_values": ()},
                    )
                except GroundFault:
                    return
                safe = result.data.get("safe_record")
                if not isinstance(safe, EventRecord):
                    return
                record = safe
            elif self._real_motion():
                return
            self.journal.emit(record)
        finally:
            self._emitting = False

    def _record(self, event: str, ticket: Ticket | None, data: Mapping[str, object]) -> EventRecord:
        self._sequence += 1
        started = (
            self._started_mono if self._started_mono is not None else self.kernel.clock.monotonic()
        )
        incident = self._admitted
        settings = self._settings
        modes = settings.modes if settings is not None else self._snapshot.modes
        return EventRecord(
            sequence=self._sequence,
            timestamp_utc=self.kernel.clock.utc_now().isoformat(),
            elapsed_s=self.kernel.clock.monotonic() - started,
            mission_id=None if incident is None else incident.mission_id,
            ticket=ticket,
            state=self._snapshot.phase,
            event=event,
            zone=None if incident is None else incident.zone,
            target=None if incident is None else incident.target,
            modes=modes,
            data=freeze_map(dict(data)),
        )

    def _arrival_payload(self) -> Mapping[str, object]:
        return freeze_map(
            {
                "arrival_confirmed": self._snapshot.arrival_confirmed is True,
                "arrival_monotonic": self._snapshot.arrival_monotonic,
                "arrival_method": self._snapshot.arrival_method or "simulated",
            }
        )

    def _motion_permitted(self) -> bool:
        if not self._motion_gate or self.kernel.authority.cancelled:
            return False
        settings = self._require_settings()
        real = settings.modes["dog"] == "real" or settings.modes["drone"] == "real"
        return not (real and not self._armed)

    def _inspection_permitted(self, request: InspectionRequest) -> bool:
        if self.kernel.authority.cancelled or not self._flight_lock:
            return False
        settings = self._require_settings()
        real = settings.modes["dog"] == "real" or settings.modes["drone"] == "real"
        if real and not self._armed:
            return False
        if request.launch_origin == "dog_pad" and settings.modes["dog"] != "real":
            return False
        expected = (
            "dog_pad" if settings.launch_tier in {"carried_pad", "stationary_pad"} else "floor"
        )
        return request.launch_origin == expected

    def _fence(self, ticket: Ticket) -> bool:
        return not self.kernel.authority.cancelled and ticket.epoch == self.kernel.authority.epoch

    def _installed(self, slot: str) -> bool:
        return slot in self.kernel.features.installed()

    def _real_motion(self) -> bool:
        if self._settings is None:
            return False
        return self._settings.modes["dog"] == "real" or self._settings.modes["drone"] == "real"

    def _require_settings(self) -> GroundSettings:
        if self._settings is None:
            raise fault("invalid_input", "settings are not loaded")
        return self._settings

    def _note(self, name: str) -> None:
        self.stage_trace.append(name)

    def _as_services(self) -> BaseServices:
        if self.services is not None:
            return self.services
        return BaseServices(
            kernel=self.kernel,
            config=self.config,
            state=self.state,
            journal=self.journal,
            executor=self.executor,
            evidence=self.evidence,
            console=self.console,
            adapters=self.adapters,
            workflow=self,
            safety=self.safety,
        )

    async def _wait_until_pending(self, name: str) -> bool:
        for _ in range(300):
            if name in self.kernel.tasks.pending():
                return True
            await asyncio.sleep(0)
        return False

    async def _synthetic_manifest(self) -> FeatureResult:
        root = Path(tempfile.mkdtemp(prefix="ground-g09-"))
        self.cleanup_paths = (str(root),)
        try:
            _write_extension(root)
            found = discover(root, only_task="23")
            manifest = found[0]
            load_callable(manifest, "factory")
            return FeatureResult(
                "ok",
                freeze_map(
                    {
                        "slot": manifest.slot,
                        "schema_version": manifest.schema_version,
                        "device_calls": 0,
                        "live_call_count": 0,
                        "simulated": True,
                        "authorized": True,
                        "detail": "synthetic",
                        "trace": (),
                    }
                ),
                (),
                None,
            )
        except GroundFault as exc:
            return _sim_failed(exc.error.code, exc.error.detail, self)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _fault_outcome(self, exc: GroundFault) -> str:
        if exc.error.code == "cancelled":
            return "aborted"
        if exc.error.code in {
            "missing_provider",
            "validation_failed",
            "stale_ticket",
            "invalid_input",
        }:
            return "unresolved"
        return "failed"


def _script_for(name: str) -> StageScript | None:
    if name == "dispatch_dismiss":
        return StageScript(dispatch_continuation="ignored")
    if name == "ground_clear":
        return StageScript(ground_continuation="resolve", resolution_outcome="cleared")
    if name == "ground_confirmed":
        return StageScript(ground_continuation="resolve", resolution_outcome="confirmed")
    if name == "blocked_resolved":
        return StageScript()
    if name == "missing_dispatch":
        return StageScript(omit=frozenset({"feature.dispatch"}))
    if name == "missing_preflight":
        return StageScript(omit=frozenset({"feature.preflight"}))
    if name in _HOLD_ROUTES:
        return StageScript()
    if name == "malformed_dispatch":
        return StageScript(malformed_slot="feature.dispatch")
    if name == "wrong_continuation":
        return StageScript(bad_continuation=True)
    return None


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise fault("validation_failed", f"{key} is not allowed")
    return value


def _reject(code: str, detail: str) -> AdmissionResult:
    return AdmissionResult(False, None, GroundError(code, detail, False))


def _output_dir(adapters: object) -> Path:
    devices = getattr(adapters, "devices", None)
    output = getattr(devices, "output_dir", None)
    if isinstance(output, Path):
        output.mkdir(parents=True, exist_ok=True)
        return output
    fallback = Path(tempfile.mkdtemp(prefix="ground-g09-out-"))
    return fallback


def _trace_of(safety: object) -> tuple[str, ...]:
    trace = getattr(safety, "trace", ())
    if isinstance(trace, list):
        return tuple(str(item) for item in trace)
    return ()


def _sim_result(workflow: Workflow) -> FeatureResult:
    data = _sim_data(workflow)
    if workflow.failure_code:
        return FeatureResult(
            "failed",
            data,
            (),
            GroundError(
                workflow.failure_code, workflow.failure_code, _recovery_code(workflow.failure_code)
            ),
        )
    return FeatureResult("ok", data, (), None)


def _sim_failed(code: str, detail: str, workflow: Workflow) -> FeatureResult:
    workflow.failure_code = workflow.failure_code or code
    if not workflow.outcome:
        workflow.outcome = detail
    return FeatureResult(
        "failed",
        _sim_data(workflow),
        (),
        GroundError(code, detail, _recovery_code(code)),
    )


def _sim_data(workflow: Workflow) -> Mapping[str, object]:
    devices = getattr(workflow.adapters, "devices", None)
    calls = getattr(devices, "calls", ())
    live = getattr(devices, "live_call_count", 0)
    return freeze_map(
        {
            "trace": tuple(workflow.stage_trace),
            "live_call_count": live if isinstance(live, int) and not isinstance(live, bool) else 0,
            "simulated": True,
            "device_calls": len(calls) if isinstance(calls, list) else 0,
            "authorized": not workflow.kernel.authority.cancelled,
            "detail": workflow.outcome or workflow.failure_code or "completed",
        }
    )


def _recovery_code(code: str) -> bool:
    return code in {"cancelled", "expired_deadline", "io_fault", "missing_provider", "timeout"}


def _write_extension(root: Path) -> None:
    directory = root / "g23"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "implementation.py").write_text(
        "def create(services):\n    return services\n",
        encoding="utf-8",
    )
    (directory / "scenarios.py").write_text(
        "def cases(seed=0):\n    return ()\n",
        encoding="utf-8",
    )
    body = {
        "schema_version": SCHEMA_VERSION,
        "task_id": "GROUND-23",
        "slot": "feature.status",
        "factory": "patrol.ground.extensions.g23.implementation:create",
        "scenario_factory": "patrol.ground.extensions.g23.scenarios:cases",
    }
    (directory / "manifest.json").write_text(json.dumps(body), encoding="utf-8")
