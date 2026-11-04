"""Pure LiDAR processing for the joystick's live panel (numpy only, no vendor imports).

Frames: scans arrive in the world/odom frame (metres). The panel wants the dog's
body frame: x forward, y left, z = height above ground.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

VIEW_RADIUS_M = 4.0
MAX_VIEW_POINTS = 4000
FLOOR_CUTOFF_M = 0.10
CEILING_M = 2.0
BODY_FRONT_M = 0.35
AHEAD_HALF_WIDTH_M = 0.25
AHEAD_Z_MAX_M = 0.60
STALE_SCAN_S = 2.0
BRAKE_DISTANCE_M = 0.5    # joystick forward brake: obstacle closer than this (from the nose) => no forward
# Free distance per direction (follow mode's dodge). Bin i = heading i * 15 deg in the body frame
# (0 = forward, + = left), wrapped to (-180, 180]. Each bin: a corridor CLEAR_HALF_WIDTH_M either side
# of that heading, distance from the body's edge to the closest point in it, capped at VIEW_RADIUS_M.
CLEAR_BINS = 24
CLEAR_STEP_RAD = 2 * math.pi / CLEAR_BINS
BODY_HALF_WIDTH_M = 0.20  # Go2 is ~0.31 m wide; legs splay a little
CLEAR_HALF_WIDTH_M = 0.30 # dog half-width + 0.10 m margin (stricter than the brake corridor)
# Turning in place: how far the footprint (+ margin) can rotate each way before it would touch a point.
TURN_CHECK_STEP_DEG = 10
TURN_CHECK_MAX_DEG = 90
TURN_MARGIN_M = 0.08      # LiDAR lag (<= 5 Hz frames), voxel size, footprint uncertainty

# (x, y, yaw_rad, ground_z | None) in the same frame as the scan.
Pose = tuple[float, float, float, float | None]


@dataclass(frozen=True)
class LidarScan:
    points: np.ndarray  # (N, 3) float32, world/odom metres
    t: float  # monotonic receive time
    frame_id: str | None
    origin: tuple[float, float, float] | None
    resolution: float | None


def scan_from_message(msg: Mapping, t: float) -> LidarScan | None:
    """Vendor LiDAR message -> LidarScan. Anything unexpected -> None; never raises."""
    try:
        data = msg["data"]
        points = np.asarray(data["data"]["points"], dtype=np.float32)
        if points.ndim != 2 or points.shape[1] != 3:
            return None
        points = points[np.isfinite(points).all(axis=1)]
        origin = data.get("origin")
        resolution = data.get("resolution")
        frame_id = data.get("frame_id")
        return LidarScan(
            points=points,
            t=float(t),
            frame_id=str(frame_id) if frame_id is not None else None,
            origin=tuple(float(v) for v in origin) if origin is not None else None,
            resolution=float(resolution) if resolution is not None else None,
        )
    except Exception:
        return None


def _ground_z(points: np.ndarray, pose: Pose) -> float:
    if pose[3] is not None:
        return float(pose[3])
    return float(np.percentile(points[:, 2], 5)) if len(points) else 0.0


def to_body(points: np.ndarray, pose: Pose) -> np.ndarray:
    """World -> body frame (x forward, y left, z above ground). Returns (N, 3) float64."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    x, y, yaw, _ = pose
    dx = pts[:, 0] - x
    dy = pts[:, 1] - y
    c, s = math.cos(yaw), math.sin(yaw)
    return np.column_stack([c * dx + s * dy, -s * dx + c * dy, pts[:, 2] - _ground_z(pts, pose)])


def nearest_ahead(body_pts: np.ndarray) -> float | None:
    """Distance from the dog's nose to the closest obstacle in the corridor ahead, or None."""
    if len(body_pts) == 0:
        return None
    x, y, z = body_pts[:, 0], body_pts[:, 1], body_pts[:, 2]
    mask = (
        (x > BODY_FRONT_M)
        & (x <= VIEW_RADIUS_M)
        & (np.abs(y) <= AHEAD_HALF_WIDTH_M)
        & (z >= FLOOR_CUTOFF_M)
        & (z <= AHEAD_Z_MAX_M)
    )
    if not mask.any():
        return None
    return round(float(x[mask].min()) - BODY_FRONT_M, 2)


def clear_bin(body_angle: float) -> int:
    """Index of the clearance bin nearest to a body-frame heading (rad, + = left)."""
    a = math.atan2(math.sin(body_angle), math.cos(body_angle))
    return int(round(a / CLEAR_STEP_RAD)) % CLEAR_BINS


