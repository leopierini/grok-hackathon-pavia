"""Small snapshot constructor used by test doubles."""

from __future__ import annotations

from collections.abc import Mapping

from patrol.contract import Incident
from patrol.ground.kernel.contracts import SessionSnapshot
from patrol.ground.kernel.validation import freeze_map, freeze_str_map


def idle_snapshot(
    *,
    epoch: int,
    modes: Mapping[str, str],
    dog_transport: str,
    incident: Incident | None = None,
    phase: str = "IDLE",
) -> SessionSnapshot:
    return SessionSnapshot(
        phase=phase,
        incident=incident,
        epoch=epoch,
        stage_id=None,
        modes=freeze_str_map(modes),
        dog_transport=dog_transport,
        armed=False,
        arrival_confirmed=None,
        arrival_monotonic=None,
        arrival_method=None,
        readiness_confirmed=None,
        confirmation_method=None,
        evidence=freeze_map({}),
        decisions=freeze_map({}),
        outcome=None,
        flight_lock=False,
        recovery_required=False,
        halt_latched=False,
        mission_id=None if incident is None else incident.mission_id,
    )
