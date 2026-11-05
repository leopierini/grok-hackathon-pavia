from __future__ import annotations

import json
from pathlib import Path

import pytest
from patrol.ground.operator.artifacts import ArtifactError, resolve_jpeg
from patrol.ground.operator.config import (
    ConfigError,
    default_config,
    explain_unset,
    validate_config,
)
from patrol.ground.operator.snapshot import command_views, numeric_metrics, rssi_points


def test_default_thresholds_stay_null_and_flight_profile_stays_disabled() -> None:
    config = default_config()
    assert config["dog_range_max_m"] is None
    assert config["drone_horizontal_max_m"] is None
    assert config["flight_profile"]["enabled"] is False
    assert any(note["field"] == "dog_range_max_m" for note in explain_unset(config))


def test_invalid_lease_rear_camera_and_secret_are_rejected() -> None:
    config = default_config()
    config["command_lease_ms"] = 900
    with pytest.raises(ConfigError, match="500"):
        validate_config(config)
    config = default_config()
    config["cameras"] = {"drone": ["rear"], "dog": ["front"]}
    with pytest.raises(ConfigError, match="rear"):
        validate_config(config)
    config = default_config()
    config["vision"] = {
        "model_id": "CONFIGURE_VERIFIED_IMAGE_MODEL",
        "prompt_version": "patrol-demo-v2.0",
        "api_key": "super-secret-value",
    }
    with pytest.raises(ConfigError, match="secret field") as caught:
        validate_config(config)
    assert "super-secret-value" not in str(caught.value)


def test_real_mode_is_stored_and_not_rewritten_to_fake() -> None:
    config = default_config()
    config["modes"] = {"dog": "real", "drone": "fake", "grok": "fake"}
    accepted = validate_config(config)
    assert accepted["modes"]["dog"] == "real"


def test_artifact_escape_and_non_jpeg_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    (root / "frame.jpg").write_bytes(b"\xff\xd8\xff" + b"jpeg")
    assert resolve_jpeg("frame.jpg", (root,)).name == "frame.jpg"
    with pytest.raises(ArtifactError):
        resolve_jpeg("../frame.jpg", (root,))
    with pytest.raises(ArtifactError):
        resolve_jpeg(str(root / "frame.jpg"), (root,))
    (root / "notes.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(ArtifactError, match="JPEG"):
        resolve_jpeg("notes.txt", (root,))


def test_accepted_ack_is_not_completion_and_rssi_null_is_not_zero() -> None:
    command = {
        "message_id": "cmd-msg",
        "destination": "drone",
        "expires_at": "2026-11-04T13:00:11Z",
        "simulated": True,
        "payload": {"command_id": "cmd-1", "action": "track_step", "lease_ms": 300},
    }
    ack = {
        "kind": "command.ack",
        "sent_at": "2026-11-04T13:00:11Z",
        "message_id": "ack-1",
        "payload": {"command_id": "cmd-1", "state": "accepted", "verified": False, "observed_motion": None},
    }
    view = command_views([command], [ack])[0]
    assert view["lifecycle"] == "accepted"
    assert "not complete" in view["execution_note"]
    points = rssi_points(
        [
            {
                "kind": "rssi.window",
                "message_id": "w1",
                "payload": {"quality": "valid", "samples": [{"rssi_dbm": -60}, {"rssi_dbm": None}]},
            }
        ]
    )
    assert points == [{"at": None, "rssi_dbm": -60.0, "message_id": "w1", "quality": "valid"}]
    assert numeric_metrics({"goal_to_verified_landing_s": {"seconds": None, "reason": "unknown"}}) == []


def test_fixture_jpeg_resolves_inside_the_store() -> None:
    from patrol.ground.kernel.paths import repo_root

    path = resolve_jpeg(
        "artifact://demo-20261104-001/drone/downward-001.jpg",
        (repo_root() / "fixtures" / "ground" / "g14" / "store",),
    )
    assert path.name == "downward-001.jpg"
    assert json.loads('{"ok": true}')["ok"] is True
