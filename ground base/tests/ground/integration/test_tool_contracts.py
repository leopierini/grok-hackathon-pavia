"""Public harness APIs and error paths, including the no-network invariant."""

from __future__ import annotations

import asyncio
import importlib
import json
import socket
from pathlib import Path
from typing import Any

import pytest
from patrol.ground import quality, sim
from patrol.ground.extensions.g24.model import DogAckTracker
from patrol.ground.kernel.contracts import FeatureRequest, IncidentInput
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.testing.builders import build_test_services
from tests.ground.g24.conftest import command, load


@pytest.mark.parametrize("task", ["05", "09", "10", "15"])
def test_unknown_simulation_case_fails_without_calling_a_device(tmp_path: Path, task: str) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        module = importlib.import_module(f"patrol.ground.extensions.g{task}.implementation")
        result = await module.create(services).execute(
            FeatureRequest("diagnostic", "unknown", None, {})
        )
        assert result.status == "failed"
        assert result.error.code == "invalid_input"
        assert services.adapters.devices.calls == []

    asyncio.run(run())


def test_peer_doubles_support_the_full_documented_lifecycle(tmp_path: Path) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        modes = {"dog": "fake", "drone": "fake", "grok": "fake"}
        settings = services.config.load(None, modes=modes, scenario="blocked_resolved")
        assert services.config.redacted(settings)["modes"] == modes
        metadata = services.adapters.devices.reasoner.metadata()
        assert metadata["mode"] == "fake" and metadata["model"] == "scripted"
        admission = await services.workflow.load(
            IncidentInput("synthetic.jpg", "display", "target", None, True)
        )
        assert admission.accepted and admission.incident is not None
        handle = services.workflow.start(admission.incident)
        await services.workflow.join(handle)
        with pytest.raises(GroundFault):
            services.workflow.start(admission.incident)
        safety = services.safety.request("test halt", handle.ticket)
        observed = await services.safety.observe(safety, deadline=1)
        assert observed.halted and observed.recovery_required
        await services.adapters.close()
        assert all(
            name in services.adapters.devices.calls
            for name in ("dog.close", "drone.close", "reasoner.close")
        )

    asyncio.run(run())


def test_socket_guard_blocks_a_patrol_socket_before_construction() -> None:
    guard = sim._SocketGuard()
    guard.install()
    try:
        probe = compile("socket.socket()", "/patrol/ground/synthetic_socket_probe.py", "exec")
        with pytest.raises(RuntimeError, match="simulation opened a socket"):
            exec(probe, {"socket": socket})
        assert guard.count == 1
    finally:
        guard.close()


def test_simulation_and_quality_entrypoints_produce_verifiable_results(tmp_path: Path) -> None:
    report = tmp_path / "simulation.json"
    assert sim.main(["--task", "31", "--seed", "7", "--report", str(report)]) == 0
    value = json.loads(report.read_text())
    assert value["live_call_count"] == 0 and value["failures"] == []
    assert quality.main(["--task", "31"]) == 0
    assert quality.owned_python("01")
    bad = tmp_path / "banned.py"
    bad.write_text("import djitellopy\n", encoding="utf-8")
    assert quality.import_boundary([str(bad)], "31") is True
    assert quality.main(["--task", "wrong"]) == 1


def test_faulted_ack_replays_and_timeouts_keep_the_fault_latched() -> None:
    tracker = DogAckTracker(lambda: 0)
    issued = command()
    completed = load("dog-ack-completed.json")
    assert tracker.track(issued, completed, None).status == "ok"
    failed: Any = load("dog-ack-completed.json")
    failed["message_id"] = "conflicting-terminal"
    failed["seq"] += 1
    failed["payload"]["state"] = "failed"
    first = tracker.track(issued, failed, None)
    assert first.status == "failed" and first.data["block_next_step"] is True
    for result in (tracker.track(issued, failed, None), tracker.timeout(issued, None)):
        assert result.status == "failed"
        assert result.data["faulted"] is True
        assert result.data["active_command"] is True


def test_proximity_does_not_substitute_one_3d_distance_for_separate_metrics(tmp_path: Path) -> None:
    from patrol.ground.extensions.g26.implementation import create
    from patrol.ground.kernel.paths import repo_root

    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        fixtures = repo_root() / "fixtures/ground/g26"
        message = json.loads((fixtures / "proximity-evidence.json").read_text())
        profile = json.loads((fixtures / "profile-open.json").read_text())
        payload = {
            "message": message,
            "track_id": "target-001",
            "dog_stopped": True,
            "hold_state": "stable",
            "evaluated_at": "2026-11-04T13:00:11.000Z",
            "profile": profile,
            "distance_3d_m": 1.0,
        }
        result = await create(services).execute(FeatureRequest("stage", "evaluate", None, payload))
        assert result.status == "ok"  # Both separate measurements are still present.
        del message["payload"]["dog"]["range_m"]
        rejected = await create(services).execute(
            FeatureRequest("stage", "evaluate", None, payload)
        )
        assert rejected.status != "ok"
        assert services.adapters.devices.calls == []

    asyncio.run(run())
