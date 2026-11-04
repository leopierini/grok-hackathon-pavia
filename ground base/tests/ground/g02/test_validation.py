"""Enum, type, and range rejection."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g02.support import FAKE, service, write_json, write_text

_GROUND = {
    "zones": ["room_2"],
    "profile_by_zone": {"room_2": "room_2_view_v1"},
    "launch_tier": "floor",
    "arrival_timeout_s": 15,
    "flight_ready_timeout_s": 30,
    "incident_timeout_s": 180,
    "output_root": "out",
}


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"zones": "room_2"}, "zones must be a list"),
        ({"zones": []}, "at least one zone"),
        ({"zones": ["lobby"]}, "frozen zone names"),
        ({"zones": ["room_2", "room_2"]}, "duplicate"),
        ({"zones": ["room_2"], "launch_tier": "roof"}, "launch_tier"),
        ({"zones": ["room_2"], "dog_transport": "LocalSTA"}, "dog_transport"),
        ({"zones": ["room_2"], "dog_transport": True}, "dog_transport"),
        ({"zones": ["room_2"], "scenario": "unknown_case"}, "unknown scenario"),
        ({"zones": ["room_2"], "arrival_timeout_s": True}, "wrong JSON type"),
        ({"zones": ["room_2"], "arrival_timeout_s": "15"}, "wrong JSON type"),
        ({"zones": ["room_2"], "arrival_timeout_s": 0}, "positive finite"),
        ({"zones": ["room_2"], "arrival_timeout_s": -5}, "positive finite"),
        ({"zones": ["room_2"], "profile_by_zone": {"lobby": "view"}}, "unknown zone"),
        ({"zones": ["entrance"], "profile_by_zone": {"room_2": "view"}}, "not configured"),
        ({"zones": ["room_2"], "vendor_ip": "secret-value"}, "unknown ground setting"),
        ({"zones": ["entrance"]}, "profile_by_zone is required"),
    ],
)
def test_ground_values_are_rejected(
    tmp_path: Path,
    payload: dict[str, object],
    detail: str,
) -> None:
    path = tmp_path / "ground.json"
    write_json(path, payload)
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(path, modes=FAKE, scenario=None)
    assert caught.value.error.code == "invalid_input"
    assert detail in caught.value.error.detail
    assert "secret-value" not in caught.value.error.detail


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        ("{", "malformed JSON"),
        ('{"zones": ["room_2"], "zones": ["display"]}', "duplicate key"),
        ('{"zones": ["room_2"], "arrival_timeout_s": Infinity}', "nonfinite"),
        ('{"zones": ["room_2"], "arrival_timeout_s": NaN}', "nonfinite"),
        ("[]", "JSON object"),
    ],
)
def test_malformed_documents_are_rejected(tmp_path: Path, text: str, detail: str) -> None:
    path = tmp_path / "ground.json"
    write_text(path, text)
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(path, modes=FAKE, scenario=None)
    assert caught.value.error.code == "invalid_input"
    assert detail in caught.value.error.detail


def test_nonfinite_overflow_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "ground.json"
    write_text(path, '{"zones": ["room_2"], "flight_ready_timeout_s": 1e309}')
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(path, modes=FAKE, scenario=None)
    assert caught.value.error.code == "invalid_input"
    assert "finite" in caught.value.error.detail


@pytest.mark.parametrize(
    ("battery", "detail"),
    [
        (True, "wrong JSON type"),
        (0, "from 1 to 100"),
        (101, "from 1 to 100"),
        (20.5, "whole number"),
        ("40", "wrong JSON type"),
    ],
)
def test_battery_range_is_rejected(tmp_path: Path, battery: object, detail: str) -> None:
    write_text(tmp_path / "profiles" / "views.json", "opaque\n")
    write_json(
        tmp_path / "drone.json",
        {
            "interface": "wifi0",
            "profiles_path": "profiles/views.json",
            "battery_min_percent": battery,
            "max_flight_s": 30,
            "command_timeout_s": 2,
        },
    )
    write_json(tmp_path / "ground.json", {**_GROUND, "drone_config_path": "drone.json"})
    modes = {"dog": "fake", "drone": "real", "grok": "fake"}
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=modes, scenario=None)
    assert detail in caught.value.error.detail


@pytest.mark.parametrize(
    ("modes", "detail"),
    [
        ({"dog": "fake", "drone": "fake"}, "dog, drone, and grok"),
        ({"dog": "yes", "drone": "fake", "grok": "fake"}, "dog mode"),
        ({"dog": True, "drone": "fake", "grok": "fake"}, "dog mode"),
        (
            {"dog": "real", "drone": "fake", "grok": "fake", "camera": "fake"},
            "dog, drone, and grok",
        ),
    ],
)
def test_mode_selection_is_explicit(tmp_path: Path, modes: dict[str, object], detail: str) -> None:
    write_json(tmp_path / "ground.json", {"zones": ["room_2"]})
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=modes, scenario=None)  # type: ignore[arg-type]
    assert detail in caught.value.error.detail


def test_real_adapter_requires_its_file_and_fields(tmp_path: Path) -> None:
    write_json(tmp_path / "ground.json", _GROUND)
    modes = {"dog": "real", "drone": "fake", "grok": "fake"}
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=modes, scenario=None)
    assert "dog_config_path" in caught.value.error.detail


def test_real_config_cannot_omit_operator_timeouts(tmp_path: Path) -> None:
    write_json(tmp_path / "ground.json", {"zones": ["room_2"], "launch_tier": "floor"})
    modes = {"dog": "fake", "drone": "fake", "grok": "real"}
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=modes, scenario=None)
    assert "arrival_timeout_s" in caught.value.error.detail


def test_utf8_and_size_limits(tmp_path: Path) -> None:
    binary = tmp_path / "ground.json"
    binary.write_bytes(b"\xff\xfe")
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(binary, modes=FAKE, scenario=None)
    assert "utf-8" in caught.value.error.detail
    huge = tmp_path / "huge.json"
    huge.write_text("{" + (" " * 300_000) + "}", encoding="utf-8")
    with pytest.raises(GroundFault) as sized:
        service(tmp_path).load(huge, modes=FAKE, scenario=None)
    assert sized.value.error.code == "validation_failed"


def test_missing_route_file_fails_before_motion(tmp_path: Path) -> None:
    write_json(
        tmp_path / "dog.json",
        {"connection_mode": "LocalSTA", "routes_path": "missing.json"},
    )
    write_json(tmp_path / "ground.json", {"dog_config_path": "dog.json", "zones": ["room_2"]})
    calls: list[str] = []
    port = service(tmp_path)
    devices = getattr(port.peers.adapters, "devices", None)
    with pytest.raises(GroundFault) as caught:
        port.load(tmp_path / "ground.json", modes=FAKE, scenario=None)
    assert caught.value.error.code == "io_fault"
    assert getattr(devices, "calls", calls) == []


def test_conflicting_fake_scenarios_are_rejected(tmp_path: Path) -> None:
    write_json(tmp_path / "dog.json", {"scenario": "dismiss"})
    write_json(tmp_path / "drone.json", {"scenario": "ground_clear"})
    write_json(
        tmp_path / "ground.json",
        {"dog_config_path": "dog.json", "drone_config_path": "drone.json", "zones": ["room_2"]},
    )
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load(tmp_path / "ground.json", modes=FAKE, scenario=None)
    assert "different scenarios" in caught.value.error.detail


def test_empty_string_path_is_not_the_fake_default(tmp_path: Path) -> None:
    with pytest.raises(GroundFault) as caught:
        service(tmp_path).load("", modes=FAKE, scenario=None)
    assert caught.value.error.code == "invalid_input"
