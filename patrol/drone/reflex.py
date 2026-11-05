"""Meters to the nearest thing ahead, fast enough to brake on.

Depth Anything V2 Metric-Indoor Small reads meters straight from one photo,
so it needs no floor in view. The drone flies into the middle third of the frame, around the horizon:
that is the room ahead. The floor just under the camera always reads about
2.5 m, so counting it as "ahead" caps every open view there and makes the
left and right sides look the same. The floor is kept on its own, and the
nearer of the two is what brakes. The 10th percentile is the near edge of
an obstacle, not one noisy pixel.

    .venv/bin/python -m patrol.drone.reflex artifacts/drone/recon/<run>/*.jpg
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models" / "depth-anything-v2-metric-indoor-small"
REPO_ID = "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
INPUT_HEIGHT = 364
HORIZON_ROWS = (0.15, 0.42)
FLOOR_ROWS = (0.42, 0.70)
COLUMNS = (1 / 3, 2 / 3)
NEAR_QUANTILE = 0.10


@dataclass(frozen=True)
class Reading:
    center_m: float
    left_m: float
    right_m: float
    seconds: float
    at: float
    near_m: float | None = None


def corridor_meters(depth) -> tuple[float, float, float, float]:
    """Horizon distance left, center and right, plus the floor in the center.

    The floor number is what is close under the camera. The three horizon
    numbers are the room the drone is flying into.
    """
    import torch

    height, width = depth.shape
    left_edge = int(width * COLUMNS[0])
    right_edge = int(width * COLUMNS[1])

    def near(part) -> float:
        return float(torch.quantile(part.reshape(-1).float(), NEAR_QUANTILE))

    def band(rows):
        return near(rows[:, left_edge:right_edge]), near(rows[:, :left_edge]), near(rows[:, right_edge:])

    horizon = depth[int(height * HORIZON_ROWS[0]) : int(height * HORIZON_ROWS[1])]
    floor = depth[int(height * FLOOR_ROWS[0]) : int(height * FLOOR_ROWS[1])]
    center, left, right = band(horizon)
    return center, left, right, band(floor)[0]


class Reflex:
    def __init__(self, model_dir: Path = MODEL_DIR, input_height: int = INPUT_HEIGHT) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        if not model_dir.is_dir():
            raise FileNotFoundError(f"missing weights: {model_dir}")
        self._torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._processor = AutoImageProcessor.from_pretrained(model_dir)
        self._model = AutoModelForDepthEstimation.from_pretrained(model_dir).to(self.device).eval()
        self._height = input_height
        self._lock = threading.Lock()

    def depth(self, image):
        """Meters per pixel at the model's resolution. One caller at a time on the device."""
        with self._lock:
            return self._depth(image)

    def _depth(self, image):
        torch = self._torch
        rgb = image.convert("RGB")
        width = round(rgb.width * self._height / rgb.height / 14) * 14
        inputs = self._processor(
            images=rgb,
            return_tensors="pt",
            size={"height": self._height, "width": width},
            keep_aspect_ratio=False,
        )
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.inference_mode():
            predicted = self._model(**inputs).predicted_depth
        if self.device == "mps":
            torch.mps.synchronize()
        return predicted.squeeze(0).float().cpu()

    def measure(self, image, at: float | None = None) -> Reading:
        started = time.perf_counter()
        center, left, right, floor = corridor_meters(self.depth(image))
        seconds = time.perf_counter() - started
        return Reading(center, left, right, seconds, time.monotonic() if at is None else at, min(center, floor))


def main(argv: list[str] | None = None) -> int:
    from PIL import Image

    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        print("give one or more photo paths")
        return 2
    reflex = Reflex()
    reflex.measure(Image.open(paths[0]))
    print(f"device {reflex.device}, input height {INPUT_HEIGHT}")
    for path in paths:
        reading = reflex.measure(Image.open(path))
        print(
            f"{path.parent.name}/{path.name}  ahead {reading.center_m:.2f} m  near {reading.near_m:.2f}"
            f"  left {reading.left_m:.2f}  right {reading.right_m:.2f}  {reading.seconds * 1000:.0f} ms"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
