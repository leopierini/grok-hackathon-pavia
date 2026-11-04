"""Route completion is not arrival."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g03.script import reach
from tests.ground.g03.support import open_session


def test_stopped_route_leaves_arrival_unconfirmed(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    reach(script, "WAIT_ARRIVAL")
    snap = store.snapshot()
    assert snap.decisions.get("route_completed") is True
    assert snap.decisions.get("route_stopped") is True
    assert snap.arrival_confirmed is None
    assert snap.arrival_monotonic is None
    assert snap.arrival_method is None
    assert snap.phase == "WAIT_ARRIVAL"


def test_arrival_timeout_keeps_a_null_metric(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    reach(script, "WAIT_ARRIVAL")
    script.apply("arrival_rejected", "arrive")
    snap = store.snapshot()
    assert snap.phase == "REPORT"
    assert snap.outcome == "unresolved"
    assert snap.arrival_confirmed is None
    assert snap.arrival_monotonic is None


def test_operator_arrival_records_monotonic_time(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    reach(script, "WAIT_ARRIVAL")
    script.apply(
        "arrival_confirmed",
        "arrive",
        zone="room_2",
        method="simulated",
        monotonic=12.5,
    )
    snap = store.snapshot()
    assert snap.arrival_confirmed is True
    assert snap.arrival_monotonic == 12.5
    assert snap.arrival_method == "simulated"
    assert snap.phase == "GROUND_VIEW"
    assert snap.incident is not None
    assert snap.incident.zone == "room_2"
