"""No-signal encoding and qualities Task 22 must not follow."""

from __future__ import annotations

from patrol.ground.kernel.contracts import BaseServices, FeaturePort
from tests.ground.g21.support import assert_quiet, payload, run, window_body


def test_no_signal_keeps_null_statistics(opened: tuple[BaseServices, FeaturePort]) -> None:
    services, feature = opened
    result = run(feature, payload("no_signal"))
    assert result.status == "ok"
    assert result.error is None
    assert result.data["quality"] == "unavailable"
    assert result.data["comparable"] is False
    assert result.data["follow"] is False
    assert result.data["median_rssi_dbm"] is None
    assert result.data["spread_db"] is None
    assert result.data["samples"] == ()
    assert result.data["epoch"] == 3
    assert result.events[0].payload["median_rssi_dbm"] is None
    assert_quiet(services, result)


def test_noisy_and_stale_are_observations(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    for quality in ("noisy", "stale"):
        body = payload()
        window_body(body)["quality"] = quality
        result = run(feature, body)
        assert result.status == "ok"
        assert result.data["detail"] == "observation"
        assert result.data["follow"] is False
        assert result.data["comparable"] is False
        assert result.data["median_rssi_dbm"] == -60
        assert result.data["quality"] == quality


def test_unavailable_with_samples_is_rejected(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    window_body(body)["quality"] = "unavailable"
    window_body(body)["median_rssi_dbm"] = None
    window_body(body)["spread_db"] = None
    result = run(feature, body)
    assert result.status == "failed"
    assert result.data["reason"] == "no-signal requires empty samples and null statistics"


def test_empty_valid_quality_is_rejected(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    inner = window_body(body)
    inner["samples"] = []
    inner["median_rssi_dbm"] = None
    inner["spread_db"] = None
    result = run(feature, body)
    assert result.status == "failed"
    assert result.data["reason"] == "this quality requires samples"
