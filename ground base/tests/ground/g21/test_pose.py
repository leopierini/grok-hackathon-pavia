"""Dog pose and sample integrity."""

from __future__ import annotations

from patrol.ground.kernel.contracts import BaseServices, FeaturePort
from tests.ground.g21.support import payload, run, window_body


def _pose(body: dict[str, object]) -> dict[str, object]:
    samples = window_body(body)["samples"]
    assert isinstance(samples, list)
    sample = samples[0]
    assert isinstance(sample, dict)
    pose = sample["pose"]
    assert isinstance(pose, dict)
    return pose


def test_other_map_epoch_drops_the_window(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    result = run(feature, payload("foreign_map"))
    assert result.status == "failed"
    assert result.data["reason"] == "sample pose is on another map epoch"
    assert result.data["map_epoch"] == 1


def test_other_map_id_and_invalid_pose_are_rejected(
    opened: tuple[BaseServices, FeaturePort],
) -> None:
    _, feature = opened
    other = payload()
    _pose(other)["map_id"] = "other-map"
    assert run(feature, other).data["reason"] == "sample pose is on another map"
    invalid = payload()
    _pose(invalid)["valid"] = False
    assert run(feature, invalid).data["reason"] == "sample pose is not valid"


def test_rssi_outside_the_closed_range_is_rejected(
    opened: tuple[BaseServices, FeaturePort],
) -> None:
    _, feature = opened
    low = payload()
    sample = window_body(low)["samples"]
    assert isinstance(sample, list)
    assert isinstance(sample[0], dict)
    sample[0]["rssi_dbm"] = -151
    assert "rssi_dbm" in str(run(feature, low).data["reason"])
    high = payload()
    high_samples = window_body(high)["samples"]
    assert isinstance(high_samples, list)
    assert isinstance(high_samples[0], dict)
    high_samples[0]["rssi_dbm"] = 1
    assert run(feature, high).status == "failed"
    flagged = payload()
    flagged_samples = window_body(flagged)["samples"]
    assert isinstance(flagged_samples, list)
    assert isinstance(flagged_samples[0], dict)
    flagged_samples[0]["rssi_dbm"] = True
    boolean = run(feature, flagged)
    assert boolean.error is not None
    assert boolean.error.code == "invalid_input"


def test_lying_median_is_not_replaced(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    window_body(body)["median_rssi_dbm"] = -40
    result = run(feature, body)
    assert result.status == "failed"
    assert result.data["reason"] == "reported median does not match the samples"
    assert "median_rssi_dbm" not in result.data
    assert "range_m" not in result.data


def test_duplicate_sample_and_reversed_window(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    samples = window_body(body)["samples"]
    assert isinstance(samples, list)
    assert isinstance(samples[1], dict)
    samples[1]["sample_id"] = "rssi-0"
    assert run(feature, body).data["reason"] == "duplicate sample_id"
    reversed_window = payload()
    inner = window_body(reversed_window)
    inner["window_end"] = "2026-11-04T13:00:09.000Z"
    result = run(feature, reversed_window)
    assert result.data["reason"] == "window_end is before window_start"


def test_unknown_heading_field_is_rejected(opened: tuple[BaseServices, FeaturePort]) -> None:
    _, feature = opened
    body = payload()
    window_body(body)["heading"] = 1.2
    result = run(feature, body)
    assert result.status == "failed"
    assert "heading" in str(result.data["reason"])
    assert "heading" not in result.data
    assert "range_m" not in result.events[0].payload
