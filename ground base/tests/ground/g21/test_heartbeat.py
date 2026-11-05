"""Clock error and heartbeat freshness."""

from __future__ import annotations

from patrol.ground.kernel.contracts import BaseServices, FeaturePort
from tests.ground.g21.support import heartbeat_body, payload, run, window_body


def test_clock_error_above_the_limit_is_rejected(
    opened: tuple[BaseServices, FeaturePort],
) -> None:
    _, feature = opened
    result = run(feature, payload("clock_error"))
    assert result.status == "failed"
    assert result.data["reason"] == "clock_error_ms exceeds the fixture limit"
    assert result.data["clock_error_ms"] == 51
    assert "median_rssi_dbm" not in result.data
    heartbeat = payload()
    heartbeat_body(heartbeat)["clock_error_ms"] = 80
    heart = run(feature, heartbeat)
    assert heart.data["reason"] == "heartbeat clock_error_ms exceeds the fixture limit"


def test_clock_error_at_the_limit_is_accepted(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    window_body(body)["clock_error_ms"] = 50
    result = run(feature, body)
    assert result.status == "ok"
    assert result.data["clock_error_ms"] == 50


def test_stale_heartbeat_drops_the_window(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    stale = run(feature, payload("stale_heartbeat"))
    assert stale.status == "failed"
    assert stale.data["reason"] == "heartbeat is older than the fixture limit"
    missing = payload()
    missing["heartbeat"] = None
    absent = run(feature, missing)
    assert absent.data["reason"] == "heartbeat is missing"
    unhealthy = payload()
    heartbeat_body(unhealthy)["healthy"] = False
    result = run(feature, unhealthy)
    assert result.data["reason"] == "heartbeat is unhealthy"


def test_string_boolean_is_not_healthy(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    heartbeat_body(body)["healthy"] = "true"
    result = run(feature, body)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"


def test_heartbeat_age_boundary(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    exact = payload()
    limits = exact["limits"]
    assert isinstance(limits, dict)
    limits["received_at"] = "2026-11-04T13:00:12.000Z"
    assert run(feature, exact).status == "ok"
    over = payload()
    over_limits = over["limits"]
    assert isinstance(over_limits, dict)
    over_limits["received_at"] = "2026-11-04T13:00:12.001Z"
    result = run(feature, over)
    assert result.data["reason"] == "heartbeat is older than the fixture limit"


def test_heartbeat_mission_epoch_must_match(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    heartbeat = body["heartbeat"]
    assert isinstance(heartbeat, dict)
    heartbeat["epoch"] = 2
    result = run(feature, body)
    assert result.data["reason"] == "heartbeat mission epoch does not match the window"
