"""Regressions found by connecting independently developed task outputs."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from patrol.ground.extensions.g11.implementation import create as envelope_gate
from patrol.ground.extensions.g16.implementation import SLOT
from patrol.ground.extensions.g16.implementation import create as decision_gate
from patrol.ground.extensions.g17.samples import armed_context
from patrol.ground.extensions.g23.implementation import create as dog_gate
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import FeatureRequest
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services
from tests.ground.g17.support import feature as drone_feature
from tests.ground.g17.support import request as drone_request
from tests.ground.g23.support import move_payload


def load(name: str) -> dict[str, Any]:
    return json.loads((repo_root() / f"contracts/examples/{name}.json").read_text())


def test_cached_drone_approval_cannot_bypass_halt_or_mutate_stored_command(tmp_path: Path) -> None:
    async def run() -> None:
        services, gate = drone_feature(tmp_path)
        context = armed_context()
        original = await gate.execute(drone_request(context))
        assert original.status == "ok"
        expected_lease = original.data["lease_ms"]
        original.data["command"]["payload"]["lease_ms"] = 999999  # type: ignore[index]
        replay = await gate.execute(drone_request(armed_context()))
        assert replay.status == "ok"
        assert replay.data["command"]["payload"]["lease_ms"] == expected_lease  # type: ignore[index]
        services.kernel.authority.latch_cancel("operator halt")
        blocked = await gate.execute(drone_request(armed_context()))
        assert blocked.status != "ok"
        assert blocked.error and blocked.error.code == "cancelled"
        assert services.adapters.devices.calls == []

    asyncio.run(run())


def test_same_dog_selection_cannot_silently_change_its_motion(tmp_path: Path) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        services.kernel.authority.reset_generation("dog approval")
        ticket = services.kernel.authority.issue("demo-20261104-001", "dog")
        gate = dog_gate(services)
        original = await gate.execute(FeatureRequest("command", "approve", ticket, move_payload()))
        assert original.status == "ok"
        changed = move_payload(operator_axis="left")
        second = await gate.execute(FeatureRequest("command", "approve", ticket, changed))
        assert second.status != "ok"
        assert services.adapters.devices.calls == []

    asyncio.run(run())


def test_command_and_all_ack_states_share_a_command_id_without_conflict(tmp_path: Path) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        services.kernel.authority.reset_generation("open command stream")
        gate = envelope_gate(services)
        for name in (
            "ground-to-dog-command",
            "dog-ack-accepted",
            "dog-ack-running",
            "dog-ack-completed",
        ):
            message = load(name)
            result = await gate.execute(
                FeatureRequest(
                    "guard",
                    "v2_envelope",
                    None,
                    {
                        "message": json.dumps(message),
                        "epoch": 1,
                        "expected_source": message["source"],
                        "expected_destination": message["destination"],
                    },
                )
            )
            assert result.status == "ok", result.error
        services.kernel.authority.reset_generation("new session")
        message = load("ground-to-dog-command")
        stale = await gate.execute(
            FeatureRequest(
                "guard",
                "v2_envelope",
                None,
                {
                    "message": json.dumps(message),
                    "epoch": 2,
                    "expected_source": "ground",
                    "expected_destination": "dog",
                },
            )
        )
        assert stale.status == "blocked"
        assert stale.error and stale.error.code == "epoch_mismatch"
        assert services.adapters.devices.calls == []

    asyncio.run(run())


def test_out_of_order_publisher_sequence_is_rejected(tmp_path: Path) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        services.kernel.authority.reset_generation("ordered publisher")
        gate = envelope_gate(services)
        message = load("drone-observation")
        for ident, seq, expected in [("a", 10, "ok"), ("b", 9, "blocked"), ("c", 11, "ok")]:
            message.update(message_id=ident, seq=seq)
            result = await gate.execute(
                FeatureRequest(
                    "guard",
                    "v2_envelope",
                    None,
                    {
                        "message": json.dumps(message),
                        "epoch": 1,
                        "expected_source": "drone",
                        "expected_destination": "ground",
                    },
                )
            )
            assert result.status == expected

    asyncio.run(run())


@pytest.mark.parametrize(
    "condition", ["valid", "expired_on_receipt", "cancelled", "foreign_mission"]
)
def test_stage_decision_checks_authority_and_local_receipt_time(
    tmp_path: Path, condition: str
) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        services.kernel.authority.reset_generation("vision session")
        clock = services.kernel.clock
        assert isinstance(clock, ManualClock)
        start = datetime.fromisoformat("2026-11-04T13:00:10.210+00:00")
        clock.advance((start - clock.utc_now()).total_seconds())
        ticket = services.kernel.authority.issue("demo-20261104-001", "vision")
        request = load("drone-vision-request")
        decision = load("drone-vision-decision")
        if condition == "expired_on_receipt":
            clock = services.kernel.clock
            assert isinstance(clock, ManualClock)
            end = datetime.fromisoformat("2026-11-04T13:00:20+00:00")
            clock.advance((end - clock.utc_now()).total_seconds())
        if condition == "cancelled":
            services.kernel.authority.latch_cancel("halt during model")
        if condition == "foreign_mission":
            request["mission_id"] = "foreign"
        result = await decision_gate(services).execute(
            FeatureRequest(
                "stage",
                SLOT,
                ticket,
                {
                    "decision": decision,
                    "request": request,
                },
            )
        )
        assert result.status == ("ok" if condition == "valid" else "blocked")
        if condition == "valid":
            proposal = result.data["proposal"]
            assert proposal["source"] == "vision"
            assert proposal["destination"] == "ground"
            assert proposal["expires_at"] is not None
            checked = await envelope_gate(services).execute(
                FeatureRequest(
                    "guard",
                    "v2_envelope",
                    None,
                    {
                        "message": json.dumps(proposal),
                        "epoch": 1,
                        "expected_source": "vision",
                        "expected_destination": "ground",
                    },
                )
            )
            assert checked.status == "ok", checked.error
        assert services.adapters.devices.calls == []

    asyncio.run(run())


def test_false_payload_latch_cannot_override_authoritative_dog_halt(tmp_path: Path) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        services.kernel.authority.reset_generation("dog session")
        ticket = services.kernel.authority.issue("demo-20261104-001", "dog")
        services.kernel.authority.latch_cancel("operator halt")
        result = await dog_gate(services).execute(
            FeatureRequest("command", "approve", ticket, move_payload())
        )
        assert result.status == "blocked"
        assert result.data.get("command") is None
        assert services.adapters.devices.calls == []

    asyncio.run(run())
