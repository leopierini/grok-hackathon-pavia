"""Simulation adapter. The harness calls this object; production code calls SessionStore."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard

from patrol.ground.extensions.g03.script import (
    DRONE_PATH,
    Script,
    phase_trace,
    reach,
    sample_incident,
)
from patrol.ground.extensions.g03.store import SessionStore
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    ServicePorts,
)
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.validation import freeze_map


class SimulationFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        handlers = {
            "normal_phases": self._normal,
            "single_admission": self._single,
            "halt_fence": self._halt,
            "reset_epoch": self._reset,
            "unknown_landing": self._unknown,
            "illegal_edges": self._illegal,
            "replay_match": self._replay,
            "pure_reduction": self._pure,
            "tri_state": self._tri_state,
            "early_confirmation": self._early,
        }
        handler = handlers.get(request.name)
        if handler is None:
            return _failed("invalid_input", "unknown state case")
        try:
            result = handler()
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail)
        if peer_activity(self.services) != 0:
            return _failed("internal", "state reduction called a peer or retained a task")
        return result

    def _normal(self) -> FeatureResult:
        _services, store, script = self._session()
        trace = phase_trace(script, "DONE")
        snap = store.snapshot()
        zone = snap.incident.zone if snap.incident is not None else "none"
        detail = (
            f"outcome={snap.outcome};arrival_confirmed={_flag(snap.arrival_confirmed)};"
            f"arrival_method={snap.arrival_method};flight_lock={_flag(snap.flight_lock)};"
            f"recovery_required={_flag(snap.recovery_required)};zone={zone}"
        )
        return _ok(trace=trace, detail=detail, authorized=True)

    def _single(self) -> FeatureResult:
        _services, store, script = self._session()
        incident = store.snapshot().incident
        settings = make_settings()
        if incident is None:
            return _failed("internal", "mission was not opened")
        try:
            store.open(incident, settings)
        except GroundFault:
            duplicate_open = True
        else:
            duplicate_open = False
        reach(script, "ASSESS")
        try:
            script.apply("permission_consumed", "start")
        except GroundFault:
            duplicate_start = True
        else:
            duplicate_start = False
        decision, ticket = script.event(
            "decision_received",
            "start",
            scope="dispatch",
            action="dispatch",
            reason="scene text is not a command",
        )
        first = store.apply(decision, expected_ticket=ticket)
        second = store.apply(decision, expected_ticket=ticket)
        duplicate_decision = first == second and first.phase == "PREPARE_DOG"
        reach(script, "DONE")
        try:
            script.apply("report_saved", "report")
        except GroundFault:
            duplicate_completion = True
        else:
            duplicate_completion = False
        publications = store.snapshot().decisions.get("publications")
        if not (
            duplicate_open
            and duplicate_start
            and duplicate_decision
            and duplicate_completion
            and store.mission_count == 1
            and publications == 1
        ):
            return _failed("validation_failed", "admission did not stay single")
        return _ok(
            trace=(
                "missions:1",
                "publications:1",
                "duplicate_start_rejected",
                "duplicate_decision_ignored",
                "duplicate_completion_rejected",
            ),
            detail="missions=1;publications=1",
            authorized=True,
        )

    def _halt(self) -> FeatureResult:
        services, store, script = self._session()
        reach(script, "MOVE_DOG")
        script.apply("operation_started", "route", operation="dog.run_route")
        late_ticket = services.kernel.authority.issue(store.snapshot().mission_id or "", "route")
        script.apply(
            "halt_requested",
            "halt",
            physical_state="known",
            reason="operator halt",
        )
        services.kernel.authority.latch_cancel("operator halt")
        late = script.bind(
            late_ticket,
            "operation_completed",
            operation="dog.run_route",
            completed=True,
            stopped=True,
        )
        try:
            store.apply(late, expected_ticket=late_ticket)
        except GroundFault:
            rejected = True
        else:
            rejected = False
        snap = store.snapshot()
        if not rejected or snap.phase != "ABORTED" or snap.outcome != "aborted":
            return _failed("validation_failed", "halt did not fence the late result")
        if snap.arrival_confirmed is not None:
            return _failed("validation_failed", "halted route was treated as arrival")
        return _ok(
            trace=("MOVE_DOG", "ABORTED", "late_result_rejected"),
            detail="phase=ABORTED;outcome=aborted;arrival_confirmed=none",
            authorized=False,
        )

    def _reset(self) -> FeatureResult:
        services, store, script = self._session()
        mission_id = store.snapshot().mission_id or ""
        old_ticket = services.kernel.authority.issue(mission_id, "arrive")
        reach(script, "MOVE_DOG")
        script.apply("halt_requested", "halt", physical_state="known", reason="operator halt")
        services.kernel.authority.latch_cancel("operator halt")
        services.kernel.authority.reset_generation("operator recovery")
        script.apply("recovery_cleared", "reset", verified=True)
        late = script.bind(
            old_ticket,
            "arrival_confirmed",
            zone="room_2",
            method="simulated",
            monotonic=12.5,
        )
        try:
            store.apply(late, expected_ticket=old_ticket)
        except GroundFault:
            rejected = True
        else:
            rejected = False
        snap = store.snapshot()
        if not rejected or snap.phase != "IDLE" or snap.incident is not None:
            return _failed("validation_failed", "recovery did not open a fresh idle session")
        if snap.epoch != 2 or snap.arrival_confirmed is not None or snap.flight_lock:
            return _failed("validation_failed", "old confirmation survived recovery")
        return _ok(
            trace=("IDLE", "epoch_advanced", "old_confirmation_rejected"),
            detail="epoch=2;arrival_confirmed=none;flight_lock=false",
            authorized=False,
        )

    def _unknown(self) -> FeatureResult:
        _services, store, script = self._session()
        reach(script, "INSPECT")
        script.apply(
            "operation_completed",
            "inspect",
            operation="drone.inspect",
            outcome="captured",
            flight_state="unknown",
            frame_source="drone",
            frame_zone="room_2",
            frame_path=DRONE_PATH,
            frame_captured_at="2026-11-04T13:00:00Z",
            frame_simulated=True,
        )
        try:
            script.apply(
                "decision_received",
                "inspect",
                scope="resolution",
                action="confirmed",
                reason="late success must not clear the fault",
            )
        except GroundFault:
            held = True
        else:
            held = False
        snap = store.snapshot()
        aerial = snap.evidence.get("aerial")
        path = aerial.get("path") if _is_mapping(aerial) else None
        if (
            not held
            or snap.phase != "FAULT"
            or snap.outcome != "failed"
            or snap.recovery_required is not True
            or snap.flight_lock is not True
            or path != DRONE_PATH
        ):
            return _failed("validation_failed", "unknown landing did not stay faulted")
        return _ok(
            trace=("FAULT", "fault_held"),
            detail=(
                "outcome=failed;phase=FAULT;recovery_required=true;"
                "flight_lock=true;frame_retained=true"
            ),
            authorized=False,
        )

    def _illegal(self) -> FeatureResult:
        _services, store, script = self._session()
        reach(script, "WAIT_ARRIVAL")
        try:
            script.apply("state_changed", "route", phase="DONE")
        except GroundFault:
            illegal = True
        else:
            illegal = False
        try:
            script.apply(
                "arrival_confirmed",
                "arrive",
                zone="display",
                method="simulated",
                monotonic=1.0,
            )
        except GroundFault:
            wrong_zone = True
        else:
            wrong_zone = False
        snap = store.snapshot()
        if not illegal or not wrong_zone or snap.phase != "WAIT_ARRIVAL":
            return _failed("validation_failed", "illegal transition was applied")
        if snap.arrival_confirmed is not None:
            return _failed("validation_failed", "wrong-zone arrival was stored")
        return _ok(
            trace=("illegal_phase_rejected", "wrong_zone_rejected"),
            detail="phase=WAIT_ARRIVAL;arrival_confirmed=none",
            authorized=False,
        )

    def _replay(self) -> FeatureResult:
        services, store, script = self._session()
        incident = store.snapshot().incident
        if incident is None:
            return _failed("internal", "mission was not opened")
        phase_trace(script, "DONE")
        other = SessionStore(services.kernel, _ports(services))
        other.open(incident, make_settings())
        for event, ticket in script.applied:
            other.apply(event, expected_ticket=ticket)
        if store.snapshot() != other.snapshot():
            return _failed("validation_failed", "replayed snapshots diverged")
        return _ok(trace=("replay_match",), detail="equal=true", authorized=True)

    def _pure(self) -> FeatureResult:
        _services, _store, script = self._session()
        phase_trace(script, "ASSESS")
        pending = self.services.kernel.tasks.pending()
        if peer_activity(self.services) != 0 or pending:
            return _failed("internal", "pure reduction retained work")
        return _ok(
            trace=("peer_calls:0",),
            detail="retained=false",
            authorized=True,
            retained=False,
        )

    def _tri_state(self) -> FeatureResult:
        _services, store, script = self._session()
        reach(script, "PREPARE_DOG")
        script.apply("operation_started", "prepare", operation="dog.prepare")
        try:
            script.apply(
                "operation_completed",
                "prepare",
                operation="dog.prepare",
                connected=True,
                standing="true",
                stationary=True,
                avoidance_enabled=True,
            )
        except GroundFault as exc:
            string_rejected = exc.error.code == "invalid_input"
        else:
            string_rejected = False
        if store.snapshot().phase != "PREPARE_DOG":
            return _failed("validation_failed", "string boolean changed the phase")
        script.apply(
            "operation_completed",
            "prepare",
            operation="dog.prepare",
            connected=True,
            standing=None,
            stationary=True,
            avoidance_enabled=True,
        )
        snap = store.snapshot()
        status = snap.decisions.get("dog_status")
        standing = status.get("standing") if _is_mapping(status) else "missing"
        if (
            not string_rejected
            or snap.phase != "FAULT"
            or snap.recovery_required is not True
            or standing is not None
            or snap.phase == "MOVE_DOG"
        ):
            return _failed("validation_failed", "unknown dog state was normalized")
        return _ok(
            trace=("string_rejected", "unknown_faulted", "route_not_started"),
            detail="phase=FAULT;recovery_required=true;standing=unknown",
            authorized=False,
        )

    def _early(self) -> FeatureResult:
        _services, store, script = self._session()
        reach(script, "WAIT_ARRIVAL")
        early, ticket = script.event("flight_ready_confirmed", "ready", method="simulated")
        try:
            store.apply(early, expected_ticket=ticket)
        except GroundFault:
            rejected = True
        else:
            rejected = False
        reach(script, "PREFLIGHT")
        store.apply(early, expected_ticket=ticket)
        snap = store.snapshot()
        if not rejected or snap.phase != "PREFLIGHT" or snap.readiness_confirmed is not None:
            return _failed("validation_failed", "early flight-ready was buffered")
        return _ok(
            trace=("early_flight_ready_rejected", "readiness_still_clear"),
            detail="phase=PREFLIGHT;readiness_confirmed=none",
            authorized=False,
        )

    def _session(self) -> tuple[BaseServices, SessionStore, Script]:
        services = self.services
        store = SessionStore(services.kernel, _ports(services))
        incident = sample_incident()
        store.open(incident, make_settings())
        script = Script(services.kernel.authority, store, incident.mission_id)
        return services, store, script


def peer_activity(services: BaseServices) -> int:
    total = 0
    ports = (
        services.config,
        services.state,
        services.journal,
        services.executor,
        services.evidence,
        services.console,
        services.adapters,
        services.workflow,
        services.safety,
    )
    for port in ports:
        for name in ("trace", "records"):
            value = getattr(port, name, None)
            if isinstance(value, list):
                total += len(value)
        devices = getattr(port, "devices", None)
        calls = getattr(devices, "calls", None)
        if isinstance(calls, list):
            total += len(calls)
    total += len(services.kernel.tasks.pending())
    return total


def _ports(services: BaseServices) -> ServicePorts:
    return ServicePorts(
        config=services.config,
        state=services.state,
        journal=services.journal,
        executor=services.executor,
        evidence=services.evidence,
        console=services.console,
        adapters=services.adapters,
        workflow=services.workflow,
        safety=services.safety,
    )


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _flag(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "none"


def _ok(
    *,
    trace: tuple[str, ...],
    detail: str,
    authorized: bool,
    retained: bool | None = None,
) -> FeatureResult:
    data: dict[str, object] = {
        "slot": "base.state",
        "schema_version": SCHEMA_VERSION,
        "simulated": True,
        "device_calls": 0,
        "live_call_count": 0,
        "authorized": authorized,
        "trace": trace,
        "detail": detail,
    }
    if retained is not None:
        data["retained"] = retained
    return FeatureResult("ok", freeze_map(data), (), None)


def _failed(code: str, detail: str) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map({"slot": "base.state", "schema_version": SCHEMA_VERSION, "device_calls": 0}),
        (),
        GroundError(code, detail, False),
    )
