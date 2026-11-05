"""Score which side of a still looks farther, and how far that is.

Uses the local Depth Anything V2 Large weights. Higher raw values are closer.
The raw values are inverse depth up to an unknown scale and offset. The floor
in the bottom of the frame is a plane at a known height, so fitting the model
to it gives that scale, and the band ahead can be read in meters.

    .venv/bin/python -m patrol.drone.depth_look artifacts/drone/forward.jpg
"""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models" / "depth-anything-v2-large"

# Checkerboard calibration of the Tello front camera at 960x720, and its pitch
# in flight (https://lucarosu.com/TELLOpage.html). The 82.6° on the spec sheet
# is wrong: 905 px is 56° horizontal, 67° diagonal. The camera is fixed and
# held at about 13.5° below horizontal while flying.
FOCAL_PX_AT_960 = 905.0
CAMERA_TILT_DEG = 13.5
LENS_ABOVE_TOF_M = 0.02
BAND = (0.12, 0.42)
FLOOR_ROWS = (0.70, 0.98)
NEAREST_M = 0.2
FARTHEST_M = 6.0
FIT_TOLERANCE = 0.35
FLOOR_CLEAN = 0.08
FLOOR_MIN_ROWS = 8


@dataclass
class FloorFit:
    """raw = a / z + b, where z is depth along the camera axis in meters."""

    a: float
    b: float
    residual: float
    rows: int

    def meters(self, raw: torch.Tensor) -> torch.Tensor:
        inverse = (raw - self.b) / self.a
        far = torch.full_like(raw, FARTHEST_M)
        z = torch.where(inverse > 1.0 / FARTHEST_M, 1.0 / inverse.clamp_min(1e-6), far)
        return z.clamp(NEAREST_M, FARTHEST_M)


def focal_px(width: int, height: int) -> float:
    return FOCAL_PX_AT_960 * width / 960


def floor_depth_m(row: float, height_px: int, width_px: int, camera_m: float, tilt_deg: float) -> float | None:
    """Depth along the camera axis of the floor seen by one pixel row, or None above the horizon."""
    f = focal_px(width_px, height_px)
    below_axis = math.atan((row - height_px / 2) / f)
    below_horizon = math.radians(tilt_deg) + below_axis
    if below_horizon < math.radians(2):
        return None
    return camera_m * math.cos(below_axis) / math.sin(below_horizon)


