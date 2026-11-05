"""Loading configuration does not import device or network stacks."""

from __future__ import annotations

import sys
from pathlib import Path

from patrol.ground.extensions.g02.implementation import create
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services
from tests.ground.g02.support import FAKE, service

_BANNED = (
    "djitellopy",
    "unitree_webrtc_connect",
    "go2_webrtc_connect",
    "xai_sdk",
    "xai",
    "requests",
    "socket",
)


def test_load_does_not_import_hardware_or_open_a_socket(tmp_path: Path) -> None:
    port = service(tmp_path)
    before = set(sys.modules)
    settings = port.load(
        repo_root() / "fixtures" / "ground" / "g02" / "site" / "ground.json",
        modes=FAKE,
        scenario=None,
    )
    introduced = set(sys.modules) - before
    assert settings.dog_transport == "ethernet"
    assert not any(name in _BANNED or name.split(".", 1)[0] in _BANNED for name in introduced)
    devices = getattr(port.peers.adapters, "devices", None)
    assert getattr(devices, "calls", []) == []


def test_harness_factory_and_port_factory_share_one_loader(tmp_path: Path) -> None:
    services = build_test_services(output_dir=tmp_path / "out")
    harness = create(services)
    direct = create(services.kernel, harness.peers)
    left = harness.load(None, modes=FAKE, scenario="dismiss")
    right = direct.load(None, modes=FAKE, scenario="dismiss")
    assert left.scenario == right.scenario == "dismiss"
    assert harness.peers is services or harness.peers.config is services.config