def clearance(body_pts: np.ndarray) -> list[float]:
    """Free distance (m, from the body's edge) along each of CLEAR_BINS body-frame headings.
    Only points between the floor cutoff and AHEAD_Z_MAX_M count; points inside the body's own
    footprint are ignored. Nothing seen in a corridor => VIEW_RADIUS_M."""
    pts = np.asarray(body_pts, dtype=np.float64).reshape(-1, 3)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    keep = ((z >= FLOOR_CUTOFF_M) & (z <= AHEAD_Z_MAX_M)
            & ~((np.abs(x) <= BODY_FRONT_M) & (np.abs(y) <= BODY_HALF_WIDTH_M)))
    x, y = x[keep], y[keep]
    ang = np.arange(CLEAR_BINS) * CLEAR_STEP_RAD
    c, s = np.cos(ang), np.sin(ang)
    with np.errstate(divide="ignore"):
        extent = np.minimum(BODY_FRONT_M / np.abs(c), BODY_HALF_WIDTH_M / np.abs(s))
    out = [VIEW_RADIUS_M] * CLEAR_BINS
    if len(x) == 0:
        return out
    u = x[:, None] * c[None, :] + y[:, None] * s[None, :]        # along the heading
    w = -x[:, None] * s[None, :] + y[:, None] * c[None, :]       # across it
    hit = (u > 0) & (np.abs(w) <= CLEAR_HALF_WIDTH_M) & (u <= VIEW_RADIUS_M + extent[None, :])
    for i in range(CLEAR_BINS):
        col = hit[:, i]
        if col.any():
            out[i] = round(float(min(VIEW_RADIUS_M, max(0.0, u[col, i].min() - extent[i]))), 2)
    return out


def turn_clearance(body_pts: np.ndarray) -> float:
    """Distance from the body CENTRE to the closest obstacle point in any direction (same height
    band, own footprint ignored), capped at VIEW_RADIUS_M. Turning in place sweeps the body's
    corners through a circle of ~0.39 m: the follower doesn't turn when this is smaller than that."""
    pts = np.asarray(body_pts, dtype=np.float64).reshape(-1, 3)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    keep = ((z >= FLOOR_CUTOFF_M) & (z <= AHEAD_Z_MAX_M)
            & ~((np.abs(x) <= BODY_FRONT_M) & (np.abs(y) <= BODY_HALF_WIDTH_M)))
    if not keep.any():
        return VIEW_RADIUS_M
    return float(min(VIEW_RADIUS_M, np.hypot(x[keep], y[keep]).min()))


def turn_room(body_pts: np.ndarray) -> tuple[int, int]:
    """(left_deg, right_deg): how far the dog can turn in place each way (multiples of
    TURN_CHECK_STEP_DEG, up to TURN_CHECK_MAX_DEG) before its footprint + TURN_MARGIN_M would
    contain an obstacle point (same height band; points inside the bare footprint = own body,
    ignored). A point already within the margin => 0 both ways."""
    pts = np.asarray(body_pts, dtype=np.float64).reshape(-1, 3)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    hx, hy = BODY_FRONT_M + TURN_MARGIN_M, BODY_HALF_WIDTH_M + TURN_MARGIN_M
    keep = ((z >= FLOOR_CUTOFF_M) & (z <= AHEAD_Z_MAX_M)
            & ~((np.abs(x) <= BODY_FRONT_M) & (np.abs(y) <= BODY_HALF_WIDTH_M))
            & (np.hypot(x, y) <= math.hypot(hx, hy) + 1e-9))      # only points the sweep can reach
    x, y = x[keep], y[keep]
    out = []
    for sign in (1.0, -1.0):                       # + = turn left (body rotates +, points rotate -)
        room = TURN_CHECK_MAX_DEG
        for deg in range(0, TURN_CHECK_MAX_DEG + 1, TURN_CHECK_STEP_DEG):
            a = math.radians(deg) * sign
            c, s = math.cos(a), math.sin(a)
            xr, yr = c * x + s * y, -s * x + c * y   # points in the rotated body frame
            if ((np.abs(xr) <= hx) & (np.abs(yr) <= hy)).any():
                room = max(0, deg - TURN_CHECK_STEP_DEG)
                break
        out.append(room)
    return out[0], out[1]


