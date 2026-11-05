"""Live mission workflow on in-process fakes: no socket, no robot, no key."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from patrol.ground.live.grok import ScriptedGrok
from patrol.ground.live.mission import LiveMission, Settings, run_until

JPEG = b"\xff\xd8fakejpeg\xff\xd9"


class FakeDrone:
    def __init__(self, airborne: bool = True) -> None:
        self.cmds: list[str] = []
        self.nudges: list[float] = []
        self.pulses: list[tuple[float, float]] = []
        self.yaw = 0.0
        self.state_name = "airborne" if airborne else "grounded"
        self.down = False

    async def state(self) -> dict[str, Any]:
        if self.down:
            raise OSError("unreachable")
        return {"state": self.state_name, "battery": 80, "yaw": self.yaw, "h": 120, "video": "ok"}

    async def frame(self) -> bytes | None:
        return None if self.down else JPEG

    async def cmd(self, action: str) -> dict[str, Any]:
        self.cmds.append(action)
        if action == "land":
            self.state_name = "landing"
        if action == "takeoff":
            self.state_name = "airborne"
        return {"ok": True}

    async def stick_pulse(self, *, fb: float = 0.0, lr: float = 0.0, yaw: float = 0.0, seconds: float) -> None:
        assert all(abs(v) <= 1.0 for v in (fb, lr, yaw)) and seconds <= 2.0
        self.pulses.append((fb, yaw))
        if yaw:
            await self.yaw_nudge(yaw, seconds)

    async def yaw_nudge(self, axis: float, seconds: float) -> None:
        assert abs(axis) <= 1.0 and seconds <= 2.0
        self.nudges.append(axis)
        self.yaw += 10 if axis > 0 else -10


class FakeDog:
    def __init__(self) -> None:
        self.ops: list[str] = []
        self.said: list[str] = []
        self.steps: list[dict[str, Any]] = []

    async def connect(self) -> dict[str, Any]:
        return {"ok": True, "armed": True, "status": {"connected": True, "standing": False}}

    async def request(self, op: str, timeout: float = 30, **fields: Any) -> dict[str, Any]:
        self.ops.append(op)
        if op == "say":
            self.said.append(fields["text"])
        return {"op": op, "ok": True, "sent": True, "status": {"standing": op == "stand"}}

    async def frame(self) -> dict[str, Any]:
        return {"ok": True, "jpeg": JPEG}

    async def lidar(self) -> dict[str, Any]:
        return {"ok": True, "view": {}}  # no LiDAR verdict: box size decides the standoff

    async def halt(self) -> dict[str, Any]:
        self.ops.append("halt")
        return {"op": "halt", "ok": True, "sent": True}

    async def move_segment(self, segment: Any) -> dict[str, Any]:
        self.steps.append(dict(segment))
        return {"ok": True, "sent": True, "detail": "moved"}

    async def close(self) -> None:
        self.ops.append("close")


class BrokenGrok(ScriptedGrok):
    name = "broken"

    def assess(self, jpeg: bytes, camera: str) -> dict[str, Any]:
        raise RuntimeError("xAI unavailable")

    def alert(self, observations: list[Any]) -> dict[str, str]:
        raise RuntimeError("xAI unavailable")


FAST = dict(stroke_s=0.01, scan_nudge_s=0.01, track_nudge_s=0.01, drone_vision_period_s=0.05, dog_vision_period_s=0.05, drone_poll_s=0.02,
            speak_cooldown_s=0.0, drone_lost_after=3, scan_period_s=0.05, allow_takeoff=True)


def _mission(tmp_path: Path, drone: FakeDrone, dog: FakeDog | None, grok: Any = None, **kw: Any) -> LiveMission:
    return LiveMission(drone=drone, dog=dog, grok=grok or ScriptedGrok(empty_drone=2, empty_dog=1),
                       run_dir=tmp_path / "run", settings=Settings(**{**FAST, **kw}))


def _kinds(m: LiveMission) -> list[str]:
    return [e["kind"] for e in m.events]


def test_one_start_runs_the_whole_demo_by_itself(tmp_path: Path) -> None:
    async def scenario() -> tuple[LiveMission, FakeDrone, FakeDog]:
        drone, dog = FakeDrone(airborne=False), FakeDog()
        m = _mission(tmp_path, drone, dog)
        await m.connect()
        assert m.phase == "standby"
        assert (await m.start())["ok"] is True
        assert await run_until(m, lambda: m.phase == "done", 10), _kinds(m)
        await m.close()
        return m, drone, dog

    m, drone, dog = asyncio.run(scenario())
    kinds = _kinds(m)
    order = ["drone_target_acquired", "dog_alert", "alert", "dog_voice", "dog_target_acquired",
             "dog_arrived", "person_left", "dog_rest", "report"]
    idx = [kinds.index(k) for k in order]
    assert idx == sorted(idx), list(zip(order, idx))
    assert drone.cmds[0] == "takeoff" and drone.cmds[1] == "hover" and drone.cmds[-1] == "land"
    assert "scan_nudge" in kinds  # patrol moved before the person appeared
    fbs = [fb for fb, _ in drone.pulses if fb]
    assert fbs and fbs[0] > 0 and sum(1 for f in fbs if f > 0) - sum(1 for f in fbs if f < 0) in (0, 1)
    assert "stand" in dog.ops and "halt" in dog.ops  # alert, then soft lie-down at the end
    assert "Search turn" in next(e["detail"] for e in m.events if e["kind"] == "dog_move")  # dog cam empty first
    first_seen = next(e["seq"] for e in m.events if e["kind"] == "dog_target_acquired")
    chase = [e["data"]["segment"] for e in m.events if e["kind"] == "dog_move" and e["seq"] > first_seen]
    turns = [s for s in chase if s["vyaw"] != 0]
    walks = [s for s in dog.steps if s["vx"] > 0]
    assert turns and turns[0]["vyaw"] < 0  # person on the right: turned right first
    assert walks and all(s["vx"] <= 0.3 and s["duration_s"] <= 1.0 for s in walks)
    assert m.incident is not None and m.incident["dog_arrived_at"] is not None
    after = [e for e in m.events if e["seq"] > next(e["seq"] for e in m.events if e["kind"] == "drone_target_acquired")]
    assert {e["incident_id"] for e in after} == {m.incident["id"]}
    lines = (tmp_path / "run" / "events.jsonl").read_text().splitlines()
    assert len(lines) == m.seq
    summary = json.loads((tmp_path / "run" / "summary.json").read_text())
    assert summary["dog_confirmed"] is True and summary["reason"] == "The person left the area."
    assert len(dog.said) >= 3  # warning, "I can see you", standoff warning (+ clear)


def test_time_limit_ends_the_demo(tmp_path: Path) -> None:
    async def scenario() -> tuple[LiveMission, FakeDrone, FakeDog]:
        drone, dog = FakeDrone(), FakeDog()
        m = _mission(tmp_path, drone, dog, ScriptedGrok(empty_drone=10_000), max_duration_s=0.5)
        await m.connect()
        await m.start()
        assert await run_until(m, lambda: m.phase == "done", 5)
        await m.close()
        return m, drone, dog

    m, drone, dog = asyncio.run(scenario())
    assert drone.cmds[-1] == "land" and "halt" in dog.ops and dog.steps == []


def test_forward_step_needs_lidar_clearance(tmp_path: Path) -> None:
    class Blocked(FakeDog):
        async def lidar(self) -> dict[str, Any]:
            return {"ok": True, "view": {"stale": False, "clear": {"m": [0.6] * 24}}}

    async def scenario() -> tuple[LiveMission, Blocked]:
        dog = Blocked()
        m = _mission(tmp_path, FakeDrone(), dog, arrive_clear_m=0.5, min_clear_m=0.8)
        await m.connect()
        await m.start()
        assert await run_until(m, lambda: "dog_blocked" in _kinds(m), 5)
        await m.halt()
        await m.close()
        return m, dog

    m, dog = asyncio.run(scenario())
    assert [s for s in dog.steps if s["vx"] > 0] == []


def test_single_frame_does_not_trigger_detection(tmp_path: Path) -> None:
    class Flicker(ScriptedGrok):
        def assess(self, jpeg: bytes, camera: str) -> dict[str, Any]:
            n = self.calls[camera] = self.calls.get(camera, 0) + 1
            state = "person_visible" if n % 2 else "not_visible"
            return {"camera": camera, "target_state": state, "confidence": 0.9,
                    "box_xyxy_norm": [0.4, 0.2, 0.6, 0.8], "reason": "x", "latency_ms": 1}

    async def scenario() -> LiveMission:
        m = _mission(tmp_path, FakeDrone(), FakeDog(), Flicker())
        await m.connect()
        await m.start()
        await asyncio.sleep(0.6)
        await m.close()
        return m

    m = asyncio.run(scenario())
    assert m.phase == "patrol" and m.incident is None


def test_halt_is_immediate_and_latches(tmp_path: Path) -> None:
    async def scenario() -> tuple[LiveMission, FakeDrone, FakeDog]:
        drone, dog = FakeDrone(), FakeDog()
        m = _mission(tmp_path, drone, dog)
        await m.connect()
        await m.start()
        await run_until(m, lambda: m.phase in {"approach", "engaged"}, 5)
        await m.halt()
        again = await m.start()
        step = await m.dog_step("forward")
        await m.close()
        assert again["ok"] is False and step["ok"] is False
        return m, drone, dog

    m, drone, dog = asyncio.run(scenario())
    assert m.phase == "halted" and "land" in drone.cmds and "halt" in dog.ops


def test_grok_failure_never_detects_and_never_moves(tmp_path: Path) -> None:
    async def scenario() -> tuple[LiveMission, FakeDrone, FakeDog]:
        drone, dog = FakeDrone(), FakeDog()
        m = _mission(tmp_path, drone, dog, BrokenGrok())
        await m.connect()
        await m.start()
        await asyncio.sleep(0.4)
        await m.close()
        return m, drone, dog

    m, drone, dog = asyncio.run(scenario())
    assert m.phase == "patrol" and m.grok_state["errors"] > 0
    assert "hover" not in drone.cmds and "stand" not in dog.ops and dog.steps == []


def test_drone_link_loss_stops_the_dog(tmp_path: Path) -> None:
    async def scenario() -> tuple[LiveMission, FakeDog]:
        drone, dog = FakeDrone(), FakeDog()
        m = _mission(tmp_path, drone, dog)
        await m.connect()
        await m.start()
        await run_until(m, lambda: m.phase in {"approach", "engaged"}, 5)
        drone.down = True
        assert await run_until(m, lambda: "drone_link_lost" in _kinds(m), 3)
        await asyncio.sleep(0.1)
        await m.close()
        return m, dog

    m, dog = asyncio.run(scenario())
    assert "stop" in dog.ops


def test_tracking_respects_yaw_budget_and_grounded_drone(tmp_path: Path) -> None:
    async def scenario() -> tuple[LiveMission, FakeDrone]:
        drone = FakeDrone(airborne=False)
        m = _mission(tmp_path, drone, FakeDog(), track_budget_deg=20, allow_takeoff=False)
        await m.connect()
        await m.start()
        await run_until(m, lambda: m.phase in {"approach", "engaged"}, 5)
        drone.state_name = "airborne"
        await run_until(m, lambda: "track_budget" in _kinds(m), 5)
        await m.close()
        return m, drone

    m, drone = asyncio.run(scenario())
    assert "track_budget" in _kinds(m)
    assert len(drone.nudges) <= 3


def test_operator_dog_step_is_bounded(tmp_path: Path) -> None:
    async def scenario() -> FakeDog:
        dog = FakeDog()
        m = _mission(tmp_path, FakeDrone(), dog)
        await m.connect()
        assert (await m.dog_step("sideways"))["ok"] is False
        await m.dog_step("forward")
        await m.close()
        return dog

    dog = asyncio.run(scenario())
    assert dog.steps == [{"vx": 0.3, "vy": 0.0, "vyaw": 0.0, "duration_s": 1.0}]


@pytest.mark.parametrize("payload", [b"not json", b'{"choices":[]}'])
def test_live_assess_rejects_bad_replies(payload: bytes) -> None:
    from patrol.ground.signal.errors import SignalError
    from patrol.ground.signal.live import assess_live

    def transport(url: str, body: bytes, headers: Any, timeout: float) -> tuple[int, bytes]:
        return 200, payload

    with pytest.raises(SignalError):
        assess_live(JPEG, camera="drone", api_key="k", transport=transport)


def test_live_assess_and_alert_parse_and_hide_key() -> None:
    from patrol.ground.signal.live import assess_live, compose_alert

    seen: list[bytes] = []

    def transport(url: str, body: bytes, headers: Any, timeout: float) -> tuple[int, bytes]:
        seen.append(body)
        text = json.loads(body)["messages"][1]["content"]
        if isinstance(text, str):  # alert call
            content = '{"alert": "Person seen by the drone.", "spoken": "Please leave."}'
        else:
            content = ('{"target_state":"person_visible","confidence":0.8,'
                       '"box_xyxy_norm":[0.1,0.1,0.3,0.9],"reason":"A person in red."}')
        return 200, json.dumps({"choices": [{"message": {"content": content}}]}).encode()

    reading = assess_live(JPEG, camera="dog", api_key="secret-key", transport=transport)
    assert reading["target_state"] == "person_visible" and reading["simulated"] is False
    assert reading["box_xyxy_norm"] == [0.1, 0.1, 0.3, 0.9]
    alert = compose_alert([reading], api_key="secret-key", transport=transport)
    assert alert["spoken"] == "Please leave."
    assert "secret-key" not in json.dumps(reading) + json.dumps(alert)
