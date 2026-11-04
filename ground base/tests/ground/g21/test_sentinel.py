"""0 dBm is a sentinel only when it stands in for no signal."""

from __future__ import annotations

from patrol.ground.kernel.contracts import BaseServices, FeaturePort
from tests.ground.g21.support import payload, run, window_body


def test_empty_median_zero_is_rejected(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    unavailable = run(feature, payload("sentinel_zero"))
    assert unavailable.status == "failed"
    assert unavailable.data["reason"] == "0 dBm is not a no-signal sentinel"
    assert "median_rssi_dbm" not in unavailable.data
    valid = payload()
    inner = window_body(valid)
    inner["samples"] = []
    inner["quality"] = "valid"
    inner["median_rssi_dbm"] = 0
    inner["spread_db"] = None
    result = run(feature, valid)
    assert result.status == "failed"
    assert result.data["reason"] == "0 dBm is not a no-signal sentinel"


def test_empty_spread_zero_is_rejected(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload("no_signal")
    window_body(body)["spread_db"] = 0
    result = run(feature, body)
    assert result.status == "failed"
    assert result.data["reason"] == "0 dBm is not a no-signal sentinel"
