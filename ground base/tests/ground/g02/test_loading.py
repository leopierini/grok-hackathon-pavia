"""Valid nested configuration and output-root resolution."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patrol.ground.extensions.g02.loading import canonical_settings
from patrol.ground.kernel.paths import repo_root
from tests.ground.g02.support import FAKE, mapping, service

FIXTURE = repo_root() / "fixtures" / "ground" / "g02"


def test_nested_paths_ignore_the_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    port = service(tmp_path)
    settings = port.load(FIXTURE / "site" / "ground.json", modes=dict(FAKE), scenario=None)
    dog = mapping(settings.adapter_configs["dog"])
    drone = mapping(settings.adapter_configs["drone"])
    route = FIXTURE / "routes" / "room_2.json"
    profile = FIXTURE / "profiles" / "views.json"
    assert settings.output_root == str((FIXTURE / "artifacts").resolve())
    assert Path(settings.output_root).is_absolute()
    assert dog["routes_path"] == str(route.resolve())
    assert drone["profiles_path"] == str(profile.resolve())
    assert route.read_text(encoding="utf-8") == "opaque-segment\n"
    assert dog["markers"] == ("calibrated", "opaque")
    assert Path.cwd() == tmp_path
    assert os.getcwd() == str(tmp_path)


def test_settings_and_caller_modes_are_immutable(tmp_path: Path) -> None:
    modes = dict(FAKE)
    port = service(tmp_path)
    settings = port.load(FIXTURE / "site" / "ground.json", modes=modes, scenario=None)
    modes["dog"] = "real"
    assert settings.modes["dog"] == "fake"
    dog = mapping(settings.adapter_configs["dog"])
    with pytest.raises(TypeError):
        dog["interface"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        settings.modes["drone"] = "real"  # type: ignore[index]
    with pytest.raises(TypeError):
        settings.adapter_configs["dog"] = {}  # type: ignore[index]


def test_shuffled_keys_normalize_to_the_same_settings(tmp_path: Path) -> None:
    from tests.ground.g02.support import write_text

    route = tmp_path / "routes" / "room.json"
    write_text(route, "opaque\n")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    dog_a = tmp_path / "dog-a.json"
    dog_b = tmp_path / "dog-b.json"
    write_text(
        dog_a,
        '{"interface": "ethernet0", "connection_mode": "LocalSTA", '
        '"routes_path": "routes/room.json"}',
    )
    write_text(
        dog_b,
        '{"routes_path": "routes/room.json", "connection_mode": "LocalSTA", '
        '"interface": "ethernet0"}',
    )
    write_text(
        first,
        '{"zones": ["room_2"], "dog_config_path": "dog-a.json", "scenario": "dismiss"}',
    )
    write_text(
        second,
        '{"scenario": "dismiss", "dog_config_path": "dog-b.json", "zones": ["room_2"]}',
    )
    port = service(tmp_path)
    left = port.load(first, modes=FAKE, scenario=None)
    right = port.load(second, modes=FAKE, scenario=None)
    assert canonical_settings(left) == canonical_settings(right)
    assert left.scenario == "dismiss"


def test_absolute_adapter_path_is_not_prefixed(tmp_path: Path) -> None:
    from tests.ground.g02.support import write_json, write_text

    route = tmp_path / "routes" / "room.json"
    write_text(route, "opaque\n")
    dog = tmp_path / "nested" / "dog.json"
    write_json(
        dog,
        {
            "connection_mode": "LocalSTA",
            "interface": "ethernet0",
            "routes_path": str(route),
        },
    )
    ground = tmp_path / "ground.json"
    write_json(ground, {"dog_config_path": str(dog), "zones": ["room_2"]})
    settings = service(tmp_path).load(ground, modes=FAKE, scenario=None)
    assert mapping(settings.adapter_configs["dog"])["routes_path"] == str(route.resolve())
