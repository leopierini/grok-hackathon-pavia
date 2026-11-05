from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from patrol.ground.operator.host import Host


def _run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def test_ethernet_start_does_not_open_webrtc_when_the_dog_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "patrol.ground.operator.host.probe_dog_ethernet",
        lambda timeout=2.0: {
            "reachable": False,
            "dog": "192.168.123.161",
            "port": 8081,
            "detail": "down",
        },
    )

    async def scenario() -> None:
        host = Host(tmp_path)
        assert (await host.act("arm", {"session_epoch": 1}, None))["ok"] is True
        started = await host.act(
            "start",
            {"session_epoch": 1, "scenario": "happy_path", "pace_s": 0, "seed": 0, "dog": "ethernet"},
            None,
        )
        assert started["ok"] is False
        assert started["error"]["code"] == "dog_unreachable"
        assert host.worker is None

    _run(scenario())


def test_direction_buttons_move_the_simulated_dog_one_step_each_way(tmp_path: Path) -> None:
    pytest.importorskip("numpy")

    async def scenario() -> None:
        host = Host(tmp_path)
        assert (await host.act("arm", {"session_epoch": 1}, None))["ok"] is True
        started = await host.act(
            "dog_test",
            {"session_epoch": 1, "dog": "sim"},
            None,
        )
        assert started["ok"] is True
        assert host.worker is not None
        await host.worker
        steps = host.dog_motion["steps"] if host.dog_motion else []
        assert [step["segment"]["command_id"] for step in steps] == [
            "dog-test-forward",
            "dog-test-back",
            "dog-test-right",
            "dog-test-left",
        ]
        assert all(step["sent"] is True and step["stopped"] is True for step in steps)

    _run(scenario())


def test_simulated_dog_body_receives_the_approved_step(tmp_path: Path) -> None:
    pytest.importorskip("numpy")

    async def scenario() -> None:
        host = Host(tmp_path)
        host.config["pace_s"] = 0
        assert (await host.act("arm", {"session_epoch": 1}, None))["ok"] is True
        started = await host.act(
            "start",
            {"session_epoch": 1, "scenario": "happy_path", "pace_s": 0, "seed": 0, "dog": "sim"},
            None,
        )
        assert started["ok"] is True
        assert host.worker is not None
        await host.worker
        assert host.dog_motion is not None
        assert host.dog_motion.get("sent") is True

    _run(scenario())


def test_duplicate_start_and_reload_do_not_open_a_second_worker(tmp_path: Path) -> None:
    async def scenario() -> None:
        host = Host(tmp_path)
        host.config["pace_s"] = 0
        assert (await host.act("status", {}, None))["ok"] is True
        assert host.worker is None
        armed = await host.act("arm", {"session_epoch": 1}, "arm-1")
        assert armed["ok"] is True
        again = await host.act("arm", {"session_epoch": 1}, "arm-1")
        assert again == armed
        stale = await host.act("start", {"session_epoch": 0, "scenario": "happy_path", "pace_s": 0}, None)
        assert stale["ok"] is False
        started = await host.act(
            "start",
            {"session_epoch": 1, "scenario": "stale_frame", "pace_s": 0, "seed": 0},
            "start-1",
        )
        assert started["ok"] is True
        second = await host.act(
            "start",
            {"session_epoch": 1, "scenario": "happy_path", "pace_s": 0},
            "start-2",
        )
        assert second["ok"] is False
        assert host.worker is not None
        await host.worker

    _run(scenario())


def test_halt_during_slow_model_does_not_clear_recovery(tmp_path: Path) -> None:
    async def scenario() -> None:
        host = Host(tmp_path)
        assert (await host.act("arm", {"session_epoch": 1}, None))["ok"] is True
        start = await host.act(
            "start",
            {"session_epoch": 1, "scenario": "slow_grok", "pace_s": 0, "seed": 1},
            None,
        )
        assert start["ok"] is True
        for _ in range(50):
            if host.demo is not None and host.demo.waiting_for_model:
                break
            await asyncio.sleep(0.05)
        assert host.demo is not None and host.demo.waiting_for_model is True
        halted = await host.act("halt", {}, "halt-1")
        assert halted["ok"] is True
        assert halted["snapshot"]["mission"]["halt_accepted"] is True
        assert halted["snapshot"]["mission"]["halt_delivered"] is not True
        assert host.worker is not None
        await host.worker
        assert host.phase == "ABORTED"
        assert host.landing_verified is False
        assert host.recovery_required is True
        assert any(note.get("kind") == "late_model" for note in host.notes)

    _run(scenario())


