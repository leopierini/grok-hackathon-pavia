"""Explicit stage pack for tests and simulation.

Production ``create()`` does not install this pack. A test or the simulation
execute path must call ``install_stage_pack`` itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from patrol.contract import (
    DispatchDecision,
    Frame,
    GroundDecision,
    Incident,
    InspectionRequest,
    InspectionResult,
    Resolution,
    RouteResult,
    RunContext,
    Zone,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    CaptureInterval,
    EventRecord,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    GroundSettings,
    OperationResult,
    SessionSnapshot,
    Ticket,
)
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.features import FeatureMap
from patrol.ground.kernel.validation import freeze_map

READY_TOKEN = "ready-token"

_PACK: tuple[str, ...] = (
    "feature.incident_input",
    "feature.dispatch",
    "feature.prepare",
    "feature.route_result",
    "feature.arrival",
    "feature.dog_frame",
    "feature.ground_view",
    "feature.preflight",
    "feature.flight_ready",
    "feature.inspection_result",
    "feature.resolution",
    "feature.report",
    "feature.restart",
    "feature.redaction",
    "feature.metrics",
    "feature.status",
    "feature.transport",
    "feature.persistence_fault",
    "feature.console_shutdown",
)


@dataclass(frozen=True)
class StageScript:
    """Overrides for one scripted run. Omitted slots are not registered."""

    dispatch_continuation: str | None = None
    ground_continuation: str | None = None
    resolution_outcome: str | None = None
    omit: frozenset[str] | None = None
    malformed_slot: str | None = None
    bad_continuation: bool = False
    forged_ticket: bool = False
    hold_slot: str | None = None
    arrival_confirmed: bool = True
    initial_may_inspect: bool = False
    restart_may_arm: bool = True
    restart_recovery: bool = False
    prepare_bad_bool: bool = False
    reject_flight_ready: bool = False


def install_stage_pack(services: BaseServices, script: StageScript | None = None) -> None:
    selected = script or StageScript()
    skipped = selected.omit or frozenset()
    features = services.kernel.features
    if not isinstance(features, FeatureMap):
        raise fault("invalid_input", "stage pack requires the kernel feature map")
    for slot in _PACK:
        if slot in skipped:
            continue
        features.register(slot, ScriptedFeature(services, selected, slot))


class ScriptedFeature:
    def __init__(self, services: BaseServices, script: StageScript, slot: str) -> None:
        self.services = services
        self.script = script
        self.slot = slot

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if self.script.hold_slot == self.slot:
            self._note(f"holding:{self.slot}")
            await self.services.kernel.barriers.wait(self.slot)
        if self.script.malformed_slot == self.slot:
            return _ok(surprise=True)
        handler = {
            "feature.incident_input": self._incident_input,
            "feature.dispatch": self._dispatch,
            "feature.prepare": self._prepare,
            "feature.route_result": self._route_result,
            "feature.arrival": self._arrival,
            "feature.dog_frame": self._dog_frame,
            "feature.ground_view": self._ground_view,
            "feature.preflight": self._preflight,
            "feature.flight_ready": self._flight_ready,
            "feature.inspection_result": self._inspection,
            "feature.resolution": self._resolution,
            "feature.report": self._report,
            "feature.restart": self._restart,
            "feature.redaction": self._redaction,
            "feature.metrics": self._metrics,
            "feature.status": self._status,
            "feature.transport": self._transport,
            "feature.persistence_fault": self._persistence,
            "feature.console_shutdown": self._shutdown,
        }.get(self.slot)
        if handler is None:
            return _failed("unknown_slot", "scripted slot is not in the pack", False)
        try:
            return await handler(request)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, exc.error.recovery_required)

    async def _incident_input(self, request: FeatureRequest) -> FeatureResult:
        image_path = request.payload.get("image_path")
        zone = request.payload.get("zone")
        target = request.payload.get("target")
        captured_at = request.payload.get("captured_at")
        simulated = request.payload.get("simulated")
        if not isinstance(image_path, str) or not image_path:
            return _failed("invalid_input", "image path is required", False)
        if not isinstance(zone, str) or zone not in {"entrance", "room_2", "display"}:
            return _failed("invalid_input", "zone is not allowed", False)
        if not isinstance(target, str) or not target.strip() or len(target.strip()) > 500:
            return _failed("invalid_input", "target is empty or too long", False)
        if simulated is not True and simulated is not False:
            return _failed("invalid_input", "simulated must be a boolean", False)
        if captured_at is not None and not isinstance(captured_at, str):
            return _failed("invalid_input", "captured_at must be a string or null", False)
        try:
            data = self.services.kernel.io.read_bytes(Path(image_path), limit=2_000_000)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail, exc.error.recovery_required)
        if not data.startswith(b"\xff\xd8"):
            return _failed("rejected", "phone input is not a JPEG", False)
        trusted = cast(Zone, zone)
        frame = Frame(
            str(Path(image_path).resolve()),
            "phone",
            trusted,
            captured_at if isinstance(captured_at, str) else None,
            simulated,
        )
        incident = Incident(f"m-{self.services.kernel.seed}-1", trusted, target.strip(), frame)
        return _ok(incident=incident, provenance="operator-supplied")

    async def _dispatch(self, request: FeatureRequest) -> FeatureResult:
        if self.script.bad_continuation:
            return _ok(decision="dispatch", continuation=1)
        if self.script.forged_ticket:
            epoch = request.ticket.epoch if request.ticket is not None else 0
            forged = Ticket("other-mission", epoch, "forged")
            event = GroundEvent("decision_received", forged, freeze_map({}))
            return FeatureResult(
                "ok",
                freeze_map({"decision": "dispatch", "continuation": "investigate"}),
                (event,),
                None,
            )
        if self.script.dispatch_continuation is not None:
            return _ok(decision="scripted", continuation=self.script.dispatch_continuation)
        operation = request.payload.get("operation")
        if not isinstance(operation, OperationResult) or not isinstance(
            operation.value, DispatchDecision
        ):
            return _failed("validation_failed", "dispatch operation is missing", False)
        mapped = {"dispatch": "investigate", "dismiss": "ignored", "review": "unresolved"}
        return _ok(decision=operation.value.action, continuation=mapped[operation.value.action])

    async def _prepare(self, request: FeatureRequest) -> FeatureResult:
        if self.script.prepare_bad_bool:
            return _ok(preparation="bad", dog_status="unknown", may_route="true")
        incident = _incident(request)
        settings = request.payload.get("settings")
        if incident is None or not isinstance(settings, GroundSettings):
            return _failed("validation_failed", "prepare inputs are incomplete", False)
        if request.ticket is None:
            return _failed("not_admitted", "prepare requires a mission ticket", False)
        context = self._context(
            incident.mission_id,
            settings.prepare_limit_s,
            settings.incident_timeout_s,
            real=settings.modes.get("dog") == "real",
        )
        status = await self.services.adapters.invoke(
            "dog",
            "prepare",
            (context,),
            ticket=request.ticket,
            context=context,
        )
        ready = (
            getattr(status, "connected", None) is True
            and getattr(status, "standing", None) is True
            and getattr(status, "stationary", None) is True
            and getattr(status, "avoidance_enabled", None) is True
        )
        return _ok(
            preparation="standing" if ready else "unsafe", dog_status=status, may_route=ready
        )

    async def _route_result(self, request: FeatureRequest) -> FeatureResult:
        operation = request.payload.get("operation")
        route = operation.value if isinstance(operation, OperationResult) else None
        if not isinstance(route, RouteResult):
            return _ok(route="missing", may_wait_arrival=False)
        may_wait = route.completed is True and route.stopped is True
        return _ok(route=route, may_wait_arrival=may_wait)

    async def _arrival(self, request: FeatureRequest) -> FeatureResult:
        if self.script.arrival_confirmed is not True:
            return _ok(arrival_confirmed=False, arrival_monotonic=None, arrival_method=None)
        return _ok(
            arrival_confirmed=True,
            arrival_monotonic=self.services.kernel.clock.monotonic(),
            arrival_method="simulated",
        )

    async def _dog_frame(self, request: FeatureRequest) -> FeatureResult:
        incident = _incident(request)
        snapshot = request.payload.get("snapshot")
        if incident is None or not isinstance(snapshot, SessionSnapshot) or request.ticket is None:
            return _failed("validation_failed", "dog frame inputs are incomplete", False)
        started = self.services.kernel.clock.monotonic()
        started_utc = self.services.kernel.clock.utc_now().isoformat()
        context = self._context(
            incident.mission_id,
            10.0,
            180.0,
            real=snapshot.modes.get("dog") == "real",
        )
        frame = await self.services.adapters.invoke(
            "dog",
            "capture_frame",
            (incident.zone, context),
            ticket=request.ticket,
            context=context,
        )
        if not isinstance(frame, Frame):
            return _failed("validation_failed", "capture did not return a frame", False)
        interval = CaptureInterval(
            started,
            self.services.kernel.clock.monotonic(),
            started_utc,
            self.services.kernel.clock.utc_now().isoformat(),
        )
        return _ok(ground=frame, interval=interval, validation="ok")

    async def _ground_view(self, request: FeatureRequest) -> FeatureResult:
        if self.script.ground_continuation is not None:
            return _ok(decision="scripted", continuation=self.script.ground_continuation)
        operation = request.payload.get("operation")
        if not isinstance(operation, OperationResult) or not isinstance(
            operation.value, GroundDecision
        ):
            return _failed("validation_failed", "ground view operation is missing", False)
        mapped = {"sufficient": "resolve", "inspect": "preflight", "review": "unresolved"}
        return _ok(decision=operation.value.action, continuation=mapped[operation.value.action])

    async def _preflight(self, request: FeatureRequest) -> FeatureResult:
        check = request.payload.get("check")
        incident = _incident(request)
        snapshot = request.payload.get("snapshot")
        if incident is None or not isinstance(snapshot, SessionSnapshot) or request.ticket is None:
            return _failed("validation_failed", "preflight inputs are incomplete", False)
        if not self.services.kernel.authority.cancelled:
            await self.services.adapters.status("dog")
            await self.services.adapters.status("drone")
        if check == "initial":
            return _ok(
                inspection_request=None,
                checks="initial",
                may_confirm=True,
                may_inspect=self.script.initial_may_inspect is True,
            )
        if check != "final":
            return _ok(
                inspection_request=None, checks="rejected", may_confirm=False, may_inspect=False
            )
        readiness = request.payload.get("readiness")
        settings = request.payload.get("settings")
        if readiness != READY_TOKEN or not isinstance(settings, GroundSettings):
            return _ok(
                inspection_request=None,
                checks="stale-readiness",
                may_confirm=False,
                may_inspect=False,
            )
        profile = settings.profile_by_zone.get(incident.zone)
        if not isinstance(profile, str):
            return _ok(
                inspection_request=None, checks="no-profile", may_confirm=False, may_inspect=False
            )
        if settings.launch_tier in {"carried_pad", "stationary_pad"}:
            inspection = InspectionRequest(incident.zone, profile, "dog_pad")
        else:
            inspection = InspectionRequest(incident.zone, profile, "floor")
        return _ok(
            inspection_request=inspection,
            checks="final",
            may_confirm=False,
            may_inspect=True,
        )

    async def _flight_ready(self, request: FeatureRequest) -> FeatureResult:
        del request
        if self.script.reject_flight_ready:
            return _ok(readiness=None, confirmation_method="rejected")
        return _ok(readiness=READY_TOKEN, confirmation_method="simulated")

    async def _inspection(self, request: FeatureRequest) -> FeatureResult:
        operation = request.payload.get("operation")
        if not isinstance(operation, OperationResult) or not isinstance(
            operation.value, InspectionResult
        ):
            return _failed("validation_failed", "inspection operation is missing", False)
        result = operation.value
        if result.flight_state == "unknown":
            continuation = "fault"
            recovery = True
        elif result.outcome == "captured" and result.flight_state == "grounded":
            continuation = "resolve"
            recovery = False
        elif result.outcome == "unavailable":
            continuation = "unresolved"
            recovery = False
        else:
            continuation = "failed"
            recovery = result.flight_state != "grounded"
        return _ok(
            aerial=result.frame,
            flight_state=result.flight_state,
            continuation=continuation,
            recovery_required=recovery,
        )

    async def _resolution(self, request: FeatureRequest) -> FeatureResult:
        if self.script.resolution_outcome is not None:
            name = self.script.resolution_outcome
        else:
            operation = request.payload.get("operation")
            value = operation.value if isinstance(operation, OperationResult) else None
            name = value.outcome if isinstance(value, Resolution) else "inconclusive"
        if name == "confirmed":
            verdict = Resolution("confirmed", "scripted summary", "scripted reason")
            terminal = "alerted"
        elif name == "cleared":
            verdict = Resolution("cleared", "scripted summary", "scripted reason")
            terminal = "cleared"
        elif name == "inconclusive":
            verdict = Resolution("inconclusive", "scripted summary", "scripted reason")
            terminal = "unresolved"
        else:
            return _failed("validation_failed", "resolution name is not allowed", False)
        return _ok(resolution=verdict, outcome=terminal)

    async def _report(self, request: FeatureRequest) -> FeatureResult:
        published = getattr(self.services.journal, "published", None)
        if published is not None:
            return _failed("rejected", "a summary was already published", True)
        incident = _incident(request)
        outcome = request.payload.get("outcome")
        resolution = request.payload.get("resolution")
        if incident is None or not isinstance(outcome, str):
            return _failed("validation_failed", "report inputs are incomplete", False)
        text: object
        if resolution is None:
            text = f"status:{outcome}"
            source = "template"
        elif isinstance(resolution, Resolution) and request.ticket is not None:
            snapshot = request.payload.get("snapshot")
            real = isinstance(snapshot, SessionSnapshot) and snapshot.modes.get("grok") == "real"
            context = self._context(incident.mission_id, 20.0, 180.0, real=real)
            text = await self.services.adapters.invoke(
                "reasoner",
                "compose_alert",
                (incident, resolution, context),
                ticket=request.ticket,
                context=context,
            )
            if not isinstance(text, str) or not text:
                return _failed("validation_failed", "wording did not return text", False)
            source = "reasoner"
        else:
            return _failed("validation_failed", "resolution payload is not usable", False)
        summary = freeze_map(
            {
                "contract_version": "1.0",
                "mission_id": incident.mission_id,
                "outcome": outcome,
                "alert": text,
            }
        )
        await self.services.journal.publish(summary)
        return _ok(
            report=text,
            summary=summary,
            wording_source=source,
            publication_status="published",
        )

    async def _restart(self, request: FeatureRequest) -> FeatureResult:
        prior = request.payload.get("prior_runs")
        incomplete: object = "none"
        may_arm = self.script.restart_may_arm
        recovery = self.script.restart_recovery
        if isinstance(prior, tuple) and prior:
            may_arm = False
            recovery = True
            incomplete = "prior-run"
        return _ok(may_arm=may_arm, recovery_required=recovery, incomplete_run=incomplete)

    async def _redaction(self, request: FeatureRequest) -> FeatureResult:
        record = request.payload.get("record")
        if not isinstance(record, EventRecord):
            return _failed("validation_failed", "record is not an EventRecord", False)
        return _ok(safe_record=record, rejected_fields=())

    async def _metrics(self, request: FeatureRequest) -> FeatureResult:
        del request
        return _ok(
            metrics=freeze_map({"source": "events"}), denominators=(), unavailable_reasons=()
        )

    async def _status(self, request: FeatureRequest) -> FeatureResult:
        snapshot = request.payload.get("snapshot")
        phase = snapshot.phase if isinstance(snapshot, SessionSnapshot) else "unknown"
        return _ok(display=phase, status_fields=freeze_map({"phase": phase}))

    async def _transport(self, request: FeatureRequest) -> FeatureResult:
        snapshot = request.payload.get("snapshot")
        profile = snapshot.dog_transport if isinstance(snapshot, SessionSnapshot) else "ethernet"
        return _ok(ready=True, checks="scripted", profile=profile)

    async def _persistence(self, request: FeatureRequest) -> FeatureResult:
        del request
        return _ok(block_actions=True, request_safety=True, persistence_status="latched")

    async def _shutdown(self, request: FeatureRequest) -> FeatureResult:
        del request
        return _ok(shutdown_intent="quit", cleanup_result="lifecycle-requested")

    def _context(
        self, mission_id: str, limit: float, mission_limit: float, *, real: bool
    ) -> RunContext:
        clock = self.services.kernel.clock
        return context_for_stage(
            mission_id,
            clock.monotonic() + mission_limit,
            limit,
            self.services.kernel.authority.cancel_event,
            clock,
            real_adapter=real,
        )

    def _note(self, name: str) -> None:
        devices = getattr(self.services.adapters, "devices", None)
        note = getattr(devices, "note", None)
        if callable(note):
            note(name)


def _incident(request: FeatureRequest) -> Incident | None:
    incident = request.payload.get("incident")
    if isinstance(incident, Incident):
        return incident
    return None


def _ok(**data: object) -> FeatureResult:
    return FeatureResult("ok", freeze_map(data), (), None)


def _failed(code: str, detail: str, recovery: bool) -> FeatureResult:
    return FeatureResult("failed", freeze_map({}), (), GroundError(code, detail, recovery))
