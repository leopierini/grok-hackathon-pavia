from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from patrol.ground.operator.host import Host
from patrol.ground.operator.mission import OPERATOR_SCENARIOS

EXPECTED = {
    "happy_path": "DONE",
    "unknown_landing": "FAULT",
    "blocked_planner": "HOME",
    "noisy_rssi": "HOME",
    "empty_rssi": "HOME",
    "stale_frame": "SCOUT",
    "uncontrolled_motion": "CONNECT",
    "missing_pi_path": "CONNECT",
    "halt": "ABORTED",
    "link_loss": "FAULT",
    "lease_expiry": "FAULT",
    "slow_grok": "SCOUT",
    "moving_beacon": "HOME",
    "old_beacon_epoch": "HOME",
    "ambiguous_target": "DOG_VISION",
    "rejected_dog_command": "FAULT",
    "missing_proximity": "FAULT",
    "journal_fault": "DONE",
}


@pytest.mark.parametrize("scenario", OPERATOR_SCENARIOS)
def test_scenario_uses_the_operator_runtime(tmp_path: Path, scenario: str) -> None:
    async def run() -> None:
        host = Host(tmp_path)
        assert (await host.act("arm", {"session_epoch": 1}, None))["ok"] is True
        started = await host.act(
            "start",
            {"session_epoch": 1, "scenario": scenario, "pace_s": 0, "seed": 0},
            None,
        )
        assert started["ok"] is True
        assert host.worker is not None
        await host.worker
        assert host.phase == EXPECTED[scenario]
        assert host.live_call_count == 0
        if scenario == "unknown_landing":
            assert host.goal_reached is True
            assert host.landing_verified is False
        if scenario == "missing_proximity":
            assert "no goal" in host.reason
        if scenario == "journal_fault":
            assert host.writer_state == "failed"
            assert host.goal_reached is True
        if scenario == "happy_path":
            assert host.landing_verified is True

    asyncio.run(run())
