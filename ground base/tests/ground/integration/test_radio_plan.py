"""The laptop has one Wi-Fi radio. These tests lock the routes that follow from that."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from patrol.ground.demo import run_demo
from patrol.ground.dog_link import dog_backend_root, segment_from_command
from patrol.ground.radio import (
    GROUND_AP,
    TELLO_AP,
    LinkError,
    Relay,
    check,
    ethernet_now,
    exchange,
    pi4,
)


def test_ethernet_now_leaves_the_laptop_wifi_unused() -> None:
    plan = ethernet_now()
    assert plan["laptop_wifi"] == []
    assert plan["dog"]["radio"] == "laptop-ethernet"
    assert plan["dog"]["address"] == "192.168.123.161"
    assert plan["drone"]["live"] is False


def test_pi4_uses_the_one_laptop_radio_for_both_robots() -> None:
    plan = pi4()
    assert plan["laptop_wifi"] == [{"radio": "laptop-wifi", "network": GROUND_AP}]
    assert plan["dog"]["radio"] == "pi-ethernet"
    assert plan["drone"]["radio"] == "simulated-script"
    assert plan["drone"]["live"] is False
    assert plan["pi"]["board"] == "raspberry-pi-4"
    assert plan["pi"]["wlan1"] == TELLO_AP


def test_a_second_laptop_association_is_refused() -> None:
    plan = ethernet_now()
    plan["laptop_wifi"] = [
        {"radio": "laptop-wifi", "network": GROUND_AP},
        {"radio": "laptop-wifi", "network": TELLO_AP},
    ]
    with pytest.raises(LinkError, match="one Wi-Fi radio"):
        check(plan)


def test_the_laptop_is_not_the_tello_client() -> None:
    plan = pi4()
    plan["laptop_wifi"] = [{"radio": "laptop-wifi", "network": TELLO_AP}]
    with pytest.raises(LinkError, match="must not join the Tello"):
        check(plan)


def test_move_local_is_the_only_dog_segment() -> None:
    command = {
        "payload": {
            "action": "move_local",
            "command_id": "cmd-dog-001",
            "motion": {
                "linear_x_m_s": 0.1,
                "linear_y_m_s": 0.0,
                "angular_z_rad_s": 0.0,
                "duration_ms": 300,
            },
        }
    }
    assert segment_from_command(command) == {
        "vx": 0.1,
        "vy": 0.0,
        "vyaw": 0.0,
        "duration_s": 0.3,
        "command_id": "cmd-dog-001",
    }
    command["payload"]["action"] = "run_route"
    with pytest.raises(LinkError, match="move_local"):
        segment_from_command(command)


def test_one_pi_session_carries_the_dog_and_the_scripted_drone() -> None:
    async def scenario() -> None:
        relay = Relay()
        await relay.start()
        try:
            replies = await exchange(
                relay.port,
                [
                    {"channel": "dog", "body": {"command_id": "cmd-dog-001", "vx": 0.1}},
                    {"channel": "drone", "body": {"script": "drone-observation.json"}},
                ],
            )
        finally:
            await relay.close()
        assert relay.clients == 1
        assert [row["channel"] for row in replies] == ["dog", "drone"]
        assert replies[0]["path"][-1] == "192.168.123.161"
        assert replies[0]["live_radio"] == "ethernet"
        assert replies[1]["simulated"] is True
        assert replies[1]["live"] is False
        assert relay.drone_messages == [{"script": "drone-observation.json"}]

    asyncio.run(scenario())


class _Link:
    def __init__(self, armed: bool, sent: bool) -> None:
        self.armed = armed
        self.sent = sent
        self.commands: list[object] = []

    async def connect(self) -> dict[str, bool]:
        return {"ok": True}

    async def execute(self, command: dict[str, object]) -> dict[str, object]:
        self.commands.append(command)
        return {"sent": self.sent, "detail": "recorded"}

    async def close(self) -> None:
        return None


def test_happy_path_sends_the_approved_dog_step(tmp_path: Path) -> None:
    link = _Link(armed=True, sent=True)
    report = asyncio.run(
        run_demo(tmp_path / "run", dog_link=link, radio=ethernet_now())
    )
    assert report["outcome"] == "completed"
    assert report["radio"]["profile"] == "ethernet-now"
    assert report["dog_ethernet"]["sent"] is True
    assert len(link.commands) == 1
    assert link.commands[0]["payload"]["action"] == "move_local"


def test_armed_dog_that_does_not_move_stops_the_rehearsal(tmp_path: Path) -> None:
    link = _Link(armed=True, sent=False)
    report = asyncio.run(run_demo(tmp_path / "run", dog_link=link))
    assert report["outcome"] == "unresolved"
    assert report["dog_ethernet"]["sent"] is False
    assert len(link.commands) == 1


def test_fake_bridge_moves_the_simulated_dog(tmp_path: Path) -> None:
    pytest.importorskip("numpy")
    root = dog_backend_root()
    bridge = root / "patrol" / "dog" / "ground_bridge.py"
    if not bridge.is_file():
        pytest.skip("dog backend is not beside this checkout")

    async def scenario() -> dict[str, object]:
        from patrol.ground.dog_link import EthernetDogLink

        link = EthernetDogLink(tmp_path / "dog", armed=True, fake=True)
        try:
            ready = await link.connect()
            assert ready["status"]["connected"] is True
            result = await link.execute(
                {
                    "payload": {
                        "action": "move_local",
                        "command_id": "cmd-dog-001",
                        "motion": {
                            "linear_x_m_s": 0.1,
                            "linear_y_m_s": 0.0,
                            "angular_z_rad_s": 0.0,
                            "duration_ms": 300,
                        },
                    }
                }
            )
        finally:
            await link.close()
        return result

    result = asyncio.run(scenario())
    assert result["sent"] is True
    assert result["stopped"] is True