def floor_fit(
    closer: torch.Tensor,
    camera_m: float,
    tilt_deg: float = CAMERA_TILT_DEG,
    tolerance: float = FIT_TOLERANCE,
) -> FloorFit | None:
    """Fit the model to the floor in front of the drone.

    Only the center columns of the bottom rows are used. Something ahead
    hides the far floor, never the near floor, so the real floor is the rows
    from the bottom up to some point. The longest such run that follows the
    floor curve wins.
    """
    if camera_m is None or camera_m <= 0.1:
        return None
    height, width = closer.shape
    third = max(width // 3, 1)
    rows = []
    for row in range(int(height * FLOOR_ROWS[0]), int(height * FLOOR_ROWS[1]), 4):
        z = floor_depth_m(row + 0.5, height, width, camera_m, tilt_deg)
        if z is None:
            continue
        raw = float(torch.median(closer[row, third : third * 2]))
        rows.append((1.0 / z, raw))
    best = None
    for start in range(0, len(rows) - FLOOR_MIN_ROWS + 1):
        run = rows[start:]
        line = _line(run)
        if line is None or line[0] <= 0:
            continue
        residual = _residual(run, line)
        if residual <= FLOOR_CLEAN:
            best = (line, residual, len(run))
            break
        if best is None or residual < best[1]:
            best = (line, residual, len(run))
    if best is None:
        return None
    (a, b), residual, count = best
    if residual > tolerance:
        return None
    return FloorFit(a=a, b=b, residual=residual, rows=count)


def _residual(points: list[tuple[float, float]], line: tuple[float, float]) -> float:
    """Misfit of the line, as a share of how much the floor values change."""
    a, b = line
    raws = torch.tensor([raw for _x, raw in points])
    spread = float(raws.std())
    misfit = float(torch.tensor([raw - (a * x + b) for x, raw in points]).pow(2).mean().sqrt())
    return misfit / spread if spread > 1e-6 else 1.0


def _line(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    n = len(points)
    mean_x = sum(x for x, _y in points) / n
    mean_y = sum(y for _x, y in points) / n
    var_x = sum((x - mean_x) ** 2 for x, _y in points)
    if var_x <= 1e-12:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / var_x
    return slope, mean_y - slope * mean_x


def free_distance_m(closer: torch.Tensor, fit: FloorFit) -> float:
    """Meters to the nearest real thing in the band ahead, about the drone's width.

    The 10th percentile is the near edge of an obstacle, not one noisy pixel.
    """
    height, width = closer.shape
    third = max(width // 3, 1)
    band = closer[int(height * BAND[0]) : int(height * BAND[1]), third : third * 2]
    meters = fit.meters(band).reshape(-1)
    return float(torch.quantile(meters, 0.10))


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("give one or more image paths")
        return 2
    if not MODEL_DIR.is_dir():
        print(f"missing weights: {MODEL_DIR}")
        return 1
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    processor = AutoImageProcessor.from_pretrained(MODEL_DIR)
    model = AutoModelForDepthEstimation.from_pretrained(MODEL_DIR).to(device).eval()
    for raw in args:
        path = Path(raw)
        closer = _predict(model, processor, path, device)
        scores = _sectors(closer)
        freest = min(scores, key=scores.get)
        print(f"{path.name}  device={device}")
        for name, value in scores.items():
            mark = "  freest" if name == freest else ""
            print(f"  {name:6} closer={value:.3f}{mark}")
        _save(path, closer)
    return 0


def _predict(model, processor, path: Path, device: str) -> torch.Tensor:
    image = Image.open(path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    if device == "mps":
        torch.mps.synchronize()
    started = time.perf_counter()
    with torch.inference_mode():
        depth = model(**inputs).predicted_depth
    if device == "mps":
        torch.mps.synchronize()
    elapsed = time.perf_counter() - started
    closer = F.interpolate(
        depth.unsqueeze(1),
        size=(image.height, image.width),
        mode="bicubic",
        align_corners=False,
    ).squeeze(0).squeeze(0)
    print(f"{path.name}  {image.size[0]}x{image.size[1]}  {elapsed:.2f}s")
    return closer.detach().float().cpu()


def openness(closer: torch.Tensor) -> float:
    """How open the center looks, compared with the sides of the same frame.

    The raw depth is not meters, and it is not comparable across photos.
    A value above 1 means the middle of this picture is farther than its edges.
    """
    height, width = closer.shape
    # The bottom of the frame is the floor under the drone. It is always
    # close and says nothing about the gap ahead, so the score uses only
    # the band in front, above that floor.
    band = closer[int(height * BAND[0]) : int(height * BAND[1])]
    third = max(width // 3, 1)
    center = float(torch.median(band[:, third : third * 2]))
    sides = torch.cat(
        [band[:, :third].reshape(-1), band[:, third * 2 :].reshape(-1)]
    )
    side = float(torch.median(sides))
    if center <= 1e-6:
        return 1.0
    return side / center


def _sectors(closer: torch.Tensor) -> dict[str, float]:
    """Median closeness in the middle band, split left / center / right."""
    height, width = closer.shape
    band = closer[int(height * BAND[0]) : int(height * BAND[1])]
    third = width // 3
    parts = {
        "left": band[:, :third],
        "center": band[:, third : third * 2],
        "right": band[:, third * 2 :],
    }
    return {name: float(torch.median(values)) for name, values in parts.items()}


def _save(path: Path, closer: torch.Tensor) -> None:
    span = closer.max() - closer.min()
    far = (1 - (closer - closer.min()) / span.clamp_min(1e-6)) * 255
    out = path.with_name(path.stem + "-depth.png")
    Image.fromarray(far.byte().numpy()).save(out)
    print(f"  wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
