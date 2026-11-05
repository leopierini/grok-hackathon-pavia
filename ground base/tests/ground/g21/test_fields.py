"""The provider does not invent a heading or a range."""

from __future__ import annotations

from patrol.ground.kernel.contracts import BaseServices, FeaturePort
from tests.ground.g21.support import FORBIDDEN, payload, run


def test_success_and_rejection_omit_range_fields(
    opened: tuple[BaseServices, FeaturePort],
) -> None:
    _, feature = opened
    for case_id in ("example_window", "no_signal", "bssid_swapped", "sentinel_zero"):
        result = run(feature, payload(case_id))
        assert FORBIDDEN.isdisjoint(result.data)
        assert FORBIDDEN.isdisjoint(result.events[0].payload)
        rendered = " ".join(str(key) for key in result.data)
        assert "range_m" not in rendered
        assert "heading" not in rendered
