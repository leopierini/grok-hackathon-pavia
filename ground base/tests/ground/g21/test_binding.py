"""Beacon, receiver, and epoch binding."""

from __future__ import annotations

from patrol.ground.kernel.contracts import BaseServices, FeaturePort
from tests.ground.g21.support import assert_quiet, heartbeat_body, payload, run, window_body


def test_epoch_mismatch_is_incomparable(opened: tuple[BaseServices, FeaturePort]) -> None:
    services, feature = opened
    body = payload("epoch_changed")
    result = run(feature, body)
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "epoch_mismatch"
    assert result.data["detail"] == "incomparable"
    assert result.data["comparable"] is False
    assert result.data["epoch"] == 3
    assert result.data["beacon_epoch"] == 2
    assert "median_rssi_dbm" not in result.data
    assert_quiet(services, result)


def test_ssid_match_does_not_excuse_a_different_bssid(
    opened: tuple[BaseServices, FeaturePort],
) -> None:
    services, feature = opened
    body = payload("bssid_swapped")
    beacon = body["beacon"]
    assert isinstance(beacon, dict)
    assert beacon["ssid"] == "TELLO-DEMO"
    result = run(feature, body)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert result.data["reason"] == "bssid does not match the armed beacon"
    assert_quiet(services, result)


def test_bad_bssid_pattern_is_rejected(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    window_body(body)["bssid"] = "02:00:00:00:00"
    result = run(feature, body)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"


def test_beacon_id_and_receiver_must_match(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    foreign_beacon = payload()
    window_body(foreign_beacon)["beacon_id"] = "tello-other"
    beacon_result = run(feature, foreign_beacon)
    assert beacon_result.error is not None
    assert "beacon id" in str(beacon_result.data["reason"])
    foreign_pi = payload()
    window_body(foreign_pi)["receiver_id"] = "pi-02"
    heartbeat_body(foreign_pi)["device_id"] = "pi-02"
    receiver_result = run(feature, foreign_pi)
    assert receiver_result.data["reason"] == "receiver_id does not match the armed Pi"


def test_moving_and_unknown_holds_are_incomparable(
    opened: tuple[BaseServices, FeaturePort],
) -> None:
    _, feature = opened
    moving = run(feature, payload("moving_hold"))
    assert moving.status == "blocked"
    assert moving.data["detail"] == "incomparable"
    unknown = payload()
    beacon = unknown["beacon"]
    assert isinstance(beacon, dict)
    beacon["hold_state"] = "unknown"
    result = run(feature, unknown)
    assert result.status == "blocked"
    assert result.data["reason"] == "beacon hold is unknown"


def test_laptop_source_and_renamed_kind_are_rejected(
    opened: tuple[BaseServices, FeaturePort],
) -> None:
    _, feature = opened
    laptop = run(feature, payload("laptop_rssi"))
    assert laptop.status == "failed"
    assert laptop.data["reason"] == "laptop RSSI is not a supported message"
    renamed = payload()
    window = renamed["window"]
    assert isinstance(window, dict)
    window["kind"] = "laptop.rssi"
    result = run(feature, renamed)
    assert result.status == "failed"
    assert "laptop" in str(result.data["reason"])


def test_receiver_mount_must_be_dog(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    window_body(body)["receiver_mount"] = "laptop"
    result = run(feature, body)
    assert result.data["reason"] == "receiver_mount must be dog"


def test_string_epoch_is_not_coerced(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    window_body(body)["beacon_epoch"] = "3"
    result = run(feature, body)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"


def test_cancelled_ticket_does_not_validate(opened: tuple[BaseServices, FeaturePort]) -> None:
    services, feature = opened
    ticket = services.kernel.authority.issue("demo-20261104-001", "rssi")
    services.kernel.authority.latch_cancel("operator halt")
    result = run(feature, payload(), ticket)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "cancelled"
    assert result.data["comparable"] is False
    assert_quiet(services, result)
