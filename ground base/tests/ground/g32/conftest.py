"""Direct rehearsal calls. Construction does not touch a robot."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from patrol.ground.extensions.g32.implementation import RehearsalFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult
from patrol.ground.testing.builders import build_test_services


@pytest.fixture
def services(tmp_path: Path) -> BaseServices:
    return build_test_services(output_dir=tmp_path)


def run(
    services: BaseServices,
    name: str,
    **payload: object,
) -> tuple[RehearsalFeature, FeatureResult]:
    feature = create(services)
    devices = getattr(services.adapters, "devices", None)
    output = getattr(devices, "output_dir", None)
    body: dict[str, object] = {
        "scenario": name,
        "seed": 0,
        "simulation_mode": "simulation",
        "output_root": str(output),
    }
    body.update(payload)
    request = FeatureRequest("diagnostic", name, None, body)
    result = asyncio.run(feature.execute(request))
    return feature, result


def report_at(services: BaseServices, name: str) -> dict[str, object]:
    devices = getattr(services.adapters, "devices", None)
    output = Path(str(getattr(devices, "output_dir", "")))
    path = output / f"rehearsal-{name}-seed0" / "report.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError("report is not an object")
    return loaded


def calls_of(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found


def assertion_ok(report: Mapping[str, object], name: str) -> bool:
    rows = report.get("assertions")
    if not isinstance(rows, list):
        return False
    for item in rows:
        if isinstance(item, dict) and item.get("name") == name:
            return item.get("ok") is True
    return False
