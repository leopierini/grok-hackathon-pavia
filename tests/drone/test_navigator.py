"""Braking, speed, vetoes and the fence. No model and no drone."""

import unittest

from patrol.drone.navigator import Limits, Navigator, Pose, Seen, View, choose_heading, speed_for
from patrol.drone.reflex import Reading


def reading(center: float, at: float = 10.0, left: float = 3.0, right: float = 3.0) -> Reading:
    return Reading(center, left, right, 0.03, at)


def seen(at: float = 10.0, blocked: float = 0.1, steer: str = "straight", person: float = 0.0, confidence: float = 0.9) -> Seen:
    return Seen(blocked, steer, confidence, person, at)


class SpeedTests(unittest.TestCase):
    def test_ramp_from_brake_to_cruise(self) -> None:
        limits = Limits()
        self.assertEqual(speed_for(0.9, limits), 0.0)
        self.assertEqual(speed_for(1.0, limits), 0.0)
        self.assertAlmostEqual(speed_for(1.5, limits), 0.25)
        self.assertEqual(speed_for(2.0, limits), 0.5)
        self.assertEqual(speed_for(5.0, limits), 0.5)


class StepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.nav = Navigator(Limits(), "jev", started_at=0.0)

    def test_the_floor_brakes_while_the_horizon_is_open(self) -> None:
        from patrol.drone.reflex import Reading as Depth

        command = self.nav.step(10.1, Depth(4.0, 4.0, 4.0, 0.03, 10.0, near_m=0.7), seen())
        self.assertEqual(command.mode, "scan")
        self.assertIn("0.70", command.reason)

    def test_close_obstacle_scans(self) -> None:
        command = self.nav.step(10.1, reading(0.8), seen())
        self.assertEqual(command.mode, "scan")
        self.assertEqual(command.fb_mps, 0.0)

    def test_stale_reflex_holds_even_when_jev_says_clear(self) -> None:
        command = self.nav.step(10.6, reading(4.0, at=10.0), seen(at=10.5))
        self.assertEqual(command.mode, "hold")
        self.assertEqual(command.fb_mps, 0.0)

    def test_both_clear_cruises(self) -> None:
        command = self.nav.step(10.2, reading(4.0), seen())
        self.assertEqual(command.mode, "cruise")
        self.assertEqual(command.fb_mps, 0.5)

    def test_jev_blocked_brakes_on_an_open_reflex(self) -> None:
        command = self.nav.step(10.2, reading(4.0), seen(blocked=0.7))
        self.assertEqual(command.mode, "scan")

    def test_old_jev_answer_does_not_count(self) -> None:
        command = self.nav.step(12.0, reading(4.0, at=11.9), seen(at=10.0, blocked=0.9))
        self.assertEqual(command.mode, "cruise")
        self.assertEqual(command.fb_mps, 0.25)

    def test_silent_jev_slows_then_scans(self) -> None:
        late = self.nav.step(13.5, reading(4.0, at=13.4), seen(at=10.0))
        self.assertEqual(late.mode, "cruise")
        self.assertEqual(late.fb_mps, 0.2)
        silent = self.nav.step(16.5, reading(4.0, at=16.4), seen(at=10.0))
        self.assertEqual(silent.mode, "scan")

    def test_no_jev_answer_yet_never_goes_full_speed(self) -> None:
        command = self.nav.step(1.0, reading(4.0, at=0.95), None)
        self.assertEqual(command.mode, "cruise")
        self.assertEqual(command.fb_mps, 0.25)

    def test_steer_turns_while_flying(self) -> None:
        right = self.nav.step(10.2, reading(4.0), seen(steer="right"))
        left = self.nav.step(10.2, reading(4.0), seen(steer="left"))
        unsure = self.nav.step(10.2, reading(4.0), seen(steer="left", confidence=0.1))
        self.assertEqual(right.yaw_dps, 20.0)
        self.assertEqual(left.yaw_dps, -20.0)
        self.assertEqual(unsure.yaw_dps, 0.0)
        self.assertEqual(right.fb_mps, 0.5)

    def test_person_needs_two_answers_in_a_row(self) -> None:
        first = seen(at=10.0, person=0.8)
        self.nav.note(first)
        self.nav.note(first)
        self.assertEqual(self.nav.step(10.2, reading(4.0), first).mode, "cruise")
        second = seen(at=10.5, person=0.9)
        self.nav.note(second)
        self.assertEqual(self.nav.step(10.6, reading(4.0, at=10.6), second).mode, "person")

    def test_person_streak_breaks_on_an_empty_frame(self) -> None:
        self.nav.note(seen(at=10.0, person=0.8))
        self.nav.note(seen(at=10.5, person=0.1))
        latest = seen(at=11.0, person=0.8)
        self.nav.note(latest)
        self.assertEqual(self.nav.step(11.1, reading(4.0, at=11.1), latest).mode, "cruise")

    def test_people_do_not_stop_the_drone_when_switched_off(self) -> None:
        self.nav.stop_on_person = False
        self.nav.note(seen(at=10.0, person=0.9))
        latest = seen(at=10.5, person=0.9)
        self.nav.note(latest)
        self.assertEqual(self.nav.step(10.6, reading(4.0, at=10.6), latest).mode, "cruise")
        self.nav.stop_on_person = True
        self.assertEqual(self.nav.step(10.7, reading(4.0, at=10.7), latest).mode, "person")

    def test_reflex_only_is_slow_and_steers_to_the_open_side(self) -> None:
        nav = Navigator(Limits(), "reflex-only")
        command = nav.step(10.1, reading(1.6, left=1.2, right=3.0), None)
        self.assertEqual(command.mode, "cruise")
        self.assertLessEqual(command.fb_mps, 0.2)
        self.assertGreater(command.yaw_dps, 0.0)

    def _steer(self, frames, nav=None):
        """Feed (left, center, right) readings at 10 Hz; return the yaw of each tick."""
        nav = nav or Navigator(Limits(), "local", started_at=0.0)
        yaws = []
        for index, (left, center, right) in enumerate(frames):
            at = 10.0 + index * 0.1
            yaws.append(nav.step(at, reading(center, at=at, left=left, right=right), seen(at=at)).yaw_dps)
        return yaws

    def test_open_space_leans_gently_toward_the_roomier_side(self) -> None:
        yaws = self._steer([(2.0, 4.0, 4.0)] * 20)
        self.assertGreater(yaws[-1], 0.0)
        self.assertLess(yaws[-1], 15.0)
        self.assertEqual(self._steer([(3.0, 4.0, 3.0)] * 20)[-1], 0.0)
        self.assertLess(self._steer([(4.0, 4.0, 2.0)] * 20)[-1], 0.0)

    def test_closing_in_turns_harder_than_the_open_room(self) -> None:
        open_room = self._steer([(2.0, 4.0, 4.0)] * 20)[-1]
        wall_ahead = self._steer([(2.0, 1.2, 4.0)] * 20)[-1]
        shrinking = self._steer([(2.0, 4.0 - 0.1 * index, 4.0) for index in range(20)])[-1]
        self.assertGreater(wall_ahead, 2 * open_room)
        self.assertGreater(shrinking, open_room)

    def test_the_turn_builds_up_instead_of_jumping(self) -> None:
        yaws = self._steer([(1.0, 1.2, 4.0)] * 10)
        self.assertLess(yaws[0], yaws[-1] / 2)
        self.assertTrue(all(later >= earlier for earlier, later in zip(yaws, yaws[1:])))
        self.assertLessEqual(yaws[-1], Limits().side_steer_dps)

    def test_geofence_stops_outward_flight(self) -> None:
        self.nav.pose = Pose(x=3.8, y=0.0, heading=0.0)
        self.assertEqual(self.nav.step(10.1, reading(4.0), seen()).mode, "scan")
        self.nav.pose = Pose(x=3.8, y=0.0, heading=180.0)
        self.assertEqual(self.nav.step(10.1, reading(4.0), seen()).mode, "cruise")