def test_unknown_landing_reset_keeps_the_run_record(tmp_path: Path) -> None:
    async def scenario() -> None:
        host = Host(tmp_path)
        assert (await host.act("arm", {"session_epoch": 1}, None))["ok"] is True
        started = await host.act(
            "start",
            {"session_epoch": 1, "scenario": "unknown_landing", "pace_s": 0, "seed": 0},
            None,
        )
        assert started["ok"] is True
        assert host.worker is not None
        await host.worker
        assert host.goal_reached is True
        assert host.landing_verified is False
        assert host.phase == "FAULT"
        denied = await host.act("reset", {"session_epoch": host.session_epoch}, None)
        assert denied["ok"] is False
        reset = await host.act(
            "reset",
            {"session_epoch": host.session_epoch, "recovery_token": "operator-recovered"},
            None,
        )
        assert reset["ok"] is True
        assert host.phase == "IDLE"
        assert host.armed is False
        assert host.goal_reached is False
        assert host.runs[0]["goal_reached"] is True
        assert host.runs[0]["landing_verified"] is False

    _run(scenario())


def test_simulated_view_serves_a_camera_frame_and_lidar(tmp_path: Path) -> None:
    async def scenario() -> None:
        host = Host(tmp_path)
        opened = await host.act("dog_view", {"session_epoch": 1, "open": True, "dog": "sim"}, None)
        assert opened["ok"] is True
        assert host.view_task is not None
        for _ in range(50):
            if host.dog_view_ready:
                break
            await asyncio.sleep(0.1)
        assert host.dog_view_ready is True
        jpeg = await host.dog_frame_jpeg()
        assert jpeg is not None and jpeg.startswith(b"\xff\xd8")
        lidar = await host.dog_lidar_view()
        assert lidar is not None and lidar["ok"] is True
        assert lidar["view"]["n"] > 0
        closed = await host.act("dog_view", {"session_epoch": 1, "open": False}, None)
        assert closed["ok"] is True
        assert host.view_task is not None
        await host.view_task
        assert host.dog_link is None
        assert host.dog_view is False

    _run(scenario())


def test_live_mode_refuses_start_without_a_fake_fallback(tmp_path: Path) -> None:
    async def scenario() -> None:
        host = Host(tmp_path)
        switched = await host.set_mode("live")
        assert switched["ok"] is True
        assert "refused" in switched["detail"] or host.snapshot["live_blockers"]
        armed = await host.act("arm", {"session_epoch": host.session_epoch}, None)
        assert armed["ok"] is False
        assert host.worker is None
        assert not any(tmp_path.iterdir())

    _run(scenario())


def test_happy_path_separates_goal_landing_and_ack_lifecycle(tmp_path: Path) -> None:
    async def scenario() -> None:
        host = Host(tmp_path)
        assert (await host.act("arm", {"session_epoch": 1}, None))["ok"] is True
        started = await host.act(
            "start",
            {"session_epoch": 1, "scenario": "happy_path", "pace_s": 0, "seed": 0},
            None,
        )
        assert started["ok"] is True
        assert host.worker is not None
        await host.worker
        assert host.phase == "DONE"
        assert host.goal_reached is True
        assert host.landing_verified is True
        assert host.live_call_count == 0
        assert host.snapshot["kernel"]["protocol_v2"] == "2.0-draft"
        assert host.snapshot["kernel"]["log_schema_status"] == "proposed_pending_team"
        assert host.snapshot["navigation"]["map_renderable"] is False
        completed = [row for row in host.snapshot["commands"] if row["lifecycle"] == "completed"]
        assert completed
        assert any(ack["state"] == "accepted" for row in completed for ack in row["acks"])
        assert host.writer_state in {"flushed", "published"}

    _run(scenario())
