"""Typed event construction. Payloads are frozen before they reach the reducer."""

from __future__ import annotations

from collections.abc import Mapping

from patrol.ground.kernel.contracts import GroundEvent, Ticket
from patrol.ground.kernel.validation import freeze_map


def make_event(
    kind: str,
    ticket: Ticket,
    payload: Mapping[str, object],
) -> GroundEvent:
    return GroundEvent(kind, ticket, freeze_map(dict(payload)))
