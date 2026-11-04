"""Pure LiDAR processing: vendor message -> scan -> body-frame view for the joystick panel."""

import math

import numpy as np

from patrol.dog import lidar as L


def vendor_msg(points, frame_id="odom"):
    return {
        "data": {
            "origin": [0.0, 0.0, 0.0],
            "resolution": 0.05,
            "stamp": 1.0,
            "frame_id": frame_id,
            "data": {"points": np.asarray(points, dtype=np.float64)},
        }
    }


def make_scan(points, t=0.0):
    return L.LidarScan(
        points=np.asarray(points, dtype=np.float32),
        t=t,
        frame_id="odom",
        origin=(0.0, 0.0, 0.0),
        resolution=0.05,
    )


def test_scan_from_message_ok():
    msg = vendor_msg([[0, 0, 0], [1, 1, 1], [2, 2, 2]])
    scan = L.scan_from_message(msg, t=5.0)
    assert isinstance(scan, L.LidarScan)
    assert scan.points.shape == (3, 3)
    assert scan.points.dtype == np.float32
    assert scan.frame_id == "odom"
    assert scan.resolution == 0.05
    assert scan.origin == (0.0, 0.0, 0.0)
    assert scan.t == 5.0


def test_scan_from_message_rejects_garbage():
    bad = [
        {},
        {"data": None},
        {"data": {"data": {"positions": [1, 2]}}},
        vendor_msg([1.0, 2.0, 3.0]),  # shape (3,)
        vendor_msg(np.zeros((4, 2))),
        None,
        "nope",
    ]
    for msg in bad:
        assert L.scan_from_message(msg, t=0.0) is None


def test_to_body_rotation():
    body = L.to_body(np.array([[1.0, 2.0, 0.3]]), (1.0, 0.0, math.pi / 2, 0.0))
    assert np.allclose(body[0], [2.0, 0.0, 0.3], atol=1e-6)


def test_nearest_ahead():
    pts = np.array(
        [
            [1.0, 0.0, 0.3],
            [0.2, 0.0, 0.3],  # inside body
            [0.8, 0.5, 0.3],  # outside corridor
            [0.6, 0.0, 0.02],  # floor
        ]
    )
    assert L.nearest_ahead(pts) == 0.65
    assert L.nearest_ahead(np.empty((0, 3))) is None


def test_view_without_pose():
    view = L.build_view(make_scan([[1, 0, 0.5]]), None, now=0.1)
    assert view["n"] == 0
    assert view["pts"] == []
    assert view["reason"] == "position unknown"
    assert view["t"] == "lidar"
    assert view["radius_m"] == L.VIEW_RADIUS_M


def test_view_no_scan():
    view = L.build_view(None, (0.0, 0.0, 0.0, 0.0), now=1.0)
    assert view["reason"] == "no scan"
    assert view["age_s"] is None
    assert view["n"] == 0


def test_view_marks_stale():
    scan = make_scan([[1, 0, 0.5]], t=0.0)
    pose = (0.0, 0.0, 0.0, 0.0)
    assert L.build_view(scan, pose, now=L.STALE_SCAN_S + 0.1)["stale"] is True
    fresh = L.build_view(scan, pose, now=0.5)
    assert fresh["stale"] is False
    assert fresh["age_s"] == 0.5
    assert fresh["reason"] is None


def test_view_caps_points():
    rng = np.random.default_rng(0)
    pts = np.column_stack(
        [rng.uniform(-3, 3, 200_000), rng.uniform(-3, 3, 200_000), rng.uniform(0.2, 1.5, 200_000)]
    )
    view = L.build_view(make_scan(pts), (0.0, 0.0, 0.0, 0.0), now=0.0)
    assert 0 < view["n"] <= L.MAX_VIEW_POINTS
    assert len(view["pts"]) == 3 * view["n"]
    assert all(type(v) is int for v in view["pts"])


def test_view_removes_floor():
    scan = make_scan(L.synthetic_room_points())
    view = L.build_view(scan, (0.0, 0.0, 0.0, 0.0), now=0.0)
    assert view["n"] > 0
    zrel_cm = view["pts"][2::3]
    assert min(zrel_cm) >= 10
    assert abs(view["nearest_ahead_m"] - (1.3 - 0.35)) <= 0.06


def test_view_infers_ground_when_unknown():
    pts = [[1.0, 0.0, 5.0], [2.0, 0.0, 5.02], [1.5, 0.0, 5.5]]
    view = L.build_view(make_scan(pts), (0.0, 0.0, 0.0, None), now=0.0)
    # lowest points are treated as floor, only the 0.5 m high point survives
    assert view["n"] == 1


