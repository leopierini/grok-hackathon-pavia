"""Land on a printed ArUco marker seen by the downward camera.

The mission pad's x and y drift by 5 to 7 cm with height, so steering on them
cannot land within a centimeter. The marker is found in the downward video
instead: its center in the image is where the target is, and its printed size
turns pixels into centimeters at any height.

Print `artifacts/landing_marker.png` so the black square is `MARKER_CM` wide,
and lay it where the drone should land, within about 20 cm of the mission pad.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from patrol.drone.pad_land import PadLander

MARKER_ID = 0
MARKER_CM = 10.0
# The downward camera is not under the middle of the drone. How far ahead of
# the middle it sits, measured once on the real drone; 0 lands the camera on
# the marker.
CAMERA_FORWARD_CM = 0.0
MARKER_LOW_CM = 25
MARKER_CENTER_CM = 1.0
MARKER_SINK_CM = 3.0
# Descent starts once the marker is inside 25 cm. Waiting for 6 cm meant the
# drone hovered forever just outside the gate. Inside 6 cm the sideways stick
# rests, because 5 is the smallest stick the Tello accepts and it kicks the
# marker back out. From 40 cm down the mouth is 35 cm, so inside 15 cm it drops.
LAND_CM = 6.0
APPROACH_CM = 25.0
FUNNEL_ALT_CM = 40
FUNNEL_RADIUS_CM = 15.0
SINK_FAST = -18
SINK_UD = -8
FUNNEL_SINK = -30
SEARCH_S = 6.0
MARKER_PNG = Path(__file__).resolve().parents[2] / "artifacts" / "landing_marker.png"

_detector = None


@dataclass(frozen=True)
class Marker:
    cx: float
    cy: float
    side_px: float
    width: int
    height: int


def downward_view(image):
    """The real downward picture, without the green pad the stream adds under it.

    The downward camera is a 320x240 infrared sensor. Its stream is padded to
    the forward-camera height, and that padding is pure green. The green is
    the normal stream, so the picture is the rows above the first green run.
    """
    rgb = image.convert("RGB")
    arr = np.asarray(rgb)
    height, width = arr.shape[:2]
    red, green, blue = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    broken = (green > 80) & (red < 40) & (blue < 40)
    row = broken.mean(axis=1)
    run = 0
    cut = height
    for y, frac in enumerate(row):
        run = run + 1 if frac > 0.85 else 0
        if run >= 8:
            cut = y - 7
            break
    if cut < 32:
        return rgb
    return rgb.crop((0, 0, width, cut))


def usable(image) -> bool:
    """False for the green, half-decoded frames the Tello sends right after the camera switch."""
    rgb = np.asarray(image.convert("RGB"))
    if rgb.ndim != 3 or min(rgb.shape[:2]) < 32:
        return False
    height, width = rgb.shape[:2]
    if height > width * 1.2:
        return False
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    broken = (green > 80) & (red < 40) & (blue < 40)
    return float(broken.mean()) < 0.2


def _aruco():
    import cv2

    global _detector
    if _detector is None:
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        _detector = cv2.aruco.ArucoDetector(dictionary, params)
    return _detector


def find_marker(image, marker_id: int = MARKER_ID) -> Marker | None:
    """The marker's center and mean side length in pixels, or None."""
    gray = np.asarray(image.convert("L"))
    corners, ids, _rejected = _aruco().detectMarkers(gray)
    if ids is None:
        return None
    for quad, found in zip(corners, ids.flatten()):
        if int(found) != marker_id:
            continue
        points = quad.reshape(4, 2)
        sides = [float(np.linalg.norm(points[i] - points[(i + 1) % 4])) for i in range(4)]
        side = sum(sides) / 4
        if side < 8:
            return None
        cx, cy = points.mean(axis=0)
        height, width = gray.shape
        return Marker(float(cx), float(cy), side, width, height)
    return None


