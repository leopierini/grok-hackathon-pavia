"""Failure rehearsals stay distinct from a successful flight."""

from __future__ import annotations

import json

from patrol.ground.extensions.g32.implementation import command_exit
from patrol.ground.extensions.g32.rehearsal import (
    BLOCKED_TRACE,
    NOISY_TRACE,
    STALE_TRACE,
    UNCONTROLLED_TRACE,
    UNKNOWN_TRACE,
    fixture_root,
    load_case,
    play,
)
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.kernel.io import FaultyIO
from tests.ground.g32.conftest import assertion_ok, calls_of, report_at, run


def test_unknown_landing_keeps_goal_distinct(services: BaseServices) -> None:
    _feature, result = run(services, "unknown_landing")
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "validation_failed"
    assert result.error.recovery_required is True
    assert result.data["trace"] == UNKNOWN_TRACE
    assert command_exit(result) == 1
    saved = report_at(services, "unknown_landing")
    assert saved["goal_status"] == "reached"
    assert saved["landing_status"] == "unverified"
    assert assertion_ok(saved, "goal") is True
    assert assertion_ok(saved, "landing") is False
    assert saved["passed"] is False
    assert calls_of(services) == []


def test_blocked_noisy_stale_and_uncontrolled(services: BaseServices) -> None:
    _feature, blocked = run(services, "blocked_planner")
    assert blocked.status == "blocked"
    assert blocked.data["trace"] == BLOCKED_TRACE
    assert "dog_step" not in blocked.data["trace"]
    assert "invented_candidate" not in blocked.data["trace"]
    saved = report_at(services, "blocked_planner")
    assert assertion_ok(saved, "no_invented_candidate") is True

    _feature, noisy = run(services, "noisy_rssi")
    assert noisy.status == "blocked"
    assert noisy.data["trace"] == NOISY_TRACE
    assert "dog_step" not in noisy.data["trace"]

    _feature, stale = run(services, "stale_frame")
    assert stale.status == "failed"
    assert stale.data["detail"] == "stale_frame_dropped"
    assert stale.data["trace"] == STALE_TRACE
    assert "drone_step" not in stale.data["trace"]

    _feature, motion = run(services, "uncontrolled_motion")
    assert motion.status == "ok"
    assert motion.data["detail"] == "supervised_or_stopped"
    assert motion.data["trace"] == UNCONTROLLED_TRACE
    assert "random_search" not in motion.data["trace"]
    assert calls_of(services) == []


def test_real_mode_and_string_flag_stop_before_steps(services: BaseServices) -> None:
    _feature, real = run(services, "happy_path", simulation_mode="real")
    assert real.status == "failed"
    assert real.data["detail"] == "real_mode_rejected"
    assert real.data["trace"] == ()
    devices = getattr(services.adapters, "devices", None)
    output = getattr(devices, "output_dir", None)
    assert output is not None
    assert list(output.rglob("report.json")) == []

    _feature, flagged = run(services, "happy_path", simulated="true")
    assert flagged.status == "failed"
    assert flagged.data["detail"] == "simulated_flag_rejected"
    assert flagged.data["trace"] == ()
    assert calls_of(services) == []


def test_catalog_is_not_one_mission(services: BaseServices) -> None:
    catalog = fixture_root() / "catalog" / "example-events.jsonl"
    text = catalog.read_text(encoding="utf-8")
    assert "demo_goal_reached" in text
    assert "landing_unverified" in text
    assert "cmd-dog-stale-example" in text
    _feature, result = run(services, "catalog_mission")
    assert result.status == "failed"
    assert result.data["detail"] == "causal_order"
    assert command_exit(result) == 1
    saved = report_at(services, "catalog_mission")
    violations = saved["violations"]
    assert isinstance(violations, list)
    assert "window_before_epoch_advance" in violations
    assert "dog_moved_during_drone" in violations
    assert "ack_without_command" in violations
    played = play(load_case(FaultyIO(), "catalog_mission"))
    assert played.violations


def test_second_takeoff_and_epoch_and_zero_dbm(services: BaseServices) -> None:
    _feature, result = run(services, "second_takeoff")
    assert result.status == "failed"
    assert result.data["detail"] == "second_takeoff_rejected"
    assert "random_search" not in result.data["trace"]
    saved = report_at(services, "second_takeoff")
    assert assertion_ok(saved, "no_second_takeoff") is False

    messages = load_case(FaultyIO(), "happy_path")
    for message in messages:
        payload = message.get("payload")
        if message.get("kind") == "dog.command" and isinstance(payload, dict):
            payload["beacon_epoch"] = 3
    replayed = play(messages)
    assert "stale_beacon" in replayed.violations
    assert "dog_step" not in replayed.trace

    window = {
        "protocol_version": "2.0-draft",
        "message_id": "msg-zero",
        "mission_id": "demo-20261104-001",
        "epoch": 1,
        "kind": "rssi.window",
        "simulated": True,
        "payload": {"quality": "valid", "beacon_epoch": 4, "median_rssi_dbm": 0, "samples": []},
    }
    assert "zero_dbm_sentinel" in play([window]).violations
    meters = json.loads(json.dumps(window))
    meters["payload"]["rssi_m"] = 1.5
    assert "rssi_to_meters" in play([meters]).violations
