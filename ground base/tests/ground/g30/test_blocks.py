"""Missing acceptance, Pi path, handover, secrets, and route changes."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.extensions.g30.probe import scripted_probe
from patrol.ground.kernel.contracts import FeatureResult
from patrol.ground.kernel.paths import repo_root
from tests.ground.g30.test_ready import _event, _feature, _run


def _text(result: FeatureResult) -> str:
    payload = {
        "data": dict(result.data),
        "error": None if result.error is None else result.error.detail,
        "events": [dict(event.payload) for event in result.events],
    }
    return json.dumps(payload)


def test_missing_tether_blocks_ethernet(tmp_path: Path) -> None:
    result = _run(_feature(tmp_path), "ethernet_no_tether")
    event = _event(result)
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert event["ready"] is False
    assert event["missing_path"] == "tether"
    assert result.data["detail"] == "blocked:tether_acceptance"


def test_missing_pi_path_blocks_rssi_and_keeps_peer_identity(tmp_path: Path) -> None:
    result = _run(_feature(tmp_path), "missing_pi_path")
    event = _event(result)
    assert result.status == "blocked"
    assert event["ready"] is False
    assert event["rssi_blocked"] is True
    assert event["missing_path"] == "pi_path"
    assert event["dog_identified"] is True
    assert event["drone_identified"] is True
    assert event["pi_path"] is None
    assert "heartbeat:ignored_without_path" in result.data["trace"]


def test_tello_association_is_not_a_pi_path(tmp_path: Path) -> None:
    result = _run(_feature(tmp_path), "tello_without_pi")
    event = _event(result)
    assert event["rssi_blocked"] is True
    assert event["dog_identified"] is True
    assert event["drone_identified"] is True
    assert "tello_ap:not_a_pi_path" in result.data["trace"]
    assert result.data["detail"] == "blocked:pi_path"


def test_transport_switch_stays_on_the_selected_profile(tmp_path: Path) -> None:
    probe = scripted_probe("transport_switch")
    result = _run(_feature(tmp_path), "transport_switch")
    event = _event(result)
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert event["dog_transport"] == "ethernet"
    assert probe["dog_transport"] == "ethernet"
    assert event["ready"] is False
    assert "handover:rejected" in result.data["trace"]
    assert "switch:wifi" in result.data["trace"]


def test_dog_link_drop_clears_ready_and_asks_for_the_latch(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    result = _run(feature, "dog_link_drop")
    event = _event(result)
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "unavailable"
    assert result.error.recovery_required is True
    assert event["ready"] is False
    assert event["request_safety"] is True
    assert event["task28_latch"] is True
    assert result.events[0].kind == "link_lost"
    assert "latch:task28" in result.data["trace"]
    assert feature.services.kernel.authority.cancelled is False


def test_router_failure_is_not_the_pi(tmp_path: Path) -> None:
    ready = _event(_run(_feature(tmp_path), "router_separate"))
    blocked = _event(_run(_feature(tmp_path), "router_not_pi_excuse"))
    assert ready["ready"] is True
    assert ready["router"] == "back_enclosure_failed"
    assert ready["pi_path"] == "usb"
    assert blocked["ready"] is False
    assert blocked["router"] == "back_enclosure_failed"
    assert blocked["missing_path"] == "pi_path"
    assert blocked["router"] != "pi"


def test_route_change_is_rejected(tmp_path: Path) -> None:
    result = _run(_feature(tmp_path), "route_change")
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "forbidden_command"
    assert result.data["detail"] == "blocked:route_change"
    assert result.events[0].kind == "composition_rejected"
    assert "repair:rejected" in result.data["trace"]


def test_secret_marker_is_not_copied(tmp_path: Path) -> None:
    marker_path = repo_root() / "fixtures" / "ground" / "g30" / "secret-marker.json"
    parsed: object = json.loads(marker_path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    marker = parsed["marker"]
    assert isinstance(marker, str)
    result = _run(_feature(tmp_path), "secrets_redacted")
    rendered = _text(result)
    assert marker not in rendered
    assert "password" not in rendered
    assert "secrets:redacted" in result.data["trace"]
    assert result.status == "ok"
