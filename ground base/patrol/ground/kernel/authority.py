"""Epoch and cancellation authority. A latch blocks every later ordinary action."""

from __future__ import annotations

import math
import threading

from patrol.ground.kernel.contracts import Clock, Ticket
from patrol.ground.kernel.faults import fault


class SessionAuthority:
    def __init__(self) -> None:
        self._epoch = 0
        self._cancelled = False
        self._reason = ""
        self._cancel = threading.Event()

    @property
    def epoch(self) -> int:
        return self._epoch

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel

    def issue(self, mission_id: str, stage_id: str) -> Ticket:
        if not isinstance(mission_id, str) or not mission_id:
            raise fault("invalid_input", "mission id is required")
        if not isinstance(stage_id, str) or not stage_id:
            raise fault("invalid_input", "stage id is required")
        if self._cancelled:
            raise fault(
                "cancelled",
                self._reason or "cancellation is latched",
                recovery_required=True,
            )
        return Ticket(mission_id, self._epoch, stage_id)

    def require_current(self, ticket: Ticket) -> None:
        if not isinstance(ticket, Ticket):
            raise fault("invalid_input", "expected a Ticket")
        if self._cancelled:
            raise fault(
                "cancelled",
                self._reason or "cancellation is latched",
                recovery_required=True,
            )
        if ticket.epoch != self._epoch:
            raise fault("stale_ticket", "ticket epoch is not current", recovery_required=True)

    def require_action(
        self,
        ticket: Ticket,
        *,
        deadline_monotonic: float,
        clock: Clock,
    ) -> None:
        self.require_current(ticket)
        if isinstance(deadline_monotonic, bool) or not isinstance(deadline_monotonic, (int, float)):
            raise fault("invalid_input", "deadline must be a real number")
        if not math.isfinite(float(deadline_monotonic)):
            raise fault("invalid_input", "deadline must be finite")
        if clock.monotonic() >= float(deadline_monotonic):
            raise fault("expired_deadline", "stage deadline has passed", recovery_required=True)

    def latch_cancel(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise fault("invalid_input", "cancel reason is required")
        if self._cancelled:
            return
        self._cancelled = True
        self._reason = reason.strip()
        self._epoch += 1
        self._cancel.set()

    def reset_generation(self, reason: str) -> int:
        if not isinstance(reason, str) or not reason.strip():
            raise fault("invalid_input", "reset reason is required")
        self._epoch += 1
        self._cancelled = False
        self._reason = ""
        self._cancel = threading.Event()
        return self._epoch
