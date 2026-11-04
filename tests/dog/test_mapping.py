"""Occupancy grid + A* planner ("mapping with known poses") on the synthetic room."""

import base64
import time

import numpy as np
import pytest

from patrol.dog import mapping as M
from patrol.dog.lidar import LidarScan, synthetic_room_points

POSE = (0.0, 0.0, 0.0, 0.0)
CUBE = (1.3, 1.7, -0.2, 0.2)  # xmin, xmax, ymin, ymax of the cube at (1.5, 0)


def make_scan(points) -> LidarScan:
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    return LidarScan(points=pts, t=0.0, frame_id="odom", origin=None, resolution=0.05)


def room_grid(n: int = 3, pose=POSE) -> M.OccupancyGrid:
    g = M.OccupancyGrid()
    scan = make_scan(synthetic_room_points())
    for _ in range(n):
        g.integrate(scan, pose)
    return g


def state_at(g: M.OccupancyGrid, x: float, y: float) -> int:
    i, j = g.world_to_cell(x, y)
    return int(g.state()[j, i])


def any_occupied_near(g: M.OccupancyGrid, x: float, y: float, tol: float = 0.08) -> bool:
    st = g.state()
    for dx in np.arange(-tol, tol + 1e-9, M.RESOLUTION_M):
        for dy in np.arange(-tol, tol + 1e-9, M.RESOLUTION_M):
            c = g.world_to_cell(x + dx, y + dy)
            if c is not None and st[c[1], c[0]] == 1:
                return True
    return False


def cluster_points(cx: float, cy: float, half: float = 0.15) -> np.ndarray:
    # Sample at cell centres so float rounding cannot merge points into fewer cells.
    xs = np.arange(cx - half, cx + half, 0.05) + 0.025
    ys = np.arange(cy - half, cy + half, 0.05) + 0.025
    zs = np.arange(0.15, 0.8, 0.05)
    return np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1).reshape(-1, 3)


def dist_to_cube(x: float, y: float) -> float:
    dx = max(CUBE[0] - x, 0.0, x - CUBE[1])
    dy = max(CUBE[2] - y, 0.0, y - CUBE[3])
    return float(np.hypot(dx, dy))


def segment_samples(path, step=0.01):
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        n = max(1, int(np.hypot(x1 - x0, y1 - y0) / step))
        for t in np.linspace(0.0, 1.0, n + 1):
            yield x0 + t * (x1 - x0), y0 + t * (y1 - y0)


# --- integrate / state ------------------------------------------------------


def test_new_grid_is_all_unknown():
    g = M.OccupancyGrid()
    st = g.state()
    assert st.dtype == np.int8
    assert st.shape == (400, 400)
    assert (st == -1).all()


def test_walls_occupied_and_floor_never_occupied():
    g = room_grid()
    assert any_occupied_near(g, 3.0, 0.0)
    assert any_occupied_near(g, -3.0, 1.0)
    assert any_occupied_near(g, 0.5, 2.5)
    assert any_occupied_near(g, 0.5, -2.5)
    # Every occupied cell lies on a wall or a cube; nothing on the open floor.
    st = g.state()
    js, is_ = np.nonzero(st == 1)
    for i, j in zip(is_, js):
        x, y = g.cell_to_world(int(i), int(j))
        on_wall = abs(abs(x) - 3.0) < 0.1 or abs(abs(y) - 2.5) < 0.1
        near_cube = dist_to_cube(x, y) < 0.1 or np.hypot(x + 1.0, y - 1.5) < 0.4
        assert on_wall or near_cube, (x, y)


def test_clear_line_of_sight_is_free():
    g = room_grid()
    assert state_at(g, 0.8, -1.0) == 0


def test_cell_behind_cube_is_not_free():
    g = room_grid()
    assert state_at(g, 2.2, 0.0) in (-1, 1)


def test_ground_taken_from_scan_when_pose_has_none():
    pts = synthetic_room_points().copy()
    pts[:, 2] += 5.0
    g = M.OccupancyGrid()
    scan = make_scan(pts)
    for _ in range(3):
        g.integrate(scan, (0.0, 0.0, 0.0, None))
    assert any_occupied_near(g, 3.0, 0.0)
    assert state_at(g, 0.8, -1.0) == 0


def test_moving_obstacle_appears_then_clears():
    # Half-cell point spacing: with 0.05 m spacing the points alias onto every other wall
    # cell, which leaves permanent gaps in the free-space ray fan for a static pose.
    room = synthetic_room_points(0.025)
    with_cluster = make_scan(np.concatenate([room, cluster_points(1.0, -1.5)]))
    without = make_scan(room)
    g = M.OccupancyGrid()
    for _ in range(3):
        g.integrate(with_cluster, POSE)
    cells = [g.world_to_cell(1.0 + dx, -1.5 + dy) for dx in (-0.1, 0, 0.1) for dy in (-0.1, 0, 0.1)]
    st = g.state()
    assert all(st[j, i] == 1 for i, j in cells)
    for _ in range(10):
        g.integrate(without, POSE)
    st = g.state()
    assert all(st[j, i] != 1 for i, j in cells)


