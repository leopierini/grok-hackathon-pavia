"""Stick landing on a simulated mission pad. No radio."""

import math
import threading
import time
import unittest

from patrol.drone.pad_land import PadLander, stick

CM_PER_STICK_S = 1.6


class PadSim:
    """A drone over a pad. Its forward is `facing_deg` from the pad's +x, and a draft pushes it."""

    def __init__(self, x=6.0, y=-6.0, z=70.0, facing_deg=130.0, draft=(1.5, -1.0)) -> None:
        self.lock = threading.Lock()
        self.x, self.y, self.z = x, y, z
        self.facing = math.radians(facing_deg)
        self.draft = draft
        self.stick = (0, 0, 0)
        self.at = time.monotonic()
        self.sent: list[str] = []
        self.landed_at = None

    def _tick(self) -> None:
        now = time.monotonic()
        dt = now - self.at
        self.at = now
        lr, fb, ud = self.stick
        cos, sin = math.cos(self.facing), math.sin(self.facing)
        vx = (fb * cos - lr * sin) * CM_PER_STICK_S + self.draft[0]
        vy = (fb * sin + lr * cos) * CM_PER_STICK_S + self.draft[1]
        self.x += vx * dt
        self.y += vy * dt
        self.z = max(10.0, self.z + ud * CM_PER_STICK_S * dt)

    def send(self, command: str) -> None:
        with self.lock:
            self._tick()
            self.sent.append(command)
            if command.startswith("rc "):
                lr, fb, ud, _yaw = (int(v) for v in command.split()[1:])
                self.stick = (lr, fb, ud)

    def query(self, command: str, timeout: float = 5) -> str:
        self.send(command)
        if command == "land":
            with self.lock:
                self.landed_at = (self.x, self.y)
        return "ok"

    def snapshot(self) -> dict:
        with self.lock:
            self._tick()
            seen = 20 <= self.z <= 120
            return {
                "mid": 5 if seen else -1,
                "x": int(round(self.x)) if seen else 0,
                "y": int(round(self.y)) if seen else 0,
                "z": int(round(self.z)),
                "at": self.at,
            }


class StickTests(unittest.TestCase):
    def test_small_commands_clear_the_dead_zone_and_big_ones_cap(self) -> None:
        self.assertEqual(stick(0.2), 0)
        self.assertEqual(stick(2.0), 5)
        self.assertEqual(stick(-2.0), -5)
        self.assertEqual(stick(40.0), 15)


class PadLanderTests(unittest.TestCase):
    def test_calibrates_any_facing_then_centers_within_two_cm_against_a_draft(self) -> None:
        for facing in (0.0, 130.0, -100.0):
            with self.subTest(facing=facing):
                sim = PadSim(facing_deg=facing)
                lander = PadLander(sim, wanted=5, say=lambda _text: None)
                self.assertTrue(lander.calibrate())
                note = lander.servo()
                self.assertIn("centered", note)
                self.assertLessEqual(math.hypot(sim.x, sim.y), 2.5)
                self.assertLessEqual(sim.z, 31)

    def test_a_drone_that_does_not_move_fails_calibration(self) -> None:
        sim = PadSim(draft=(0.0, 0.0))
        sim.send = lambda command: sim.sent.append(command)
        lander = PadLander(sim, wanted=5, say=lambda _text: None)
        self.assertFalse(lander.calibrate())

    def test_wrong_pad_is_not_used(self) -> None:
        sim = PadSim()
        lander = PadLander(sim, wanted=2, say=lambda _text: None)
        self.assertFalse(lander.calibrate())


if __name__ == "__main__":
    unittest.main()
