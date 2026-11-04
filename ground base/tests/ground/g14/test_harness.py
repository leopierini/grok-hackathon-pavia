"""Task 01 harness cases. The v1 loader does not admit this v2 manifest yet."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from patrol.ground.extensions.g14.implementation import SLOT, create
from patrol.ground.extensions.g14.scenarios import cases
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def test_manifest_names_the_v2_slot() -> None:
    path = repo_root() / "patrol" / "ground" / "extensions" / "g14" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ground-task-v2"
    assert manifest["task_id"] == "GROUND-14"
    assert manifest["slot"] == SLOT
    assert manifest["factory"].endswith("g14.implementation:create")


def test_harness_cases_accept_and_reject_without_device_calls(tmp_path: Path) -> None:
    async def body() -> None:
        built = build_test_services(clock_mode="manual", seed=0, output_dir=tmp_path)
        checker = create(built)
        failures: list[str] = []
        for case in cases(seed=0):
            report = await built.kernel.simulator.run(
                case,
                providers={"feature": checker, "services": built},
                clock_mode="manual",
            )
            if report.failures:
                failures.append(f"{case.case_id}: {report.cases[0]['failures']}")
            assert report.live_call_count == 0
        assert failures == []
        assert built.adapters.devices.calls == []

    asyncio.run(body())
