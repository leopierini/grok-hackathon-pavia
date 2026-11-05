"""The Task 01 harness runs every dog-ack case against a fresh manual clock."""

from __future__ import annotations

import tempfile
from pathlib import Path

from patrol.ground.extensions.g24.implementation import DogAckFeature, create
from patrol.ground.extensions.g24.scenarios import cases
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.testing.builders import build_test_services
from tests.ground.g24.conftest import run


def test_harness_plays_every_case() -> None:
    async def body() -> None:
        for case in cases(seed=0):
            services = _services()
            feature = create(services)
            assert isinstance(feature, DogAckFeature)
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            assert report.failures == (), report.cases
            assert report.live_call_count == 0
            assert report.cases[0]["passed"] is True

    run(body)


def _services() -> BaseServices:
    root = Path(tempfile.mkdtemp(prefix="ground-g24-sim-"))
    return build_test_services(output_dir=root, clock_mode="manual", seed=0)
