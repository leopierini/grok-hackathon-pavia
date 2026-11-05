"""Floor-anchored meters on synthetic depth maps. Needs torch, not the model."""

import unittest

import torch

from patrol.drone.depth_look import (
    CAMERA_TILT_DEG,
    LENS_ABOVE_TOF_M,
    floor_depth_m,
    floor_fit,
    free_distance_m,
)
from patrol.drone.recon import assess

HEIGHT, WIDTH = 720, 960


def scene(camera_m: float, wall_m: float, box_m: float | None = None, tilt: float = 0.0) -> torch.Tensor:
    """Model output for a floor plus a wall ahead: raw = 2 / z + 0.5."""
    z = torch.full((HEIGHT, WIDTH), wall_m)
    for row in range(HEIGHT):
        floor = floor_depth_m(row + 0.5, HEIGHT, WIDTH, camera_m, tilt)
        if floor is not None and floor < wall_m:
            z[row, :] = floor
    if box_m is not None:
        z[int(HEIGHT * 0.12) : int(HEIGHT * 0.42), 400:560] = box_m
    return 2.0 / z + 0.5


class FloorTests(unittest.TestCase):
    def test_the_floor_gives_back_the_wall_distance(self) -> None:
        closer = scene(1.0, 3.0)
        fit = floor_fit(closer, 1.0, 0.0)
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit.a, 2.0, delta=0.1)
        self.assertAlmostEqual(free_distance_m(closer, fit), 3.0, delta=0.1)

    def test_an_obstacle_ahead_is_the_free_distance(self) -> None:
        closer = scene(1.0, 4.0, box_m=1.0)
        fit = floor_fit(closer, 1.0, 0.0)
        self.assertAlmostEqual(free_distance_m(closer, fit), 1.0, delta=0.1)

    def test_wrong_height_scales_the_distance(self) -> None:
        closer = scene(1.0, 3.0)
        fit = floor_fit(closer, 0.5, 0.0)
        self.assertAlmostEqual(free_distance_m(closer, fit), 1.5, delta=0.1)

    def test_no_floor_falls_back_to_the_ratio(self) -> None:
        torch.manual_seed(0)
        noise = torch.rand(HEIGHT, WIDTH)
        self.assertIsNone(floor_fit(noise, 1.0, 0.0))
        view = assess(noise, 100, 0.5, 0.4, 4)
        self.assertFalse(view["metric"])
        self.assertIsNone(view["free_m"])
        view = assess(scene(1.0, 3.0), None, 0.5, 0.4, 4)
        self.assertFalse(view["metric"])

    def test_room_beyond_one_hop_does_not_count(self) -> None:
        lens = 1.0 + LENS_ABOVE_TOF_M
        far = assess(scene(lens, 5.0, tilt=CAMERA_TILT_DEG), 100, 0.5, 0.4, 4)
        near = assess(scene(lens, 3.0, tilt=CAMERA_TILT_DEG), 100, 0.5, 0.4, 4)
        self.assertAlmostEqual(far["value"], 0.5 + 4 * 0.4)
        self.assertAlmostEqual(near["value"], far["value"])

    def test_measured_view_hops_to_the_margin(self) -> None:
        lens = 1.0 + LENS_ABOVE_TOF_M
        view = assess(scene(lens, 3.0, tilt=CAMERA_TILT_DEG), 100, 0.5, 0.4, 8)
        self.assertTrue(view["metric"])
        self.assertAlmostEqual(view["hop"], (3.0 - 0.5) / 0.4, delta=0.3)


if __name__ == "__main__":
    unittest.main()
