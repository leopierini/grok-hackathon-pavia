"""Dog transport stays independent of the vendor connection mode."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.paths import repo_root
from tests.ground.g02.support import FAKE, mapping, service, write_json, write_text

FIXTURE = repo_root() / "fixtures" / "ground" / "g02"


def test_fixture_ethernet_is_not_inferred_from_local_ap(tmp_path: Path) -> None:
    settings = service(tmp_path).load(FIXTURE / "site" / "ground.json", modes=FAKE, scenario=None)
    dog = mapping(settings.adapter_configs["dog"])
    capability = mapping(settings.adapter_configs["capability"])
    assert settings.dog_transport == "ethernet"
    assert settings.profile_identity == "dog.ethernet"
    assert dog["connection_mode"] == "LocalSTA"
    assert capability["wifi_configured"] is True
    assert capability["ethernet_configured"] is True
    assert capability["physical_acceptance"] == "not_accepted"
    assert capability["transport_explicit"] is True


def test_wifi_selection_does_not_change_modes_or_acceptance(tmp_path: Path) -> None:
    modes = dict(FAKE)
    write_text(tmp_path / "routes" / "room.json", "opaque\n")
    write_json(
        tmp_path / "dog.json",
        {
            "connection_mode": "LocalSTA",
            "interface": "ethernet0",
            "routes_path": "routes/room.json",
        },
    )
    write_json(
        tmp_path / "ground.json",
        {
            "dog_transport": "wifi",
            "dog_config_path": "dog.json",
            "zones": ["room_2"],
        },
    )
    settings = service(tmp_path).load(tmp_path / "ground.json", modes=modes, scenario=None)
    capability = mapping(settings.adapter_configs["capability"])
    assert settings.dog_transport == "wifi"
    assert settings.profile_identity == "dog.wifi"
    assert mapping(settings.adapter_configs["dog"])["connection_mode"] == "LocalSTA"
    assert settings.modes["dog"] == "fake"
    assert capability["physical_acceptance"] == "not_accepted"
    assert capability["wifi_configured"] is True
    assert modes["dog"] == "fake"


def test_vendor_mode_ethernet_is_not_a_transport(tmp_path: Path) -> None:
    write_json(tmp_path / "dog.json", {"connection_mode": "ethernet"})
    write_json(tmp_path / "ground.json", {"dog_config_path": "dog.json", "zones": ["room_2"]})
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=FAKE, scenario=None)
    assert "connection_mode" in caught.value.error.detail
    assert "ethernet" not in caught.value.error.detail


def test_dog_file_cannot_set_ground_transport(tmp_path: Path) -> None:
    write_json(tmp_path / "dog.json", {"connection_mode": "LocalAP", "dog_transport": "wifi"})
    write_json(
        tmp_path / "ground.json",
        {"dog_config_path": "dog.json", "dog_transport": "ethernet"},
    )
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=FAKE, scenario=None)
    assert "ground file" in caught.value.error.detail


def test_selected_profile_must_match_the_transport_map(tmp_path: Path) -> None:
    write_json(tmp_path / "wired.json", {"connection_mode": "LocalSTA"})
    write_json(tmp_path / "wireless.json", {"connection_mode": "LocalAP"})
    write_json(
        tmp_path / "ground.json",
        {
            "dog_transport": "ethernet",
            "dog_config_path": "wireless.json",
            "dog_profile_paths": {"ethernet": "wired.json", "wifi": "wireless.json"},
            "zones": ["room_2"],
        },
    )
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=FAKE, scenario=None)
    assert "does not match" in caught.value.error.detail


def test_real_pad_with_a_fake_dog_is_rejected(tmp_path: Path) -> None:
    write_text(tmp_path / "profiles" / "views.json", "opaque\n")
    write_json(
        tmp_path / "drone.json",
        {
            "interface": "wifi0",
            "profiles_path": "profiles/views.json",
            "battery_min_percent": 50,
            "max_flight_s": 30,
            "command_timeout_s": 2,
        },
    )
    write_json(
        tmp_path / "ground.json",
        {
            "zones": ["room_2"],
            "launch_tier": "stationary_pad",
            "arrival_timeout_s": 15,
            "flight_ready_timeout_s": 30,
            "incident_timeout_s": 180,
            "output_root": "out",
            "profile_by_zone": {"room_2": "room_2_view_v1"},
            "drone_config_path": "drone.json",
        },
    )
    modes = {"dog": "fake", "drone": "real", "grok": "fake"}
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=modes, scenario=None)
    assert caught.value.error.code == "invalid_input"
    assert "fake dog" in caught.value.error.detail


def test_floor_flight_can_name_a_fake_dog(tmp_path: Path) -> None:
    write_text(tmp_path / "profiles" / "views.json", "opaque\n")
    write_json(
        tmp_path / "drone.json",
        {
            "interface": "wifi0",
            "profiles_path": "profiles/views.json",
            "battery_min_percent": 50,
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
    assert settings.launch_tier == "floor"
    assert settings.modes["dog"] == "fake"
    assert settings.modes["drone"] == "real"


def test_non_wifi_tello_transport_is_rejected(tmp_path: Path) -> None:
    write_json(tmp_path / "drone.json", {"radio_transport": "ethernet", "sdk": "other-sdk"})
    write_json(tmp_path / "ground.json", {"drone_config_path": "drone.json", "zones": ["room_2"]})
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=FAKE, scenario=None)
    assert caught.value.error.code == "invalid_input"
