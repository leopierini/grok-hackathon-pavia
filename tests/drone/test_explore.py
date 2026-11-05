"""The whole explore loop against a simulated Tello in a square room. No radio, no model."""

import math
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from patrol.drone import jev
from patrol.drone.pilot import Pilot
from patrol.drone.reflex import Reading

ROOM_HALF_M = 2.0
STICK_PER_MPS = 25 / 0.4


class Room:
    """A square room centered on the takeoff point. The drone starts facing +x."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.fb = 0.0
        self.yaw_rate = 0.0
        self.at = time.monotonic()
        self.closest = ROOM_HALF_M
        self.travelled = 0.0

    def tick(self) -> None:
        with self.lock:
            now = time.monotonic()
            dt = now - self.at
            self.at = now
            self.yaw = (self.yaw + self.yaw_rate * dt) % 360
            rad = math.radians(self.yaw)
            self.x += self.fb * dt * math.cos(rad)
            self.y += self.fb * dt * math.sin(rad)
            self.travelled += abs(self.fb) * dt
            self.closest = min(self.closest, ROOM_HALF_M - max(abs(self.x), abs(self.y)))

    def ray(self, offset_deg: float = 0.0) -> float:
        with self.lock:
            rad = math.radians(self.yaw + offset_deg)
            dx, dy = math.cos(rad), math.sin(rad)
            hits = []
            for d, p in ((dx, self.x), (dy, self.y)):
                if abs(d) > 1e-9:
                    wall = ROOM_HALF_M if d > 0 else -ROOM_HALF_M
                    hits.append((wall - p) / d)
            return max(0.0, min(hits))


class SimSDK:
    def __init__(self, room: Room) -> None:
        self.room = room
        self.sent: list[str] = []
        self.bat = 90
        self.mid = -1

    def query(self, command: str, timeout: float = 5) -> str:
        self.room.tick()
        self.sent.append(command)
        if command == "battery?":
            return str(self.bat)
        if command == "height?":
            return "10dm"
        parts = command.split()
        if parts[0] in ("cw", "ccw"):
            sign = 1 if parts[0] == "cw" else -1
            with self.room.lock:
                self.room.yaw = (self.room.yaw + sign * int(parts[1])) % 360
        if command in ("stop", "land"):
            with self.room.lock:
                self.room.fb = 0.0
                self.room.yaw_rate = 0.0
        return "ok"

    def send(self, command: str) -> None:
        self.room.tick()
        self.sent.append(command)
        if command.startswith("rc "):
            _lr, fb, _ud, yaw = (int(v) for v in command.split()[1:])
            with self.room.lock:
                self.room.fb = fb / STICK_PER_MPS
                self.room.yaw_rate = float(yaw)

    def snapshot(self) -> dict:
        self.room.tick()
        with self.room.lock:
            yaw = int(round(self.room.yaw))
        return {"yaw": (yaw + 180) % 360 - 180, "bat": self.bat, "tof": 100, "mid": self.mid}

    def close(self) -> None:
        return None


class SimGrabber:
    def __init__(self) -> None:
        self.image = Image.new("RGB", (320, 240), "gray")

    def start(self) -> None:
        return None

    def ready(self) -> bool:
        return True

    def latest(self):
        return self.image, time.monotonic()

    def frame_after(self, not_before: float, timeout: float = 2.5):
        image, at = self.latest()
        return (image, at) if at >= not_before else (None, 0.0)

    def capture(self, dest, not_before: float, timeout: float = 2.5) -> bool:
        self.image.save(dest)
        return True

    def close(self) -> None:
        return None


class RoomReflex:
    device = "sim"

    def __init__(self, room: Room) -> None:
        self.room = room

    def measure(self, image, at: float | None = None) -> Reading:
        self.room.tick()
        return Reading(self.room.ray(0), self.room.ray(-20), self.room.ray(20), 0.001, time.monotonic() if at is None else at)


class RoomJev:
    """Jev that sees the room: blocked under 1.5 m. `delay_s` makes it slow."""

    def __init__(self, room: Room, delay_s: float = 0.05, person: float = 0.0) -> None:
        self.room = room
        self.delay_s = delay_s
        self.person = person
        self.guides = 0
        self.scans = 0

    def guide(self, frame_b64: str, height_cm=None) -> jev.Guide:
        time.sleep(self.delay_s)
        self.guides += 1
        ahead = self.room.ray(0)
        return jev.Guide(1.0 if ahead < 1.5 else 0.05, "straight", 0.9, self.person, self.delay_s)

    def scan(self, frames, back=None, height_cm=None) -> jev.Scan:
        self.scans += 1
        judgments = {}
        with self.room.lock:
            yaw_now = self.room.yaw
        for heading, _b64 in frames:
            ahead = self.room.ray(heading - yaw_now)
            judgments[heading] = jev.Judgment(1.0 if ahead < 1.5 else 0.1, 2.0 if ahead > 1.5 else 0.3, 0.0)
        return jev.Scan(judgments, None, 0.01)

    def box(self, frame_b64: str) -> jev.Box:
        self.boxes = getattr(self, "boxes", 0) + 1
        if self.boxes > 5:
            raise jev.JevError("no person in the frame")
        return jev.Box(0.6, 0.8, 0.2, 0.9, 0.9, 0.9)

    def close(self) -> None:
        return None


def pilot_in(room: Room, folder: Path, client=None, **settings) -> tuple[Pilot, SimSDK]:
    sdk = SimSDK(room)
    pilot = Pilot(
        folder,
        sdk_factory=lambda: sdk,
        grabber_factory=SimGrabber,
        reflex_factory=lambda: RoomReflex(room),
        jev_factory=(lambda: client) if client is not None else None,
    )
    error = pilot.update_settings({"cruise_mps": 0.5, "explore_s": 12, **settings})
    assert error is None, error
    return pilot, sdk


class ExploreTests(unittest.TestCase):
    def test_flies_scans_and_never_reaches_a_wall(self) -> None:
        room = Room()
        client = RoomJev(room)
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), client, explore_s=14)
            self.assertEqual(pilot.run_patrol(), 0)
        self.assertGreater(room.travelled, 0.8)
        self.assertGreater(room.closest, 0.5)
        self.assertGreaterEqual(client.scans, 1)
        self.assertNotIn("land", sdk.sent)
        self.assertEqual(pilot.board.data["phase"], "hovering")
        last_rc = [c for c in sdk.sent if c.startswith("rc ")][-1]
        self.assertEqual(last_rc, "rc 0 0 0 0")

    def test_slow_jev_does_not_slow_the_control_loop(self) -> None:
        room = Room()
        client = RoomJev(room, delay_s=2.5)
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), client, explore_s=10, cruise_mps=0.5)
            from patrol.drone.explore import Explorer
            from patrol.drone.navigator import Limits

            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot._begin_run()
            explorer = Explorer(pilot, SimGrabber(), RoomReflex(room), client, Limits(cruise_mps=0.5), "jev", 2.0)
            started = time.monotonic()
            explorer.run()
            elapsed = time.monotonic() - started
        ticks = sum(1 for c in sdk.sent if c.startswith("rc "))
        self.assertGreaterEqual(ticks / elapsed, 8)
        moving = [c for c in sdk.sent if c.startswith("rc ") and c != "rc 0 0 0 0"]
        self.assertTrue(moving)
        self.assertTrue(all(int(c.split()[2]) <= round(0.25 * STICK_PER_MPS) for c in moving))

    def _scan_with(self, grabber_class):
        room = Room()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pilot, sdk = pilot_in(room, Path(tmp.name), RoomJev(room))
        from patrol.drone.explore import Explorer
        from patrol.drone.navigator import Limits

        pilot.sdk = sdk
        pilot.airborne = True
        pilot._landed = False
        pilot._begin_run()
        grabber = grabber_class(room, sdk)
        explorer = Explorer(pilot, grabber, RoomReflex(room), RoomJev(room), Limits(), "jev", 30.0)
        explorer._telemetry_heading()
        explorer._scan()
        return pilot, grabber

    def test_scan_photos_are_taken_stopped_and_labelled_with_the_heading_they_show(self) -> None:
        class StillGrabber(SimGrabber):
            def __init__(self, room, sdk) -> None:
                super().__init__()
                self.room, self.sdk, self.shots = room, sdk, []

            def frame_after(self, not_before, timeout=2.5):
                last_rc = [c for c in self.sdk.sent if c.startswith("rc ")][-1]
                with self.room.lock:
                    self.shots.append((last_rc, self.room.yaw))
                return super().frame_after(not_before, timeout)

        pilot, grabber = self._scan_with(StillGrabber)
        self.assertEqual(len(grabber.shots), 4)
        self.assertTrue(all(last_rc == "rc 0 0 0 0" for last_rc, _yaw in grabber.shots))
        labels = [frame["heading"] for frame in pilot.board.data["frames"]]
        for label, (_rc, yaw) in zip(labels, grabber.shots):
            self.assertLessEqual(abs((label - yaw + 180) % 360 - 180), 2)

    def test_scan_skips_a_stop_with_no_fresh_frame(self) -> None:
        class DroppyGrabber(SimGrabber):
            def __init__(self, room, sdk) -> None:
                super().__init__()
                self.calls = 0

            def frame_after(self, not_before, timeout=2.5):
                self.calls += 1
                return (None, 0.0) if self.calls == 2 else super().frame_after(not_before, timeout)

        pilot, grabber = self._scan_with(DroppyGrabber)
        self.assertEqual(grabber.calls, 4)
        self.assertEqual(len(pilot.board.data["frames"]), 3)

    def test_frozen_video_ends_the_flight(self) -> None:
        class FrozenGrabber(SimGrabber):
            def __init__(self) -> None:
                super().__init__()
                self.frozen_at = time.monotonic() + 1.0

            def latest(self):
                return self.image, min(time.monotonic(), self.frozen_at)

        room = Room()
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), RoomJev(room), explore_s=30)
            from patrol.drone.explore import Explorer
            from patrol.drone.navigator import Limits

            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot._begin_run()
            explorer = Explorer(pilot, FrozenGrabber(), RoomReflex(room), RoomJev(room), Limits(), "jev", 30.0)
            started = time.monotonic()
            self.assertEqual(explorer.run(), "video")
            elapsed = time.monotonic() - started
        self.assertGreater(elapsed, 8.0)
        self.assertLess(elapsed, 16.0)
        self.assertIn("streamon", sdk.sent)
        self.assertEqual([c for c in sdk.sent if c.startswith("rc ")][-1], "rc 0 0 0 0")

    def test_land_during_explore_lands_once_and_stops_the_sticks_first(self) -> None:
        room = Room()
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), RoomJev(room), explore_s=30)
            worker = threading.Thread(target=pilot.run_patrol)
            worker.start()
            deadline = time.monotonic() + 10
            while not any(c.startswith("rc ") and c != "rc 0 0 0 0" for c in list(sdk.sent)):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.05)
            pilot.submit({"action": "land"})
            worker.join(10)
            self.assertFalse(worker.is_alive())
        self.assertEqual(sdk.sent.count("land"), 1)
        before_land = sdk.sent[: sdk.sent.index("land")]
        self.assertEqual([c for c in before_land if c.startswith("rc ")][-1], "rc 0 0 0 0")

    def test_person_in_view_stops_and_hovers(self) -> None:
        room = Room()
        client = RoomJev(room, person=0.9)
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), client, explore_s=20)
            self.assertEqual(pilot.run_patrol(), 0)
            self.assertNotIn("land", sdk.sent)
            self.assertEqual(pilot.board.data["phase"], "person")
            self.assertIsNotNone(pilot.board.data["person"])
            self.assertTrue((pilot.board.folder / "person0.jpg").is_file())
            self.assertFalse(any(command.split()[0] in ("cw", "ccw") for command in sdk.sent))
            self.assertLess(abs(pilot.board.data["person"]["heading"] - 11), 8)

    def test_a_person_ahead_is_approached_then_held_from_above(self) -> None:
        room = Room()

        class Approach(RoomJev):
            def box(self, frame_b64: str) -> jev.Box:
                self.boxes = getattr(self, "boxes", 0) + 1
                if self.boxes <= 4:
                    return jev.Box(0.42, 0.58, 0.15, 0.45, 0.9, 0.9)
                if self.boxes <= 6:
                    return jev.Box(0.25, 0.75, 0.40, 0.95, 0.9, 0.9)
                if self.boxes <= 8:
                    return jev.Box(0.46, 0.54, 0.42, 0.58, 0.9, 0.9)
                raise jev.JevError("no person in the frame")

        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), Approach(room, person=0.9), explore_s=20)
            self.assertEqual(pilot.run_patrol(), 0)
        self.assertNotIn("land", sdk.sent)
        self.assertIn("downvision 1", sdk.sent)
        self.assertIn("up 80", sdk.sent)
        forward = [c for c in sdk.sent if c.startswith("rc ") and int(c.split()[2]) > 0]
        self.assertTrue(forward)
        self.assertLess(sdk.sent.index(forward[0]), sdk.sent.index("downvision 1"))

    def test_person_stop_switched_off_keeps_exploring(self) -> None:
        room = Room()
        client = RoomJev(room, person=0.9)
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), client, explore_s=10, stop_on_person=False)
            self.assertEqual(pilot.run_patrol(), 0)
            self.assertNotIn("land", sdk.sent)
            self.assertEqual(pilot.board.data["phase"], "hovering")
            self.assertIsNone(pilot.board.data["person"])
            self.assertGreater(room.travelled, 0.3)

    def test_jev_brain_without_a_key_refuses_before_takeoff(self) -> None:
        room = Room()
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), None, brain="jev")
            with mock.patch("patrol.drone.jev.api_key", return_value=None):
                self.assertEqual(pilot.run_patrol(), 1)
        self.assertNotIn("takeoff", sdk.sent)
        self.assertIn("OPENROUTER_API_KEY", pilot.status["note"])

    def test_local_brain_without_its_models_refuses_before_takeoff(self) -> None:
        room = Room()
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), None, brain="local")
            missing = FileNotFoundError("no model at models/qwen3-vl-2b-instruct")
            with mock.patch("patrol.drone.local.LocalBrain", side_effect=missing):
                self.assertEqual(pilot.run_patrol(), 1)
        self.assertNotIn("takeoff", sdk.sent)
        self.assertIn("local brain", pilot.status["note"])

    def test_low_battery_lands(self) -> None:
        room = Room()
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), RoomJev(room), explore_s=30)
            threading.Timer(3.5, lambda: setattr(sdk, "bat", 20)).start()
            started = time.monotonic()
            pilot.run_patrol()
            self.assertLess(time.monotonic() - started, 15)
        self.assertEqual(sdk.sent.count("land"), 1)

    def test_reflex_only_never_exceeds_its_speed_cap(self) -> None:
        room = Room()
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), None, brain="reflex-only", explore_s=10)
            pilot.run_patrol()
        sticks = [int(c.split()[2]) for c in sdk.sent if c.startswith("rc ")]
        self.assertTrue(any(sticks))
        self.assertLessEqual(max(sticks), round(0.2 * STICK_PER_MPS))
        self.assertGreater(room.closest, 0.5)

    def test_a_pad_under_the_drone_does_not_end_the_patrol(self) -> None:
        room = Room()
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), RoomJev(room), explore_s=10, pad=True)
            sdk.mid = 2
            pilot.run_patrol()
        self.assertNotIn("land", sdk.sent)
        self.assertFalse(any(command.startswith("go ") for command in sdk.sent))
        self.assertEqual(pilot.board.data["phase"], "hovering")

    def test_pad_switch_while_hovering_takes_a_down_photo(self) -> None:
        room = Room()
        with tempfile.TemporaryDirectory() as tmp:
            pilot, sdk = pilot_in(room, Path(tmp), RoomJev(room), explore_s=10)
            pilot.start()
            self.assertEqual(pilot.run_patrol(), 0)
            self.assertEqual(pilot.board.data["phase"], "hovering")
            self.assertIsNone(pilot.update_settings({"pad": True}))
            deadline = time.monotonic() + 5
            while not list(pilot.board.folder.glob("pad-*.jpg")) and time.monotonic() < deadline:
                time.sleep(0.05)
            photos = list(pilot.board.folder.glob("pad-*.jpg"))
            pilot.settings["pad"] = False
        self.assertTrue(photos)
        self.assertIn("downvision 1", sdk.sent)
        self.assertNotIn("land", sdk.sent)


if __name__ == "__main__":
    unittest.main()
