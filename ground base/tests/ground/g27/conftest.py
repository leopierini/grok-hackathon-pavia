"""Direct doubles for recovery tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

import pytest
from patrol.ground.extensions.g27.implementation import RecoveryFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult
from patrol.ground.kernel.validation import freeze_map
from patrol.ground.testing.builders import build_test_services


@pytest.fixture
def services(tmp_path: Path) -> BaseServices:
    return build_test_services(output_dir=tmp_path)


@pytest.fixture
def feature(services: BaseServices) -> RecoveryFeature:
    return create(services)


def evaluate(feature: RecoveryFeature, **payload: object) -> FeatureResult:
    request = FeatureRequest("diagnostic", "evaluate", None, freeze_map(payload))
    return asyncio.run(feature.execute(request))


def calls_of(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found


def journal_count(services: BaseServices) -> int:
    records = getattr(services.journal, "records", None)
    if not isinstance(records, list):
        raise AssertionError("journal record list is missing")
    return len(records)


def record(result: FeatureResult) -> Mapping[str, object]:
    found = result.data["recovery_record"]
    if not isinstance(found, Mapping):
        raise AssertionError("recovery record is missing")
    return found
