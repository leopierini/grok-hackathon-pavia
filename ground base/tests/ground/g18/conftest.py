"""Shared fixtures for drone acknowledgement tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

import pytest
from patrol.ground.extensions.g18.implementation import DroneAckFeature, create
from patrol.ground.extensions.g18.messages import load_fixture
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult
from patrol.ground.testing.builders import build_test_services


@pytest.fixture
def services(tmp_path: Path) -> BaseServices:
    return build_test_services(output_dir=tmp_path)


@pytest.fixture
def feature(services: BaseServices) -> DroneAckFeature:
    created = create(services)
    if not isinstance(created, DroneAckFeature):
        raise AssertionError("factory did not return the drone ack feature")
    return created


def call(feature: DroneAckFeature, request: FeatureRequest) -> FeatureResult:
    return asyncio.run(feature.execute(request))


def clock_of(services: BaseServices) -> ManualClock:
    clock = services.kernel.clock
    if not isinstance(clock, ManualClock):
        raise AssertionError("tests require the manual clock")
    return clock


def device_calls(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    calls = getattr(devices, "calls", None)
    if not isinstance(calls, list):
        raise AssertionError("device call trace is missing")
    return calls


def load(name: str) -> dict[str, object]:
    return load_fixture(name)


def track() -> dict[str, object]:
    return load("ground-to-drone-command.json")


def land() -> dict[str, object]:
    return load("ground-to-drone-land.json")


def observation() -> dict[str, object]:
    return load("drone-observation.json")


def payload_of(message: Mapping[str, object]) -> dict[str, object]:
    payload = message["payload"]
    if not isinstance(payload, dict):
        raise AssertionError("payload must be an object")
    return dict(payload)


def rewrite(message: dict[str, object], **fields: object) -> dict[str, object]:
    updated = payload_of(message)
    updated.update(fields)
    cloned = dict(message)
    cloned["payload"] = updated
    return cloned


def apply_request(
    ack: Mapping[str, object],
    command: Mapping[str, object],
    *,
    seen: Mapping[str, object] | None = None,
    deadline: float | None = 10.0,
) -> FeatureRequest:
    payload: dict[str, object] = {"ack": ack, "command": command}
    if seen is not None:
        payload["observation"] = seen
    if deadline is not None:
        payload["reply_deadline_monotonic"] = deadline
    return FeatureRequest("command", "apply_ack", None, payload)


def kinds(result: FeatureResult) -> list[str]:
    return [event.kind for event in result.events]
