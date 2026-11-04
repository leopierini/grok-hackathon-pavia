# Live LiDAR Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** See the Go2's LiDAR live (top-down view + "nearest obstacle ahead") in the joystick page as soon as the dog is connected, with zero motion; plus a `--step lidar` that saves one scan to disk.

**Architecture:** A pure module `patrol/dog/lidar.py` turns the vendor's decoded voxel-map message into a `LidarScan` and a compact body-frame view. `RealDog` subscribes to the LiDAR topic on connect and exposes `lidar_view()` / `lidar_status()` / `lidar_switch_on()`. `SimConn` emits a synthetic room so everything runs without the dog. The joystick server pushes the view over `/ws` at 5 Hz and the page draws it on a canvas.

**Tech Stack:** Python 3 (asyncio, numpy), `unitree_webrtc_connect` 2.2.0 native LiDAR decoder, aiohttp, vanilla JS canvas, pytest.

**Spec:** `docs/Lidar + SLAM.md` §4 (Stage 1). Hard rules: `docs/dog.md` §7.

## Global Constraints

- Never write firmware, switch network/motion modes or send motion from any LiDAR code. Subscribing is read-only.
- `rt/utlidar/switch` `"on"` is sent **only** by `RealDog.lidar_switch_on()`, which is called **only** from the page button (controller only, logged). Never automatic, never from `connect()` or `--step lidar`.
- Every STOP stays StopMove + StandDown; LiDAR code never touches the STOP path. Vendor callbacks must never raise.
- Body frame: **x forward, y left, z up**, metres. Page draws forward = up.
- Constants (in `patrol/dog/lidar.py`): `VIEW_RADIUS_M = 4.0`, `MAX_VIEW_POINTS = 4000`, `FLOOR_CUTOFF_M = 0.10`, `CEILING_M = 2.0`, `BODY_FRONT_M = 0.35`, `AHEAD_HALF_WIDTH_M = 0.25`, `AHEAD_Z_MAX_M = 0.60`, `STALE_SCAN_S = 2.0`.
- Joystick: `LIDAR_PERIOD_S = 0.2` (≤ 5 Hz), `NO_LIDAR_WARN_S = 5.0`.
- Run tests with `.venv/bin/python -m pytest`. Full dog suite must stay green (142 passed before this work).
- **Do not commit.** The working tree has the user's uncommitted audio work in the same files; the user commits.

## Review Focus

1. **Malformed / unexpected LiDAR messages** (missing keys, zero points, libvoxel-shaped `{"positions": …}` output if the decoder switch failed): parsed as `None`, never an exception in the vendor callback. Tests in Task 1 (`test_scan_from_message_rejects_garbage`) and Task 3 (`test_on_lidar_never_raises`).
2. **No fresh odometry**: points can't be put in the dog's frame; the view says so (`n = 0`, `reason = "position unknown"`) instead of drawing points in the wrong place. Test in Task 1 (`test_view_without_pose`).
3. **LiDAR stops sending**: the age grows and `stale` becomes true after `STALE_SCAN_S`; the page shows it in red and never presents old points as live. Test in Task 1 (`test_view_marks_stale`).
4. **Huge scans** (100k+ points): view capped at `MAX_VIEW_POINTS`, and the server builds it off the event loop (`asyncio.to_thread`) so STOP/drive aren't delayed. Tests in Task 1 (`test_view_caps_points`) and Task 2 (`test_lidar_view_built_in_thread`).
5. **Dog absent / re-arm / adapter without LiDAR methods**: the push loop sends nothing and doesn't crash or spam. Test in Task 2 (`test_lidar_loop_survives_no_dog`).

---

## Execution waves (parallel)

- **Wave 1 (parallel):** Task 1 (`lidar.py`) and Task 2 (joystick server + page). Task 2 tests patch `lidar_view` / `lidar_status` / `lidar_switch_on` onto the dog object, so they don't need Task 1 or Task 3.
- **Wave 2:** Task 3 (`RealDog` + `SimConn` + `--step lidar`), needs Task 1.
- **Wave 3 (controller):** integration check with `python -m patrol.dog.joystick --fake`, full test suite, docs update, whole-branch review.

Files per task are disjoint, so wave-1 agents never touch the same file.

---

### Task 1: Pure LiDAR module

**Files:**
- Create: `patrol/dog/lidar.py`
- Test: `tests/dog/test_lidar.py`

