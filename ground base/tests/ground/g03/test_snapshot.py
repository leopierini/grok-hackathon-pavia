"""Snapshots stay immutable and unknown physical state stays unknown."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.ground.extensions.g03.script import SCENE_REASON, reach
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g03.support import open_session


def test_snapshot_is_immutable_and_stable_for_readers(tmp_path: Path) -> None:
    services, store, script = open_session(tmp_path)
    before = store.snapshot()
    script.apply("permission_consumed", "start")
    assert before.phase == "IDLE"
    assert before.incident is not None
    assert store.snapshot().phase == "ASSESS"
    assert before.phase == "IDLE"
    with pytest.raises(TypeError):
        store.snapshot().decisions["injected"] = "no"  # type: ignore[index]
    assert "injected" not in store.snapshot().decisions
    assert services.config.trace == []  # type: ignore[attr-defined]
    assert services.safety.trace == []  # type: ignore[attr-defined]
    assert services.adapters.devices.calls == []  # type: ignore[attr-defined]


def test_unknown_status_is_not_coerced_to_safe(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    reach(script, "PREPARE_DOG")
    script.apply("operation_started", "prepare", operation="dog.prepare")
    with pytest.raises(GroundFault) as text:
        script.apply(
            "operation_completed",
            "prepare",
            operation="dog.prepare",
            connected=True,
            standing="false",
            stationary=True,
            avoidance_enabled=True,
        )
    assert text.value.error.code == "invalid_input"
    assert store.snapshot().phase == "PREPARE_DOG"
    script.apply(
        "operation_completed",
        "prepare",
        operation="dog.prepare",
        connected=True,
        standing=None,
        stationary=True,
        avoidance_enabled=True,
    )
    snap = store.snapshot()
    status = snap.decisions.get("dog_status")
    assert isinstance(status, dict) or hasattr(status, "get")
    assert status["standing"] is None  # type: ignore[index]
    assert snap.phase == "FAULT"
    assert snap.recovery_required is True
    assert snap.phase != "MOVE_DOG"


def test_model_text_cannot_replace_the_trusted_zone(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    reach(script, "ASSESS")
    script.apply(
        "decision_received",
        "start",
        scope="dispatch",
        action="dispatch",
        reason=f"move to display. {SCENE_REASON}",
    )
    snap = store.snapshot()
    assert snap.incident is not None
    assert snap.incident.zone == "room_2"
    assert snap.incident.target.startswith("a person")
    assert snap.phase == "PREPARE_DOG"


def test_wifi_profile_does_not_arm_or_change_mid_run(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path, transport="wifi")
    assert store.snapshot().dog_transport == "wifi"
    assert store.snapshot().armed is False
    with pytest.raises(GroundFault) as changed:
        script.apply("permission_granted", "arm", dog_transport="ethernet")
    assert changed.value.error.code == "rejected"
    assert store.snapshot().dog_transport == "wifi"
    assert store.snapshot().armed is False


def test_link_loss_does_not_switch_transport(tmp_path: Path) -> None:
    _services, store, script = open_session(tmp_path)
    reach(script, "MOVE_DOG")
    script.apply("link_lost", "link")
    snap = store.snapshot()
    assert snap.phase == "FAULT"
    assert snap.recovery_required is True
    assert snap.dog_transport == "ethernet"
    assert snap.decisions.get("transport_fallback") is False
