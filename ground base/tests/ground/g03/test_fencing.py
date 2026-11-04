"""Stale mission, epoch, and stage results cannot advance the session."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.contract import Frame, Incident
from patrol.ground.extensions.g03.script import reach
from patrol.ground.kernel.contracts import GroundEvent, Ticket
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.validation import freeze_map
from tests.ground.g03.support import open_session


def test_stale_mission_epoch_and_stage(tmp_path: Path) -> None:
    services, store, script = open_session(tmp_path)
    reach(script, "MOVE_DOG")
    script.apply("operation_started", "route", operation="dog.run_route")
    current = store.snapshot()
    assert current.mission_id is not None
    other = Incident(
        "other-mission",
        "room_2",
        "a person or an object left in a marked closed area",
        Frame("C:/evidence/phone.jpg", "phone", "room_2", None, True),
    )
    foreign = services.kernel.authority.issue(other.mission_id, "route")
    with pytest.raises(GroundFault) as stale_mission:
        store.apply(_event("operation_completed", foreign, sequence=90), expected_ticket=foreign)
    assert stale_mission.value.error.code == "stale_ticket"
    assert store.snapshot().phase == "MOVE_DOG"

    services.kernel.authority.latch_cancel("operator halt")
    aged = Ticket(current.mission_id, current.epoch, "route")
    with pytest.raises(GroundFault) as cancelled:
        store.apply(
            _event(
                "operation_completed",
                aged,
                sequence=91,
                operation="dog.run_route",
                completed=True,
                stopped=True,
            ),
            expected_ticket=aged,
        )
    assert cancelled.value.error.code == "cancelled"
    assert store.snapshot().phase == "MOVE_DOG"
    assert services.kernel.authority.cancelled is True


def test_stage_mismatch_rejects_a_completed_route(tmp_path: Path) -> None:
    services, store, script = open_session(tmp_path)
    reach(script, "MOVE_DOG")
    script.apply("operation_started", "route", operation="dog.run_route")
    wrong = services.kernel.authority.issue(store.snapshot().mission_id or "", "prepare")
    with pytest.raises(GroundFault) as mismatch:
        store.apply(
            _event(
                "operation_completed",
                wrong,
                sequence=80,
                operation="dog.run_route",
                completed=True,
                stopped=True,
            ),
            expected_ticket=wrong,
        )
    assert mismatch.value.error.code == "stale_ticket"
    assert store.snapshot().phase == "MOVE_DOG"
    assert store.snapshot().arrival_confirmed is None


def test_late_result_after_halt_cannot_advance(tmp_path: Path) -> None:
    services, store, script = open_session(tmp_path)
    reach(script, "MOVE_DOG")
    script.apply("operation_started", "route", operation="dog.run_route")
    mission_id = store.snapshot().mission_id or ""
    late_ticket = services.kernel.authority.issue(mission_id, "route")
    script.apply("halt_requested", "halt", physical_state="known", reason="operator halt")
    services.kernel.authority.latch_cancel("operator halt")
    late = script.bind(
        late_ticket,
        "operation_completed",
        operation="dog.run_route",
        completed=True,
        stopped=True,
    )
    with pytest.raises(GroundFault):
        store.apply(late, expected_ticket=late_ticket)
    snap = store.snapshot()
    assert snap.phase == "ABORTED"
    assert snap.outcome == "aborted"
    assert snap.arrival_confirmed is None
    assert snap.halt_latched is True


def _event(kind: str, ticket: Ticket, sequence: int, **payload: object) -> GroundEvent:
    body: dict[str, object] = {"event_id": f"{kind}-{sequence}", "sequence": sequence}
    body.update(payload)
    return GroundEvent(kind, ticket, freeze_map(body))
