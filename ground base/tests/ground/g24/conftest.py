"""Shared fixtures for dog acknowledgement tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

import pytest
from patrol.ground.extensions.g24.implementation import DogAckFeature, create
from patrol.ground.extensions.g24.model import as_dict
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult, Ticket
from patrol.ground.testing.builders import build_test_services

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "ground" / "g24"


@pytest.fixture
def opened(tmp_path: Path) -> tuple[BaseServices, DogAckFeature]:
    services = build_test_services(output_dir=tmp_path)
    feature = create(services)
    if not isinstance(feature, DogAckFeature):
        raise AssertionError("factory did not return the dog ack feature")
    return services, feature


def load(name: str) -> dict[str, object]:
    return as_dict(json.loads((FIXTURES / name).read_text(encoding="utf-8")), name)


def command() -> dict[str, object]:
    return load("ground-to-dog-command.json")


def expired_command() -> dict[str, object]:
    return load("expired-dog-command.json")


def halt_command() -> dict[str, object]:
    return load("ground-to-dog-halt.json")


def run(test: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(test())


async def execute(
    feature: DogAckFeature,
    name: str,
    payload: Mapping[str, object],
    ticket: Ticket | None = None,
) -> FeatureResult:
    return await feature.execute(FeatureRequest("stage", name, ticket, dict(payload)))


def calls_of(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found
