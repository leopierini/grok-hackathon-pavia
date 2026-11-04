"""Shared builders for envelope tests. They stay on the manual clock."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.ground.extensions.g11.implementation import create
from patrol.ground.extensions.g11.schema_check import fixture_root
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import build_test_services


def services(tmp: Path) -> BaseServices:
    built = build_test_services(clock_mode="manual", seed=0, output_dir=tmp)
    if built.kernel.authority.epoch == 0:
        built.kernel.authority.reset_generation("admit")
    return built


def gate(built: BaseServices) -> object:
    return create(built)


def load(name: str) -> dict[str, object]:
    loaded = json.loads((fixture_root() / name).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"{name} is not an object")
    return loaded


def request_for(
    message: dict[str, object],
    *,
    expected_source: str | None = None,
    expected_destination: str | None = None,
    epoch: int | None = None,
    barrier: str | None = None,
    raw: object | None = None,
) -> FeatureRequest:
    source = message.get("source")
    destination = message.get("destination")
    payload: dict[str, object] = {
        "message": json.dumps(message) if raw is None else raw,
        "expected_source": source if expected_source is None else expected_source,
        "expected_destination": (
            destination if expected_destination is None else expected_destination
        ),
        "epoch": message.get("epoch") if epoch is None else epoch,
    }
    if barrier is not None:
        payload["barrier"] = barrier
    return FeatureRequest("guard", "v2_envelope", None, freeze_map(payload))


async def run(port: object, request: FeatureRequest) -> FeatureResult:
    execute = getattr(port, "execute", None)
    if not callable(execute):
        raise AssertionError("provider has no execute")
    result = await execute(request)
    if not isinstance(result, FeatureResult):
        raise AssertionError("provider did not return FeatureResult")
    return result


def calls(built: BaseServices) -> list[str]:
    devices = getattr(built.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if isinstance(found, list):
        return [str(item) for item in found]
    return []
