import unittest

from PIL import Image

from patrol.drone import jev
from patrol.drone.local import GLASS_LIMIT, NO_LIMIT_M, LocalBrain, rescale
from patrol.drone.navigator import Limits, Navigator, Seen


def frame(color=(120, 120, 120)) -> str:
    return jev.encode_frame(Image.new("RGB", (960, 720), color))


class FakeDetector:
    def __init__(self, people=None, fail=False) -> None:
        self.found = people or []
        self.fail = fail

    def people(self, image):
        if self.fail:
            raise RuntimeError("mps out of memory")
        return self.found


class FakeJudge:
    device = "cpu"
    name = "fake"

    def __init__(self, glass) -> None:
        self.glass = glass
        self.asked = []
        self.sizes = []

    def ask(self, items, options):
        self.asked.append(len(items))
        self.sizes.extend(image.size for image, _question in items)
        values = self.glass if isinstance(self.glass, list) else [self.glass] * len(items)
        return [[value, 1 - value] for value in values]


class RescaleTests(unittest.TestCase):
    def test_the_glass_line_lands_on_the_navigator_line(self) -> None:
        self.assertAlmostEqual(rescale(0.0), 0.0)
        self.assertAlmostEqual(rescale(GLASS_LIMIT), Limits.blocked_limit)
        self.assertAlmostEqual(rescale(1.0), 1.0)
        self.assertLess(rescale(0.71), Limits.blocked_limit)
        self.assertGreater(rescale(0.82), Limits.blocked_limit)


class LocalBrainTests(unittest.TestCase):
    def test_guide_reads_glass_and_people_and_leaves_steering_to_the_reflex(self) -> None:
        brain = LocalBrain(detector=FakeDetector([(0.92, (0.4, 0.1, 0.6, 0.9))]), judge=FakeJudge(0.9))
        guide = brain.guide(frame())
        self.assertGreater(guide.blocked, 0.5)
        self.assertEqual(guide.person, 0.92)
        self.assertEqual(guide.steer_confidence, 0.0)
        self.assertEqual(brain.judge.asked, [1])

    def test_glass_is_judged_on_the_whole_photo(self) -> None:
        judge = FakeJudge(0.1)
        brain = LocalBrain(detector=FakeDetector(), judge=judge)
        brain.guide(frame())
        brain.scan([(0, frame()), (90, frame())])
        self.assertEqual(judge.sizes, [(640, 480)] * 3)

    def test_guide_failure_is_a_jev_error(self) -> None:
        brain = LocalBrain(detector=FakeDetector(fail=True), judge=FakeJudge(0.1))
        with self.assertRaises(jev.JevError):
            brain.guide(frame())

    def test_scan_judges_every_photo_in_one_batch(self) -> None:
        judge = FakeJudge([0.1, 0.95, 0.2, 0.3])
        brain = LocalBrain(detector=FakeDetector(), judge=judge)
        scan = brain.scan([(heading, frame()) for heading in (0, 90, 180, 270)], back=180)
        self.assertEqual(judge.asked, [4])
        self.assertIsNone(scan.choice)
        self.assertGreater(scan.judgments[90].blocked, 0.5)
        self.assertLess(scan.judgments[0].blocked, 0.5)
        self.assertEqual(scan.judgments[0].room_m, NO_LIMIT_M)

    def test_failed_scan_reads_blocked(self) -> None:
        brain = LocalBrain(detector=FakeDetector(fail=True), judge=FakeJudge(0.1))
        scan = brain.scan([(0, frame()), (90, frame())])
        self.assertTrue(all(judgment.blocked == 1.0 for judgment in scan.judgments.values()))

    def test_box_is_the_best_person_or_an_error(self) -> None:
        brain = LocalBrain(detector=FakeDetector([(0.8, (0.6, 0.2, 0.8, 0.9)), (0.4, (0.0, 0.0, 0.1, 0.1))]), judge=FakeJudge(0.0))
        box = brain.box(frame())
        self.assertAlmostEqual(box.center_x, 0.7)
        self.assertEqual(box.person, 0.8)
        with self.assertRaises(jev.JevError):
            LocalBrain(detector=FakeDetector(), judge=FakeJudge(0.0)).box(frame())


class LocalNavigatorTests(unittest.TestCase):
    def test_local_brain_steers_from_the_reflex_sides(self) -> None:
        class Reading:
            center_m, left_m, right_m, at = 1.5, 0.8, 2.5, 10.0

        nav = Navigator(Limits(), "local", started_at=10.0)
        command = nav.step(10.05, Reading(), Seen(0.1, "straight", 0.0, 0.0, 10.0))
        self.assertEqual(command.mode, "cruise")
        self.assertGreater(command.yaw_dps, 0)


if __name__ == "__main__":
    unittest.main()
