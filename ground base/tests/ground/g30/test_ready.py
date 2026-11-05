"""Full Ethernet and Wi-Fi profiles."""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g30.implementation import SCHEMA, SLOT, LinkFeature, create
from patrol.ground.kernel.contracts import FeatureRequest, FeatureResult
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def _feature(tmp_path: Path) -> LinkFeature:
    created = create(build_test_services(output_dir=tmp_path))
    if not isinstance(created, LinkFeature):
        raise AssertionError("factory did not return the link feature")
    return created


def _run(feature: LinkFeature, name: str) -> FeatureResult:
    return asyncio.run(
        feature.execute(FeatureRequest("diagnostic", name, None, {"seed": 0}))
    )


def _event(result: FeatureResult) -> dict[str, object]:
    assert result.events
    return dict(result.events[0].payload)


def _fixture(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g30" / name
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"{name} is not an object")
    return {str(key): value for key, value in parsed.items()}


def test_ethernet_profile_is_ready_with_usb_pi_and_failed_router(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    devices = feature.services.adapters.devices  # type: ignore[attr-defined]
    calls = list(devices.calls)
    result = _run(feature, "ethernet_ready")
    event = _event(result)
    assert result.status == "ok"
    assert result.error is None
    assert result.data["slot"] == SLOT
    assert result.data["schema_version"] == SCHEMA
    assert result.data["authorized"] is False
    assert result.data["detail"] == "ready:ethernet-tether"
    assert event["ready"] is True
    assert event["profile"] == "ethernet-tether"
    assert event["dog_transport"] == "ethernet"
    assert event["pi_path"] == "usb"
    assert event["router"] == "back_enclosure_failed"
    assert event["rssi_blocked"] is False
    assert event["request_safety"] is False
    assert event["evidence"] == "simulated"
    assert "router:repaired" not in result.data["trace"]
    assert feature.services.kernel.authority.cancelled is False
    assert list(devices.calls) == calls


def test_wifi_profile_does_not_require_the_tether(tmp_path: Path) -> None:
    result = _run(_feature(tmp_path), "wifi_ready")
    event = _event(result)
    assert result.status == "ok"
    assert event["ready"] is True
    assert event["dog_transport"] == "wifi"
    assert event["pi_path"] == "second_radio"
    assert event["profile"] == "wifi-lan"
    assert "tether:not_required" in result.data["trace"]
    assert "handover:rejected" not in result.data["trace"]


def test_contract_examples_are_the_peer_evidence(tmp_path: Path) -> None:
    dog = _fixture("dog-capabilities.json")
    drone = _fixture("drone-capabilities.json")
    heartbeat = _fixture("pi-heartbeat.json")
    assert dog["kind"] == "capabilities.report"
    assert dog["source"] == "dog"
    assert drone["kind"] == "capabilities.report"
    assert drone["source"] == "drone"
    assert heartbeat["kind"] == "heartbeat"
    assert heartbeat["source"] == "pi"
    assert heartbeat["simulated"] is True
    result = _run(_feature(tmp_path), "ethernet_ready")
    event = _event(result)
    assert event["dog_identified"] is True
    assert event["drone_identified"] is True
    assert event["pi_telemetry"] is True


def test_provider_modules_do_not_import_sockets() -> None:
    root = repo_root() / "patrol" / "ground" / "extensions" / "g30"
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            assert "socket" not in modules
            assert "subprocess" not in modules
