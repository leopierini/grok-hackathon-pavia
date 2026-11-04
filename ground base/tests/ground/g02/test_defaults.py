"""Fake defaults and explicit scenario override."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.ground.kernel.paths import repo_root
from tests.ground.g02.support import FAKE, mapping, service, write_json


def test_missing_file_uses_fake_defaults_without_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "environment-secret-value")
    monkeypatch.setenv("PATROL_SCENARIO", "dismiss")
    monkeypatch.chdir(tmp_path)
    settings = service(tmp_path).load(None, modes=dict(FAKE), scenario=None)
    assert settings.scenario == "blocked_resolved"
    assert settings.dog_transport == "ethernet"
    assert settings.launch_tier == "floor"
    assert settings.modes["dog"] == "fake"
    assert settings.arrival_timeout_s == 15.0
    assert settings.incident_timeout_s == 180.0
    assert settings.output_root == str((repo_root() / "artifacts").resolve())
    assert "environment-secret-value" not in settings.output_root
    assert mapping(settings.adapter_configs["drone"])["scenario"] == "blocked_resolved"
    capability = mapping(settings.adapter_configs["capability"])
    assert capability["flight_capability"] == "disabled"
    assert capability["physical_acceptance"] == "not_accepted"
    assert capability["transport_explicit"] is False


def test_empty_object_anchors_output_to_its_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    path = tmp_path / "site" / "ground.json"
    write_json(path, {})
    settings = service(tmp_path).load(path, modes=FAKE, scenario=None)
    assert settings.output_root == str((path.parent / "artifacts").resolve())
    assert settings.scenario == "blocked_resolved"


def test_caller_scenario_overrides_the_file(tmp_path: Path) -> None:
    write_json(tmp_path / "dog.json", {"scenario": "dismiss"})
    write_json(
        tmp_path / "ground.json",
        {"scenario": "ground_clear", "dog_config_path": "dog.json"},
    )
    settings = service(tmp_path).load(
        tmp_path / "ground.json",
        modes=FAKE,
        scenario="blocked_resolved",
    )
    assert settings.scenario == "blocked_resolved"
    assert mapping(settings.adapter_configs["dog"])["scenario"] == "blocked_resolved"
    assert mapping(settings.adapter_configs["grok"])["scenario"] == "blocked_resolved"


def test_real_mode_cannot_start_from_an_empty_default(tmp_path: Path) -> None:
    from patrol.ground.kernel.faults import GroundFault

    modes = {"dog": "real", "drone": "fake", "grok": "fake"}
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(None, modes=modes, scenario=None)
    assert "configuration file" in caught.value.error.detail


def test_null_battery_keeps_real_drone_and_disables_flight(tmp_path: Path) -> None:
    from tests.ground.g02.support import write_text

    write_text(tmp_path / "profiles" / "views.json", "opaque\n")
    write_json(
        tmp_path / "drone.json",
        {
            "interface": "wifi0",
            "profiles_path": "profiles/views.json",
            "battery_min_percent": None,
            "max_flight_s": 30,
            "command_timeout_s": 2,
        },
    )
    write_json(
        tmp_path / "ground.json",
        {
            "zones": ["room_2"],
            "launch_tier": "floor",
            "arrival_timeout_s": 15,
            "flight_ready_timeout_s": 30,
            "incident_timeout_s": 180,
            "output_root": "out",
            "profile_by_zone": {"room_2": "room_2_view_v1"},
            "drone_config_path": "drone.json",
        },
    )
    modes = {"dog": "fake", "drone": "real", "grok": "fake"}
    settings = service(tmp_path).load(tmp_path / "ground.json", modes=modes, scenario=None)
    capability = mapping(settings.adapter_configs["capability"])
    assert settings.modes["drone"] == "real"
    assert capability["flight_capability"] == "disabled"
    assert capability["flight_disabled_reason"] == "reserve_unset"
    assert "battery_min_percent" not in mapping(settings.adapter_configs["drone"])


def test_present_reserve_is_not_arming(tmp_path: Path) -> None:
    from tests.ground.g02.support import write_text

    write_text(tmp_path / "profiles" / "views.json", "opaque\n")
    write_json(
        tmp_path / "drone.json",
        {
            "interface": "wifi0",
            "profiles_path": "profiles/views.json",
            "battery_min_percent": 40,
            "max_flight_s": 30,
            "command_timeout_s": 2,
        },
    )
    write_json(
        tmp_path / "ground.json",
        {
            "zones": ["room_2"],
            "launch_tier": "floor",
            "arrival_timeout_s": 15,
            "flight_ready_timeout_s": 30,
            "incident_timeout_s": 180,
            "output_root": "out",
            "profile_by_zone": {"room_2": "room_2_view_v1"},
            "drone_config_path": "drone.json",
        },
    )
    modes = {"dog": "real", "drone": "real", "grok": "fake"}
    write_text(tmp_path / "routes" / "room.json", "opaque\n")
    write_json(
        tmp_path / "dog.json",
        {
            "connection_mode": "LocalSTA",
            "interface": "ethernet0",
            "routes_path": "routes/room.json",
            "max_route_s": 30,
            "command_timeout_s": 2,
        },
    )
    ground = {
        "zones": ["room_2"],
        "launch_tier": "floor",
        "arrival_timeout_s": 15,
        "flight_ready_timeout_s": 30,
        "incident_timeout_s": 180,
        "output_root": "out",
        "profile_by_zone": {"room_2": "room_2_view_v1"},
        "drone_config_path": "drone.json",
        "dog_config_path": "dog.json",
    }
    write_json(tmp_path / "ground.json", ground)
    settings = service(tmp_path).load(tmp_path / "ground.json", modes=modes, scenario=None)
    capability = mapping(settings.adapter_configs["capability"])
    drone = mapping(settings.adapter_configs["drone"])
    assert capability["flight_capability"] == "reserve_configured"
    assert capability["physical_acceptance"] == "not_accepted"
    assert drone["sdk"] == "DJITelloPy"
    assert drone["radio_transport"] == "wifi"
    assert settings.modes == modes