class PoseTests(unittest.TestCase):
    def test_dead_reckoning_and_visited_cells(self) -> None:
        pose = Pose()
        pose.advance(0.5, 2.0)
        self.assertAlmostEqual(pose.x, 1.0)
        pose.turn_to(90)
        pose.advance(0.5, 2.0)
        self.assertAlmostEqual(pose.y, 1.0)
        self.assertTrue(pose.seen_ahead(270, 1.0))
        self.assertFalse(pose.seen_ahead(90, 1.0))


class ChooseTests(unittest.TestCase):
    def test_jev_pick_wins_when_it_passes(self) -> None:
        views = {0: View(3.0, 0.1, 3.0), 90: View(4.0, 0.1, 3.0)}
        heading, _why = choose_heading(views, 0, Pose(), Limits())
        self.assertEqual(heading, 0)

    def test_jev_pick_into_a_close_reflex_is_refused(self) -> None:
        views = {0: View(1.2, 0.1, 3.0), 90: View(2.5, 0.2, 2.0)}
        heading, why = choose_heading(views, 0, Pose(), Limits())
        self.assertEqual(heading, 90)
        self.assertIn("reflex", why[0])

    def test_everything_blocked_stays(self) -> None:
        views = {0: View(3.0, 0.8, 3.0), 90: View(0.6, 0.1, 3.0), 180: View(3.0, 0.1, 0.3)}
        heading, why = choose_heading(views, 0, Pose(), Limits())
        self.assertIsNone(heading)
        self.assertTrue(all(reason for reason in why.values()))

    def test_visited_and_back_headings_count_less(self) -> None:
        pose = Pose()
        pose.advance(0.5, 2.0)
        pose.turn_to(0)
        views = {0: View(3.0), 180: View(3.0), 90: View(2.0)}
        heading, _why = choose_heading(views, None, pose, Limits(), back=180)
        self.assertEqual(heading, 0)
        pose.visited.add(pose.cell(*pose.ahead(0, 1.0)))
        heading, _why = choose_heading(views, None, pose, Limits(), back=180)
        self.assertEqual(heading, 90)

    def test_a_heading_just_blocked_by_glass_loses_to_any_other(self) -> None:
        views = {169: View(3.1, 0.1, 3.0), 260: View(1.8, 0.1, 3.0), 350: View(0.7, 0.1, 3.0)}
        heading, why = choose_heading(views, None, Pose(), Limits(), avoid=[166])
        self.assertEqual(heading, 260)
        self.assertEqual(why[169], "just blocked")

    def test_a_just_blocked_heading_stays_when_it_is_the_only_way_out(self) -> None:
        views = {169: View(3.1, 0.1, 3.0), 260: View(0.8, 0.1, 3.0)}
        heading, why = choose_heading(views, None, Pose(), Limits(), avoid=[169])
        self.assertEqual(heading, 169)
        self.assertIsNone(why[169])


if __name__ == "__main__":
    unittest.main()
