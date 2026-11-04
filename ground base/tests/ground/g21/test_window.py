"""Happy-path Pi window."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g21.implementation import PROBE_NAMES, SCHEMA, SLOT
from patrol.ground.extensions.g21.scenarios import cases
from patrol.ground.kernel.contracts import BaseServices, FeaturePort
from patrol.ground.kernel.paths import repo_root
from tests.ground.g21.support import assert_quiet, payload, run, window_body


def test_manifest_names_the_v2_slot() -> None:
    path = repo_root() / "patrol" / "ground" / "extensions" / "g21" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == SCHEMA == "ground-task-v2"
    assert manifest["slot"] == SLOT == "feature.v2_rssi"
    assert manifest["task_id"] == "GROUND-21"
    assert {case.case_id for case in cases(0)} == set(PROBE_NAMES)


def test_example_window_is_comparable(opened: tuple[BaseServices, FeaturePort]) -> None:
    services, feature = opened
    result = run(feature, payload())
    assert result.status == "ok"
    assert result.error is None
    assert result.data["comparable"] is True
    assert result.data["follow"] is True
    assert result.data["quality"] == "valid"
    assert result.data["epoch"] == 3
    assert result.data["beacon_epoch"] == 3
    assert result.data["map_epoch"] == 1
    assert result.data["mission_epoch"] == 1
    assert result.data["median_rssi_dbm"] == -60
    assert type(result.data["median_rssi_dbm"]) is int
    assert result.data["spread_db"] == 4
    assert result.data["interface"] == "wlan-measurement"
    assert result.data["clock_error_ms"] == 15
    assert result.data["bssid"] == "02:00:00:00:00:01"
    assert result.data["sample_ids"] == ("rssi-0", "rssi-1", "rssi-2")
    samples = result.data["samples"]
    assert isinstance(samples, tuple)
    assert samples[0]["rssi_dbm"] == -62
    pose = samples[0]["pose"]
    assert isinstance(pose, Mapping)
    assert pose["yaw_rad"] == 0.0
    assert pose["map_epoch"] == 1
    event = result.events[0].payload
    assert event["message_id"] == "msg-pi-rssi-window"
    assert event["mission_id"] == "demo-20261104-001"
    assert event["epoch"] == 3
    assert event["beacon_epoch"] == 3
    assert event["map_epoch"] == 1
    assert event["median_rssi_dbm"] == -60
    assert_quiet(services, result)
    again = run(feature, payload())
    assert again.data["median_rssi_dbm"] == result.data["median_rssi_dbm"]
    assert again.status == "ok"


def test_measured_zero_is_not_rewritten(opened: tuple[BaseServices, FeaturePort]) -> None:
    services, feature = opened
    body = payload()
    inner = window_body(body)
    pose = {
        "frame_id": "museum/map",
        "map_id": "museum-map-demo",
        "map_epoch": 1,
        "x_m": 0.0,
        "y_m": 0,
        "z_m": 0,
        "yaw_rad": 0.0,
        "observed_at": "2026-11-04T13:00:09.600Z",
        "valid": True,
    }
    inner["samples"] = [
        {
            "sample_id": "rssi-0",
            "captured_at": "2026-11-04T13:00:09.600Z",
            "rssi_dbm": 0,
            "pose": pose,
        }
    ]
    inner["median_rssi_dbm"] = 0
    inner["spread_db"] = 0
    result = run(feature, body)
    assert result.status == "ok"
    assert result.data["median_rssi_dbm"] == 0
    assert result.data["quality"] == "valid"
    assert_quiet(services, result)


def test_fixture_files_are_present() -> None:
    root = Path(repo_root() / "fixtures" / "ground" / "g21")
    for name in (
        "pi-rssi-window.json",
        "pi-heartbeat.json",
        "no-signal-window.json",
        "beacon-hold.json",
        "navigation.json",
        "limits.json",
    ):
        assert (root / name).is_file()
