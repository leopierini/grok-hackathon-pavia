"""Shared callers for GROUND-21 tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from patrol.ground.extensions.g21.implementation import scripted_payload
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeaturePort,
    FeatureRequest,
    FeatureResult,
    Ticket,
)
from patrol.ground.kernel.validation import freeze_map

FORBIDDEN = frozenset(
    {"heading", "bearing", "range_m", "distance_m", "meters", "range", "distance"}
)


def payload(case_id: str = "example_window") -> dict[str, object]:
    return scripted_payload(case_id)


def window_body(body: dict[str, object]) -> dict[str, object]:
    window = body["window"]
    assert isinstance(window, dict)
    inner = window["payload"]
    assert isinstance(inner, dict)
    return inner


def heartbeat_body(body: dict[str, object]) -> dict[str, object]:
    heartbeat = body["heartbeat"]
    assert isinstance(heartbeat, dict)
    inner = heartbeat["payload"]
    assert isinstance(inner, dict)
    return inner


def run(
    feature: FeaturePort,
    body: Mapping[str, object],
    ticket: Ticket | None = None,
) -> FeatureResult:
    request = FeatureRequest("stage", "rssi.window", ticket, freeze_map(dict(body)))
    return asyncio.run(feature.execute(request))


def assert_quiet(services: BaseServices, result: FeatureResult) -> None:
    devices = getattr(services.adapters, "devices", None)
    assert getattr(devices, "calls", None) == []
    assert "state.apply" not in getattr(services.state, "trace", [])
    records = getattr(services.journal, "records", None)
    assert records == []
    assert FORBIDDEN.isdisjoint(result.data)
    assert result.events
    for event in result.events:
        assert event.kind == "decision_received"
        assert FORBIDDEN.isdisjoint(event.payload)
        assert "dog.command" not in event.payload