def test_save_scan_roundtrip(tmp_path):
    scan = make_scan([[0, 0, 0], [1, 2, 3], [4, 5, 6]])
    npy, ply = L.save_scan(scan, tmp_path / "scan")
    assert npy.suffix == ".npy" and ply.suffix == ".ply"
    assert np.array_equal(np.load(npy), scan.points)
    assert "element vertex 3" in ply.read_text()


# ------------------------------------------------------------------ free distance per direction (dodge)

def wall_x(x, y0=-0.5, y1=0.5, z=0.3):
    return [[x, y, z] for y in np.arange(y0, y1 + 1e-9, 0.05)]


def test_clearance_bins_layout():
    c = L.clearance(np.zeros((0, 3)))
    assert len(c) == L.CLEAR_BINS == 24
    assert all(v == L.VIEW_RADIUS_M for v in c)     # nothing seen = clear to the view edge


def test_clearance_wall_ahead_blocks_front_only():
    body = np.asarray(wall_x(1.0))                 # 1 m wide wall 1 m ahead of the body centre
    c = L.clearance(body)
    front = c[L.clear_bin(0.0)]
    assert abs(front - (1.0 - L.BODY_FRONT_M)) < 0.06          # measured from the nose
    assert c[L.clear_bin(math.pi / 2)] == L.VIEW_RADIUS_M      # left clear
    assert c[L.clear_bin(-math.pi / 2)] == L.VIEW_RADIUS_M     # right clear
    assert c[L.clear_bin(math.pi)] == L.VIEW_RADIUS_M          # behind clear
    assert c[L.clear_bin(math.radians(30))] < 1.0              # 30 deg left still hits the 1 m wide wall
    assert c[L.clear_bin(math.radians(75))] == L.VIEW_RADIUS_M


def test_clearance_ignores_floor_ceiling_and_own_body():
    body = np.asarray([[0.8, 0.0, 0.02], [0.8, 0.0, 1.5], [0.2, 0.05, 0.3], [-0.3, -0.1, 0.3]])
    assert all(v == L.VIEW_RADIUS_M for v in L.clearance(body))


def test_clearance_side_obstacle_from_body_edge():
    body = np.asarray([[x, 1.0, 0.3] for x in np.arange(-0.2, 0.21, 0.05)])   # 1 m to the left
    c = L.clearance(body)
    assert abs(c[L.clear_bin(math.pi / 2)] - (1.0 - L.BODY_HALF_WIDTH_M)) < 0.06


def test_view_carries_clearance_with_its_yaw():
    scan = make_scan(wall_x(1.0), t=0.0)
    v = L.build_view(scan, (0.0, 0.0, 0.0, 0.0), 0.1)
    assert v["clear"]["yaw"] == 0.0 and v["clear"]["step_deg"] == 15 and len(v["clear"]["m"]) == 24
    assert L.build_view(scan, None, 0.1)["clear"] is None


def test_turn_clearance_is_radial_from_the_body_centre():
    assert L.turn_clearance(np.zeros((0, 3))) == L.VIEW_RADIUS_M
    body = np.asarray([[-0.40, 0.25, 0.3], [2.0, 0.0, 0.3], [0.1, 0.1, 0.3], [0.3, 0.3, 0.02]])
    assert abs(L.turn_clearance(body) - math.hypot(0.40, 0.25)) < 1e-6   # own body + floor ignored
    v = L.build_view(make_scan(body), (0.0, 0.0, 0.0, 0.0), 0.1)
    assert abs(v["clear"]["near_m"] - round(math.hypot(0.40, 0.25), 2)) < 1e-6


def test_turn_room_open_space_and_flank_point():
    assert L.turn_room(np.zeros((0, 3))) == (L.TURN_CHECK_MAX_DEG, L.TURN_CHECK_MAX_DEG)
    # a post 0.10 m off the left flank, level with the centre: turning either way swings the body into it
    left, right = L.turn_room(np.asarray([[0.0, 0.30, 0.3]]))
    assert left < 60 and right < 60
    # a post just off the front-left corner: turning RIGHT swings that corner away, LEFT into it
    left, right = L.turn_room(np.asarray([[0.36, 0.33, 0.3]]))
    assert left < 20 and right >= 60


def test_view_carries_turn_room():
    v = L.build_view(make_scan([[0.36, 0.33, 0.3]]), (0.0, 0.0, 0.0, 0.0), 0.1)
    left, right = v["clear"]["turn_room"]
    assert left < 20 and right >= 60
