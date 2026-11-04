"""The frozen simulator runs the beacon cases without a dog call."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g19.implementation import create
from patrol.ground.extensions.g19.scenarios import cases
from patrol.ground.testing.builders import build_test_services
from tests.ground.g19.support import run


def test_scripted_cases_match_the_harness(tmp_path: Path) -> None:
    async def body() -> None:
        scripted = cases(seed=0)
        assert len(scripted) == 10
        epochs: list[str] = []
        for case in scripted:
            built = build_test_services(output_dir=tmp_path / case.case_id, seed=0)
            port = create(built)
            report = await built.kernel.simulator.run(
                case,
                providers={"feature": port, "services": built},
                clock_mode="manual",
            )
            assert report.failures == (), report
            assert report.live_call_count == 0
            epochs.extend(report.trace)
        joined = " ".join(epochs)
        assert "beacon_epoch:3" in joined
        assert "beacon_epoch:4" in joined
        assert "commanded_epoch:4" in joined
        assert "dog_command:none" in joined
        assert "dog.run_route" not in joined

    run(body)
