"""Doubles for the proximity goal. Construction does not call devices."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from patrol.ground.extensions.g26.implementation import ProximityFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest
from patrol.ground.testing.builders import build_test_services


@pytest.fixture
def opened(tmp_path: Path) -> tuple[BaseServices, ProximityFeature]:
    services = build_test_services(output_dir=tmp_path)
    created = create(services)
    if not isinstance(created, ProximityFeature):
        raise AssertionError("factory did not return the proximity feature")
    return services, created


def request(name: str, payload: dict[str, object] | None = None) -> FeatureRequest:
    body: dict[str, object] = {"seed": 0}
    if payload is not None:
        body = payload
    return FeatureRequest("diagnostic", name, None, body)


def run(test: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(test())
