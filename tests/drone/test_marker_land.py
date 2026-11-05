"""Marker landing on a simulated downward camera. No radio."""

import math
import time
import unittest

import cv2
from PIL import Image

from patrol.drone.marker_land import (
    FUNNEL_SINK,
    MARKER_CM,
    SINK_FAST,
    SINK_UD,
    MarkerLander,
    downward_view,
    find_marker,
    landing_move,
    usable,
)
from tests.drone.test_pad_land import PadSim

WIDTH, HEIGHT = 320, 240
CM_PER_PX_PER_CM_UP = 0.004


def marker_image(marker_id: int, side: int) -> Image.Image:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return Image.fromarray(cv2.aruco.generateImageMarker(dictionary, marker_id, side))


def floor_view(cx: float, cy: float, side: int, marker_id: int = 0) -> Image.Image:
    page = Image.new("L", (WIDTH, HEIGHT), 200)
    page.paste(marker_image(marker_id, side), (int(round(cx - side / 2)), int(round(cy - side / 2))))
    return page.convert("RGB")


class DownCamera:
    """Draws the marker where the simulated drone would see it; the marker sits at the sim's origin."""

    def __init__(self, sim: PadSim) -> None:
        self.sim = sim

    def frame_after(self, not_before: float, timeout: float = 2.5):
        snap = self.sim.snapshot()
        cm_per_px = max(snap["z"], 10) * CM_PER_PX_PER_CM_UP
        with self.sim.lock:
            x, y, facing = self.sim.x, self.sim.y, self.sim.facing
        # Measured mounting: forward stick moves the marker right, right stick moves it down.
        cos, sin = math.cos(facing), math.sin(facing)
        image_x = x * cos + y * sin
        image_y = -x * sin + y * cos
        side = int(round(MARKER_CM / cm_per_px))
        cx = WIDTH / 2 + image_x / cm_per_px
        cy = HEIGHT / 2 + image_y / cm_per_px
        time.sleep(0.03)
        return floor_view(cx, cy, side), max(not_before, time.monotonic())


class MarkerSim(PadSim):
    def snapshot(self) -> dict:
        snap = super().snapshot()
        snap["tof"] = snap["z"]
        return snap


class FindMarkerTests(unittest.TestCase):
    def test_finds_the_center_and_size_in_pixels(self) -> None:
        mark = find_marker(floor_view(200, 90, 60))
        self.assertIsNotNone(mark)
        self.assertAlmostEqual(mark.cx, 200, delta=1.0)
        self.assertAlmostEqual(mark.cy, 90, delta=1.0)
        self.assertAlmostEqual(mark.side_px, 60, delta=2.0)

    def test_the_green_pad_under_the_infrared_picture_is_cropped_away(self) -> None:
        real = floor_view(200, 90, 60)
        padded = Image.new("RGB", (320, 720), (0, 180, 0))
        padded.paste(real, (0, 0))
        self.assertFalse(usable(padded))
        cropped = downward_view(padded)
        self.assertLessEqual(cropped.size[1], 250)
        mark = find_marker(cropped)
        self.assertIsNotNone(mark)
        self.assertAlmostEqual(mark.cx, 200, delta=1.0)

    def test_a_green_half_decoded_frame_is_not_used(self) -> None:
        broken = Image.new("RGB", (320, 720), (0, 180, 0))
        self.assertFalse(usable(broken))
        self.assertTrue(usable(floor_view(160, 120, 60)))

    def test_other_ids_and_empty_floors_are_not_the_marker(self) -> None:
        self.assertIsNone(find_marker(floor_view(160, 120, 60, marker_id=3)))
        self.assertIsNone(find_marker(Image.new("RGB", (WIDTH, HEIGHT), (180, 180, 180))))


class MarkerLanderTests(unittest.TestCase):
    def test_steers_toward_the_marker_and_rests_when_close(self) -> None:
        lander = MarkerLander(None, None, say=lambda _text: None)
        right, forward = lander.steer(12, 0)
        self.assertEqual(right, 0)
        self.assertLess(forward, 0)
        right, forward = lander.steer(0, 10)
        self.assertLess(right, 0)
        self.assertEqual(forward, 0)
        self.assertEqual(lander.steer(1, -1), (0, 0))

    def test_inside_the_cone_it_only_descends_and_lands_when_low(self) -> None:
        ud, level, land = landing_move(2, 2, 80, 0.0)
        self.assertEqual((ud, level, land), (SINK_FAST, True, False))
        ud, level, land = landing_move(18, 0, 80, 0.0)
        self.assertEqual((ud, level, land), (SINK_FAST, False, False))
        ud, level, land = landing_move(30, 0, 80, 0.0)
        self.assertEqual((ud, level, land), (0, False, False))
        ud, level, land = landing_move(12, 0, 35, 0.0)
        self.assertEqual((ud, level, land), (FUNNEL_SINK, True, False))
        ud, level, land = landing_move(20, 0, 30, 1.0)
        self.assertEqual((ud, level, land), (0, False, False))
        ud, level, land = landing_move(2, 1, None, 1.0)
        self.assertEqual((ud, level, land), (SINK_UD, True, False))
        ud, level, land = landing_move(12, 0, 22, 0.0)
        self.assertEqual((ud, level, land), (0, True, True))


    def test_lands_within_a_centimeter_for_any_facing_against_a_draft(self) -> None:
        for facing in (0.0, 130.0, -100.0):
            with self.subTest(facing=facing):
                sim = MarkerSim(x=8.0, y=-6.0, z=70.0, facing_deg=facing)
                lander = MarkerLander(sim, DownCamera(sim), say=lambda _text: None)
                self.assertIsNotNone(lander.find())
                self.assertTrue(lander.calibrate())
                note = lander.servo()
                self.assertIn("marker centered", note)
                self.assertLessEqual(math.hypot(sim.x, sim.y), 1.5)
                self.assertLessEqual(sim.z, 26)

    def test_kept_axes_skip_the_test_pulses(self) -> None:
        first = MarkerSim(facing_deg=40.0)
        lander = MarkerLander(first, DownCamera(first), say=lambda _text: None)
        self.assertTrue(lander.calibrate())
        axes = (lander.forward, lander.right)
        again = MarkerSim(x=-5.0, y=7.0, facing_deg=40.0)
        second = MarkerLander(again, DownCamera(again), say=lambda _text: None)
        second.use_axes(*axes)
        self.assertIn("marker centered", second.servo())
        self.assertLessEqual(math.hypot(again.x, again.y), 1.5)

    def test_no_marker_in_view_is_reported(self) -> None:
        class Blank:
            def frame_after(self, not_before, timeout=2.5):
                return Image.new("RGB", (WIDTH, HEIGHT), (180, 180, 180)), time.monotonic()

        lander = MarkerLander(MarkerSim(), Blank(), say=lambda _text: None)
        self.assertIsNone(lander.find(timeout=0.3))


if __name__ == "__main__":
    unittest.main()
