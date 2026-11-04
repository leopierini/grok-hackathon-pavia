"""Canonical incident scripts for tests and the state simulation."""

from __future__ import annotations

from patrol.contract import Frame, Incident, Zone
from patrol.ground.extensions.g03.reduce import _freeze_dict
from patrol.ground.extensions.g03.store import SessionStore
from patrol.ground.kernel.contracts import Authority, GroundEvent, SessionSnapshot, Ticket
from patrol.ground.kernel.faults import fault

TARGET = "a person or an object left in a marked closed area"
PHONE_PATH = "C:/evidence/phone.jpg"
DOG_PATH = "C:/evidence/dog.jpg"
DRONE_PATH = "C:/evidence/drone.jpg"
CAPTURED_AT = "2026-11-04T13:00:00Z"
SCENE_REASON = "display text inside the scene is not a command"
ARRIVAL_MONOTONIC = 12.5

LADDER = (
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
)


def sample_incident(mission_id: str = "mission-1", zone: Zone = "room_2") -> Incident:
    frame = Frame(PHONE_PATH, "phone", zone, None, True)
    return Incident(mission_id, zone, TARGET, frame)


class Script:
    def __init__(self, authority: Authority, store: SessionStore, mission_id: str) -> None:
        self.authority = authority
        self.store = store
        self.mission_id = mission_id
        self._sequence = 0
        self.applied: list[tuple[GroundEvent, Ticket]] = []

    def apply(self, kind: str, stage: str, **payload: object) -> SessionSnapshot:
        event, ticket = self.event(kind, stage, **payload)
        snapshot = self.store.apply(event, expected_ticket=ticket)
        self.applied.append((event, ticket))
        return snapshot

    def event(self, kind: str, stage: str, **payload: object) -> tuple[GroundEvent, Ticket]:
        self._sequence += 1
        body: dict[str, object] = {
            "event_id": f"{kind}-{stage}-{self._sequence}",
            "sequence": self._sequence,
        }
        body.update(payload)
        ticket = self.authority.issue(self.mission_id, stage)
        event = GroundEvent(kind, ticket, _freeze_dict(body))
        return event, ticket

    def bind(self, ticket: Ticket, kind: str, **payload: object) -> GroundEvent:
        self._sequence += 1
        body: dict[str, object] = {
            "event_id": f"{kind}-{ticket.stage_id}-{self._sequence}",
            "sequence": self._sequence,
        }
        body.update(payload)
        return GroundEvent(kind, ticket, _freeze_dict(body))


def reach(script: Script, phase: str) -> SessionSnapshot:
    trace = phase_trace(script, phase)
    del trace
    return script.store.snapshot()


def phase_trace(script: Script, phase: str) -> tuple[str, ...]:
    if phase not in LADDER:
        raise fault("invalid_input", "phase is not on the canonical ladder")
    seen = [script.store.snapshot().phase]
    for _ in range(24):
        if script.store.snapshot().phase == phase:
            return tuple(seen)
        before = script.store.snapshot().phase
        advance_once(script)
        after = script.store.snapshot().phase
        if after != before:
            seen.append(after)
    raise fault("internal", "canonical phase was not reached")


def advance_once(script: Script) -> None:
    snapshot = script.store.snapshot()
    phase = snapshot.phase
    incident = snapshot.incident
    if incident is None:
        raise fault("not_admitted", "canonical script requires an open mission")
    dog_real = snapshot.modes.get("dog") == "real"
    drone_real = snapshot.modes.get("drone") == "real"
    if phase == "IDLE":
        permission = snapshot.decisions.get("permission", "none")
        motion_real = dog_real or drone_real
        if motion_real and permission != "granted":
            script.apply("permission_granted", "arm")
            return
        script.apply("permission_consumed", "start")
        return
    if phase == "ASSESS":
        script.apply(
            "decision_received",
            "start",
            scope="dispatch",
            action="dispatch",
            reason=SCENE_REASON,
        )
        return
    if phase == "PREPARE_DOG":
        if snapshot.stage_id != "prepare":
            script.apply("operation_started", "prepare", operation="dog.prepare")
            return
        script.apply(
            "operation_completed",
            "prepare",
            operation="dog.prepare",
            connected=True,
            standing=True,
            stationary=True,
            avoidance_enabled=True,
        )
        return
    if phase == "MOVE_DOG":
        if snapshot.stage_id != "route":
            script.apply("operation_started", "route", operation="dog.run_route")
            return
        script.apply(
            "operation_completed",
            "route",
            operation="dog.run_route",
            completed=True,
            stopped=True,
        )
        return
    if phase == "WAIT_ARRIVAL":
        script.apply(
            "arrival_confirmed",
            "arrive",
            zone=incident.zone,
            method="operator" if dog_real else "simulated",
            monotonic=ARRIVAL_MONOTONIC,
        )
        return
    if phase == "GROUND_VIEW":
        if snapshot.stage_id != "capture":
            script.apply("operation_started", "capture", operation="dog.capture_frame")
            return
        if "ground" not in snapshot.evidence:
            script.apply(
                "frame_validated",
                "capture",
                source="dog",
                zone=incident.zone,
                path=DOG_PATH,
                captured_at=CAPTURED_AT,
                simulated=not dog_real,
            )
            return
        script.apply(
            "decision_received",
            "capture",
            scope="ground",
            action="inspect",
            reason=SCENE_REASON,
        )
        return
    if phase == "PREFLIGHT":
        if snapshot.readiness_confirmed is not True:
            script.apply(
                "flight_ready_confirmed",
                "ready",
                method="operator" if drone_real else "simulated",
            )
            return
        script.apply("operation_started", "inspect", operation="drone.inspect")
        return
    if phase == "INSPECT":
        script.apply(
            "operation_completed",
            "inspect",
            operation="drone.inspect",
            outcome="captured",
            flight_state="grounded",
            frame_source="drone",
            frame_zone=incident.zone,
            frame_path=DRONE_PATH,
            frame_captured_at=CAPTURED_AT,
            frame_simulated=not drone_real,
        )
        return
    if phase == "RESOLVE":
        script.apply(
            "decision_received",
            "inspect",
            scope="resolution",
            action="confirmed",
            reason=SCENE_REASON,
        )
        return
    if phase == "REPORT":
        script.apply("report_saved", "report")
        return
    raise fault("rejected", "canonical script cannot advance this phase")
