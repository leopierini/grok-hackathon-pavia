"""Helpers for dog-command tests. They call the g23 factory directly."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from patrol.ground.extensions.g23.implementation import DogCommandFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult, Ticket
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import build_test_services


def run(test: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(test())


def opened(tmp_path: Path) -> tuple[BaseServices, DogCommandFeature]:
    services = build_test_services(output_dir=tmp_path)
    services.kernel.authority.reset_generation("open dog-command test mission")
    return services, create(services)


def fixture(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g23" / name
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError(f"{name} is not an object")
    return {str(key): value for key, value in raw.items()}


def move_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "proposal": fixture("proposal.json"),
        "candidates": fixture("candidates.json"),
        "readiness": fixture("readiness.json"),
        "safety_snapshot_id": "safety-001",
        "halt_latched": False,
        "issue_halt": False,
        "simulated": True,
    }
    payload.update(overrides)
    return payload


async def approve(feature: DogCommandFeature, payload: Mapping[str, object]) -> FeatureResult:
    request = FeatureRequest(
        kind="command",
        name="approve",
        ticket=Ticket("demo-20261104-001", 1, "dog-command"),
        payload=freeze_map(dict(payload)),
    )
    return await feature.execute(request)


def command_of(result: FeatureResult) -> dict[str, object]:
    if result.status != "ok" or result.error is not None:
        detail = "" if result.error is None else result.error.detail
        raise AssertionError(f"{result.status}: {detail}")
    command = result.data["command"]
    if not isinstance(command, dict):
        raise AssertionError("command was not an object")
    return {str(key): value for key, value in command.items()}


def payload_of(command: Mapping[str, object]) -> dict[str, object]:
    body = command["payload"]
    if not isinstance(body, dict):
        raise AssertionError("payload was not an object")
    return {str(key): value for key, value in body.items()}


def calls_of(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return [str(item) for item in found]
