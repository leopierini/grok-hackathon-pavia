"""Pilot decisions with a fake drone. No radio and no model."""

import tempfile
import threading
import time
import unittest
from pathlib import Path

from patrol.drone.live import resolve_frame
from patrol.drone.pilot import FrameGrabber, Pilot


class FakeImage:
    def save(self, dest) -> None:
        Path(dest).write_bytes(b"frame")


class FakeGrabber:
    def start(self) -> None:
        return None

    def capture(self, dest, not_before: float, timeout: float = 2.5) -> bool:
        Path(dest).write_bytes(b"frame")
        return True

    def ready(self) -> bool:
        return True

    def frame_after(self, not_before: float, timeout: float = 2.5):
        """No marker in the downward view, so the marker landing steps aside."""
        return None, 0.0

    def latest(self):
        return None, 0.0

    def close(self) -> None:
        return None


class FakeSDK:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.height_reply = "8dm"
        self.state = {"mid": -1, "x": 0, "y": 0, "h": 80, "bat": 90}
        self.release = threading.Event()

    def query(self, command: str, timeout: float = 5) -> str:
        self.sent.append(command)
        if command.startswith("cw"):
            self.release.wait(timeout=2)
            return "ok"
        if command == "battery?":
            return "90"
        if command == "height?":
            return self.height_reply
        return "ok"

    def send(self, command: str) -> None:
        self.sent.append(command)

    def snapshot(self) -> dict:
        return dict(self.state)

    def close(self) -> None:
        return None