def test_pose_none_and_empty_scan_are_noops():
    g = M.OccupancyGrid()
    g.integrate(make_scan(synthetic_room_points()), None)
    assert (g.state() == -1).all()
    g.integrate(make_scan(np.zeros((0, 3))), POSE)
    assert (g.state() == -1).all()


def test_nan_point_does_not_wipe_scan_with_ground_fallback():
    pts = synthetic_room_points().copy()
    pts[5] = (np.nan, np.nan, np.nan)
    pts[9, 2] = np.inf
    g = M.OccupancyGrid()
    for _ in range(3):
        g.integrate(make_scan(pts), (0.0, 0.0, 0.0, None))
    assert any_occupied_near(g, 3.0, 0.0)
    assert state_at(g, 0.8, -1.0) == 0


def test_points_near_the_dog_are_not_obstacles():
    ring = lambda r: np.array(  # noqa: E731
        [[r * np.cos(a), r * np.sin(a), 0.3] for a in np.linspace(0, 2 * np.pi, 40, endpoint=False)]
    )
    assert M.BODY_EXCLUDE_RADIUS_M == 0.35
    g = M.OccupancyGrid()
    g.integrate(make_scan(ring(0.25)), POSE)  # legs / body
    assert (g.state() == -1).all()
    g.integrate(make_scan(ring(0.6)), POSE)  # real obstacles
    assert (g.state() == 1).any()
    # exclusion is around the pose, not the origin
    g2 = M.OccupancyGrid()
    g2.integrate(make_scan(ring(0.25) + [2.0, 0.0, 0.0]), (2.0, 0.0, 0.0, 0.0))
    assert (g2.state() == -1).all()


def test_points_outside_grid_are_ignored():
    g = M.OccupancyGrid()
    far = np.array([[50.0, 50.0, 0.5], [-30.0, 2.0, 0.5], [1.0, 1.0, 0.5]])
    g.integrate(make_scan(far), POSE)
    st = g.state()
    assert (st == 1).sum() >= 1  # the in-grid point only
    assert state_at(g, 1.0, 1.0) == 1


def test_integrate_is_deterministic_with_many_endpoints():
    rng = np.random.default_rng(0)
    ang = rng.uniform(0, 2 * np.pi, 20000)
    r = rng.uniform(0.5, 8.0, 20000)
    pts = np.column_stack([r * np.cos(ang), r * np.sin(ang), rng.uniform(0.15, 0.9, 20000)])
    a, b = M.OccupancyGrid(), M.OccupancyGrid()
    a.integrate(make_scan(pts), POSE)
    b.integrate(make_scan(pts), POSE)
    assert (a.state() == b.state()).all()


# --- coordinates ------------------------------------------------------------


def test_world_cell_round_trip_and_outside():
    g = M.OccupancyGrid(center_xy=(1.0, -2.0))
    for x, y in [(1.0, -2.0), (-8.9, 7.9), (10.9, -11.9), (3.33, 0.17)]:
        i, j = g.world_to_cell(x, y)
        cx, cy = g.cell_to_world(i, j)
        assert abs(cx - x) <= M.RESOLUTION_M / 2 + 1e-9
        assert abs(cy - y) <= M.RESOLUTION_M / 2 + 1e-9
        assert g.world_to_cell(cx, cy) == (i, j)
    assert g.world_to_cell(11.5, 0.0) is None
    assert g.world_to_cell(0.0, -12.5) is None
    assert g.world_to_cell(float("nan"), 0.0) is None


# --- planning ---------------------------------------------------------------


def test_plan_goes_around_cube():
    g = room_grid()
    path = g.plan((0.0, 0.0), (2.5, 0.0))
    assert path is not None
    assert path[0] == (0.0, 0.0)
    assert path[-1] == (2.5, 0.0)
    length = sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:]))
    assert length > 2.5 + 0.05
    assert len(path) < 15  # straight runs collapsed
    blocked = g.blocked(0.30)
    for x, y in segment_samples(path):
        i, j = g.world_to_cell(x, y)
        assert not blocked[j, i], (x, y)
        # Cell quantisation (occupied cell + sampled cell) costs up to ~1.5 cells.
        assert dist_to_cube(x, y) >= 0.30 - 1.5 * M.RESOLUTION_M, (x, y)


