"""Fixtures for the RSSI window provider."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.ground.extensions.g21.implementation import create
from patrol.ground.kernel.contracts import BaseServices, FeaturePort
from patrol.ground.testing.builders import build_test_services


@pytest.fixture
def opened(tmp_path: Path) -> tuple[BaseServices, FeaturePort]:
    services = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
    return services, create(services)
