"""Occupancy grid + A* path planning from known poses (numpy only, no vendor imports).

"Mapping with known poses": the dog's odometry is the localisation, so there is no
scan matching. Each LiDAR scan (world/odom-frame points) is folded into a log-odds
grid; the planner then runs A* over the inflated grid.

Frame handling is isolated in `_obstacle_points`: scans are assumed to already be in
the same world/odom frame as the pose. If the real dog turns out to publish another
frame, that is the one function to change.

Cell convention: cell (i, j) = (column along +x, row along +y). The state array is
indexed [j, i], row 0 = lowest y. Not thread-safe: callers must serialise integrate(),
plan(), state(), blocked() and to_view().
"""

from __future__ import annotations

import base64
import heapq
import math

import numpy as np

from patrol.dog.lidar import LidarScan, Pose

RESOLUTION_M = 0.05
SIZE_M = 20.0
L_OCC = 0.85
L_FREE = -0.4
L_MIN = -4.0
L_MAX = 4.0
OCC_LOGODDS = 0.6
FREE_LOGODDS = -0.6
OBST_Z_MIN_M = 0.10
OBST_Z_MAX_M = 1.0
MAX_RAYS = 1500
GOAL_SEARCH_M = 0.5
BODY_EXCLUDE_RADIUS_M = 0.35

_SQRT2 = math.sqrt(2.0)
_INF = float("inf")


def _ground_z(points: np.ndarray, pose: Pose) -> float:
    """Same rule as lidar.to_body: pose ground height, else 5th percentile of scan z."""
    if pose[3] is not None:
        return float(pose[3])
    return float(np.percentile(points[:, 2], 5)) if len(points) else 0.0


def _obstacle_points(scan: LidarScan, pose: Pose) -> np.ndarray:
    """World-frame (x, y) of scan points inside the obstacle height band. (M, 2) float64.

    Non-finite points are dropped first (so one NaN cannot poison the ground estimate),
    and points within BODY_EXCLUDE_RADIUS_M (2D) of the pose are dropped last so the
    dog's own body and legs never become obstacles.
    """
    pts = np.asarray(scan.points, dtype=np.float64).reshape(-1, 3)
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) == 0:
        return np.zeros((0, 2))
    z = pts[:, 2] - _ground_z(pts, pose)
    keep = (z >= OBST_Z_MIN_M) & (z <= OBST_Z_MAX_M)
    keep &= np.hypot(pts[:, 0] - pose[0], pts[:, 1] - pose[1]) >= BODY_EXCLUDE_RADIUS_M
    return pts[keep, :2]