def test_plan_straight_line_collapses_to_two_points():
    g = room_grid()
    path = g.plan((-2.0, -1.0), (-2.0, 0.5))
    assert path == [(-2.0, -1.0), (-2.0, 0.5)]


@pytest.mark.parametrize(
    "goal",
    [(3.0, 0.0), (3.05, 0.5), (0.5, 2.55), (-3.05, 0.5)],  # in a wall / just outside one
)
def test_plan_blocked_goal_resolves_to_reachable_cell_on_dog_side(goal):
    g = room_grid()
    path = g.plan((0.0, 0.0), goal)
    assert path is not None
    last = path[-1]
    assert np.hypot(last[0] - goal[0], last[1] - goal[1]) <= 0.5 + M.RESOLUTION_M
    i, j = g.world_to_cell(*last)
    assert not g.blocked(0.30)[j, i]
    assert abs(last[0]) < 3.0 and abs(last[1]) < 2.5  # inside the room


def test_plan_start_inside_inflation_still_succeeds():
    g = room_grid()
    start = (0.0, -2.3)  # 0.2 m from the south wall
    i, j = g.world_to_cell(*start)
    assert g.blocked(0.30)[j, i]
    path = g.plan(start, (0.0, 0.0))
    assert path is not None
    assert path[0] == start
    assert path[-1] == (0.0, 0.0)


def test_plan_unreachable_outside_closed_room_returns_none():
    g = room_grid()
    assert g.plan((0.0, 0.0), (4.5, 0.0)) is None


def test_plan_outside_grid_returns_none():
    g = room_grid()
    assert g.plan((0.0, 0.0), (50.0, 0.0)) is None
    assert g.plan((50.0, 0.0), (0.0, 0.0)) is None


def test_plan_max_expansions_exceeded_returns_none():
    g = room_grid()
    assert g.plan((0.0, 0.0), (2.5, 0.0), max_expansions=10) is None


def test_plan_through_unknown_space_is_allowed():
    g = M.OccupancyGrid()
    path = g.plan((0.0, 0.0), (3.0, 0.0))  # all unknown is traversable
    assert path == [(0.0, 0.0), (3.0, 0.0)]


def test_blocked_inflates_occupied_by_disc():
    g = room_grid()
    b = g.blocked(0.30)
    st = g.state()
    assert b[st == 1].all()
    # a point 0.25 m in front of the east wall is blocked, 0.6 m is not
    i, j = g.world_to_cell(2.75, 0.8)
    assert b[j, i]
    i, j = g.world_to_cell(2.4, 0.8)
    assert not b[j, i]
    assert (g.blocked(0.0) == (st == 1)).all()


# --- view -------------------------------------------------------------------


def test_to_view_matches_state_crop():
    g = room_grid()
    v = g.to_view((0.0, 0.0), radius_m=2.0)
    assert v["t"] == "map"
    assert v["res"] == M.RESOLUTION_M
    cells = np.frombuffer(base64.b64decode(v["cells"]), dtype=np.int8)
    assert cells.size == v["w"] * v["h"]
    arr = cells.reshape(v["h"], v["w"])
    i0 = int(round((v["x0"] - (-10.0)) / M.RESOLUTION_M))
    j0 = int(round((v["y0"] - (-10.0)) / M.RESOLUTION_M))
    assert (arr == g.state()[j0:j0 + v["h"], i0:i0 + v["w"]]).all()
    assert abs(v["w"] * M.RESOLUTION_M - 4.0) <= 2 * M.RESOLUTION_M
    assert (arr == 1).any() and (arr == 0).any()


def test_to_view_clips_at_grid_edge_and_outside():
    g = M.OccupancyGrid()
    v = g.to_view((9.5, 0.0), radius_m=4.0)
    assert v["x0"] + v["w"] * M.RESOLUTION_M <= 10.0 + 1e-9
    cells = np.frombuffer(base64.b64decode(v["cells"]), dtype=np.int8)
    assert cells.size == v["w"] * v["h"]
    far = g.to_view((100.0, 100.0))
    assert far["w"] == 0 and far["h"] == 0 and far["cells"] == ""


# --- performance ------------------------------------------------------------


def test_integrate_performance():
    pts = synthetic_room_points()
    assert len(pts) > 15000
    scan = make_scan(pts)
    g = M.OccupancyGrid()
    g.integrate(scan, POSE)  # warm up
    t0 = time.perf_counter()
    g.integrate(scan, POSE)
    assert time.perf_counter() - t0 < 0.25


def test_plan_performance_across_room():
    g = room_grid()
    t0 = time.perf_counter()
    path = g.plan((-2.5, -2.0), (2.5, 2.0))
    assert time.perf_counter() - t0 < 0.5
    assert path is not None