def brake_forward(vx: float, nearest_ahead_m: float | None) -> tuple[float, str | None]:
    """Forward brake: (0.0, reason) when moving forward with an obstacle closer than
    BRAKE_DISTANCE_M ahead, else (vx, None). Turning, sideways and backward are never braked."""
    if vx > 0 and nearest_ahead_m is not None and nearest_ahead_m < BRAKE_DISTANCE_M:
        return 0.0, f"obstacle {nearest_ahead_m:.2f} m ahead (< {BRAKE_DISTANCE_M:g} m)"
    return vx, None


def build_view(scan: LidarScan | None, pose: Pose | None, now: float) -> dict:
    """The JSON-able frame the panel draws. Always returns a complete dict."""
    view = {
        "t": "lidar",
        "n": 0,
        "pts": [],
        "age_s": None,
        "stale": False,
        "nearest_ahead_m": None,
        "frame_id": None,
        "radius_m": VIEW_RADIUS_M,
        "reason": None,
        "clear": None,       # {"yaw": odom yaw the bins are relative to, "step_deg": 15, "m": [24 floats]}
    }
    if scan is None:
        view["reason"] = "no scan"
        return view

    age = max(0.0, now - scan.t)
    view["age_s"] = round(age, 2)
    view["stale"] = age > STALE_SCAN_S
    view["frame_id"] = scan.frame_id
    if pose is None:
        view["reason"] = "position unknown"
        return view

    body = to_body(scan.points, pose)
    view["nearest_ahead_m"] = nearest_ahead(body)
    view["clear"] = {"yaw": round(float(pose[2]), 4), "step_deg": round(math.degrees(CLEAR_STEP_RAD)),
                     "m": clearance(body), "near_m": round(turn_clearance(body), 2),
                     "turn_room": list(turn_room(body))}

    keep = (
        (body[:, 2] >= FLOOR_CUTOFF_M)
        & (body[:, 2] <= CEILING_M)
        & (np.abs(body[:, 0]) <= VIEW_RADIUS_M)
        & (np.abs(body[:, 1]) <= VIEW_RADIUS_M)
    )
    body = body[keep]
    if len(body) > MAX_VIEW_POINTS:
        body = body[np.linspace(0, len(body) - 1, MAX_VIEW_POINTS).astype(int)]
    view["n"] = len(body)
    view["pts"] = np.rint(body * 100).astype(int).ravel().tolist()
    return view


def synthetic_room_points(resolution: float = 0.05) -> np.ndarray:
    """World-frame (N, 3) points: 6 x 5 m room (walls 0-1 m, floor at z=0) and two 0.4 m cubes."""

    def axis(lo: float, hi: float) -> np.ndarray:
        n = int(round((hi - lo) / resolution))
        return lo + resolution * np.arange(n + 1)

    def grid(xs, ys, zs) -> np.ndarray:
        return np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1).reshape(-1, 3)

    def cube(cx: float, cy: float) -> np.ndarray:
        xs, ys, zs = axis(cx - 0.2, cx + 0.2), axis(cy - 0.2, cy + 0.2), axis(0.0, 0.4)
        g = grid(xs, ys, zs)
        on_shell = (
            np.isclose(g[:, 0], xs[0]) | np.isclose(g[:, 0], xs[-1])
            | np.isclose(g[:, 1], ys[0]) | np.isclose(g[:, 1], ys[-1])
            | np.isclose(g[:, 2], zs[0]) | np.isclose(g[:, 2], zs[-1])
        )
        return g[on_shell]

    xs, ys, zs = axis(-3.0, 3.0), axis(-2.5, 2.5), axis(0.0, 1.0)
    floor = grid(xs, ys, [0.0])
    walls = np.concatenate([
        grid(xs, [-2.5, 2.5], zs),
        grid([-3.0, 3.0], ys, zs),
    ])
    pts = np.concatenate([floor, walls, cube(1.5, 0.0), cube(-1.0, 1.5)])
    return np.unique(np.round(pts, 6), axis=0)


def save_scan(scan: LidarScan, stem: Path) -> tuple[Path, Path]:
    """Write <stem>.npy (float32 N x 3) and an ASCII <stem>.ply."""
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    npy = stem.parent / (stem.name + ".npy")
    ply = stem.parent / (stem.name + ".ply")
    pts = np.asarray(scan.points, dtype=np.float32)
    np.save(npy, pts)
    header = (
        "ply\nformat ascii 1.0\n"
        f"element vertex {len(pts)}\n"
        "property float x\nproperty float y\nproperty float z\nend_header\n"
    )
    with ply.open("w") as f:
        f.write(header)
        np.savetxt(f, pts, fmt="%.4f")
    return npy, ply