def landing_move(
    x: float,
    y: float,
    height_cm: int | None,
    held_s: float,
) -> tuple[int, bool, bool]:
    """Cone descent, then a committed drop into the funnel. Returns `(ud, level, land_now)`.

    `level` means the horizontal sticks stay at zero. Descent starts inside 25 cm
    and keeps steering until the marker is inside 6 cm. From 40 cm down the mouth
    is 35 cm across, so inside 15 cm it sinks hard and does not trim. `land` is
    under 25 cm. With no height it sinks slowly and does not land.
    """
    dist = math.hypot(x, y)
    del held_s
    if height_cm is not None and height_cm <= FUNNEL_ALT_CM:
        if dist > FUNNEL_RADIUS_CM:
            return 0, False, False
        if height_cm <= MARKER_LOW_CM:
            return 0, True, True
        return FUNNEL_SINK, True, False
    if dist > APPROACH_CM:
        return 0, False, False
    level = dist <= LAND_CM
    if height_cm is None:
        return SINK_UD, level, False
    return SINK_FAST, level, False


def marker_offset_cm(image, marker_id: int = MARKER_ID, marker_cm: float = MARKER_CM) -> tuple[float, float] | None:
    """Marker offset from the picture center, in cm. x is right, y is down."""
    mark = find_marker(image, marker_id)
    if mark is None:
        return None
    cm = marker_cm / mark.side_px
    return (mark.cx - mark.width / 2) * cm, (mark.cy - mark.height / 2) * cm


def write_marker_png(path: Path = MARKER_PNG, marker_id: int = MARKER_ID, dpi: int = 300) -> Path:
    """A printable marker: `MARKER_CM` wide at `dpi`, with a white margin the detector needs."""
    import cv2
    from PIL import Image

    side = int(round(MARKER_CM / 2.54 * dpi))
    margin = side // 4
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    square = cv2.aruco.generateImageMarker(dictionary, marker_id, side)
    page = np.full((side + 2 * margin, side + 2 * margin), 255, dtype=np.uint8)
    page[margin : margin + side, margin : margin + side] = square
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(page).save(path, dpi=(dpi, dpi))
    return path


