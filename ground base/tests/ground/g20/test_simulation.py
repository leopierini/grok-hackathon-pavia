"""The frozen simulator runs navigation cases without a dog call."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g20.implementation import create
from patrol.ground.extensions.g20.scenarios import CASE_IDS, cases
from patrol.ground.testing.builders import build_test_services
from tests.ground.g20.support import run


def test_scripted_cases_match_the_harness(tmp_path: Path) -> None:
    async def body() -> None:
        scripted = cases(seed=0)
        assert tuple(case.case_id for case in scripted) == CASE_IDS
        traces: list[str] = []
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
            traces.extend(report.trace)
        joined = " ".join(traces)
        assert "usable:candidate-forward-01" in joined
        assert "ready_to_wait:true" in joined
        assert "dropped:expired" in joined
        assert "dropped:map_epoch" in joined
        assert "target_range:absent" in joined
        assert "move_local:none" in joined
        assert "command:none" in joined
        assert "move_local" not in joined.replace("move_local:none", "")
        assert "dog.run_route" not in joined

    run(body)
