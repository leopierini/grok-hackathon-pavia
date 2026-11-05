"""Allowed phase transitions and representative forbidden jumps."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.extensions.g03.reduce import LEGAL_EDGES
from patrol.ground.extensions.g03.script import phase_trace, reach
from patrol.ground.kernel.paths import repo_root
from tests.ground.g03.support import open_session


def _walk(tmp_path: Path, phase: str) -> tuple[object, object, object]:
    services, store, script = open_session(tmp_path)
    reach(script, phase)
    return services, store, script


def _edges(tmp_path: Path) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    _services, store, script = open_session(tmp_path / "canonical")
    seen = phase_trace(script, "DONE")
    for before, after in zip(seen, seen[1:], strict=False):
        found.add((before, after))
    assert store.snapshot().phase == "DONE"
    return found


def test_canonical_phases_match_fixture(tmp_path: Path) -> None:
    _services, _store, script = open_session(tmp_path)
    fixture_path = repo_root() / "fixtures" / "ground" / "g03" / "happy_path.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert list(phase_trace(script, "DONE")) == fixture["phases"]


def test_every_legal_edge_is_reachable(tmp_path: Path) -> None:
    found = _edges(tmp_path / "canon")
    branches = {
        "dismiss": (
            "ASSESS",
            "decision_received",
            {"scope": "dispatch", "action": "dismiss", "reason": "empty"},
        ),
        "prepare_failed": (
            "PREPARE_DOG",
            "operation_completed",
            {
                "operation": "dog.prepare",
                "connected": True,
                "standing": False,
                "stationary": True,
                "avoidance_enabled": True,
            },
        ),
        "prepare_unknown": (
            "PREPARE_DOG",
            "operation_completed",
            {
                "operation": "dog.prepare",
                "connected": True,
                "standing": None,
                "stationary": True,
                "avoidance_enabled": True,
            },
        ),
        "route_blocked": (
            "MOVE_DOG",
            "operation_completed",
            {"operation": "dog.run_route", "completed": False, "stopped": True},
        ),
        "route_unstopped": (
            "MOVE_DOG",
            "operation_completed",
            {"operation": "dog.run_route", "completed": False, "stopped": False},
        ),
        "arrival_timeout": ("WAIT_ARRIVAL", "arrival_rejected", {}),
        "sufficient": (
            "GROUND_VIEW",
            "decision_received",
            {"scope": "ground", "action": "sufficient", "reason": "visible"},
        ),
        "ground_review": (
            "GROUND_VIEW",
            "decision_received",
            {"scope": "ground", "action": "review", "reason": "unclear"},
        ),
        "ready_timeout": ("PREFLIGHT", "flight_ready_rejected", {}),
        "status_unknown": (
            "PREFLIGHT",
            "operation_completed",
            {
                "operation": "dog.get_status",
                "connected": True,
                "standing": None,
                "stationary": True,
                "avoidance_enabled": True,
            },
        ),
        "unavailable": (
            "INSPECT",
            "operation_completed",
            {"operation": "drone.inspect", "outcome": "unavailable", "flight_state": "grounded"},
        ),
    }
    for name, (phase, kind, payload) in branches.items():
        _services, store, script = _walk(tmp_path / name, phase)
        stage = store.snapshot().stage_id or "stage"
        if phase == "PREPARE_DOG":
            script.apply("operation_started", "prepare", operation="dog.prepare")
            stage = "prepare"
        if phase == "MOVE_DOG" and kind == "operation_completed":
            script.apply("operation_started", "route", operation="dog.run_route")
            stage = "route"
        if phase == "GROUND_VIEW" and kind == "decision_received":
            _capture(script)
            stage = "capture"
        before = store.snapshot().phase
        script.apply(kind, stage, **payload)
        found.add((before, store.snapshot().phase))

    for phase in (
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
    ):
        _services, store, script = _walk(tmp_path / f"halt-{phase}", phase)
        before = store.snapshot().phase
        script.apply("halt_requested", "halt", physical_state="known", reason="operator halt")
        found.add((before, store.snapshot().phase))

    for phase in (
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
    ):
        _services, store, script = _walk(tmp_path / f"link-{phase}", phase)
        before = store.snapshot().phase
        script.apply("link_lost", "link")
        found.add((before, store.snapshot().phase))

    _services, store, script = _walk(tmp_path / "aborted", "MOVE_DOG")
    script.apply("halt_requested", "halt", physical_state="known", reason="operator halt")
    before = store.snapshot().phase
    script.apply("link_lost", "link")
    found.add((before, store.snapshot().phase))
    assert found == LEGAL_EDGES


def test_forbidden_phase_jump_does_not_apply(tmp_path: Path) -> None:
    from patrol.ground.kernel.faults import GroundFault

    _services, store, script = _walk(tmp_path, "ASSESS")
    try:
        script.apply("state_changed", "start", phase="DONE")
    except GroundFault as exc:
        assert exc.error.code == "rejected"
    else:
        raise AssertionError("phase jump was accepted")
    assert store.snapshot().phase == "ASSESS"
    assert store.snapshot().outcome is None


def _capture(script: object) -> None:
    from patrol.ground.extensions.g03.script import CAPTURED_AT, DOG_PATH, Script

    if not isinstance(script, Script):
        raise AssertionError("expected a script")
    incident = script.store.snapshot().incident
    if incident is None:
        raise AssertionError("missing incident")
    script.apply("operation_started", "capture", operation="dog.capture_frame")
    script.apply(
        "frame_validated",
        "capture",
        source="dog",
        zone=incident.zone,
        path=DOG_PATH,
        captured_at=CAPTURED_AT,
        simulated=True,
    )
