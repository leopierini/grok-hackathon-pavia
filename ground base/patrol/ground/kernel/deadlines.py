"""Stage deadlines. Real adapters always use time.monotonic, never a manual clock."""

from __future__ import annotations

import math
import time
from threading import Event

from patrol.contract import RunContext
from patrol.ground.kernel.contracts import Clock
from patrol.ground.kernel.faults import fault


def context_for_stage(
    mission_id: str,
    mission_deadline: float,
    stage_limit_s: float,
    cancellation: Event,
    clock: Clock,
    *,
    real_adapter: bool,
) -> RunContext:
    if not isinstance(mission_id, str) or not mission_id:
        raise fault("invalid_input", "mission id is required")
    if not isinstance(cancellation, Event):
        raise fault("invalid_input", "cancellation token must be a threading.Event")
    if real_adapter and clock.is_manual():
        raise fault(
            "invalid_input",
            "a manual clock cannot create deadlines for a real adapter",
        )
    limit = _finite(stage_limit_s, "stage limit")
    if limit <= 0:
        raise fault("invalid_input", "stage limit must be positive")
    mission = _finite(mission_deadline, "mission deadline")
    now = time.monotonic() if real_adapter else clock.monotonic()
    return RunContext(
        mission_id=mission_id,
        deadline_monotonic=min(mission, now + limit),
        cancel=cancellation,
    )


def _finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", f"{label} must be a real number")
    number = float(value)
    if not math.isfinite(number):
        raise fault("invalid_input", f"{label} must be finite")
    return number