**Interfaces:**
- Consumes: nothing (numpy only).
- Produces:
  - `@dataclass(frozen=True) class LidarScan: points: np.ndarray  # (N,3) float32, world/odom metres; t: float  # monotonic receive time; frame_id: str | None; origin: tuple[float, float, float] | None; resolution: float | None`
  - `Pose = tuple[float, float, float, float | None]` → `(x, y, yaw_rad, ground_z | None)` in the same frame as the scan.
  - `scan_from_message(msg: Mapping, t: float) -> LidarScan | None` — vendor shape: `msg["data"]["data"]["points"]` (ndarray N×3), `msg["data"]["origin"]`, `msg["data"]["resolution"]`, `msg["data"].get("frame_id")`. Anything else → `None`. Never raises.
  - `to_body(points: np.ndarray, pose: Pose) -> np.ndarray` — world → body frame (x fwd, y left).
  - `nearest_ahead(body_pts: np.ndarray) -> float | None` — among points with `x > BODY_FRONT_M`, `|y| <= AHEAD_HALF_WIDTH_M`, `FLOOR_CUTOFF_M <= z_rel <= AHEAD_Z_MAX_M`: `min(x) - BODY_FRONT_M` (distance from the dog's nose), rounded to 0.01; `None` if none within `VIEW_RADIUS_M`. `body_pts` z is already height above ground.
  - `build_view(scan: LidarScan | None, pose: Pose | None, now: float) -> dict` — always returns `{"t": "lidar", "n": int, "pts": list[int], "age_s": float | None, "stale": bool, "nearest_ahead_m": float | None, "frame_id": str | None, "radius_m": VIEW_RADIUS_M, "reason": str | None}`. `pts` is flat `[x_cm, y_cm, zrel_cm, …]` ints in body frame, floor (`z_rel < FLOOR_CUTOFF_M`) and `z_rel > CEILING_M` removed, cropped to `|x|,|y| <= VIEW_RADIUS_M`, evenly strided down to `≤ MAX_VIEW_POINTS`. `nearest_ahead_m` is computed before striding. `reason`: `"no scan"`, `"position unknown"` (pose None → `n = 0`), else `None`. Ground: `z_rel = z - ground_z`; if `ground_z` is None use the 5th percentile of the scan's z.
  - `synthetic_room_points(resolution: float = 0.05) -> np.ndarray` — world-frame (N,3) points: walls of a 6 × 5 m room centred on (0, 0) from z = 0 to 1.0 m, floor at z = 0, a 0.4 m cube centred at (1.5, 0, 0.2) and one at (-1, 1.5, 0.2). Used by `SimConn` and tests.
  - `save_scan(scan: LidarScan, stem: Path) -> tuple[Path, Path]` — writes `<stem>.npy` (float32 N×3) and ASCII `<stem>.ply` (`element vertex N`, `property float x/y/z`).

- [ ] **Step 1: Write failing tests** in `tests/dog/test_lidar.py`:
  - `test_scan_from_message_ok`: vendor-shaped msg with 3 points → `LidarScan` with `points.shape == (3, 3)`, dtype float32, `frame_id`, `resolution == 0.05`.
  - `test_scan_from_message_rejects_garbage`: `{}`, `{"data": None}`, `{"data": {"data": {"positions": [1, 2]}}}`, points with shape (3,) → all `None`, no exception.
  - `test_to_body_rotation`: pose `(1, 0, pi/2, 0)`, world point `(1, 2, 0.3)` → body `(2, 0, 0.3)` (±1e-6).
  - `test_nearest_ahead`: body points `(1.0, 0, 0.3)`, `(0.2, 0, 0.3)` (inside body), `(0.8, 0.5, 0.3)` (outside corridor), `(0.6, 0, 0.02)` (floor) → `0.65`. Empty → `None`.
  - `test_view_without_pose`: scan present, pose None → `n == 0`, `reason == "position unknown"`.
  - `test_view_no_scan`: scan None → `reason == "no scan"`, `age_s is None`.
  - `test_view_marks_stale`: scan `t = 0`, `now = STALE_SCAN_S + 0.1` → `stale is True`; `now = 0.5` → `False`.
  - `test_view_caps_points`: 200 000 random points in ±3 m, z 0.2–1.5 → `n <= MAX_VIEW_POINTS`, `len(pts) == 3 * n`, all ints.
  - `test_view_removes_floor`: synthetic room at pose `(0, 0, 0, 0)` → no point with `zrel_cm < 10`; `nearest_ahead_m` ≈ `1.3 - 0.35 = 0.95` (cube face at x = 1.3) ±0.06.
  - `test_save_scan_roundtrip`: saved `.npy` loads equal; `.ply` header contains `element vertex 3`.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/dog/test_lidar.py -q` → FAIL (module missing).
- [ ] **Step 3:** Implement `patrol/dog/lidar.py` with the interfaces above (numpy only; no vendor imports).
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/dog/test_lidar.py -q` → all pass.

---

### Task 2: Joystick server push + page panel

**Files:**
- Modify: `patrol/dog/joystick.py` (Controller: new loop, status field, `lidar_on` message)
- Modify: `patrol/dog/joystick.html` (new panel)
- Test: `tests/dog/test_joystick_lidar.py`

**Interfaces:**
- Consumes (duck-typed on the dog; use `getattr(dog, name, None)` and skip if missing):
  - `dog.lidar_view() -> dict` (shape = Task 1 `build_view`; sync, may be slow → call via `asyncio.to_thread`)
  - `dog.lidar_status() -> dict` (`{"msgs": int, "age_s": float | None, "points": int | None, "rate_hz": float | None, "frame_id": str | None, "switch_sent": bool, "error": str | None}`)
  - `async dog.lidar_switch_on() -> dict` (`{"utc": str}`)
- Produces:
  - `Controller._lidar_loop()` started in `start()` next to `_status_loop`: every `LIDAR_PERIOD_S`, if clients and the dog has `lidar_view`, build the view with `asyncio.to_thread(dog.lidar_view)` and send it to **all** clients (view-only too, like video). Exceptions: print once per distinct message, keep looping.
  - `status()` gains `"lidar": dog.lidar_status()` (or `None`).
  - ws message `{"t": "lidar_on"}`: controller only → `request_lidar_on()` → awaits `dog.lidar_switch_on()`, logs `self.log.write("lidar_switch", ...)`, sends an event to all; refused with an event if not connected. Not a motion command; allowed while motion is locked.
  - Page panel "LiDAR (top-down)": canvas, 8 × 8 m (±`radius_m`), 1 m rings, dog triangle at centre pointing up, points coloured by height (low → high), status line `LiDAR: <n> pts · <age> s old` (red when `stale`), `Nearest obstacle ahead: <d> m` (or `–`), `reason` shown when set. When connected and `lidar.msgs == 0` for `NO_LIDAR_WARN_S`: text "No LiDAR data, the sensor may be off" + button **"Turn LiDAR on (ask staff first)"** (controller only) sending `{"t": "lidar_on"}`. Panel never blocks or delays the STOP button.

- [ ] **Step 1: Write failing tests** in `tests/dog/test_joystick_lidar.py` (reuse helpers from `tests/dog/test_joystick.py`: `make_ctl`, `serve`, `SimConn`). After connect, patch the methods onto `ctl.dog`:
  - `test_lidar_pushed_to_view_clients`: patched `lidar_view` returns a fixed dict; a view-only ws receives a message with `t == "lidar"` and the same `n` within 1 s.
  - `test_lidar_view_built_in_thread`: patched `lidar_view` records `threading.get_ident()`; it differs from the event-loop thread.
  - `test_status_has_lidar`: patched `lidar_status` → status message contains `lidar.msgs`.
  - `test_lidar_on_controller_only`: view-only ws sends `lidar_on` → patched `lidar_switch_on` not called; controller sends it → called once and `joystick.jsonl` has a `lidar_switch` line.
  - `test_lidar_loop_survives_no_dog`: dog without the methods (plain `SimConn` dog) and `ctl.dog = None` periods → no `lidar` messages, no exception, status still flows.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/dog/test_joystick_lidar.py -q` → FAIL.
- [ ] **Step 3:** Implement the Controller changes and the HTML panel (vanilla JS, matching the page's existing style and ws handler).
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/dog/test_joystick_lidar.py tests/dog/test_joystick.py -q` → pass.

---

### Task 3: RealDog subscription, simulated LiDAR, `--step lidar`

**Files:**
- Modify: `patrol/dog/real.py`
- Modify: `patrol/dog/sim_conn.py`
- Modify: `patrol/dog/real_selftest.py`
- Test: `tests/dog/test_real_lidar.py`

**Interfaces:**
- Consumes: Task 1 (`LidarScan`, `scan_from_message`, `build_view`, `save_scan`, `synthetic_room_points`).
- Produces (`RealDog`):
  - In `connect()`, after the state subscriptions: if `conn.datachannel` has `set_decoder`, call `set_decoder(decoder_type="native")`; then `await asyncio.wait_for(conn.datachannel.disableTrafficSaving(True), 3.0)` (session-only WebRTC transport flag, not a dog setting; failure is recorded in `lidar_status()["error"]`, never fatal); subscribe `topics["ULIDAR_ARRAY"]` → `_on_lidar`. `_topics()` sim mapping gains `"ULIDAR_ARRAY"` and `"ULIDAR_SWITCH"`.
  - `_on_lidar(msg) -> None`: `scan_from_message(msg, time.monotonic())`; store latest, count messages, keep a rate estimate; never raises.
  - `latest_lidar() -> LidarScan | None`
  - `lidar_pose() -> Pose | None`: from fresh sport state: `position[0:2]`, `imu_state.rpy[2]`, `ground_z = position[2] - body_height` (None if either missing).
  - `lidar_view() -> dict`: `build_view(self.latest_lidar(), self.lidar_pose(), time.monotonic())`.
  - `lidar_status() -> dict` (shape in Task 2).
  - `async lidar_switch_on() -> dict`: requires connected; `publish_without_callback(topics["ULIDAR_SWITCH"], "on")`; sets `switch_sent`; returns `{"utc": ...}`. Allowed while motion is locked.
- Produces (`SimConn`): constructor flags `lidar: bool = True`, `lidar_needs_switch: bool = False`; `LIDAR_HZ = 5.0`. In `_stream`, at `LIDAR_HZ`, if subscribed to `"ULIDAR_ARRAY"` (and switched on when `lidar_needs_switch`), call the callback with `{"topic": "ULIDAR_ARRAY", "data": {"origin": [...], "resolution": 0.05, "frame_id": "odom", "stamp": t, "data": {"points": synthetic_room_points()}}}` (cache the array). `SimPubSub.publish_without_callback(topic, data)` records into `conn.sent` and sets the switch when topic is `"ULIDAR_SWITCH"` and data is `"on"`. Sim datachannel gets `set_decoder(decoder_type)` and `async disableTrafficSaving(switch)`, both recorded.
- Produces (`real_selftest.py`): `"lidar"` in `STEPS`, not in `MOTION_STEPS` (no `--arm`). After connect: wait up to 5 s for the first scan (none → `rec["lidar"] = {"ok": False, "reason": "no LiDAR data in 5 s, the sensor may be off (not switched on by this step)"}`); else collect 5 s and record `msgs`, `rate_hz`, `points_last`, `xyz_min`, `xyz_max`, `frame_id`, `pose_start`/`pose_end`, and save the last scan with `save_scan` to `<out>/lidar_<utc>` (paths in `rec`). Never sends the switch, never moves.

- [ ] **Step 1: Write failing tests** in `tests/dog/test_real_lidar.py` (pattern: `make_dog(tmp_path, SimConn(...))` as in `tests/dog/test_joystick.py`):
  - `test_connect_subscribes_and_uses_native_decoder`: after `connect()`, sim recorded `set_decoder("native")` and `disableTrafficSaving(True)`; within 1 s `lidar_status()["msgs"] >= 1`.
  - `test_connect_never_sends_switch`: after connect + 1 s, no `"ULIDAR_SWITCH"` in `sim.sent`.
  - `test_lidar_view_shows_room`: `lidar_view()["n"] > 0`, `reason is None`, `nearest_ahead_m` ≈ 0.95 ±0.06 at the start pose.
  - `test_lidar_switch_on_button_path`: `SimConn(lidar_needs_switch=True)` → no scans for 1 s; `await dog.lidar_switch_on()` → scans arrive; `sim.sent` has exactly one switch entry.
  - `test_on_lidar_never_raises`: `_on_lidar({})`, `_on_lidar({"data": 5})` → no exception, `latest_lidar()` unchanged.
  - `test_selftest_lidar_step_saves_scan`: run `real_selftest._run("lidar", config, tmp_path, dog=make_dog(...), keys=False)` → `rec["lidar"]["ok"] is True`, `.npy` and `.ply` exist, no `SPORT_MOD` Move in `sim.sent`.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/dog/test_real_lidar.py -q` → FAIL.
- [ ] **Step 3:** Implement in `real.py`, `sim_conn.py`, `real_selftest.py`. Update the module docstring of `real.py` ("connect() never moves…") to mention the LiDAR subscription and the session-only traffic-saving flag.
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/dog -q` → all pass (142 + new).

---

### Task 4 (controller, after waves): integration + docs

- [ ] Start `.venv/bin/python -m patrol.dog.joystick --fake`, open the page, confirm the panel shows the synthetic room, the dog triangle, the boxes, and "nearest ahead" changes when driving toward a box. Screenshot.
- [ ] `docs/dog.md`: §2c joystick table gets the LiDAR panel row; §2b runbook gets `--step lidar` (no motion); §4 capabilities LiDAR row stays "unknown" until the real-dog run. `docs/Lidar + SLAM.md` §4: mark built (sim) / not yet tested on the dog.
- [ ] Whole-change review (fresh reviewer), then hand back to the user for the real-dog run.
