# LiDAR + SLAM (dog)

Status (2026-11-04 ~20:00): **Stage 1 (LiDAR panel) built and proven on the real dog. Stage 2: plain Move ignores avoidance → sticks drive mode + LiDAR brake built (sim only). Stage 4 core (`mapping.py`) built, not wired. Stage 5 demo mode (§8b, virtual signal) built (sim only). Stage 3 (Pi) not started (not Leonardo's task).** Next: real-dog test of sticks / brake / follow — see `handoff/dog.md` §0.
Related: [`docs/pi-bridge.md`](pi-bridge.md) (Raspberry Pi on the dog), [`docs/dog.md`](dog.md) (dog module, safety rules), [`handoff/dog.md`](../handoff/dog.md).

> ⛔ Same hard rules as `docs/dog.md`: **never overwrite, flash, update or reset the dog's firmware or on-board software. No AP ↔ Network mode switch, no motion-mode switching. Every STOP = StopMove + StandDown (soft lie-down), never Damp.** Staff present for anything that moves the dog.

## 1. Why

The demo story (Leonardo's words, tidied up):

1. The Tello drone rides on the dog's back.
2. Someone enters the room and the system notices them.
3. The drone takes off and flies to the person to inspect them.
4. Something decides the person is an intruder (Grok, a fast image model, or a local pose-estimation model; **not decided, and out of scope for this doc**).
5. The drone follows the intruder.
6. **The dog goes to the drone and sticks to it, by following the drone's Wi-Fi signal strength (RSSI).** The intruder moves, the drone follows them, and the dog follows the drone.

This doc covers what the dog needs for step 6:

- **LiDAR** so we can see the dog sensing the room, and so it doesn't walk into furniture or people.
- **Auto-dodge**: does the dog's built-in obstacle avoidance work with our commands?
- **SLAM / a map** so the dog can plan a route around obstacles instead of only dodging them.
- **Signal following**: the dog homes in on the drone's RSSI.

## 2. Goals, non-goals, anti-goals

**Goals (in order; each stage is useful on its own):**
1. See the LiDAR working live in the joystick page as soon as the dog is connected.
2. Test whether the dog dodges obstacles by itself when we drive it.
3. Get the dog off the laptop cable (Pi on the dog, see `pi-bridge.md`).
4. Build a map of the room from the dog's LiDAR and odometry, and plan paths on it.
5. Make the dog follow the drone's signal and stay near it.

**Decided by Leonardo / the team:**
- The dog follows the drone **by its signal strength only**. Other ways of finding the drone (the drone's computed position, the dog's camera) are notes in §9, not the plan.
- A **Raspberry Pi 5** rides on the dog and does the dog-side work. The laptop stays untethered.
- The live LiDAR view goes **in the joystick page**.

**Non-goals:**
- Intruder detection (separate topic).
- Drone control and the drone's own following of the intruder (drone workstream).
- A full floor plan of the building. One room is enough.
- Claiming a phone scan was made by the dog. A phone scan may be used as a background map, but it's presented as "pre-mapped site".

**Anti-goals (would make this a failure even if it "works"):**
- Anything that changes the dog's firmware, network mode or motion mode.
- The dog moving without a working STOP path, or with the staff controller out of reach.
- Silently turning off the existing safety thresholds (fence, speed, tilt) to make following "work".

- **All AI (Grok, intruder decision) runs on the laptop. In the demo the laptop is connected to nothing by cable and doesn't appear in the video.** So every laptop ⟷ dog interaction (Grok's dog actions, camera, audio, joystick, following) goes over Wi-Fi through the Pi.
- **Following starts from the intruder decision:** when the AI decides "intruder", it triggers "follow the drone" (a new action in the shared contract, see `pi-bridge.md` §3).

**Scope note:** `docs/plan-linear-copy.md` lists RSSI homing and SLAM as outside the core build; the team has now added signal following. The deadline is **Thursday 5 Nov, 16:00** (video). *My call on order, given about one day:* stage 1 → 2 → 3 (Pi, needed for the cable-free demo anyway) → **stage 5 v1 without a map** (steer toward the stronger signal + LiDAR brake). Stage 4 (map + route planning) only if time is left; stage 5 then upgrades to plan around obstacles on the map.

## 3. What we know (and what we don't)

| Fact | Source / status |
|---|---|
| Every Go2 edition has the Unitree L1 LiDAR in the head (360° around, about 90° vertical, low density, fills in over seconds) | Vendor spec |
| Our library streams it: subscribe to `rt/utlidar/voxel_map_compressed`; decoders `native` (list of x, y, z points) or `libvoxel` (voxel mesh) | `robot-docs/sdks/go2_webrtc_connect/examples/go2/data_channel/lidar/` |
| Decoder works in our venv (`from unitree_webrtc_connect.lidar import lidar_decoder_libvoxel` → OK) | Checked 2026-11-04 |
| The vendor example first publishes `"on"` to `rt/utlidar/switch` | Example code. **Whether the sensor is already on for this dog: unknown** |
| The data is a **local voxel map** around the dog (about 5 cm cells), not raw laser returns. How far it reaches and which frame it is in (odometry vs body): **unknown, measure in stage 1** | Library README + example |
| Other topics: `rt/utlidar/robot_pose` (odometry), `rt/utlidar/lidar_state`; on-board SLAM topics `rt/uslam/*` | `unitree_webrtc_connect/constants.py`. **uslam probably not running on this dog** (firmware likely < 1.1.11, staff removed ROS) |
| Obstacle avoidance is **on** (`obstaclesAvoidSwitch = true`, service query = true) | `handoff/dog.md`, read on the real dog |
| **Does plain sport `Move` (api 1008, what our joystick sends) respect avoidance? Unknown.** The library example says avoidance filters `rt/wirelesscontroller` commands, and the avoid service has its own `MOVE` (api 1003) plus `USE_REMOTE_COMMAND_FROM_API` (1004) | `examples/go2/data_channel/obstacles_avoid/`, `constants.py` `OBSTACLES_AVOID_API` |
| Only **one WebRTC client** at a time (phone app, joystick, selftest: one of them) | `docs/dog.md` |
| Safety thresholds today: fence radius 3.0 m around home, max speed 0.6 m/s, max tilt 25° | `patrol/dog/real.py` `SAFETY_DEFAULTS` |

## 4. Stage 1: LiDAR live in the joystick page

> **Status 2026-11-04:** built and tested on the simulator (panel, `--step lidar`, button). Plan: `docs/superpowers/plans/2026-11-04-lidar-live-panel.md`. **Not yet run on the real dog.**

**Goal:** connect the dog, open the joystick page, and see the LiDAR working with no motion at all.

**What to build:**
- `RealDog` subscribes to `rt/utlidar/voxel_map_compressed` on connect, decodes with the **native** decoder (we want points, not a mesh) and keeps only the latest scan plus its timestamp. Subscribing is read-only and fits the "connect never changes settings" rule.
- Decoding and downsampling happen off the event loop if they're slow, so the status/STOP path is never delayed.
- The joystick server sends a downsampled scan to the page over the existing `/ws` at **at most 5 Hz** (the builder picks the format; binary or compact JSON).
- **New panel on the joystick page: top-down LiDAR view.**
  - About 8 × 8 m around the dog, dog drawn as a triangle showing its heading, rings every 1 m.
  - Points coloured by height; floor points hidden (a height band, the builder picks it).
  - Status line: `LiDAR: 3 412 pts · 0.2 s old` / `LiDAR: no data`.
  - "Nearest obstacle ahead: 0.84 m": the closest point in a corridor about the dog's width in front of it. This is the number to watch in the dodge test.
- **Sensor off?** If nothing arrives within ~5 s of connecting, the panel says "No LiDAR data, the sensor may be off" and shows a **"Turn LiDAR on" button** (controller only, logged). It publishes `"on"` to `rt/utlidar/switch` once. *My call:* never automatic, because it is a (runtime-only, non-firmware) change on the dog. **Ask staff before the first press** (§10).
- `real_selftest.py --step lidar` (no `--arm`, no motion): connect, collect ~5 s, save one scan as `.npy` + `.ply` (opens in MeshLab or CloudCompare), print point count, x/y/z range, message rate, and whether the points move with the dog's odometry or stay fixed.
- `FakeDog` / `sim_conn.py` produce a synthetic scan (a box-shaped room with a couple of obstacles), so the panel and tests work without the dog.

**Measure on the real dog (fill into `docs/dog.md` §4):** message rate, points per message, how far the map reaches, units (metres?), and frame (rotate the dog by hand / with a slow turn: do the walls stay put in the view or rotate with the dog?).

**Done when:** on the real dog, the panel shows the room's walls and a person walking around within ~1 s, with zero motion commands sent.

## 5. Stage 2: auto-dodge test

**Goal:** know whether the dog avoids obstacles by itself when **we** drive it, and through which command path.

**Before:** staff present with the controller, slowest speed, a soft obstacle (cardboard box), clear space, fence on. LiDAR panel open so we see the box and the "nearest obstacle ahead" number.

**Test, in this order:**
1. **A: our normal joystick (sport `Move`).** Drive slowly straight at the box. Does the dog stop or step around it? 3 tries.
2. **B: only if A doesn't avoid, and only after staff OK:** drive through the avoidance service (`OBSTACLES_AVOID` `MOVE`, which needs `USE_REMOTE_COMMAND_FROM_API = true`) or through the simulated wireless controller topic. These change how the dog takes commands at runtime, so they're staff questions (§10).
3. Record video + the joystick log for each try.

**Pass:** the dog stops or goes around before touching the box, 3 of 3, on one command path. Write the path that works into `docs/dog.md`.

**If no path avoids:** add our own **software brake** in `RealDog`: refuse forward motion while "nearest obstacle ahead" is under a threshold (*my call: 0.5 m*, tune on the dog), StopMove only (the dog stays standing). Stage 5 needs this anyway as a second layer.

## 6. Stage 3: off the cable (Raspberry Pi 5)

See [`docs/pi-bridge.md`](pi-bridge.md). Short version: the Pi rides on the dog, plugged into the dog's Ethernet, runs `RealDog` + the joystick server, measures the drone's signal with a USB Wi-Fi dongle, and talks to the laptop over Wi-Fi. The laptop's AI reaches the dog through a `RemoteDog` that keeps the same `DogPort` contract. Stages 4 and 5 run on the Pi.

## 7. Stage 4: map + path planning ("SLAM") (only if time is left before the deadline)

**Goal:** a map of the room and the dog's position on it, good enough to plan a path around obstacles for a few minutes.

**Step 1: check what the dog already has (read-only).** Subscribe to the `rt/uslam/*` topics (e.g. `server_log`, `frontend/odom`, `cloud_map`) for ~10 s and log whether anything arrives. **Never send `rt/uslam/client_command`** (it starts on-board mapping) without staff OK. *Expectation: nothing arrives on this dog.*

**Step 2 (default plan): our own mapping on the Pi.**
- Position comes from the dog's own odometry (already used by the safety fence; `rt/utlidar/robot_pose` as a cross-check). Over one room and a few minutes, its drift is acceptable, so this is "mapping with known poses", not full SLAM. *My call.*
- Each LiDAR scan goes into a **2D occupancy grid** (*my call: 5 cm cells*): points in a height band roughly from just above the floor to the dog's head height mark a cell as blocked; cells the dog has seen through are free; everything else is unknown.
- Obstacles are inflated by the dog's half-width plus a margin, so planned paths keep clear.
- **Path planning:** A* (or similar) on the inflated grid from the dog to a goal cell. The output is a short list of waypoints the dog walks with slow `Move` commands, re-planning when the map changes (people move).
- The map shows in the joystick LiDAR panel (grey = free, black = blocked) with the planned path drawn on top. Later, the dashboard can show it over the phone-scan background map.

**Done when:** you click a point on the map in the joystick page and the dog walks there around a box, staying inside the fence, 3 of 3.

## 8. Stage 5: follow the drone's signal

**Goal:** the dog walks toward the drone and stays near it, using only the drone's Wi-Fi signal strength.
- **v1 (for the deadline):** no map. Steer toward the stronger signal; the LiDAR "nearest obstacle ahead" brake (stage 2) plus the dog's built-in avoidance keep it off obstacles. If blocked, turn and probe another direction.
- **v2 (if stage 4 exists):** plan the path to each goal on the map instead.

**How it starts and stops:**
- **Start:** the AI on the laptop decides "intruder" → calls the new contract action `follow_drone` → the Pi starts following. The dog must be standing, stationary, avoidance on, inside the fence (same checks as `run_route`).
- **Stop:** a new `stop_follow` action (e.g. intruder gone, operator dismisses), any page STOP, lost link to the laptop, or a safety trip. Arriving is not a stop: the dog holds and resumes if the signal drops.
- The joystick page shows the follow state and has a manual "Stop following" control (plus the normal STOP).

**Measuring:** the Pi's USB Wi-Fi dongle is joined to the Tello's own Wi-Fi network (`TELLO-…`, 2.4 GHz) and reads the link's signal strength (dBm) about 5–10 times a second. The signal is noisy indoors, so it's smoothed (e.g. median then moving average). If joining the Tello's network clashes with the drone team's control link, the fallback is listening passively to the Tello's beacons (dongle must support monitor mode). See `pi-bridge.md`.

**Calibration (before any following):** dog standing, drone on a table, record RSSI at about 0.5, 1, 2, 4 m and around obstacles. This tells us how noisy it really is and sets the **"arrived" threshold**.

**Steering (suggested; the builder may pick another way):**
1. Keep the last few seconds of `(dog x, dog y, smoothed RSSI)` samples in the map frame.
2. Estimate the direction in which RSSI rises (positions come from the dog's odometry; no map needed) (fit a plane to the samples). If the samples don't tell (dog standing still, flat signal), take a short probing step (~0.5 m) in a direction not yet tried.
3. Put a goal ~1 m in that direction and walk to it slowly (v2: plan the path on the map).
4. Repeat. When the smoothed RSSI is above the "arrived" threshold, stop and hold (StopMove, stay standing). Resume when it drops again.

**Limits:**
- Slow: well under the 0.6 m/s speed trip. *My call: about 0.3 m/s.*
- The fence stays on. Following an intruder across a room may need a bigger radius than 3 m. That's a config change, agreed with staff on the day, never disabling the fence.
- A STOP from the page, a lost link, or any safety trip stops following immediately (see `pi-bridge.md` §5).

**Show it on the page/dashboard:** live RSSI number + sparkline, the estimated direction as an arrow from the dog, "following / arrived / lost signal" state. This makes it easy to read in the demo, and honest when the dog wanders.

**Moving drone (my call):** in the story the drone keeps moving with the intruder, so old samples go stale. Keep the sample window short (a few seconds), weight recent samples more, and re-probe when the estimate stops improving. Test with a still drone first (the "done" test below), then with someone slowly carrying the drone.

**Expectation, said plainly:** inside one room RSSI bounces off walls and people and mostly says "how far", not "which way". Expect the dog to wander before it closes in. Calibration tells us early whether it's good enough.

**Done when:** drone hovering or held still somewhere in the room, the dog starts ≥ 3 m away and gets within the "arrived" distance in under ~60 s, 3 of 3, without touching anything.

## 8b. Demo mode: follow a virtual signal point (no Pi, no drone)

Status: **built (sim), not yet on the real dog** (2026-11-04; design agreed with Leonardo the same day). Code: `patrol/dog/follow.py` + the joystick's "Follow signal (demo)" panel; tests: `tests/dog/test_follow.py`, `tests/dog/test_joystick_follow.py`; runbook: `docs/dog.md` §2c "Follow demo on the real dog". Builder's additions to the agreed design: start is also refused with the safety thresholds off, the LiDAR brake off, or no fresh LiDAR, and following ends if any of these happens mid-run; when a straight leg's estimate points back along that leg (passed the closest point), the follower probes sideways instead of retracing. Lets us test and film signal following on the real dog before the Pi and the drone are ready.

**Idea:** a *virtual signal point* placed in the room. A simulated signal source turns the dog's real distance to it (from odometry) into a fake RSSI with realistic noise. The follower only ever sees the RSSI number, never the point's position: it is the same follower that will read the real drone RSSI from the Pi later, only the signal source changes. On camera: "simulated signal source, real following logic".

**Decided by Leonardo:**
- Follow is **start once, STOP to end** (no hold-to-follow). All existing automatic stops still apply.
- The signal is shown on the joystick page.

**Pieces**
- `patrol/dog/follow.py` (pure, testable):
  - `SignalSource` protocol: `read() -> float | None` (dBm). `VirtualBeacon(point_xy, pose_fn)`: RSSI = −40 − 25·log10(max(d, 0.3) m) + Gaussian noise σ = 3 dB (joystick demo: 2 dB since 2026-11-04 evening), clamped to [−95, −30], ~10 Hz. (*My call:* path-loss exponent 2.5, typical indoors.) Later `WifiRssiSource` on the Pi.
  - `Follower` state machine: `idle → following ↔ probing → arrived`, plus `stopped(reason)`. Input each tick: pose, smoothed RSSI, LiDAR nearest-ahead, brake state. Output: forward speed + turn rate (no sideways).
  - Steering = stage 5 v1: short recency-weighted window of (x, y, RSSI) samples, plane fit for the uphill direction; turn toward it, then walk ~1 m legs; probe a new direction (~0.6 m step) when the fit is weak.
  - Stuck rule: no progress (< 0.15 m moved in 4 s while commanding forward) or brake held > 2 s → turn 60–90° (alternating sides) and probe.
  - Arrived: smoothed RSSI ≥ −38 dBm (≈ 0.8 m; was −43 ≈ 1.3 m) → StopMove, hold standing; resume below −43 dBm (≈ 1.3 m). Hysteresis avoids jitter.
- **Limits (my calls):** speed ≤ 0.3 m/s forward, ≤ 0.5 rad/s turn; 60 s per run then stop (StopMove, stays standing); fence on; LiDAR brake on. Following drives through the selected drive mode; in "move" mode the page warns "dog's own dodging is off, LiDAR brake only".
- **Stops:** page STOP (soft lie-down), "Stop following" (StopMove, stays standing), time limit, any safety trip, ws loss / tab blur / controller lost (existing rules), drive input from the sticks (manual takes over → follow ends).
- **Joystick page:**
  - "Place signal point": click on the LiDAR panel (converted to the odom frame with the current pose); click again to move it (imitates the drone moving).
  - Point drawn on the LiDAR panel (marked "simulated").
  - Live RSSI number + 30 s sparkline.
  - Estimated direction arrow from the dog.
  - Follow state + reason, run timer, and the Start following / Stop following buttons (controller only, logged).
- **Logs:** follow start/stop with reason, point placements, per-second follow samples (pose, RSSI, state) so a run can be replayed/plotted.
- **Done when:** sim tests pass (follows to the point around a box in `--fake`); on the real dog, with staff, the dog starts ≥ 3 m away and reaches "arrived" in < 60 s, 3 of 3, without touching anything.

## 9. Notes: other ways to find the drone (not the plan)

Kept only in case signal following isn't good enough on the day:
- **Computed drone position:** the drone takes off from the dog and our code sends every move, so the laptop knows roughly where it is relative to the dog's start. Tello EDU mission pads make that exact over the pads.
- **Dog camera:** keep the drone in view and steer toward it.

## 10. Open questions

**For staff:**
1. Does plain sport `Move` respect obstacle avoidance? If not, may we use the avoid service's `MOVE` (+ `USE_REMOTE_COMMAND_FROM_API`) or the wireless-controller topic?
2. Is the LiDAR already on? May we publish `"on"` to `rt/utlidar/switch` if it's off?
3. Is the on-board SLAM (`rt/uslam/*`) present on this dog? (We'll only listen, not start it.)
4. May we strap a Pi 5 + power bank to the dog next to the drone? Where?
5. Fence radius for the demo room?

**For the team:** see `pi-bridge.md` §7 (dongle, power bank, network, drone team OK, contract change).

**Dependency on the drone team:** the agreed plan (`project-plan.md`, `patrol/contract.py`) has the drone doing a short hop (about 1.5 m up, look, land). "The drone follows the intruder" is new drone work; it must be agreed with them.

## 11. Decision log

| Decision | By |
|---|---|
| Dog follows the drone by RSSI only | Leonardo / team |
| Raspberry Pi 5 on the dog, laptop untethered | Leonardo |
| Live LiDAR view in the joystick page | Leonardo |
| Intruder detection out of this doc | Agreed in chat |
| All AI runs on the laptop; in the demo the laptop has no cable and isn't in the video, so all dog traffic goes through the Pi | Leonardo |
| The intruder decision triggers "follow the drone" | Leonardo |
| Order for the deadline: stages 1 → 2 → 3 → 5 v1 (no map); stage 4 only if time is left | Claude's call |
| Moving drone: short, recency-weighted sample window | Claude's call |
| Native decoder, ≤ 5 Hz to the page, top-down view, "nearest obstacle ahead" number | Claude's call |
| "Turn LiDAR on" is a manual button, never automatic | Claude's call |
| Own mapping from odometry + LiDAR (not full SLAM), 5 cm grid, A* | Claude's call |
| Software brake at 0.5 m if the built-in avoidance doesn't cover our commands | Claude's call |
| Following speed ~0.3 m/s; fence stays on | Claude's call |
