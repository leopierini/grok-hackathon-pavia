"""Behavior checks for FakeDrone. Stdlib only."""

import ast
import asyncio
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from patrol.contract import AdapterError, InspectionRequest, RunContext
from patrol.drone import create_drone
from patrol.drone import fake as fake_module


ROOT = Path(__file__).resolve().parents[2]


class FakeDroneTests(unittest.TestCase):
    def test_fake_module_has_no_flight_sdk_or_socket(self) -> None:
        tree = ast.parse((ROOT / "patrol/drone/fake.py").read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.isdisjoint({"socket", "djitellopy", "cv2", "av"}))
        self.assertEqual(fake_module.FakeDrone.__module__, "patrol.drone.fake")

    def test_unknown_mode_and_scenario(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(AdapterError) as raised:
                create_drone(mode="sim", config={}, output_dir=Path(tmp))
            self.assertEqual(raised.exception.code, "invalid_input")
            with self.assertRaises(AdapterError) as raised:
                create_drone(
                    mode="fake",
                    config={"scenario": "pads"},
                    output_dir=Path(tmp),
                )
            self.assertEqual(raised.exception.code, "invalid_input")

    def test_cancel_does_not_take_off(self) -> None:
        with TemporaryDirectory() as tmp:
            drone = create_drone(mode="fake", config={}, output_dir=Path(tmp))

            async def run():
                await drone.connect()
                cancel = Event()
                cancel.set()
                ctx = RunContext("cancel", time.monotonic() + 30, cancel)
                return await drone.inspect(
                    InspectionRequest("room_2", "room_2_view_v1", "floor"), ctx
                )

            result = asyncio.run(run())
        self.assertEqual(result.outcome, "cancelled")
        self.assertNotIn("takeoff_attempt", drone.trace)

    def test_real_import_does_not_load_a_sdk(self) -> None:
        import sys

        sys.modules.pop("djitellopy", None)
        from patrol.drone import RealDrone

        self.assertNotIn("djitellopy", sys.modules)
        drone = RealDrone(config={}, output_dir=Path("."))

        async def run():
            await drone.connect()

        with self.assertRaises(AdapterError) as raised:
            asyncio.run(run())
        self.assertEqual(raised.exception.code, "unsupported")


if __name__ == "__main__":
    unittest.main()
