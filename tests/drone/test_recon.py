"""Hop timing and yaw choice. No model and no drone."""

import unittest

from patrol.drone.recon import (
    height_commands,
    hop_seconds,
    pad_centered,
    pad_go_command,
    parse_height_cm,
    pick,
    rank_score,
    sweep_plan,
    will_move,
    yaw_command,
)
from patrol.drone.tello_sdk import parse_state


class ReconMathTests(unittest.TestCase):
    def test_blocked_view_does_not_hop(self) -> None:
        self.assertFalse(will_move(1.0))
        self.assertFalse(will_move(1.04))

    def test_open_view_may_hop(self) -> None:
        self.assertTrue(will_move(1.05))
        self.assertTrue(will_move(2.0))

    def test_hop_flies_to_the_margin_and_no_further(self) -> None:
        self.assertAlmostEqual(hop_seconds(1.5, 0.5, 0.4, 8), 2.5)
        self.assertAlmostEqual(hop_seconds(6.0, 0.5, 0.4, 4), 4.0)
        self.assertIsNone(hop_seconds(0.7, 0.5, 0.4, 4))
        self.assertIsNone(hop_seconds(0.85, 0.5, 1.5, 4))

    def test_measured_views_outrank_ratio_only_views(self) -> None:
        views = {
            0: {"metric": False, "value": 3.0, "hop": 2.0},
            90: {"metric": True, "value": 1.2, "hop": 1.7},
            180: {"metric": True, "value": 2.0, "hop": None},
        }
        self.assertEqual(pick(views, None), 90)
        self.assertIsNone(pick({0: {"metric": True, "value": 0.5, "hop": None}}, None))

    def test_height_steps_stay_inside_the_sdk_limits(self) -> None:
        self.assertEqual(parse_height_cm("7dm"), 70)
        self.assertEqual(parse_height_cm("80cm"), 80)
        self.assertEqual(height_commands(80, 80), [])
        self.assertEqual(height_commands(80, 90), [])
        self.assertEqual(height_commands(50, 80), ["up 30"])
        self.assertEqual(height_commands(80, 50), ["down 30"])
        self.assertEqual(height_commands(40, 200), ["up 100", "up 60"])
        self.assertEqual(height_commands(None, 80), [])

    def test_pad_approach_only_when_the_wanted_pad_is_seen(self) -> None:
        self.assertIsNone(pad_go_command(-1, None))
        self.assertIsNone(pad_go_command(0, None))
        self.assertIsNone(pad_go_command(3, 1))
        self.assertIsNone(pad_go_command(3, None, 10, 10))
        self.assertEqual(pad_go_command(3, None), "go 0 0 30 10 m3")
        self.assertEqual(pad_go_command(3, 3, 70, 30), "go 0 0 70 30 m3")
        self.assertTrue(pad_centered(4, -3))
        self.assertFalse(pad_centered(5, 0))
        self.assertFalse(pad_centered(10, -8))
        self.assertFalse(pad_centered(None, 0))

    def test_state_packet_keeps_height_battery_and_pad(self) -> None:
        packet = "h:80;bat:90;mid:3;x:10;y:-5;z:60;pitch:1;yaw:-37;"
        self.assertEqual(parse_state(packet), {"h": 80, "bat": 90, "mid": 3, "x": 10, "y": -5, "z": 60, "yaw": -37})

    def test_angle_count_is_at_least_four(self) -> None:
        self.assertEqual(sweep_plan(4), (4, 90))
        self.assertEqual(sweep_plan(8), (8, 45))
        self.assertEqual(sweep_plan(6), (6, 60))
        with self.assertRaises(ValueError):
            sweep_plan(3)

    def test_straight_ahead_loses_to_an_equal_turn(self) -> None:
        self.assertLess(rank_score(0, 1.4), rank_score(90, 1.4))
        self.assertGreater(rank_score(0, 2.2), rank_score(90, 1.4))

    def test_the_way_back_loses_to_an_equal_side(self) -> None:
        self.assertLess(rank_score(180, 2.0, 180), rank_score(90, 2.0, 180))
        self.assertLess(rank_score(180, 5.0, 180), rank_score(90, 2.0, 180))
        self.assertLess(rank_score(135, 2.0, 180), rank_score(90, 2.0, 180))
        self.assertEqual(rank_score(180, 2.0, None), 2.0)

    def test_yaw_takes_the_short_way(self) -> None:
        self.assertIsNone(yaw_command(315, 315))
        self.assertEqual(yaw_command(315, 0), "cw 45")
        self.assertEqual(yaw_command(315, 270), "ccw 45")


if __name__ == "__main__":
    unittest.main()
