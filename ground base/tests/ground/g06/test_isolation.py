"""Evidence validation does not call a model, a device, or the network."""

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path

from patrol.ground.extensions.g06 import implementation
from patrol.ground.extensions.g06.model import ServicePorts
from tests.ground.g06.support import live_frame, validate


def test_provider_source_does_not_import_devices_or_network() -> None:
    root = Path("patrol/ground/extensions/g06")
    forbidden = {
        "socket",
        "urllib",
        "requests",
        "djitellopy",
        "unitree_webrtc_connect",
        "xai",
        "patrol.dog",
        "patrol.drone",
        "patrol.grok",
    }
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                assert module.split(".", 1)[0] not in forbidden
                assert module not in forbidden


def test_validation_does_not_call_peers_or_load_device_modules(tmp_path: Path) -> None:
    root = tmp_path / "adapter"
    root.mkdir()
    frame, interval = live_frame(root)

    class Probe:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def __getattr__(self, name: str) -> object:
            def record(*_args: object, **_kwargs: object) -> None:
                self.calls.append(name)

            return record

    probe = Probe()
    peers = ServicePorts(reasoner=probe, dog=probe, drone=probe)
    before = set(sys.modules)

    result = asyncio.run(validate(frame, root=root, interval=interval, peers=peers))

    assert result.status == "accepted"
    assert probe.calls == []
    assert "djitellopy" not in sys.modules
    assert "unitree_webrtc_connect" not in sys.modules
    assert "xai_sdk" not in sys.modules
    assert "requests" not in set(sys.modules) - before
    assert implementation.create is not None
