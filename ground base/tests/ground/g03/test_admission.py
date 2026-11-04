"""One admission, one start, and one terminal publication."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from patrol.ground.extensions.g03.script import reach
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.settings import make_settings
from tests.ground.g03.support import open_session


def test_second_open_and_start_are_rejected(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    incident = store.snapshot().incident
    assert incident is not None
    with pytest.raises(GroundFault) as opened:
        store.open(incident, make_settings())
    assert opened.value.error.code == "rejected"
    reach(script, "ASSESS")
    with pytest.raises(GroundFault) as started:
        script.apply("permission_consumed", "start")
    assert started.value.error.code == "rejected"
    assert store.mission_count == 1
    assert store.snapshot().phase == "ASSESS"


def test_same_turn_starts_admit_one_mission(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    first = script.event("permission_consumed", "start")
    second = script.event("permission_consumed", "start")
    barrier = threading.Barrier(2)
    results: list[str] = []

    def run(pair: tuple[object, object]) -> None:
        barrier.wait()
        try:
            store.apply(pair[0], expected_ticket=pair[1])  # type: ignore[arg-type]
            results.append("admitted")
        except GroundFault as exc:
            results.append(exc.error.code)

    threads = [threading.Thread(target=run, args=(pair,)) for pair in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["admitted", "rejected"]
    assert store.mission_count == 1
    assert store.snapshot().phase == "ASSESS"


def test_duplicate_completion_does_not_publish_twice(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    reach(script, "ASSESS")
    decision, ticket = script.event(
        "decision_received",
        "start",
        scope="dispatch",
        action="dismiss",
        reason="nothing matches the target",
    )
    first = store.apply(decision, expected_ticket=ticket)
    second = store.apply(decision, expected_ticket=ticket)
    assert first == second
    assert first.outcome == "ignored"
    reach(script, "DONE")
    with pytest.raises(GroundFault) as published:
        script.apply("report_saved", "report")
    assert published.value.error.code == "rejected"
    assert store.snapshot().decisions.get("publications") == 1
    assert store.mission_count == 1
