"""RSSI homing selects one safe candidate or stops, and never emits a dog command."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g22.assemble import assemble
from patrol.ground.extensions.g22.implementation import create
from patrol.ground.extensions.g22.policy import DISPATCH_EVENT, DISPATCH_PHASE, SLOT
from patrol.ground.extensions.g22.scenarios import cases
from patrol.ground.kernel.contracts import FeatureRequest, FeatureResult, Ticket
from patrol.ground.kernel.loader import discover
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def test_manifest_declares_the_v2_slot() -> None:
    path = repo_root() / "patrol" / "ground" / "extensions" / "g22" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ground-task-v2"
    assert manifest["slot"] == SLOT
    assert manifest["task_id"] == "GROUND-22"


def test_gate_c_admits_owned_v2_manifest() -> None:

    found = discover(repo_root() / "patrol" / "ground" / "extensions", only_task="22")
    assert len(found) == 1
    assert found[0].schema_version == "ground-task-v2"
    assert found[0].task_id == "GROUND-22"
    assert found[0].slot == "feature.v2_rssi_homing"


def test_example_forward_candidate_is_selected(tmp_path: Path) -> None:
    result = _run(tmp_path, "select_forward")
    assert result.status == "ok"
    assert result.data["detail"] == "select:candidate-forward-01"
    event = result.events[0].payload
    assert event["candidate_id"] == "candidate-forward-01"
    assert event["event"] == DISPATCH_EVENT
    assert event["phase"] == DISPATCH_PHASE
    assert event["beacon_epoch"] == 3
    assert event["map_epoch"] == 1
    assert "rssi-0" in event["sample_ids"]
    assert "rssi-5" in event["sample_ids"]
    _assert_no_motion_fields(event)
    example = _example("dog-navigation-candidates.json")
    payload = example["payload"]
    assert isinstance(payload, dict)
    rows = payload["candidates"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    assert rows[0]["candidate_id"] == event["candidate_id"]


def test_stops_do_not_invent_a_step_or_a_range(tmp_path: Path) -> None:
    expectations = {
        "empty_candidates": "stop:no_safe_candidate",
        "quality_noisy": "stop:noisy",
        "quality_stale": "stop:stale",
        "quality_unavailable": "stop:unavailable",
        "motion_denied": "stop:motion_not_allowed",
        "beacon_moving": "stop:beacon_not_stable",
        "beacon_epoch": "stop:beacon_epoch_mismatch",
        "budget_exhausted": "stop:budget_exhausted",
        "planner_blocked": "stop:planner_blocked",
        "strong_no_candidate": "stop:no_safe_candidate",
        "flat_trend": "stop:flat_trend",
        "unaligned_candidate": "stop:no_aligned_candidate",
        "range_field_rejected": "stop:no_safe_candidate",
        "expired_candidate": "stop:no_safe_candidate",
        "no_spatial_gradient": "stop:no_spatial_gradient",
        "bssid_mismatch": "stop:bssid_mismatch",
        "map_epoch": "stop:map_epoch_mismatch",
    }
    for name, detail in expectations.items():
        result = _run(tmp_path / name, name)
        assert result.data["detail"] == detail, name
        assert result.events[0].payload["candidate_id"] is None
        assert "event" not in result.events[0].payload
        _assert_no_motion_fields(result.events[0].payload)


def test_single_window_holds_and_hysteresis_does_not_flip(tmp_path: Path) -> None:
    held = _run(tmp_path / "one", "single_window")
    assert held.data["detail"] == "hold:single_window"
    assert held.events[0].payload["candidate_id"] is None
    sticky = _run(tmp_path / "hyst", "hysteresis_hold")
    assert sticky.data["detail"] == "hold:hysteresis"
    assert sticky.events[0].payload["candidate_id"] is None
    assert "candidate-forward-01" not in sticky.data["trace"][2]


def test_active_command_blocks_a_second_selection(tmp_path: Path) -> None:
    result = _run(tmp_path, "active_command")
    assert result.data["detail"] == "stop:command_active"
    assert result.events[0].payload["command_id"] == "dog-cmd-001"
    assert result.events[0].payload["candidate_id"] is None


def test_dog_vision_handoff_skips_another_rssi_step(tmp_path: Path) -> None:
    result = _run(tmp_path, "handoff_vision")
    assert result.data["detail"] == "handoff:dog_vision"
    assert result.events[0].payload["candidate_id"] is None
    assert "event" not in result.events[0].payload
    ambiguous = _run(tmp_path / "two", "vision_ambiguous")
    assert ambiguous.data["detail"] == "review:vision_ambiguous"


def test_reverse_gradient_selects_only_the_aligned_id(tmp_path: Path) -> None:
    result = _run(tmp_path, "select_reverse")
    assert result.data["detail"] == "select:candidate-back"
    assert result.events[0].payload["candidate_id"] == "candidate-back"


def test_equal_alignment_breaks_ties_by_candidate_id(tmp_path: Path) -> None:
    homing = assemble({"plan": "improving_forward", "candidates": "tie"})
    result = _run(tmp_path, "ignored", homing=homing)
    assert result.events[0].payload["candidate_id"] == "candidate-a"


def test_invalid_motion_and_sentinel_do_not_select(tmp_path: Path) -> None:
    text = _run(tmp_path / "text", "string_motion")
    assert text.status == "failed"
    assert text.error is not None
    assert text.error.code == "invalid_input"
    assert text.events == ()
    sentinel = _run(tmp_path / "zero", "sentinel_rejected")
    assert sentinel.status == "failed"
    assert sentinel.error is not None
    assert sentinel.error.detail == "rssi median 0 is not a no-signal value"


def test_cancel_and_stale_ticket_cannot_select(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(output_dir=tmp_path)
        feature = create(services)
        ticket = services.kernel.authority.issue("demo-20261104-001", "homing")
        services.kernel.authority.latch_cancel("operator halt")
        cancelled = await feature.execute(_request("select_forward", ticket=ticket))
        assert cancelled.status == "blocked"
        assert cancelled.error is not None
        assert cancelled.error.code == "cancelled"
        assert cancelled.events == ()
        services.kernel.authority.reset_generation("recovered")
        stale = await feature.execute(_request("select_forward", ticket=ticket))
        assert stale.status == "failed"
        assert stale.error is not None
        assert stale.error.code == "stale_ticket"

    asyncio.run(body())


def test_provider_does_not_call_devices(tmp_path: Path) -> None:
    services = build_test_services(output_dir=tmp_path)

    async def body() -> None:
        feature = create(services)
        await feature.execute(_request("select_forward"))
        await feature.execute(_request("planner_blocked"))

    asyncio.run(body())
    devices = getattr(services.adapters, "devices", None)
    assert getattr(devices, "calls", []) == []


def test_kernel_simulator_covers_every_case(tmp_path: Path) -> None:
    async def body() -> None:
        for case in cases(seed=0):
            services = build_test_services(output_dir=tmp_path / case.case_id, seed=0)
            feature = create(services)
            report = await services.kernel.simulator.run(
                case,
                providers={"feature": feature, "services": services},
                clock_mode="manual",
            )
            assert report.failures == (), report.cases
            assert report.live_call_count == 0

    asyncio.run(body())


def test_dispatched_example_fields_match_the_copied_log() -> None:
    example = _example("event-dog_dispatched.json")
    payload = example["payload"]
    assert isinstance(payload, dict)
    assert payload["event"] == DISPATCH_EVENT
    assert payload["phase"] == DISPATCH_PHASE
    window = _example("pi-rssi-window.json")
    assert window["kind"] == "rssi.window"
    assert window["source"] == "pi"


def _run(
    directory: Path,
    name: str,
    *,
    homing: Mapping[str, object] | None = None,
) -> FeatureResult:
    async def body() -> FeatureResult:
        services = build_test_services(output_dir=directory)
        feature = create(services)
        payload: dict[str, object] = {"seed": 0}
        if homing is not None:
            payload["homing"] = dict(homing)
        request = FeatureRequest("diagnostic", name, None, payload)
        return await feature.execute(request)

    return asyncio.run(body())


def _request(name: str, ticket: Ticket | None = None) -> FeatureRequest:
    return FeatureRequest("diagnostic", name, ticket, {"seed": 0})


def _example(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g22" / "examples" / name
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _assert_no_motion_fields(payload: Mapping[str, object]) -> None:
    keys = _keys(payload)
    assert "range_m" not in keys
    assert "target_range_m" not in keys
    assert "distance_m" not in keys
    assert "dog.command" not in keys
    assert "heading_deg" not in keys


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.add(str(key))
            found.update(_keys(item))
    elif isinstance(value, tuple):
        for item in value:
            found.update(_keys(item))
    return found