class MarkerLander(PadLander):
    """`PadLander`'s calibration and stick loop, steering on the marker in the downward video."""

    low_z_cm = MARKER_LOW_CM
    center_cm = MARKER_CENTER_CM
    sink_cm = MARKER_SINK_CM
    what = "marker"
    # A full stick pulse walks a marker this size out of the downward picture.
    pulse_stick = 8

    def __init__(
        self,
        sdk,
        grabber,
        marker_id: int = MARKER_ID,
        marker_cm: float = MARKER_CM,
        camera_forward_cm: float = CAMERA_FORWARD_CM,
        say=print,
        sleep=time.sleep,
    ) -> None:
        super().__init__(sdk, wanted=None, say=say, sleep=sleep)
        self.grabber = grabber
        self.marker_id = marker_id
        self.marker_cm = marker_cm
        self.camera_forward_cm = camera_forward_cm
        self._frame_at = 0.0
        self.pulse_stick = type(self).pulse_stick
        self.image = None

    def _height(self) -> int | None:
        tof = self.sdk.snapshot().get("tof")
        if tof is None or not 5 <= int(tof) <= 400:
            return None
        return int(tof)

    def _read(self, after: float, timeout: float) -> tuple[float, float, int | None] | None:
        """Marker offset from the drone's middle, in cm along the image's x (right) and y (down)."""
        image, at = self.grabber.frame_after(max(after, self._frame_at + 1e-6), timeout)
        if image is None:
            self._miss = "video stopped"
            return None
        self._frame_at = at
        raw_size = image.size
        image = downward_view(image)
        self.image = image
        gray = np.asarray(image.convert("L"))
        _edges = np.abs(gray[:, 1:].astype(np.int16) - gray[:, :-1].astype(np.int16))
        # #region agent log
        try:
            import json
            _payload = {
                "sessionId": "a15148",
                "runId": "pre-fix",
                "hypothesisId": "A",
                "location": "marker_land.py:_read",
                "message": "downward frame",
                "data": {
                    "raw": list(raw_size),
                    "crop": list(image.size),
                    "gray_mean": round(float(gray.mean()), 1),
                    "gray_std": round(float(gray.std()), 1),
                    "saturated": round(float((gray > 240).mean()), 3),
                    "edge_p95": round(float(np.percentile(_edges, 95)), 1),
                    "usable": usable(image),
                },
                "timestamp": int(time.time() * 1000),
            }
            with open("/Users/ares-pc/localrepo/grok-hackathon-pavia/.cursor/debug-a15148.log", "a") as _fh:
                _fh.write(json.dumps(_payload) + "\n")
        except Exception:
            pass
        # #endregion
        if not usable(image):
            self._miss = "picture broken"
            return None
        mark = find_marker(image, self.marker_id)
        # #region agent log
        try:
            import json
            _payload = {
                "sessionId": "a15148",
                "runId": "pre-fix",
                "hypothesisId": "B",
                "location": "marker_land.py:_read",
                "message": "marker on the cropped infrared picture",
                "data": {
                    "found": mark is not None,
                    "side_px": None if mark is None else round(mark.side_px, 1),
                    "center": None if mark is None else [round(mark.cx, 1), round(mark.cy, 1)],
                },
                "timestamp": int(time.time() * 1000),
            }
            with open("/Users/ares-pc/localrepo/grok-hackathon-pavia/.cursor/debug-a15148.log", "a") as _fh:
                _fh.write(json.dumps(_payload) + "\n")
        except Exception:
            pass
        # #endregion
        if mark is None:
            self._miss = "marker not in the picture"
            return None
        cm = self.marker_cm / mark.side_px
        x = (mark.cx - mark.width / 2) * cm
        y = (mark.cy - mark.height / 2) * cm
        if self.forward is not None and self.camera_forward_cm:
            x -= self.forward[0] * self.camera_forward_cm
            y -= self.forward[1] * self.camera_forward_cm
        return x, y, self._height()

    def calibrate(self) -> bool:
        """The camera is bolted on, so image up is the nose and image right is drone right.

        A stick pulse is the wrong way to learn this. The vision hover cancels a
        small stick, the round trip measures only a couple of centimeters, and
        the drone walks until the marker sits on the edge of the picture.
        """
        # Measured on the drone: forward stick moves the marker right in the
        # picture, right stick moves it down. The nose is the left of the image.
        self.forward = (1.0, 0.0)
        self.right = (0.0, 1.0)
        self.say("marker axes from the flight (forward stick moves the marker right)")
        # #region agent log
        try:
            import json
            _payload = {
                "sessionId": "a15148",
                "runId": "post-fix",
                "hypothesisId": "D",
                "location": "marker_land.py:calibrate",
                "message": "fixed camera axes, no stick pulses",
                "data": {"forward": list(self.forward), "right": list(self.right)},
                "timestamp": int(time.time() * 1000),
            }
            with open("/Users/ares-pc/localrepo/grok-hackathon-pavia/.cursor/debug-a15148.log", "a") as _fh:
                _fh.write(json.dumps(_payload) + "\n")
        except Exception:
            pass
        # #endregion
        return True

    def steer(self, x: float, y: float, rest_cm: float = 3.0) -> tuple[int, int]:
        """Stick command that carries the drone toward the marker. (0, 0) when it is close.

        x and y are centimeters, right and down in the downward picture. On this
        drone a forward stick moves the marker right, and a right stick moves it down.
        """
        if self.forward is None or self.right is None:
            self.calibrate()
        if math.hypot(x, y) <= rest_cm:
            return 0, 0
        along_f, along_r = self._split(-x, -y)
        from patrol.drone.pad_land import stick

        # Softer than the pad loop. Stick 15 on a 10 cm error ran away last flight.
        return stick(0.35 * along_r), stick(0.35 * along_f)

    def find(self, timeout: float = SEARCH_S) -> tuple[float, float, int | None] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._rc()
            reading = self._read(time.monotonic() - 0.2, 0.5)
            if reading is not None:
                self.last = reading
                return reading
        return None

    def use_axes(self, forward: tuple[float, float], right: tuple[float, float]) -> None:
        """Stick directions from an earlier landing. The camera is bolted on, so they do not change."""
        self.forward, self.right = forward, right


if __name__ == "__main__":
    print(write_marker_png())
