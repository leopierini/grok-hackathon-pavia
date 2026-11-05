"""The corridor split: horizon for the room, floor for what is close."""

import unittest

import torch

from patrol.drone.reflex import corridor_meters


class CorridorTests(unittest.TestCase):
    def test_the_near_floor_does_not_cap_the_room_ahead(self) -> None:
        depth = torch.full((100, 90), 6.0)
        depth[42:70, :] = 2.5
        depth[15:42, 30:60] = 4.0
        depth[15:42, 60:] = 8.0
        center, left, right, floor = corridor_meters(depth)
        self.assertAlmostEqual(center, 4.0)
        self.assertAlmostEqual(left, 6.0)
        self.assertAlmostEqual(right, 8.0)
        self.assertAlmostEqual(floor, 2.5)


if __name__ == "__main__":
    unittest.main()