class OccupancyGrid:
    """Log-odds occupancy grid, SIZE_M square at RESOLUTION_M, centred on `center_xy`."""

    def __init__(self, center_xy: tuple[float, float] = (0.0, 0.0)) -> None:
        self.n = int(round(SIZE_M / RESOLUTION_M))
        self.x0 = float(center_xy[0]) - SIZE_M / 2.0
        self.y0 = float(center_xy[1]) - SIZE_M / 2.0
        self._logodds = np.zeros((self.n, self.n), dtype=np.float32)

    # -- coordinates ---------------------------------------------------------

    def world_to_cell(self, x: float, y: float) -> tuple[int, int] | None:
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        i = math.floor((x - self.x0) / RESOLUTION_M)
        j = math.floor((y - self.y0) / RESOLUTION_M)
        if 0 <= i < self.n and 0 <= j < self.n:
            return i, j
        return None

    def cell_to_world(self, i: int, j: int) -> tuple[float, float]:
        """Centre of cell (i, j) in world metres."""
        return (self.x0 + (i + 0.5) * RESOLUTION_M, self.y0 + (j + 0.5) * RESOLUTION_M)

    # -- mapping -------------------------------------------------------------

    def integrate(self, scan: LidarScan, pose: Pose | None) -> None:
        """Fold one scan into the map. No-op for a None pose or no obstacle points.

        Obstacle cells get L_OCC once per scan. Free space is ray-cast (2D) from the
        dog's cell to a deterministic subsample (<= MAX_RAYS, uniform in bearing) of the
        obstacle cells; a ray stops at the first obstacle cell of this scan so shadows
        behind obstacles stay unknown. Each free cell gets L_FREE at most once per scan.
        """
        if pose is None or scan is None:
            return
        xy = _obstacle_points(scan, pose)
        if len(xy) == 0:
            return
        ii = np.floor((xy[:, 0] - self.x0) / RESOLUTION_M).astype(np.int64)
        jj = np.floor((xy[:, 1] - self.y0) / RESOLUTION_M).astype(np.int64)
        inside = (ii >= 0) & (ii < self.n) & (jj >= 0) & (jj < self.n)
        if not inside.any():
            return
        flat = np.unique(jj[inside] * self.n + ii[inside])
        obs_j, obs_i = np.divmod(flat, self.n)
        obs = np.zeros((self.n, self.n), dtype=bool)
        obs[obs_j, obs_i] = True

        free = np.zeros((self.n, self.n), dtype=bool)
        start = self.world_to_cell(pose[0], pose[1])
        if start is not None:
            ei, ej = self._subsample_endpoints(obs_i, obs_j, start)
            self._cast_free(free, obs, start, ei, ej)

        lo = self._logodds
        lo[free & ~obs] += L_FREE
        lo[obs] += L_OCC
        np.clip(lo, L_MIN, L_MAX, out=lo)

    @staticmethod
    def _subsample_endpoints(obs_i, obs_j, start):
        if len(obs_i) <= MAX_RAYS:
            return obs_i, obs_j
        bearing = np.arctan2(obs_j - start[1], obs_i - start[0])
        order = np.argsort(bearing, kind="stable")
        pick = order[np.linspace(0, len(order) - 1, MAX_RAYS).astype(np.int64)]
        return obs_i[pick], obs_j[pick]

    @staticmethod
    def _cast_free(free, obs, start, ei, ej) -> None:
        """Mark cells strictly between `start` and each endpoint, stopping at obstacles."""
        di = ei - start[0]
        dj = ej - start[1]
        n = np.maximum(np.abs(di), np.abs(dj))
        keep = n > 0
        if not keep.any():
            return
        di, dj, n = di[keep], dj[keep], n[keep]
        steps = np.arange(int(n.max()))[None, :]  # k = 0 .. nmax-1
        nn = n[:, None]
        valid = steps < nn
        ci = start[0] + np.floor(steps * di[:, None] / nn + 0.5).astype(np.int64)
        cj = start[1] + np.floor(steps * dj[:, None] / nn + 0.5).astype(np.int64)
        ci = np.where(valid, ci, start[0])
        cj = np.where(valid, cj, start[1])
        hit = obs[cj, ci] & valid & (steps > 0)
        first_hit = np.where(hit.any(axis=1), hit.argmax(axis=1), n)
        ok = valid & (steps < first_hit[:, None])
        free[cj[ok], ci[ok]] = True

    def state(self) -> np.ndarray:
        """int8 (H, W): -1 unknown, 0 free, 1 occupied. Row 0 = lowest y."""
        out = np.full((self.n, self.n), -1, dtype=np.int8)
        out[self._logodds < FREE_LOGODDS] = 0
        out[self._logodds > OCC_LOGODDS] = 1
        return out

    def blocked(self, inflate_m: float = 0.30) -> np.ndarray:
        """Boolean (H, W): occupied cells dilated by a disc of radius `inflate_m`."""
        return self._dilate(self.state() == 1, inflate_m)

    def _dilate(self, occ: np.ndarray, inflate_m: float) -> np.ndarray:
        out = occ.copy()
        r = inflate_m / RESOLUTION_M
        rc = int(math.floor(r + 1e-9))
        n = self.n
        for dj in range(-rc, rc + 1):
            for di in range(-rc, rc + 1):
                if (di or dj) and di * di + dj * dj <= r * r + 1e-9:
                    out[max(dj, 0):n + min(dj, 0), max(di, 0):n + min(di, 0)] |= occ[
                        max(-dj, 0):n + min(-dj, 0), max(-di, 0):n + min(-di, 0)
                    ]
        return out

    # -- planning ------------------------------------------------------------

    def plan(
        self,
        start_xy: tuple[float, float],
        goal_xy: tuple[float, float],
        *,
        inflate_m: float = 0.30,
        unknown_cost: float = 3.0,
        max_expansions: int = 200_000,
    ) -> list[tuple[float, float]] | None:
        """A* (8-connected) over the inflated grid; world-metre waypoints or None.

        Free cells cost 1 per step, unknown cells `unknown_cost`; inflated-occupied
        cells are blocked. Escape: blocked-by-inflation cells within `inflate_m` of the
        start stay passable (raw occupied cells never do). A blocked goal is replaced
        by the cheapest-to-reach passable cell within GOAL_SEARCH_M of it (so a goal just
        outside a wall resolves to a reachable cell on the dog's side), else None. Waypoints are
        pruned by line-of-sight; first = start, last = goal (or the substitute).
        """
        s = self.world_to_cell(*start_xy)
        g = self.world_to_cell(*goal_xy)
        if s is None or g is None:
            return None

        state = self.state()
        occ = state == 1
        passable = ~self._dilate(occ, inflate_m)
        r = inflate_m / RESOLUTION_M
        rc = int(math.ceil(r))
        j_lo, j_hi = max(s[1] - rc, 0), min(s[1] + rc + 1, self.n)
        i_lo, i_hi = max(s[0] - rc, 0), min(s[0] + rc + 1, self.n)
        jj, ii = np.mgrid[j_lo:j_hi, i_lo:i_hi]
        near = (ii - s[0]) ** 2 + (jj - s[1]) ** 2 <= r * r + 1e-9
        passable[j_lo:j_hi, i_lo:i_hi] |= near & ~occ[j_lo:j_hi, i_lo:i_hi]
        passable[s[1], s[0]] = True

        goals = [g] if passable[g[1], g[0]] else self._goal_candidates(passable, g)
        if not goals:
            return None

        cells = self._astar(state, passable, s, g, goals, unknown_cost, max_expansions)
        if cells is None:
            return None
        cells = self._prune(cells, passable)
        path = [self.cell_to_world(i, j) for i, j in cells]
        path[0] = (float(start_xy[0]), float(start_xy[1]))
        if cells[-1] == g:
            path[-1] = (float(goal_xy[0]), float(goal_xy[1]))
        return path

    def _goal_candidates(self, passable, g) -> list[tuple[int, int]]:
        """Every passable cell within GOAL_SEARCH_M of goal cell g."""
        rc = int(math.ceil(GOAL_SEARCH_M / RESOLUTION_M))
        j_lo, j_hi = max(g[1] - rc, 0), min(g[1] + rc + 1, self.n)
        i_lo, i_hi = max(g[0] - rc, 0), min(g[0] + rc + 1, self.n)
        jj, ii = np.mgrid[j_lo:j_hi, i_lo:i_hi]
        near = (ii - g[0]) ** 2 + (jj - g[1]) ** 2 <= (GOAL_SEARCH_M / RESOLUTION_M) ** 2 + 1e-9
        ok = near & passable[j_lo:j_hi, i_lo:i_hi]
        return [(int(i), int(j)) for i, j in zip(ii[ok], jj[ok])]

    def _astar(self, state, passable, s, g, goals, unknown_cost, max_expansions):
        n = self.n
        w = n + 2  # one-cell border of impassable cells removes bounds checks
        cost = np.full((w, w), _INF)
        cost[1:-1, 1:-1] = np.where(state == -1, unknown_cost, 1.0)
        cost[1:-1, 1:-1][~passable] = _INF
        cl = cost.ravel().tolist()

        hmin = min(1.0, unknown_cost)
        d_straight, d_diag = hmin, hmin * _SQRT2
        gi, gj = g[0] + 1, g[1] + 1
        start = (s[1] + 1) * w + (s[0] + 1)
        goal_set = {(j + 1) * w + (i + 1) for i, j in goals}
        slack = 0.0 if len(goals) == 1 else GOAL_SEARCH_M / RESOLUTION_M
        moves = [
            (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, _SQRT2), (1, -1, _SQRT2), (-1, 1, _SQRT2), (1, 1, _SQRT2),
        ]

        def heur(i, j):
            dx, dy = abs(i - gi), abs(j - gj)
            if slack:  # any candidate within `slack` cells of the goal: stay admissible
                return d_straight * max(0.0, math.hypot(dx, dy) - slack)
            return d_straight * (dx + dy) + (d_diag - 2 * d_straight) * min(dx, dy)

        best = {start: 0.0}
        parent = {start: -1}
        closed = set()
        heap = [(heur(s[0] + 1, s[1] + 1), 0.0, start)]
        expansions = 0
        while heap:
            _, gcur, cur = heapq.heappop(heap)
            if cur in closed:
                continue
            if cur in goal_set:
                out = []
                while cur != -1:
                    j, i = divmod(cur, w)
                    out.append((i - 1, j - 1))
                    cur = parent[cur]
                return out[::-1]
            closed.add(cur)
            expansions += 1
            if expansions > max_expansions:
                return None
            cj, ci = divmod(cur, w)
            for di, dj, mult in moves:
                nxt = cur + dj * w + di
                c = cl[nxt]
                if c == _INF:
                    continue
                if mult != 1.0 and (cl[cur + di] == _INF or cl[cur + dj * w] == _INF):
                    continue  # no diagonal squeeze between two blocked cells
                ng = gcur + c * mult
                if ng < best.get(nxt, _INF):
                    best[nxt] = ng
                    parent[nxt] = cur
                    heapq.heappush(heap, (ng + heur(ci + di, cj + dj), ng, nxt))
        return None

    @staticmethod
    def _los(a, b, passable) -> bool:
        """True if the straight segment between the centres of cells a and b crosses only
        passable cells (exact grid traversal: every cell the segment passes through)."""
        x0, y0, x1, y1 = a[0] + 0.5, a[1] + 0.5, b[0] + 0.5, b[1] + 0.5
        ts = [np.array([0.0, 1.0])]
        if x1 != x0:
            xs = np.arange(math.floor(min(x0, x1)) + 1, math.ceil(max(x0, x1)))
            ts.append((xs - x0) / (x1 - x0))
        if y1 != y0:
            ys = np.arange(math.floor(min(y0, y1)) + 1, math.ceil(max(y0, y1)))
            ts.append((ys - y0) / (y1 - y0))
        t = np.sort(np.concatenate(ts))
        mid = (t[:-1] + t[1:]) / 2.0
        ci = np.floor(x0 + mid * (x1 - x0)).astype(np.int64)
        cj = np.floor(y0 + mid * (y1 - y0)).astype(np.int64)
        return bool(passable[cj, ci].all())

    def _prune(self, cells, passable):
        """Greedy line-of-sight pruning: keep only the corners of the A* path."""
        if len(cells) <= 2:
            return cells
        out = [cells[0]]
        anchor = 0
        while anchor < len(cells) - 1:
            far = anchor + 1
            for k in range(anchor + 2, len(cells)):
                if not self._los(cells[anchor], cells[k], passable):
                    break
                far = k
            out.append(cells[far])
            anchor = far
        return out

    # -- view ----------------------------------------------------------------

    def to_view(self, center_xy: tuple[float, float], radius_m: float = 4.0) -> dict:
        """Compact snapshot for the page: the state() crop around `center_xy`.

        {"t": "map", "res": metres/cell, "x0", "y0": world coordinates of the crop's
        lower-left corner (outer edge of its first cell), "w", "h": crop size in cells,
        "cells": base64 of the int8 crop, row-major, row 0 = lowest y, values
        -1 unknown / 0 free / 1 occupied}. The crop is clipped to the grid; a centre
        far outside gives w = h = 0 and cells = "".
        """
        r = int(math.ceil(radius_m / RESOLUTION_M))
        ci = math.floor((center_xy[0] - self.x0) / RESOLUTION_M)
        cj = math.floor((center_xy[1] - self.y0) / RESOLUTION_M)
        i_lo, i_hi = max(ci - r, 0), min(ci + r + 1, self.n)
        j_lo, j_hi = max(cj - r, 0), min(cj + r + 1, self.n)
        w, h = max(i_hi - i_lo, 0), max(j_hi - j_lo, 0)
        if w == 0 or h == 0:
            w = h = 0
            crop = np.zeros((0, 0), dtype=np.int8)
        else:
            crop = np.ascontiguousarray(self.state()[j_lo:j_hi, i_lo:i_hi])
        return {
            "t": "map",
            "res": RESOLUTION_M,
            "x0": self.x0 + i_lo * RESOLUTION_M,
            "y0": self.y0 + j_lo * RESOLUTION_M,
            "w": w,
            "h": h,
            "cells": base64.b64encode(crop.tobytes()).decode("ascii"),
        }
