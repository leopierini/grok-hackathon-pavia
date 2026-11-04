"""Authoritative session store. Peers are retained and never called."""

from __future__ import annotations

import threading
from collections.abc import Mapping

from patrol.contract import Incident
from patrol.ground.extensions.g03.reduce import (
    ROTATE_KINDS,
    SAFETY_KINDS,
    fresh_idle,
    reduce_event,
)
from patrol.ground.kernel.catalog import ZONES
from patrol.ground.kernel.contracts import (
    GroundEvent,
    GroundSettings,
    KernelContext,
    ServicePorts,
    SessionSnapshot,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.snapshots import idle_snapshot

_BLANK_MODES = {"dog": "fake", "drone": "fake", "grok": "fake"}


class SessionStore:
    """One current mission, fenced by the kernel epoch and explicit event identity."""

    def __init__(self, kernel: KernelContext, peers: ServicePorts) -> None:
        self._kernel = kernel
        self._peers = peers
        self._lock = threading.Lock()
        self._snapshot = _blank(kernel.authority.epoch)
        self._admitted = False
        self._accepted: set[str] = set()
        self._rejected: set[str] = set()
        self._rejections: list[str] = []
        self._last_sequence = 0
        self._missions = 0

    def open(self, incident: Incident, settings: GroundSettings) -> SessionSnapshot:
        with self._lock:
            return self._open(incident, settings)

    def apply(self, event: GroundEvent, *, expected_ticket: Ticket) -> SessionSnapshot:
        with self._lock:
            return self._apply(event, expected_ticket)

    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def mission_count(self) -> int:
        return self._missions

    @property
    def rejections(self) -> tuple[str, ...]:
        return tuple(self._rejections)

    @property
    def peers(self) -> ServicePorts:
        """Injected ports. The reducer does not call them."""
        return self._peers

    def _open(self, incident: Incident, settings: GroundSettings) -> SessionSnapshot:
        if not isinstance(incident, Incident) or not isinstance(settings, GroundSettings):
            raise fault("invalid_input", "open requires an incident and settings")
        if not isinstance(incident.mission_id, str) or not incident.mission_id.strip():
            raise fault("invalid_input", "mission id is required")
        if incident.zone not in ZONES or incident.initial_frame.zone != incident.zone:
            raise fault("invalid_input", "incident zone is not trusted")
        if not isinstance(incident.target, str) or not incident.target.strip():
            raise fault("invalid_input", "target is required")
        if self._kernel.authority.cancelled:
            raise fault("cancelled", "cancellation is latched", recovery_required=True)
        if self._admitted:
            raise fault("rejected", "a mission is already admitted")
        if (
            self._snapshot.recovery_required
            or self._snapshot.flight_lock
            or self._snapshot.halt_latched
        ):
            raise fault("recovery_required", "recovery is still required", recovery_required=True)
        self._snapshot = idle_snapshot(
            epoch=self._kernel.authority.epoch,
            modes=settings.modes,
            dog_transport=settings.dog_transport,
            incident=incident,
            phase="IDLE",
        )
        self._admitted = True
        self._missions = 0
        self._clear_identity()
        return self._snapshot

    def _apply(self, event: GroundEvent, expected_ticket: Ticket) -> SessionSnapshot:
        if not isinstance(event, GroundEvent):
            raise fault("invalid_input", "expected a GroundEvent")
        if not isinstance(expected_ticket, Ticket):
            raise fault("invalid_input", "expected a Ticket")
        event_id = _event_id(event.payload)
        if event_id in self._accepted or event_id in self._rejected:
            return self._snapshot
        if event.ticket is not None and event.ticket != expected_ticket:
            self._reject(event_id, "stale_ticket", "event ticket does not match the stage")
            raise fault("stale_ticket", "event ticket does not match the stage")
        try:
            sequence = _sequence(event.payload)
            if sequence <= self._last_sequence:
                raise fault("rejected", "duplicate or reordered event sequence")
            if event.kind in {"recovery_cleared", "reset_requested"}:
                self._check_recovery_ticket(expected_ticket)
                reduce_event(self._snapshot, event, expected_ticket)
                restored = fresh_idle(self._snapshot, self._kernel.authority.epoch)
                self._commit(event_id, sequence, restored, reset=True)
                return restored
            if not self._admitted or self._snapshot.mission_id is None:
                raise fault("not_admitted", "no mission is admitted")
            if expected_ticket.mission_id != self._snapshot.mission_id:
                raise fault("stale_ticket", "event belongs to a different mission")
            if event.kind in SAFETY_KINDS:
                self._check_safety_ticket(expected_ticket)
            else:
                self._kernel.authority.require_current(expected_ticket)
                if expected_ticket.epoch != self._snapshot.epoch:
                    raise fault("epoch_mismatch", "ticket epoch is not the session epoch")
            if self._stage_mismatch(event, expected_ticket):
                raise fault("stale_ticket", "event stage is not current")
            updated = reduce_event(self._snapshot, event, expected_ticket)
        except GroundFault as exc:
            self._reject(event_id, exc.error.code, exc.error.detail)
            raise
        self._commit(event_id, sequence, updated, reset=False)
        if event.kind == "permission_consumed":
            self._missions += 1
        return updated

    def _check_recovery_ticket(self, ticket: Ticket) -> None:
        authority = self._kernel.authority
        if authority.cancelled:
            raise fault(
                "cancelled",
                "reset the kernel generation before recovery",
                recovery_required=True,
            )
        if ticket.epoch != authority.epoch:
            raise fault("epoch_mismatch", "recovery ticket is not current")
        if self._admitted and ticket.mission_id != self._snapshot.mission_id:
            raise fault("stale_ticket", "recovery ticket belongs to a different mission")
        if ticket.epoch == self._snapshot.epoch:
            raise fault("epoch_mismatch", "recovery requires a new kernel generation")

    def _check_safety_ticket(self, ticket: Ticket) -> None:
        if ticket.mission_id != self._snapshot.mission_id:
            raise fault("stale_ticket", "safety event belongs to a different mission")
        if ticket.epoch != self._snapshot.epoch:
            raise fault("epoch_mismatch", "safety event epoch is not current")

    def _stage_mismatch(self, event: GroundEvent, ticket: Ticket) -> bool:
        current = self._snapshot.stage_id
        if event.kind in ROTATE_KINDS or current is None:
            return False
        return ticket.stage_id != current

    def _commit(
        self,
        event_id: str,
        sequence: int,
        snapshot: SessionSnapshot,
        *,
        reset: bool,
    ) -> None:
        self._accepted.add(event_id)
        self._last_sequence = sequence
        self._snapshot = snapshot
        if reset:
            self._admitted = False
            self._missions = 0
            self._clear_identity()

    def _clear_identity(self) -> None:
        self._accepted.clear()
        self._rejected.clear()
        self._rejections.clear()
        self._last_sequence = 0

    def _reject(self, event_id: str, code: str, detail: str) -> None:
        self._rejected.add(event_id)
        self._rejections.append(f"{code}: {detail}")


def _blank(epoch: int) -> SessionSnapshot:
    return idle_snapshot(epoch=epoch, modes=_BLANK_MODES, dog_transport="ethernet")


def _event_id(payload: Mapping[str, object]) -> str:
    value = payload.get("event_id")
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", "event_id is required")
    return value.strip()


def _sequence(payload: Mapping[str, object]) -> int:
    value = payload.get("sequence")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise fault("invalid_input", "sequence must be a positive integer")
    return value
