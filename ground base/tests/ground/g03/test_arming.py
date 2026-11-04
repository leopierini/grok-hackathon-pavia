"""Arming, confirmation scope, and recovery-lock monotonicity."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.ground.extensions.g03.script import reach
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.settings import make_settings
from tests.ground.g03.support import open_session

REAL_DOG = {"dog": "real", "drone": "fake", "grok": "fake"}
REAL_DRONE = {"dog": "fake", "drone": "real", "grok": "fake"}


def test_real_motion_requires_one_use_arming(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path, modes=REAL_DOG)
    with pytest.raises(GroundFault) as unarmed:
        script.apply("permission_consumed", "start")
    assert unarmed.value.error.code == "rejected"
    assert store.snapshot().phase == "IDLE"
    assert store.mission_count == 0
    script.apply("permission_granted", "arm")
    assert store.snapshot().armed is True
    script.apply("permission_consumed", "start")
    assert store.snapshot().phase == "ASSESS"
    assert store.snapshot().armed is False
    assert store.mission_count == 1
    with pytest.raises(GroundFault):
        script.apply("permission_granted", "arm")
    assert store.mission_count == 1


def test_early_and_wrong_confirmations_are_not_buffered(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    reach(script, "ASSESS")
    early, early_ticket = script.event(
        "arrival_confirmed",
        "arrive",
        zone="room_2",
        method="simulated",
        monotonic=4.0,
    )
    with pytest.raises(GroundFault):
        store.apply(early, expected_ticket=early_ticket)
    reach(script, "WAIT_ARRIVAL")
    store.apply(early, expected_ticket=early_ticket)
    assert store.snapshot().arrival_confirmed is None
    with pytest.raises(GroundFault) as wrong:
        script.apply(
            "arrival_confirmed",
            "arrive",
            zone="display",
            method="simulated",
            monotonic=4.0,
        )
    assert wrong.value.error.code == "rejected"
    assert store.snapshot().arrival_confirmed is None
    script.apply(
        "arrival_confirmed",
        "arrive",
        zone="room_2",
        method="simulated",
        monotonic=12.5,
    )
    assert store.snapshot().arrival_confirmed is True
    assert store.snapshot().phase == "GROUND_VIEW"


def test_simulated_confirmation_cannot_clear_real_hardware(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path, modes=REAL_DOG)
    script.apply("permission_granted", "arm")
    reach(script, "WAIT_ARRIVAL")
    with pytest.raises(GroundFault) as simulated:
        script.apply(
            "arrival_confirmed",
            "arrive",
            zone="room_2",
            method="simulated",
            monotonic=12.5,
        )
    assert simulated.value.error.code == "rejected"
    assert store.snapshot().arrival_confirmed is None
    script.apply(
        "arrival_confirmed",
        "arrive",
        zone="room_2",
        method="operator",
        monotonic=12.5,
    )
    assert store.snapshot().arrival_method == "operator"


def test_flight_lock_survives_success_until_verified_recovery(tmp_path: Path) -> None:
    services, store, script = open_session(tmp_path)
    reach(script, "DONE")
    incident = store.snapshot().incident
    assert incident is not None
    assert store.snapshot().flight_lock is True
    assert store.snapshot().outcome == "alerted"
    with pytest.raises(GroundFault) as second:
        store.open(incident, make_settings())
    assert second.value.error.code == "rejected"
    services.kernel.authority.reset_generation("operator recovery")
    with pytest.raises(GroundFault) as unverified:
        script.apply("recovery_cleared", "reset", verified="true")
    assert unverified.value.error.code == "recovery_required"
    assert store.snapshot().flight_lock is True
    script.apply("recovery_cleared", "reset", verified=True)
    assert store.snapshot().flight_lock is False
    assert store.snapshot().recovery_required is False
    assert store.snapshot().incident is None
    assert store.snapshot().armed is False


def test_fake_pad_launch_is_rejected_for_a_real_drone(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path, modes=REAL_DRONE)
    script.apply("permission_granted", "arm")
    reach(script, "PREFLIGHT")
    script.apply("flight_ready_confirmed", "ready", method="operator")
    with pytest.raises(GroundFault) as pad:
        script.apply(
            "operation_started",
            "inspect",
            operation="drone.inspect",
            launch_origin="dog_pad",
        )
    assert pad.value.error.code == "unsafe_state"
    assert store.snapshot().phase == "PREFLIGHT"
