from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from patrol.ground.operator.host import Host
from patrol.ground.operator.public_patrol import PatrolBoard, PatrolRejected


def test_start_patrol_holds_the_drone_call_and_does_not_call_the_dog() -> None:
    board = PatrolBoard()
    detail = board.start()
    assert board.phase == "waiting"
    assert "find_drone was not called" in detail
    assert [call["name"] for call in board.calls] == ["start_patrol"]
    assert board.calls[0]["sent"] is False
    assert board.calls[0]["target"] == "drone"


def test_stop_patrol_sends_the_dog_home_and_holds_landing() -> None:
    board = PatrolBoard()
    board.start()
    detail = board.stop()
    assert board.phase == "stopped"
    assert [call["name"] for call in board.calls] == ["start_patrol", "return_home"]
    assert board.land_called is False
    assert "Landing stays closed" in detail


def test_a_safe_verdict_authorizes_land_without_sending_it() -> None:
    board = PatrolBoard()
    board.start()
    board.apply_verdict("safe_to_land", "The AI teammate said the back of the dog is clear.")
    board.stop()
    assert board.land_called is True
    land = board.calls[-1]
    assert land["name"] == "land"
    assert land["sent"] is False
    assert land["target"] == "drone"


def test_an_intruder_report_records_find_drone_without_a_point() -> None:
    board = PatrolBoard()
    board.start()
    board.intruder_reported()
    find = board.calls[-1]
    assert find["name"] == "find_drone"
    assert find["sent"] is False
    assert "point" not in find
    assert board.situation == "intruder_seen"


def test_frames_do_not_change_the_situation() -> None:
    board = PatrolBoard()
    board.record_frame("drone", "artifact://drone/frame-1")
    board.record_frame("dog", "artifact://dog/frame-1")
    assert board.situation == "awaiting_ai"
    assert len(board.frames) == 2


def test_rejected_transitions() -> None:
    board = PatrolBoard()
    with pytest.raises(PatrolRejected):
        board.stop()
    with pytest.raises(PatrolRejected):
        board.intruder_reported()
    board.start()
    with pytest.raises(PatrolRejected):
        board.start()
    with pytest.raises(PatrolRejected):
        board.apply_verdict("safe", "no")
    with pytest.raises(PatrolRejected):
        board.record_frame("phone", "artifact://x")


def test_the_operator_records_patrol_without_opening_the_dog(tmp_path: Path) -> None:
    async def scenario() -> None:
        host = Host(tmp_path)
        started = await host.act("start_patrol", {"session_epoch": 1}, None)
        assert started["ok"] is True
        assert host.dog_link is None
        assert host.patrol.phase == "waiting"
        stopped = await host.act("stop_patrol", {"session_epoch": 1}, None)
        assert stopped["ok"] is True
        assert host.patrol.land_called is False
        names = [call["name"] for call in host.patrol.calls]
        assert names == ["start_patrol", "return_home"]
        assert host.snapshot["patrol"]["phase"] == "stopped"

    asyncio.run(scenario())
