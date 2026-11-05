"""Shared request builder for drone-command tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from patrol.ground.extensions.g17.implementation import SLOT, DroneCommandFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult, Ticket
from patrol.ground.testing.builders import build_test_services


def feature(tmp_path: Path) -> tuple[BaseServices, DroneCommandFeature]:
    services = build_test_services(output_dir=tmp_path)
    created = create(services)
    return services, created


def request(
    context: Mapping[str, object],
    ticket: Ticket | None = None,
) -> FeatureRequest:
    return FeatureRequest("stage", SLOT, ticket, context)


def run(test: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(test())


def payload(result: FeatureResult) -> Mapping[str, object]:
    command = result.data["command"]
    assert isinstance(command, Mapping)
    body = command["payload"]
    assert isinstance(body, Mapping)
    return body


def calls_of(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found