class PilotTests(unittest.TestCase):
    def test_capture_waits_for_a_frame_after_the_turn(self) -> None:
        grabber = FrameGrabber()
        grabber._image = FakeImage()
        grabber._at = 10.0
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "a.jpg"
            self.assertFalse(grabber.capture(dest, not_before=10.1, timeout=0.2))
            self.assertFalse(dest.exists())
            self.assertTrue(grabber.capture(dest, not_before=10.0, timeout=0.2))
            self.assertEqual(dest.read_bytes(), b"frame")

    def test_land_does_not_steer_toward_the_pad(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sdk = FakeSDK()
            sdk.state.update(mid=3, x=50, y=20)
            pilot = Pilot(Path(tmp), sdk_factory=lambda: sdk, grabber_factory=FakeGrabber)
            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot.settings["pad"] = True
            pilot._begin_run()
            pilot._land_once()
            pilot._land_once()
        self.assertFalse(any(command.startswith("go ") for command in sdk.sent))
        self.assertEqual(sdk.sent.count("land"), 1)

    def test_pad_search_saves_a_down_photo_and_does_not_land(self) -> None:
        from PIL import Image

        class Shot(FakeGrabber):
            def frame_after(self, not_before: float, timeout: float = 2.5):
                return Image.new("RGB", (320, 240), (30, 30, 30)), time.monotonic()

        with tempfile.TemporaryDirectory() as tmp:
            sdk = FakeSDK()
            pilot = Pilot(Path(tmp), sdk_factory=lambda: sdk, grabber_factory=Shot)
            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot.settings["pad"] = True
            pilot._begin_run()
            import patrol.drone.pilot as pilot_mod

            previous = pilot_mod.PAD_PHOTO_S
            pilot_mod.PAD_PHOTO_S = 0.05

            def stop() -> None:
                time.sleep(2.0)
                pilot.settings["pad"] = False

            threading.Thread(target=stop, daemon=True).start()
            try:
                pilot._watch_pad()
            finally:
                pilot_mod.PAD_PHOTO_S = previous
            photos = list(Path(tmp).glob("*/pad-*.jpg"))
        self.assertGreaterEqual(len(photos), 1)
        self.assertNotIn("land", sdk.sent)
        self.assertIn("downvision 1", sdk.sent)

    def test_a_person_already_below_is_held_without_flying_forward_or_landing(self) -> None:
        from PIL import Image

        from patrol.drone.jev import Box

        class Eyes(FakeGrabber):
            def latest(self):
                return Image.new("RGB", (64, 48), "gray"), time.monotonic()

        seen = {"n": 0}

        def spot(_image):
            seen["n"] += 1
            if seen["n"] > 3:
                return None
            return Box(0.70, 0.90, 0.40, 0.60, 0.9, 0.9)

        sdk = FakeSDK()
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Pilot(Path(tmp), sdk_factory=lambda: sdk, grabber_factory=Eyes)
            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot.follow_person(Eyes(), spot, already_down=True)
        self.assertNotIn("land", sdk.sent)
        self.assertNotIn("up 80", sdk.sent)
        self.assertFalse(any(c.startswith("rc ") and int(c.split()[2]) > 0 for c in sdk.sent))
        self.assertTrue(any(c.startswith("rc ") and int(c.split()[2]) < 0 for c in sdk.sent))

    def test_a_centered_marker_low_down_lands(self) -> None:
        from tests.drone.test_marker_land import floor_view

        class Centered(FakeGrabber):
            def frame_after(self, not_before: float, timeout: float = 2.5):
                return floor_view(160, 120, 40), time.monotonic()

        sdk = FakeSDK()
        sdk.state["tof"] = 22
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Pilot(Path(tmp), sdk_factory=lambda: sdk, grabber_factory=Centered)
            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot.settings["pad"] = True
            pilot._begin_run()
            pilot._watch_pad()
            self.assertIn("land", sdk.sent)
            self.assertLess(sdk.sent.index("downvision 1"), sdk.sent.index("land"))

    def test_pad_checkbox_starts_the_down_camera_and_does_not_land(self) -> None:
        sdk = FakeSDK()
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Pilot(Path(tmp), sdk_factory=lambda: sdk, grabber_factory=FakeGrabber)
            pilot.start()
            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot.submit({"action": "set", "pad": True})
            deadline = time.monotonic() + 3
            while "downvision 1" not in sdk.sent and time.monotonic() < deadline:
                time.sleep(0.05)
            pilot.submit({"action": "set", "pad": False})
            self.assertIn("downvision 1", sdk.sent)
            self.assertNotIn("land", sdk.sent)

    def test_a_dropped_hover_command_does_not_kill_the_pad_switch(self) -> None:
        class Flaky(FakeSDK):
            def __init__(self) -> None:
                super().__init__()
                self.boomed = False

            def send(self, command: str) -> None:
                if command == "rc 0 0 0 0" and not self.boomed:
                    self.boomed = True
                    raise OSError(51, "Network is unreachable")
                super().send(command)

        sdk = Flaky()
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Pilot(Path(tmp), sdk_factory=lambda: sdk, grabber_factory=FakeGrabber)
            pilot.start()
            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot._kept_at = 0.0
            deadline = time.monotonic() + 3
            while not any("hover keep failed" in line for line in pilot._lines) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(sdk.boomed)
            pilot.submit({"action": "set", "pad": True})
            while "downvision 1" not in sdk.sent and time.monotonic() < deadline + 3:
                time.sleep(0.05)
            pilot.submit({"action": "set", "pad": False})
            self.assertIn("downvision 1", sdk.sent)

    def test_land_pressed_while_busy_still_lands(self) -> None:
        sdk = FakeSDK()
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Pilot(Path(tmp), sdk_factory=lambda: sdk, grabber_factory=FakeGrabber)
            pilot.start()
            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot._busy = True
            pilot.submit({"action": "land"})
            deadline = time.monotonic() + 3
            while "land" not in sdk.sent and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertIn("land", sdk.sent)

    def test_height_change_while_hovering_climbs_immediately(self) -> None:
        sdk = FakeSDK()
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Pilot(Path(tmp), sdk_factory=lambda: sdk, grabber_factory=FakeGrabber)
            pilot.start()
            pilot.sdk = sdk
            pilot.airborne = True
            pilot._landed = False
            pilot._begin_run()
            pilot.submit({"action": "set", "height_cm": 120})
            deadline = time.monotonic() + 2
            while "up 40" not in sdk.sent and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertIn("up 40", sdk.sent)

    def test_a_grounded_drone_clears_the_takeoff_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            down = FakeSDK()
            down.height_reply = "0dm"
            pilot = Pilot(Path(tmp) / "down", sdk_factory=lambda: down, grabber_factory=FakeGrabber)
            pilot.sdk = down
            pilot._blocked = True
            pilot.airborne = True
            self.assertTrue(pilot._ready_to_arm())
            self.assertFalse(pilot._blocked)
            self.assertFalse(pilot.airborne)
            self.assertNotIn("takeoff", down.sent)

            up = FakeSDK()
            other = Pilot(Path(tmp) / "up", sdk_factory=lambda: up, grabber_factory=FakeGrabber)
            other.sdk = up
            other._blocked = True
            other.airborne = True
            self.assertFalse(other._ready_to_arm())
            self.assertTrue(other._blocked)
            self.assertNotIn("takeoff", up.sent)

    def test_patrol_checks_its_flight_time_before_anything_flies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Pilot(Path(tmp), sdk_factory=FakeSDK, grabber_factory=FakeGrabber)
            refused = pilot.submit({"action": "patrol", "explore_s": 900})
            self.assertFalse(refused["ok"])
            self.assertIsNone(pilot.sdk)
            accepted = pilot.submit({"action": "patrol", "explore_s": 30})
            self.assertTrue(accepted["ok"])
            self.assertEqual(pilot.settings["explore_s"], 30)
            self.assertIsNone(pilot.sdk)

    def test_flight_settings_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Pilot(Path(tmp), sdk_factory=FakeSDK, grabber_factory=FakeGrabber)
            self.assertIsNotNone(pilot.update_settings({"cruise_mps": 1.2}))
            self.assertIsNotNone(pilot.update_settings({"brake_m": 0.3}))
            self.assertIsNotNone(pilot.update_settings({"brain": "grok"}))
            self.assertIsNone(pilot.update_settings({"cruise_mps": 0.35, "brake_m": 1.2, "brain": "reflex-only"}))
            self.assertEqual(pilot.status["cruise_mps"], 0.35)
            self.assertEqual(pilot.status["brain"], "reflex-only")
            self.assertTrue(pilot.status["stop_on_person"])
            self.assertIsNone(pilot.update_settings({"stop_on_person": False}))
            self.assertFalse(pilot.settings["stop_on_person"])
            self.assertIsNone(pilot.update_settings({"height_cm": 300}))
            self.assertEqual(pilot.settings["height_cm"], 300)
            self.assertEqual(pilot.update_settings({"height_cm": 301}), "height must be 40 to 300 cm")

    def test_frame_urls_stay_inside_one_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "2026-11-04T150000Z"
            second = root / "2026-11-04T150100Z"
            first.mkdir()
            second.mkdir()
            (first / "step0-h000.jpg").write_bytes(b"one")
            (second / "step0-h000.jpg").write_bytes(b"two")
            self.assertEqual(resolve_frame(root, first.name, "step0-h000.jpg").read_bytes(), b"one")
            self.assertEqual(resolve_frame(root, second.name, "step0-h000.jpg").read_bytes(), b"two")
            self.assertIsNone(resolve_frame(root, first.name, "../2026-11-04T150100Z/step0-h000.jpg"))
            self.assertIsNone(resolve_frame(root, "..", "step0-h000.jpg"))
            self.assertIsNone(resolve_frame(root, first.name, "note.txt"))


if __name__ == "__main__":
    unittest.main()
