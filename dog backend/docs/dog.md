# Dog (Unitree Go2): working notes

Everything about the dog in one place: status, how to connect, what we know, tasks and a session log.
Owner: Leonardo. Linear project: [P-HAC-1 · Dog (Go2)](https://linear.app/federico-navoni/project/1-dog-go2-ead712b89878).
The formal handoff for the rest of the team is [`handoff/dog.md`](../handoff/dog.md) (HAC-7). Copy final, verified facts there.
Last updated: 2026-11-04. Times below are local (UTC+1) unless marked UTC. `evidence/dog/session.jsonl` stores UTC.

> ⛔ **NEVER overwrite, flash, update or reset the dog's firmware or on-board software.** Staff modified it (ROS removed). The setup is fragile.
> Only read-only and connect-level actions. No OTA updates in the app, no re-bind, no factory reset, no motion-mode or AP/Network mode switching, no changes over SSH.

> 🔑 No credentials in this file. Real values go in `config/dog.local.json` (git-ignored) or env vars.

---

## 1. Status at a glance

| | |
|---|---|
| Network link | ✅ Wired Ethernet works (2026-11-04) |
| WebRTC connect (no motion) | ✅ Probe: 1.7 s, 2 of 3 tries (try 1 timed out). Supervised session: 5 of 5 connects, 2.05–2.69 s |
| Camera photo | ✅ 1280×720 frames saved (probe 12:54, 12:55; session 13:33) |
| Status readback | ✅ Sport state ~20 Hz, battery, settings |
| Halt proven | ✅ Still: 0.154 s · **mid-walk (joystick release, 15 stops): median 0.08 s, max 0.91 s to stationary** (15:00–15:04) |
| Short supervised move | ✅ 0.2 m/s × 1 s → 0.214 m, stop verified |
| Soft lie-down (STOP = StopMove + StandDown) | ✅ 3 of 3 on the real dog (joystick STOP/REST). StandDown replies only after > 3 s → posture timeout raised to 8 s |
| Command expiry (what happens when commands stop) | ⏳ Not tested (step 6 skipped) |
| Browser joystick | ✅ Used on the real dog in Chrome (15:00–15:04): drive, live camera, STOP, Re-arm, Stand up, head light. Audio panel's own buttons (Say, Listen, Hold to talk…) not tried on the real dog yet |
| One-click workflow | ✅ Real dog 17:20–17:24: launcher, **auto-connect** (2.07 s once the dog answered), **Run test → Read check** PASS, **auto re-arm** after each test, **Shut down server**. ⏳ **Run test → Audio test** needs one real run after the volume-0 fix (restart the joystick first) |
| Speaker + mic | ✅ `--step audio --volume 5` (15:41): chime heard at the dog and by the dog's mic (660 Hz +28.6 dB, 990 Hz +17.7 dB, ~0.2 s delay). Volume set + restored. Mic also fine at 17:21 (200 of 200 frames); that page test only failed to hear because it ran at volume 0 (fixed) |
| Safety thresholds | 🟡 Built + 2 reviews, tested on the simulator; no trip seen on the real dog yet (never left the fence) |
| room_2 route | ⏳ Route file exists but `calibrated: false` |
| FakeDog (HAC-1) | ✅ Done, 30 tests |
| RealDog adapter + session script | ✅ 17 logic tests (fake connection). Steps 1–4 run on the real dog |
| LiDAR live panel | ✅ Real dog 18:08–18:13: 4000 pts live, walls + people visible, nearest-ahead 0.53 m. Streams **only while standing**. `--step lidar` needs the dog standing |
| Plain `Move` respects obstacle avoidance | ❌ **No** (18:08: avoidance on, dog walked into person/box) |
| Sticks drive mode (remote-controller path, dog's own avoidance) | 🟡 Built + reviewed, sim only. **Not tried on the real dog** (staff-stop test first, then directions) |
| LiDAR brake (0.5 m, forward only) | 🟡 Built + reviewed, sim only |
| Follow a virtual signal point (demo) | 🟡 Built + reviewed, sim only (reaches "arrived" around a box in `--fake`). Not tried on the real dog |
| Map + path planning (`mapping.py`) | 🟡 Pure module, 28 tests, **not wired** into joystick/dog |
| `pytest tests/dog` | ✅ 332 passed (+1 test added after), 2026-11-04 ~20:00 |

---

## 2. How to connect (wired, verified)

**Physical:** Ethernet cable from the dog's port → USB LAN adapter on the Mac (shows up as **en5**, "USB 10/100/1000 LAN").

**Mac network settings** (one time; already done on Leonardo's Mac):

```bash
networksetup -setmanual "USB 10/100/1000 LAN" 192.168.123.222 255.255.255.0
```

- Mac: `192.168.123.222/24`. Dog: `192.168.123.161`.
- **No router** on this interface. Wi-Fi stays the default route, so the laptop keeps internet (Grok API) while talking to the dog.
- Don't use addresses the dog may use (`.161`, `.18`, other low numbers).
- To undo: `networksetup -setdhcp "USB 10/100/1000 LAN"`.

**Check the link:**

```bash
ping -c 3 192.168.123.161
nc -vz -G 3 192.168.123.161 8081   # should say "succeeded"
```

The first ping right after plugging in can say `No route to host` while the Mac looks up the dog's address. Try again after a few seconds.

**Library:** `unitree_webrtc_connect` (local clone in `robot-docs/sdks/go2_webrtc_connect`, v2.2.0, commit `e0abc57`). Connection method `LocalSTA`, legacy signaling (`/offer` on port 8081), **no AES key** (verified: connects without one).

```python
from unitree_webrtc_connect import UnitreeWebRTCConnection, WebRTCConnectionMethod

conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip="192.168.123.161")
await conn.connect()   # no AES key needed on this dog
```

**Read-only probe** (connect, read status, save one photo, disconnect; sends no motion or settings commands):

```bash
.venv/bin/python scripts/dog_probe_readonly.py            # writes to evidence/dog/ (git-ignored)
```

**Setup once:**

```bash
bash robot-docs/fetch-sdks.sh        # gets the library clone (robot-docs/sdks/ is git-ignored)
brew install portaudio
python3.12 -m venv .venv
.venv/bin/pip install -r requirements/dog.txt
```

- Python **3.12** (tested on 3.12.15). Pins are in `requirements/dog.txt`: aiortc 1.15.0, av 17.1.0, cryptography 50.0.2, opencv-python 5.0.0.93, numpy 2.5.4, aiohttp 3.14.5 (added for the joystick), pytest 9.2.0.
- The library is a **non-editable** install on purpose (no `pip install -e`). macOS can flag the editable `.pth` file as hidden, and Python then skips it, so the import fails.
- Always run with `.venv/bin/python`. The first two real_selftest runs (13:07) failed with "unitree_webrtc_connect is not installed": the interpreter used did not have the library (probably not the venv).

**Config:** `config/dog.local.json` (git-ignored) holds `connection_mode: "LocalSTA"`, `interface` (this is the dog's IP, `192.168.123.161`), `routes_path`, `max_route_s`, `command_timeout_s` (default 3.0). Optional: `connect_timeout_s` (25), `move_rate_hz` (10). `config/dog.example.json` is the template. `routes_path` is read relative to where you start Python, so run from the repo root.

**Tests and fake selftest (no robot):**

```bash
.venv/bin/python -m pytest tests/dog -q                  # 146 passed
.venv/bin/python -m patrol.dog.selftest --mode fake      # PASS
```

Rules:
- **Close the Unitree phone app first.** Only one WebRTC client at a time (`RobotBusyError` otherwise).
- Connecting must never move the dog. Movement only after an explicit `--arm` (selftest) or an explicit stick input (joystick).

---

## 2b. Supervised session runbook (HAC-3)

Code: `patrol/dog/real.py` (RealDog), `patrol/dog/real_selftest.py` (one step per run). Config: `config/dog.local.json` (git-ignored).
Each run appends to `evidence/dog/session.jsonl`. Steps that move or command the dog refuse to run without `--arm`.
**STOP while a step runs: `Q` or `Enter` = stop walking + lie down softly (top priority, never the rough drop) · Ctrl+C = stop walking (dog stays standing) + exit.** Run the steps in your own Terminal so the keys work.

**Before any `--arm` step:** staff present **holding their controller**, 2 m clear in front of the dog, phone app closed.

| # | Command (prefix `.venv/bin/python -m patrol.dog.real_selftest`) | What it does | Look for | Result 2026-11-04 |
|---|---|---|---|---|
| 1 | `--step read` | Connect, status, motion mode, avoidance query, photo. **No motion.** No `--arm` needed. | `ok: true`, `motion_mode`, photo path | ✅ 2.09 s, mode `normal`, avoidance on, photo |
| 1b | `--step lidar` | Connect, collect ~5 s of LiDAR, save the last scan as `.npy` + `.ply` (MeshLab / CloudCompare), report rate (`rate_hz` exact over the 5 s, `rate_hz_window` from the last 20 messages), points, range, frame, start/end pose. **No motion, never switches the sensor on.** Fails fast with `disabled by config` when `lidar_enabled: false`. No `--arm`. | `lidar.ok: true`, file paths | not run yet |
| 2 | `--step prepare --arm` | Stand up only if not standing, read back. Avoidance is **read-only** (never switched on): if not confirmed on, the step FAILs with "avoidance not confirmed on — motion refused; ask staff" | `status_after_prepare` all `true` | ✅ no action needed, all `true` |
| 3 | `--step halt --arm` | StopMove while stationary | accepted, still standing | ✅ 0.154 s, stayed standing |
| 4 | `--step move --arm` | 0.2 m/s forward for 1.0 s (route control path) | `moved_m` ≈ 0.2, `stopped: true` | ✅ 0.214 m, ~4 cm sideways, stop verified |
| 5 | `--step halt-mid-move --arm` | 0.2 m/s for 3 s, `halt()` after 0.8 s | `stationary_after_halt_s`, `moved_m` < 0.4 | **Skipped by team decision. Assumed to work, NOT tested.** |
| 6 | `--step expiry --arm` | ONE Move at 0.2 m/s, nothing else, watch 2 s, then halt | `stopped_by_itself_after_s` (= command expiry) | **Skipped by team decision. Assumed, NOT tested.** |
| any | `--step rest --arm` | Lie down on demand: StopMove, then StandDown (same as pressing Q). Stand up again with `--step prepare --arm`. | `standdown_sent: true`, dog lying | Not run on the real dog |
| any | `--step audio --volume 5` | **No motion, no `--arm`.** Volume → 5, record the mic 4 s, chime at 1.5 s, volume restored. Checks the chime's two tones (660/990 Hz) in the recording, not just loudness | `loopback_heard: true`, `loopback_tone_rise_db` ≥ 10 each, `volume_restored` | ✅ 15:41: heard at the dog; 660 Hz +28.6 dB, 990 Hz +17.7 dB |

Stop after any FAIL and look at the error before going on. Never re-run a motion step that timed out without checking the dog first.
Mitigation for the skipped steps: speeds ≤ 0.3 m/s, staff controller always ready, and the joystick logs stop latency to `evidence/dog/joystick.jsonl` (see §2c).

`python -m patrol.dog.selftest --mode real --config config/dog.local.json --arm` only **delegates** to real_selftest and runs the `read` step. To run any other step, call `real_selftest` directly as above.

**Sport API calls we send** (topic `SPORT_MOD`): StopMove 1003, StandUp 1004, BalanceStand 1002, Move 1008, StandDown 1005. **Damp (1001, motors go limp, rough drop) is never sent.** Other topics: obstacle-avoid **get only** (1002; the set call 1001 is never sent, avoidance is read-only), motion switcher read (1001, read only), VUI head light get/set (1006/1005). Joystick "sticks" mode only: simulated remote-controller sticks on `rt/wirelesscontroller` (runtime input, no setting changed; see §2c).

**Movement path:** sport `Move` (api 1008), re-sent at 10 Hz. We do **not** use the obstacle-avoid service's own move API: it needs `USE_REMOTE_COMMAND_FROM_API`, which may take control away from the staff controller (we never touch it). **Plain `Move` does not respect avoidance** (2026-11-04 18:08: avoidance on, the dog walked into a person/box; §4). The joystick therefore has a second drive mode, "sticks", that sends the stick input the Unitree remote/app sends (`rt/wirelesscontroller`, the path the avoidance service filters per the vendor example `obstacles_avoid.py`), plus our own LiDAR forward brake in both modes (§2c). Sticks mode is **not yet tried on the real dog**: run "First sticks-mode test" (§2c) first.

**Hard caps in RealDog** (applied after any route file): 0.5 m/s forward/back, 0.3 m/s sideways, 0.8 rad/s yaw, 10 s per segment. `drive()` and routes refuse unless connected, not locked, standing and avoidance confirmed on (routes also need stationary). Unknown = refused.

## 2c. Browser joystick (`patrol/dog/joystick.py`)

Local web page to drive the dog by hand. It serves on `127.0.0.1` only, and one process owns the single WebRTC connection (close the phone app).

**Easiest: double-click `scripts/dog_joystick.command`** in Finder. It starts the server for the real dog in a Terminal window and opens the page. If a joystick is already running, it only opens the page. Keep that Terminal window open: Q / Enter there = STOP.

```bash
scripts/dog_joystick.command                              # real dog, opens the page (same as double-click)
scripts/dog_joystick.command --fake                       # simulated dog
.venv/bin/python -m patrol.dog.joystick --fake            # by hand: simulated dog, no network at all
.venv/bin/python -m patrol.dog.joystick --config config/dog.local.json --open   # by hand: real dog
# page: http://127.0.0.1:8765/   (--port to change, --out for photos and logs, --open opens it,
#        --no-auto-connect turns auto-connect off)
```

**Workflow on the real dog** (no terminal typing needed):
1. Start the launcher. The cable can still be out: the server **connects by itself** as soon as the dog answers on port 8081 (it checks every 3 s, and only while the dog was never reached; no motion on connect). The page says "waiting for the dog…".
2. **Run test** (Dog panel): pick *Audio test* or *Read check*. The server releases its connection, runs the same code as `real_selftest --step audio|read` on a fresh connection (audio uses the *Set volume* slider, or 5 if the slider is at 0, and restores the old volume after; it is **FAIL** unless the mic hears the chime), appends the result to `evidence/dog/session.jsonl` (`"source": "joystick"`), shows PASS/FAIL and the key numbers under the button, then **re-arms automatically**. No motion. Sticks are off meanwhile; **STOP still works** (it is sent on the test's connection). A STOP during a test leaves the re-armed connection **locked**: press Re-arm yourself when ready.
3. **Shut down server** (Dog panel, click twice within 4 s): same as Ctrl+C in the terminal. The dog lies down softly, then the server exits.

Motion steps (`move`, `halt-mid-move`, `expiry`, `rest`, `prepare`) are **not** on the page: they stay terminal-only with `--arm`.

`--fake` runs the real RealDog code on a simulated body (`patrol/dog/sim_conn.py`). The simulator's own behaviour (for example a Move that expires after 1.0 s) is an assumption, **not** a measurement of the real dog.

Connecting never moves the dog. Run it in your own Terminal so the terminal keys work.

**Restart the server after changing any `.py` file.** `joystick.html` is re-read on every page load, but the Python code is loaded only at start. A stale server shows the new buttons and silently ignores them (2026-11-04: the audio panel did nothing because the server had started at 14:55, before the audio code existed).

| Control | Action |
|---|---|
| **STOP (lie down softly)** button, `Space`, `Q`, REST button | `RealDog.rest()`: StopMove, then StandDown (1005). **Never Damp.** Top priority, works any time, from any open page (even view-only) |
| Terminal `Q` / `Enter` | Same soft lie-down. `Ctrl+C` = lie down, then exit (unlike real_selftest, where Ctrl+C only stops walking) |
| Left stick / `W` `S` `A` `D` | Walk forward/back, sideways |
| Right stick / `J` `L` / `←` `→` | Turn |
| Speed slider | 10–100 % of the caps (default 50 %, i.e. 0.15 m/s forward) |
| Release stick/keys | One StopMove, dog stays standing |
| Stand up | `prepare()` (StandUp + BalanceStand), only when stationary and not locked |
| Re-arm | STOP latches RealDog's motion lock. Re-arm closes the adapter and connects a new one (no motion), then Stand up. Refused while sticks are held, busy, resting, or the dog is not stationary |
| Head light | On/off + brightness 0–10 (VUI api 1005, read with 1006 on connect). Worked on the real dog (15:00–15:04) |
| Run test | `read` or `audio` from real_selftest, no motion; then automatic re-arm (see workflow above). Controller only; refused while busy, resting, moving, recording or talking, or if the dog is not stationary |
| Shut down server | Click twice within 4 s. = Ctrl+C: soft lie-down, then exit. Controller only. Logged (`shutdown_requested`) |
| Speaker & microphone panel | Volume 0–10 (VUI 1003/1004; the dog starts at **0 = silent**), Say (macOS TTS, Italian/English), Test chime, Stop audio, Hold to talk (laptop mic → dog speaker, controller only), Listen (dog mic → browser, any tab), Record N s of the dog's mic to a WAV. Meters at 10 Hz. Every STOP also cuts the speaker. Audio never affects motion. Not yet tried on the real dog through this page |
| Photo | `capture_frame` → JPEG in `evidence/dog/`, path shown on the page |
| Set home here | Centres the safety fence on the dog's current spot. Controller only, stationary only. Logged (`set_home`). See §7 "Automatic safety thresholds" |
| Safety thresholds checkbox | Fence / speed / tilt / overshoot trips. **Checked at every server start.** Unchecking: controller only, stationary only, logged (`safety_envelope_off`), red "SAFETY THRESHOLDS OFF" banner + terminal line. **Back ON after every Re-arm and every restart** (never carried over). Can't be changed while connecting; the checkbox shows the dog adapter's real setting (greyed out while unknown) |
| Take control | Shown on every view-only tab. Moves control to this tab: the server sends StopMove first (dog stays standing), demotes the old tab, logs `control_taken`. A view-only tab that touches a stick or move key gets a "press Take control" hint |
| Live video | MJPEG, ~10 fps, downscaled to 640 px wide |
| LiDAR panel (top-down) | Live from the dog's L1 LiDAR (`rt/utlidar/voxel_map_compressed`, native decoder), pushed at ≤ 5 Hz to every tab. 8 × 8 m around the dog, forward = up, 1 m rings, points coloured by height, floor hidden. Shows `LiDAR: N pts · age` (red when old or when updates stop) and **Nearest obstacle ahead** (closest point in a dog-wide corridor, measured from the nose). The LiDAR streams **only while the dog is standing**: lying down with no data the panel says "LiDAR streams only while the dog is standing — press Stand up" (no button). Standing and no data within 5 s: "No LiDAR data, the sensor may be off" + **Turn LiDAR on (ask staff first)** (standing only: the page hides it and the server and `lidar_switch_on()` refuse while not standing; controller only, logged `lidar_switch`, sends `"on"` to `rt/utlidar/switch` once; never automatic; offered only when no message at all arrived, if messages arrive but cannot be decoded the page says so instead). Connect-time problems show as `warning: ...` (e.g. traffic-saving refused); without the native decoder (`set_decoder` missing or failing) the stream is **not subscribed** at all. `--no-lidar` / `lidar_enabled: false` turns the whole panel off ("LiDAR disabled by config"). Connect subscribes (read-only) and asks the WebRTC session to stop traffic-saving (session only, not a dog setting). Works with `--fake` (simulated room with two boxes). **Not yet tried on the real dog** |
| Drive via remote-controller path (checkbox, Dog panel) | Drive mode **"sticks"**: the sticks go out as simulated remote-controller input on `rt/wirelesscontroller` (`RealDog.send_sticks`, `{"lx","ly","rx","ry","keys":0}`, each clamped to **±0.3** = `STICK_MAX`) instead of `Move`, so the dog's own obstacle avoidance applies. Mapping: forward `ly +`, strafe right `lx +` (so stick left = `lx −`) from the vendor example, not measured; **turn left = `rx −`** (measured on the real dog 2026-11-04 19:30: `rx +` turns right, the vendor example is wrong; this mirrored turn made the follow demo dither at 180° from its heading, stepping in place, until fixed); stick = commanded speed / joystick cap × 0.3. Speed per stick unit depends on the dog's speed level (unknown): watch the measured speed on the page; the 0.6 m/s speed trip is the backstop. Same preconditions as Move (connected, not locked, standing, avoidance confirmed, inside the fence); stick sends count as motion for the fence. **"Move" at every server start.** Switch: controller only, only while stationary and no stick held (else refused with an event), logged `drive_mode`. Header badge shows the mode. Every stop (release, dead-man, WS loss, blur, Take control, STOP) also publishes **zero sticks** right away and 4 more times over ~0.2 s, before StopMove. After sticks were used (or while in sticks mode), every new connection (Re-arm, auto-connect, after a page test) sends one zero-stick burst right after connect (no motion; logged `zero_sticks`) and its stops zero the sticks too, in case a dropped link ate the release zero. "test first: staff controller stop must still win" |
| LiDAR brake (0.5 m) (checkbox, Dog panel) | Both drive modes. While the latest LiDAR view is fresh (received ≤ 1 s ago, its scan ≤ 1 s old, not stale, scan and pose known), forward speed becomes **0** when *nearest obstacle ahead* < **0.5 m** (`lidar.brake_forward`); the next Move carries vx 0 (sticks: ly 0). Turning, sideways and backward are never braked, and the brake never starts motion. **No fresh LiDAR = no brake** (fails open): badge and status say `inactive (no fresh LiDAR)` in amber. Engage / release: one event + one log line each (`lidar_brake`). **On at every server start**; unchecking is controller only, logged `lidar_brake_off`. Badge: ready (green) / BRAKING (red) / inactive (amber) / OFF (red) |
| Follow signal (demo) panel (below the LiDAR panel) | Demo of `docs/Lidar + SLAM.md` §8b: the dog follows a **simulated** Wi-Fi signal. **Place signal point** (or **Move signal point**), then click the LiDAR panel: the point is converted to the odometry frame with the pose of the LiDAR frame on screen and drawn in magenta, labelled "simulated", with a dashed circle where "arrived" starts (~0.8 m; was 1.3 m until 2026-11-04 21:00). `VirtualBeacon` (`patrol/dog/follow.py`) turns the dog's odometry distance into a fake RSSI (−40 − 25·log10 d dBm, σ 2 dB noise (was 3 dB), clamped −95…−30); the follower only ever sees that number. Live RSSI + 30 s sparkline (with the −38 arrive / −43 resume lines), estimated direction as a yellow arrow from the dog, state (following / probing / arrived / stopped) + reason, run timer "x / 60 s", header badge. The point must lie within **fence radius − 1.5 m of home** (home and radius from the dog's safety status; unknown home = refused); otherwise placing and Start following are refused (event, log, reason shown in the panel); the page draws the allowed area while placing. **Start following** (controller only, re-checked after the status read: refused if control moved to another tab) is refused (event + `follow_start` log with the reason) unless: point placed and inside that area, connected, standing, stationary, no stick held, avoidance confirmed on, safety thresholds **on** and inside the fence, LiDAR brake **on** and fresh, position known, not locked / busy / resting. While following, the follower's forward speed (≤ 0.3 m/s, never backward or sideways) and turn rate (≤ 0.5 rad/s) go out through the **same drive path as the sticks**: LiDAR brake, the selected drive mode (Move or sticks), the joystick caps, RealDog's checks. "arrived" (smoothed RSSI ≥ −38 dBm, ~0.8 m) = one StopMove, the dog holds standing, and following resumes below −43 dBm (~1.3 m). Ends on: Stop following / Clear (StopMove, stays standing), the **60 s time limit** (StopMove, stays standing), **any page stick or key** (manual takeover: no stop, the page drives on), STOP / REST (soft lie-down), **follow dead-man** (while following the page sends `follow_alive` every 250 ms; > 1 s of silence ends following with StopMove, since no stick messages flow then), WebSocket loss, tab blur / hidden / page closed, Take control, safety trip, Re-arm, disconnect, motion lock, LiDAR brake off or not fresh, safety thresholds off. While following: Stand up, Run test, Set home here, drive-mode switch and turning the thresholds off are refused. In Move mode the panel says "dog's own avoidance is off — our LiDAR dodge + brake only". **LiDAR dodge** (2026-11-04 evening): every LiDAR frame also carries `clear` = free distance in 24 directions (every 15°, from the body's edge, 0.6 m wide corridor, `lidar.clearance`) and `near_m` = closest point to the body centre (`lidar.turn_clearance`). While following, a leg whose heading is blocked within **0.8 m** is steered to the nearest free heading within ±120° (same side kept while it stays open; released once the goal heading is clear past 1.0 m); it walks only while the way it faces is clear past 0.6 m (so it turns first instead of pushing at the obstacle), and a leg never ends half-way round an obstacle, but a dodge is cut off after 2 legs' length or 10 s and the signal is re-checked (no wall-following for metres). Nothing free within ±120° → probe the freest direction; boxed in → hold still. **Turn guard** (swept footprint): each LiDAR frame also carries `turn_room` = how far the dog can turn in place each way (10° steps, up to 90°) before its footprint (0.70 × 0.40 m) + 8 cm would touch a point (`lidar.turn_room`). It turns toward a side only with ≥ 20° room (slowly, ≤ 0.25 rad/s, when room < 90° or something is within 0.6 m); if the short way is blocked and the long way fully open it goes the long way round (latched, no dithering); if neither, it steps out straight at most 0.4 m (only if ahead is clear), then takes a short leg toward the side with more room, else holds still (60 s limit / STOP end it). Missing or bad `turn_room` → radial fallback (nothing within 0.50 m of the centre). Stuck rule (braked while asking forward) is now 1 s (was 2 s). The 0.5 m brake stays as the backstop, in both drive modes; in sticks mode the dog's own avoidance applies as well. The LiDAR panel draws the 24 directions while following (red = blocked within 0.8 m). Logs: `follow_dodge` (start/end, side, reason), `follow_sample` gains `dodge`, `near_m`, `turn_room`, `bad_turn_room`. Kinematic sim (5 layouts × 10 noisy runs, 3 dB noise): arrived 9/9/7/6/10 of 10 vs 8/4/4/5/9 without the dodge, ~0 s braking, no footprint overlap (also with 0.2–1.0 s LiDAR lag, reviewer's sim). **Check on the first real run:** `turn_room` in open space must read `[90, 90]`; if the dog's own legs show up as obstacles it reads `[0, 0]` and the dog never turns while following (fails safe, but then the footprint in `lidar.py` needs widening). Logs: `beacon_place` / `beacon_clear`, `follow_start` / `follow_stop` (reason), `follow_state` (transitions), one `follow_sample` per second (pose, rssi, rssi_s, state, cmd, nearest ahead, braking), `stop` kinds `follow_arrived` / `follow_stop` / `follow_hold`. Built and tested in `--fake` (goes around the box). **Not yet tried on the real dog** |
| Status panel | 4 Hz: drive mode, LiDAR brake state, safety envelope state (OK / TRIPPED: reason / OUTSIDE FENCE / OFF), distance from home / radius, tilt, standing, stationary, avoidance, battery, speed, lock reason, last stop latency, event log |

Safety:
- **Staff controller is always the primary stop.** This page is a backup.
- **Every operator STOP = stop walking + lie down softly.** Automatic stops (stick release, dead-man, WebSocket loss, tab hidden or window blur) = StopMove only; the dog stays standing.
- Speed caps in the server: **0.3 m/s** forward/back, **0.2 m/s** sideways, **0.6 rad/s** yaw (RealDog's own caps 0.5/0.3/0.8 apply too). `Move` ≤ 20 Hz (the page sends ~15 Hz).
- `RealDog.drive()` refuses unless connected, not locked, standing **and** avoidance confirmed on (unknown = refused). A failed or timed-out Move locks the adapter and is never retried. `RealDog.send_sticks()` (sticks mode) has the same checks; a failed publish locks the adapter, zeroes the sticks and fires StopMove.
- Sticks mode: `halt()`, `rest()` and `stop_move()` publish zero sticks first (no wait, repeated for ~0.2 s) once sticks were used on that adapter, so a stick stream can't keep the dog walking. Zero sticks are allowed even when motion is locked.
- **Dead-man:** no stick message for 300 ms while moving → StopMove. Also StopMove on page close, tab switch, window blur, or WebSocket loss.
- One browser controls (the first to connect). Other tabs are view-only (STOP still works). No avoidance-off, no tricks, no mode or firmware commands.
- Localhost only: the server binds `127.0.0.1`, rejects any Host that is not `127.0.0.1`/`localhost`, and rejects foreign `Origin` headers with 403 (blocks other websites and DNS rebinding).

**First sticks-mode test** (real dog, staff present, before relying on it):
1. Dog standing, open floor, LiDAR brake on. Speed slider at the minimum (10 %). Switch on "Drive via remote-controller path" (badge: `drive: STICKS`).
2. **Staff stop test first:** push a stick briefly so our sticks are active, and have staff press their controller stop while we keep pushing. The dog **must stop**. If it does not, release the stick, press STOP, switch sticks mode off and do not use it.
3. Verify directions **one at a time**, short pushes: forward (`W`), strafe left (`A`) and right (`D`), turn left (`J`) and right (`L`). If any is mirrored, stop and fix the mapping (`Controller._to_sticks`) before going on. (Turn was mirrored on 2026-11-04 19:30 and is fixed: `rx −` = turn left; re-check `J`/`L` first.) Watch measured speed: at 10 % it should be well under 0.3 m/s.
4. Release test: release the stick mid-walk, and once let the dead-man trigger (switch tab): the dog must stop (log shows `stop` with zero sticks before StopMove).
5. Box test: walk slowly toward a box with the LiDAR brake **off** (checkbox) to see the dog's own avoidance; then with the brake on. Note the stopping distances in the session log.
6. Unknown, not tested: whether the dog keeps the last stick value if messages stop arriving (link loss). Treat it like Move: **if the WebRTC link drops, only the staff controller can stop the dog.**

**Follow demo on the real dog** (§8b; staff present; not done yet):
1. Staff present with their controller in hand. Open area **≥ 4 m** across, nothing fragile within reach; people stand outside the area. Safety thresholds on (fence 3 m), LiDAR brake on, LiDAR panel live.
2. Drive mode: **Move** (the panel warns: dog's own dodging is off, LiDAR brake only) unless the **first sticks-mode test above has passed**; only then use sticks mode, so the dog's own avoidance applies too.
3. **Set home here at the area centre**, then walk the dog **~1.5 m to one side** of it. Stand up. Press **Place signal point** and click the LiDAR panel **~1.5 m on the other side** of the centre (the page shows the allowed area while placing: within fence radius − 1.5 m of home, so 1.5 m with the 3 m fence; outside it, placing and Start following are refused with the reason shown in the panel). Check the magenta point is where you meant and the RSSI number reacts.
4. Hand on **STOP** (Space / Q). **Start following**. Watch the dog, not the page; the run ends by itself after 60 s.
5. Any doubt: staff controller stop, or STOP (soft lie-down). Touching a stick or key also ends following and gives manual control.
6. Done when: "arrived" in < 60 s, 3 of 3 runs, without touching anything. Note in the session log: time to arrive, min nearest-ahead (from `follow_sample`), any brake / stuck events.
7. **Dodge test** (after step 6 passes): put a box (≥ 40 cm tall, soft, light) on the straight line between dog and point, ~1 m in front of the dog. Start following. Expected: red rays on the LiDAR panel toward the box, reason "dodging: … going left/right", the dog curves round it without stopping at it, `follow_dodge` in the log. Anything touching the box: STOP. Note the closest approach (`near_m` in `follow_sample`).

Logs (JSON lines, `evidence/dog/joystick.jsonl`; `--fake` writes to `evidence/dog/fake/`): every stop (STOP, release, dead-man, WS close) with **stop latency** (stop command → `stationary`), speed at the stop and time since the last Move; dead-man triggers; connections and re-arms; photos; brightness changes. The latest stop latency is shown on the page. During normal use this collects the halt-mid-move data (step 5). It does **not** measure command expiry (step 6): the joystick always sends StopMove, so a Move that is left to expire never happens.

How it was built and checked: written by an agent, then reviewed by a separate high-effort reviewer. Fixes applied after review:
- Stuck-key bug: keys are tracked by physical key, any modifier releases all keys, STOP keys always work.
- Cross-site control blocked (403 on foreign Origin/Host).
- STOP during a re-arm is delivered on the old adapter, and loudly reported if it cannot be delivered.
- NaN and infinite values from the browser are rejected.
- A dead WebRTC link is reported as disconnected.
- Selftest cancellation handling and startup cleanup.

Not fixed (harmless): a pending-request bookkeeping leak in the vendor library; `rest()` can fire one extra StandDown if the first gets no reply.

## 3. What we know about this dog

| Item | Value | Source |
|---|---|---|
| Wired IP | `192.168.123.161` | Staff; verified by ping 2026-11-04 |
| MAC (wired) | `7e:1d:75:60:f5:89` | ARP table |
| Connection method | `LocalSTA` over wired Ethernet | Verified: connects |
| Signaling | **Legacy `/offer` on port 8081** (Python 3.8 aiohttp server). Port 9991 closed. | Port check + library source (`unitree_auth.py`); connect works |
| AES key needed? | **No.** Connects without a key. | Verified 2026-11-04 (7 successful connects) |
| Firmware | Probably **older than 1.1.11** (only the legacy port is open) | Inferred, confirm with staff |
| Motion mode | `normal` | Motion switcher read, 2026-11-04 |
| SSH (22) | Open. **Read-only use at most, never change anything.** | Port check |
| Port 1234 | Closed (connection refused). The port staff mentioned isn't in use. | Port check |
| Battery (at 12:55) | 59 %, 28.6 V, 11 charge cycles | `lowstate` (`soc`, `power_v`, `cycle`) |
| Posture | Standing: `mode` 1, body height 0.32 m | `sportmodestate` |
| Settings readback | avoidance **on**, volume 0, brightness 0, speed level 0, UWB on, foot raise 0.09 m | `multiplestate` |
| Odometry | Origin is not fixed: probe read (2.49, -1.52) m, session started near (0.18, 0.00) m. Use deltas only. | `sportmodestate.position` |
| Edition (AIR/PRO/EDU) | TBD | Ask staff |
| Modifications | ROS dependency removed by staff. Details TBD. | Staff |
| Unitree account holder | TBD (only matters if a key turns out to be needed; it did not) | Ask staff |

---

## 4. Capabilities (HAC-2)

Status: `supported` / `unsupported` / `unknown`. Add evidence (date, output, photo path).

| Capability | Status | Evidence |
|---|---|---|
| Network reachable | supported | Ping 4/4, ~0.5 ms; 8081 open (2026-11-04) |
| Connect (no motion) | supported | Probe 12:54 + 12:55 (1.73 s); 5 of 5 in the 13:33–13:37 session (2.05–2.69 s). First probe try timed out (see §8). |
| Video / front camera | supported | 1280×720 BGR frame, `evidence/dog/go2_frame_20261104-125502.jpg`; `capture_frame` photos in session 13:33 |
| Fresh status reading | supported | `rt/lf/sportmodestate` 161 msgs in 8 s; `lowstate` + `multiplestate` ~1 Hz |
| Stand up / lie down | supported | Joystick: StandDown 3 of 3 (dog lay down softly; reply takes > 3 s, so it counted as a timeout and the backup send went out). Stand up (StandUp + BalanceStand) worked after Re-arm, 14:03 UTC. |
| Velocity move (`Move`) | supported | `--step move`: 0.2 m/s for 1 s → 0.214 m, ~4 cm sideways drift, stop verified (2026-11-04 13:37) |
| Obstacle avoidance on/off + readback | readback supported | `multiplestate.obstaclesAvoidSwitch = true` and service query = true. Switching not tested (already on); our code never switches it (read-only). |
| Does plain `Move` respect avoidance? | **no** | 2026-11-04 18:08 (joystick, Move): avoidance on (`obstaclesAvoidSwitch = true`, panel "avoidance: yes"), the dog walked into a person and a box without dodging. |
| Do remote-controller sticks (`rt/wirelesscontroller`) respect avoidance? | unknown | Vendor example says the avoidance service filters this path. Joystick "sticks" mode built (sim-tested only); run "First sticks-mode test" (§2c). |
| `halt` / `StopMove` while still | supported | Accepted in 0.154 s, stays standing |
| `halt` / `StopMove` mid-walk | supported | 15 joystick releases (StopMove): stationary after median 0.08 s, max 0.91 s; speed at release up to 0.39 m/s |
| Command expiry (commands stop arriving) | unknown | Skipped by team decision (step 6) |
| Odometry (`rt/sportmodestate`) | supported (read) | `position` [2.49, -1.52, 0.31], `velocity`, IMU `rpy` |
| Head light (VUI brightness) | supported | Joystick: set 0 → 5 → 6 → 0 (api 1005), read back on connect (api 1006) |
| Speaker | supported | `--step audio --volume 5` 15:41: chime streamed over the WebRTC audio track (`sendrecv` transceiver, no renegotiation), heard at the dog by Leonardo. Volume get/set (api 1004/1003): 0 → 5 → restored 0. Nothing uploaded to the dog (we don't use the vendor's audiohub upload) |
| Microphone | supported | Same run: 48 kHz stereo s16, 200 of 200 frames in 4 s. Loopback: 660 Hz +28.6 dB, 990 Hz +17.7 dB above the pre-chime background, ~0.2 s after sending. `evidence/dog/audio_selftest_20261104T144159932871Z.wav` |
| LiDAR | **supported** | 2026-11-04 18:08–18:13 (screen recording): live in the joystick panel, 4000 pts shown, 0.0 s old, room walls + people visible, "nearest obstacle ahead" 0.53 m. Sensor was already on (no switch sent). **Streams only while the dog is standing**: lying down → 0 pts (`--step lidar` at 18:11 with the dog lying: 0 messages); after Stand up → points again. Rate, range and frame still to measure (run `--step lidar` with the dog standing) |

Rule: **unknown standing / stationary / avoidance state blocks walking. Never default to true.**

---

## 5. Tasks

Mirrors Linear (P-HAC-1). Tick here and in Linear.

### HAC-1 · D1 · Build FakeDog that runs without the robot · 🔴 Urgent · 0–3h · Linear: Done
- [x] Export `create_dog(mode, config, output_dir)` from `patrol/dog/__init__.py`
- [x] Implement every DogPort method (connect, prepare, get_status, run_route, capture_frame, halt, close) with the contract dataclasses
- [x] Keep a `trace` list of calls so tests can check what happened
- [x] On capture, copy a small bundled JPEG into `output_dir` and mark it `simulated=True`
- [x] Scenarios `route_blocked` (completed=False, stopped=True) and `stale_frame` (old timestamp); reject unknown names
- [x] No hardware imports, no busy waits (`tests/dog/test_fake_dog.py`, 30 tests)

### HAC-2 · D2 · Find out what our exact Go2 supports · 🟠 High · 3–10h · Linear: In Progress
- [x] Find the connection mode → wired Ethernet, LocalSTA, `192.168.123.161`
- [x] Find the signaling method → legacy 8081, no AES key needed (verified)
- [ ] Get edition and firmware from staff
- [x] Install the library: `.venv` with **Python 3.12**, non-editable install of the local clone (aiortc 1.15.0, av 17.1.0, cryptography 50.0.2). Pinned in `requirements/dog.txt`.
- [x] Video and status reading work
- [x] Movement API works (`Move`, 0.2 m/s, 1 s)
- [ ] Avoidance switching and whether `Move` respects avoidance (needs staff slot)
- [x] Speaker + mic: supported (`--step audio`, 15:41)
- [ ] Fill §4 with evidence (done for what we ran; LiDAR and command expiry still unknown)

### HAC-3 · D3 · Prove connect, camera and halt on the real dog · 🟠 High · 3–10h (staff slot) · Linear: Done
- [x] Connect without any motion, read fresh status, save one live photo (2026-11-04)
- [ ] Show that `halt` stops the dog (staff holds their controller). Still: ✅ 0.154 s · mid-walk: skipped by team decision (step 5), assumed
- [x] Stand, turn on avoidance, read it back (already standing + on; `prepare` confirmed)
- [x] One short supervised move with the same control path (0.214 m)
- [ ] Note what happens if commands stop arriving (command expiry): skipped by team decision (step 6), assumed
- [ ] Unknown standing/stationary/avoidance blocks walking: done in code and logic tests (fake connection); not provoked on the real dog

### HAC-4 · D4 · Calibrate the room_2 route (start → room_2) · 🟠 High · 10–18h · Linear: Todo
- [ ] Mark `start` and `room_2` on the floor; record start pose and orientation
- [ ] Route as bounded segments in a route file (units + turn direction documented; template: `config/dog_routes.example.json`, `calibrated: false`)
- [ ] Check cancel/deadline before every segment and during waits
- [ ] Return completed=False/stopped=True if blocked; stopped=False if stop can't be verified
- [ ] Reject `entrance`/`display` as `unsupported` until calibrated

### HAC-6 · D5 · Make halt and camera dependable · 🟠 High · 10–18h · Linear: Done
- [x] `halt()` works while `run_route()` is running (doesn't wait for the route lock). Tested with a fake connection; **real dog: not tested** (step 5 skipped)
- [x] All vendor calls have timeouts; a cancelled worker sends no more commands
- [x] Never auto-retry a timed-out move (`tests/dog/test_real_dog_logic.py`)
- [x] Capture only after the request starts; reject frames older than 5 s (`capture_frame`)
- [x] Save a unique complete JPEG (temp file `.tmp_<name>.jpg` + rename), return its absolute path. Works on the real dog.
- [x] After cancel or halt, block new routes until the adapter is recreated (code: any incomplete route locks it)
- [x] Tests: disconnect, unknown avoidance, halt during route, timed-out command

### HAC-7 · D6 · Package dog selftest and handoff · 🟡 Medium · fake by 3h, full by 18h · Linear: In Progress
- [x] `python -m patrol.dog.selftest --mode fake` works
- [ ] Real mode in `selftest`: `--mode real` currently only delegates to the `read` step of `real_selftest`. Full real runs use `real_selftest --step ... --arm` (never moves on import/connect)
- [x] Pin deps in `requirements/dog.txt`; add `config/dog.example.json` (+ `config/dog_routes.example.json`)
- [ ] Finish `handoff/dog.md` (updated 2026-11-04; stays open until the staff questions in §6 are answered)

### HAC-5 · D4b · (Stretch) Entrance and display routes · ⚪ Low · 18–24h, only if room_2 is solid
- [ ] Calibrate `entrance` and `display` routes the same way as room_2
- [ ] Supervised test each, or leave as `unsupported`

---

## 5b. Next up (backlog)

- **LiDAR + SLAM + signal following, and the Raspberry Pi 5 on the dog.** Plan in [`Lidar + SLAM.md`](Lidar%20+%20SLAM.md) (live LiDAR panel in the joystick page, auto-dodge test, map + path planning, follow the drone's RSSI) and [`pi-bridge.md`](pi-bridge.md) (laptop off the cable). Stages 1–2 can start now; the rest comes after the core demo.
- **Project dashboard (view-only), separate from the joystick page.** Dog camera (+ drone camera later), dog status, event log (camera event → Grok decision → dispatch → drone hop → alert), Grok reasons, KPIs from the plan, and a STOP button (= soft lie-down). The joystick server adds view-only endpoints (video, snapshot, status) and the dashboard embeds them; it never opens its own connection to the dog (one WebRTC client only). Check ownership with the Console workstream first. (Today the joystick server only has `/`, `/ws` and `/video.mjpg`.)
- **HAC-46 (High): page STOP on a dead WebRTC link** (15:29, `Data channel is not open`). Show a dead link on the page within ~1 s and report an undelivered STOP loudly.
- **Next at the dog:** restart the joystick (Shut down, then the launcher), press **Run test → Audio test** once: expect the chime and "mic heard chime: yes". Then try the audio panel: volume, Say, Test chime, Listen, Record, Hold to talk.

## 6. Open questions for staff

1. Edition (AIR/PRO/EDU) and firmware version?
2. Port 1234: what was it meant to be? It's closed. Is it a service of theirs that should be running?
3. What exactly did they change (ROS removal)? Anything running on the dog we mustn't stop?
4. Is wired Ethernet OK to use during the demo, or should we use Wi-Fi?
5. Can we strap a small plate on its back for the Tello? (Shared with the drone project.)
6. Booked slot times for supervised tests (dog + drone together if possible).
7. What is the emergency button combo on their controller?
8. Is `StandDown` the "slow rest" they mean, or do they want `Sit`?
9. Does plain `Move` respect obstacle avoidance? (Answered by test 2026-11-04 18:08: **no**. Still ask: does the remote-controller topic from our client respect it, and does their controller stop override it?)

---

## 7. Safety rules

### Hard stop layers (in order)
1. **Staff handheld controller.** The primary stop; it doesn't depend on our laptop or cable. Staff hold it during every motion step. Emergency button combo: _TBD, ask staff_.
2. **Keyboard** in the terminal running `real_selftest` or the joystick. Only works when **you run it in your own Terminal** (single key, no Enter needed):
   - **Q or Enter = STOP**, top priority. Stops walking, then **lies down softly** (`StandDown`, api 1005). Works at any moment. Never sends `Damp` (1001), the rough drop. **Rule: every operator STOP = soft lie-down.**
   - **Ctrl+C in `real_selftest`**: stop walking (stay standing), then exit.
   - **Ctrl+C in the joystick**: lie down softly, then exit.
   - After `real_selftest` exits, `--step rest --arm` lies the dog down on demand. Stand it up again with `--step prepare --arm`.
   - Checked in a pseudo-terminal with a fake connection (ad hoc, not in `tests/`): Q and Enter both give Move…→StopMove×4→StandDown.
3. **Joystick page** (§2c): STOP button / Space / Q, plus the terminal keys above, all call `rest()` (soft lie-down). This is a backup, not the primary stop.
4. **Battery power button** (staff only). Last resort: the dog drops.

Automatic stops (stick release, dead-man 300 ms, WebSocket loss, page blur, Take control) send **StopMove only**; the dog stays standing. In joystick sticks mode every stop (automatic or STOP) also publishes zero sticks first (repeated ~0.2 s). The LiDAR brake (0.5 m) only zeroes forward speed and fails open without fresh LiDAR: it is a help, not a stop layer. **Safety threshold trips** (fence, speed, tilt, route overshoot; below) lie the dog down softly.

⚠️ **The soft lie-down has not been tried on the real dog yet.** Until it has, the staff controller is the stop you can trust.
⚠️ **Pulling the Ethernet cable is NOT a stop** until the `expiry` step shows what the dog does when commands stop arriving.
⚠️ A second script **can't** stop the dog while the first is connected (only one WebRTC client). The stop must come from the running script or the staff controller.

### Automatic safety thresholds ("safety envelope")

`RealDog` checks every sport-state message (~20 Hz, in the callback, no I/O). A trip **latches the motion lock** (reason like `safety: fence 3.21 m > 3 m`) and schedules **one** `rest()` (StopMove, then StandDown 1005; never Damp). The joystick shows it as a loud event + banner and logs `safety_trip` (and the stop latency as `stop` kind `safety_trip`). Recover with Re-arm, then Stand up. Re-arm is refused while a trip's lie-down is still running, and closing the adapter waits for it.

Extra checks added after the second review:
- **Odometry jump**: position changing > 0.5 m between two readings (reset or glitch) → motion refused (trip if moving) until "Set home here".
- **Unknown home or position** blocks Stand up / `prepare()` too, not just driving.
- A **running route stops** as soon as anything blocks motion (e.g. thresholds turned back on while outside the fence).
- If STOP is already lying the dog down, a trip doesn't send a second StandDown.
- **StandDown reply code 4201** (seen on the real dog 2026-11-04 16:24, 17:11, 17:13; it lay down every time) = accepted/busy: no second StandDown, logged `standdown_code_4201`, and "lying down" is confirmed from state within the same 8 s posture wait: sport mode 5 (lie down) or 7 (damping), or body height < 0.25 m (the real dog's `body_height` did not drop on 2026-11-04 evening, the mode is what changes). The rest report logs `posture_after` {mode, body_height}. Only if the state does not confirm it does the page show "STOP MAY NOT HAVE ARRIVED".
- A zero-stick burst on a closed data channel is logged as `zero_sticks dropped (data channel not open)` (never raises).
- The joystick's control loop runs the safety-event check in its own try/except: a failing check can never skip the dead-man / stop logic.

| Config key | Default | Trips when |
|---|---|---|
| `fence_radius_m` | 3.0 | horizontal distance from **home** > radius, while motion is possible (route running, a Move in the last 1 s, or measured motion) |
| `max_speed_mps` | 0.6 | measured horizontal speed > limit for ≥ 0.3 s (short gait peaks don't trip; our caps are 0.3–0.5) |
| `max_tilt_deg` | 25 | abs(roll) or abs(pitch) > limit for ≥ 0.2 s |
| `route_overshoot` | `{"factor": 1.3, "margin_m": 0.3}` | during `run_route` / `run_segments`: odometry travel since route start > planned × factor + margin (planned = Σ hypot(vx, vy) · duration) |
| `safety_envelope_enabled` | `true` | `false` = no automatic trips (values still measured and shown) |
| `lidar_enabled` | `true` | `false` = no LiDAR at all: no decoder switch, no traffic-saving flag, no topic subscription; the page says "LiDAR disabled by config"; `lidar_switch_on()` refuses. Safety valve, and for comparing stop latency with/without LiDAR (every selftest record and the joystick connect log have `lidar_enabled`). Joystick flag: `--no-lidar` |
| `home` | none | `[x, y]` odometry metres; otherwise set from the first position after connect |

Values must be positive finite numbers (`margin_m` may be 0); anything else → `AdapterError("invalid_input")`.

- **Home** = the first fresh position after connect, unless passed in (`home=`, config `home`, or `adopt_home()` before connect). Odometry is the dog's own frame since boot, so it stays valid across WebRTC reconnects. **The joystick keeps home across Re-arm**, so a re-arm after a fence trip doesn't silently move the fence.
- **Set home here** (`set_home()`): moves home to the current spot. Only connected, stationary, no route, no Move in the last second. Logged.
- **Outside the fence and not moving** (odometry drift, dragged, or after a trip + Re-arm): reported (state `outside_fence`), the dog is **not** laid down, but drive, routes and Stand up are refused until it is back inside or the operator presses **Set home here**. Decision: lying a still dog down gains nothing; refusing new motion is enough.
- **Unknown is never safe**: no home or no fresh position → motion is refused (`safety: position unknown`).
- **Switch off / on** (`set_safety_envelope()`, joystick checkbox): off only while stationary. Off disables only these four trips; caps, dead-man, STOP/Q, motion lock are unchanged. Turning it back on takes effect at once; if the dog is outside the fence then, it is not laid down, but driving is refused until Set home here.
- Only the first trip rests the dog; later trips of another kind are recorded only. `safety_status()` returns home, distance, radius, speed, tilt, limits, state, last trip and home changes.

Limitations:
- **Odometry drifts** (slips, turns, long runs): the fence and overshoot distances are approximate, not a geofence. Keep the real space bigger than the radius.
- **If the WebRTC link drops, our software can't see or stop the dog.** Only the staff controller works then.
- The thresholds are untested on the real dog (fake/sim only so far).

### Rules

- Dog only in our booked slot, **with staff present** and their controller ready.
- Never auto-retry a timed-out move. Every vendor call has a timeout.
- Photos only after the request starts. Reject frames older than 5 s.
- Speeds ≤ 0.3 m/s forward/back by hand (joystick caps); the first runs used 0.2 m/s.
- **Firmware: never overwrite, update or flash it. No OTA, no re-bind, no factory reset, no AP ↔ Network mode switch, no motion-mode switching** without staff.
- SSH: read-only at most. Never change anything on the dog.
- **Obstacle avoidance is read-only.** Our code never switches it (no set call anywhere). Not confirmed on → Stand up still works, but drive / sticks / routes are refused ("avoidance not confirmed on — motion refused; ask staff").
- If it misbehaves: staff controller stop first → `halt` → power cycle only with staff.

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `ping: No route to host` right after plugging in | Address lookup still in progress. Wait a few seconds and retry. |
| Ping times out, `route get` shows `en0` | Ethernet IP not set. Run the `networksetup` command in §2. |
| `LocalSignalingPortError` (tried 9991, 8081) | Wrong IP, cable out, dog off, or 8081 closed. Re-run the `nc` check. Seen once at 13:08, cause not recorded. |
| `unsupported: unitree_webrtc_connect is not installed` | That Python has no library. Use `.venv/bin/python`. If it still fails after `pip install -e`, reinstall non-editable (hidden `.pth` file, §2). |
| `RobotBusyError` | Phone app or another script connected (or a joystick still running). Close it. |
| `AesKeyRequiredError` | Not expected on this dog (connects without a key). Would mean firmware changed. Ask staff for the key. |
| `DataChannelTimeoutError` (peer=connecting, ice=completed) | Happened on the very first connect (probe try 1), then never again in 7 connects. Wait 10–20 s and run again. If it repeats, ask staff. |
| `NoSdpAnswerError` | Reconnect. If it keeps failing, ask staff. |
| Joystick: "MOTION LOCKED (...)" | A STOP, halt or failed Move latched the lock. Release the sticks, press **Re-arm** (no motion on connect), then **Stand up** if the dog is lying. |
| Joystick: "Cannot listen on 127.0.0.1:8765" | Another joystick is running. Close it or use `--port`. |
| Joystick: sticks do nothing | Read the block bar: not standing, avoidance not confirmed, busy, or view-only tab (click Take control if no other tab has it). |
| Joystick: buttons enabled but nothing happens, Volume shows `?` | Server older than the code. Ctrl+C the joystick (or Shut down server), start it again. |
| Joystick: "waiting for the dog…" forever | Cable / power / Mac's static IP (§2). Check `ping 192.168.123.161`. Auto-connect only runs until the first successful connection; after a dropped link press Re-arm (HAC-46). |
| Joystick: MOTION LOCKED "STOP during test" | You pressed STOP while a page test ran. Press Re-arm when the dog is safe. |
| Joystick STOP logs `Data channel is not open` | WebRTC link dead: the stop did **not** reach the dog. Staff controller, then Re-arm. Seen at 15:29, cause unknown (HAC-46). |
| Joystick posture commands time out after ~3 s | Server started before the 8 s posture timeout fix. Restart it. |
| Audio selftest `loopback_heard: false` | Volume 0 (see `note`), or the mic didn't hear the chime. Listen at the dog; try `--volume 7`. |
| Speaker silent | The dog's volume starts at **0**. Set it (joystick slider or `--volume 5`). |
| `--step ...` says "re-run with --arm" | The step moves or commands the dog. Check the preflight (staff, 2 m clear, app closed), then add `--arm`. |

---

## 9. Session log

Newest first. Date, who, what was done, result.

### 2026-11-04 21:48–21:58 local: Follow demo on the real dog, Move + sticks mode (Leonardo, staff present)
- **Worked:** STOP → soft lie-down confirmed every time (`lying_confirmed: true`, `posture_after` mode 5, body height stays 0.32). Turn sign now correct in both modes (commanded +0.5 → yaw up, ~0.46 rad/s in sticks mode). `turn_room` read `[90, 90]` in every sample (own legs not seen as obstacles). One live dodge start (`follow_dodge`, obstacle 0.77 m toward the goal, going right). LiDAR brake engaged at 0.13–0.30 m in manual driving.
- **Follow never reached its steering phase:** all runs stayed in `probing`. The follower only gets RSSI, so the first move is a blind probe: turn 75° (side alternates every run, regardless of where the point is) and walk 0.6 m. Points were 1.2–2.4 m from the dog, so runs either "arrived" during the probe (at 1.2–1.5 m = the old circle) or were stopped by hand after 3–8 s (median time to arrive in sim is ~25–35 s). This explains "sometimes it turns ~70° toward the signal, sometimes away".
- **Changed (21:00 UTC):** arrive −43 → **−38 dBm (~0.8 m)**, resume −48 → **−43 dBm**, demo noise 3 → **2 dB**. Sim, dog 3 m from the point: 56/60 arrive, median 34 s, stop ~0.75 m from the point. Round-a-box sim: 14/24 arrive in 60 s (16/24 before), 19/24 with 90 s; no overlaps.
- **Retest after the change (Leonardo):** works but **slow and not smooth**: it stops to re-estimate every leg and the estimate is often wrong. Next step if there's time: smoother follower, or a direction source (drone reports its position) for the video.
- Sticks mode reached 0.35–0.40 m/s while following (cap 0.3; 0.6 trip never fired).

### 2026-11-04 ~21:00–late local: turn-sign fix, STOP confirmation, LiDAR dodge (Claude, no robot)
- **Real follow test 19:30–19:34 (Leonardo, sticks mode):** the dog turned ~90–180° the wrong way and then stepped in place, never walking. Log: commanded turn `+0.5` → yaw decreased (and `−` → increased) in every run; each settled at its leg heading + 180°, where the steering flips every tick. **Cause: `rx +` = turn RIGHT on this dog** (vendor example wrong). Fixed in `_to_sticks`; simulator now turns like the real dog; manual `J`/`L` in sticks mode were mirrored too. Two runs "arrived" at once because the point was within ~1.3 m.
- **STOP showed "may not have arrived" every time:** `body_height` stays ≥ 0.25 m when the dog lies; the next connect read `standing: false` (the mode changed). Lying is now also confirmed from sport mode 5/7; rest report logs `posture_after`.
- `close()` zeroes the sticks even when the dog reads stationary.
- **LiDAR dodge for follow mode** (Leonardo: a main feature): see §2c follow row. Swept-footprint turn guard added after the sim found corner clips while turning in place.
- Two independent safety reviews (Opus, read-only): no blockers. Fixed: unbounded step-out (18 m along a wall), unbounded dodge leg (17 m), thin turn margin, bad `turn_room` disabling all guarding. Open: lx/ly stick signs unmeasured; whether the dog holds the last stick on link loss; sticks-mode speed per unit (0.44 m/s seen vs 0.39 in Move); after "arrived" the follower resumes by itself below −48 dBm.
- `pytest tests/dog`: **361 passed**. Not looked at in a browser (Chrome extension not connected); **not tried on the real dog**.

### 2026-11-04 17:07–17:24 local: One-click workflow on the real dog (Leonardo)
- Launcher + **auto-connect worked**: startup connect failed at 17:11 (dog not reachable yet), then connected by itself at 17:20 in 2.07 s (`reason: auto`).
- **Run test → Read check: PASS**, connect 3.6 s, battery 53 %, photo saved. **Auto re-arm after each test worked** (3.75 s, `reason: after_check`).
- **Run test → Audio test ran at volume 0** (the page's slider had synced to the dog's volume, 0): speaker silent, mic heard nothing (660 Hz +1.5 dB, 990 Hz +3.9 dB), but it still said PASS because `ok` only meant "no error". **Fixed:** the page never runs the audio test at 0 (uses 5, restores after), and an audio step whose mic doesn't hear the chime is now FAIL (page and terminal). 4 new tests; `SimConn(volume_mutes=True)` makes the simulator's speaker silent at volume 0 like the real dog. **The audio test via the page still needs one real run at volume > 0.**
- **Shut down server worked** twice (17:11, 17:24): lie down, then exit.
- `pytest tests/dog`: **146 passed**.

### 2026-11-04 ~16:00–17:00 local: One-click workflow for the joystick (Claude, no robot)
- Launcher `scripts/dog_joystick.command` (double-click; opens the page). Auto-connect when the dog becomes reachable (TCP probe of 8081 every 3 s, only until the first connection). **Run test** button (read / audio, same code as real_selftest, then automatic re-arm; STOP works during it and stays latched). **Shut down server** button (= Ctrl+C). `RealDog.latch_lock()` added.
- Loopback check fix: the recording starts slightly after the test clock, so the chime can land before 1.5 s in the WAV (simulator: 1.4 s). Background now ends 0.5 s before the nominal chime time. Real-dog WAV unchanged: 660 Hz +28.6 dB, 990 Hz +17.7 dB.
- Checked: 10 new tests (`tests/dog/test_joystick_workflow.py` + 1 audio), `pytest tests/dog` **142 passed**; end-to-end on the real server process in `--fake` (audio + read test, both re-armed, Shut down → lie down → exit). Page JS parses and every element id exists; **not looked at in a browser and not tried on the real dog yet.**

### 2026-11-04 15:29–15:42 local: Speaker + mic test (Leonardo + Claude)
- **15:29: two STOPs from the page failed** with `device_error: Data channel is not open`: the WebRTC link was dead, so StandDown never reached the dog. Re-arm at 15:30 connected again in 2.6 s. Cause not known. **Open issue: HAC-46.**
- 15:30 and 15:41: STOP/REST logged `timeout: request api_id=1005 timed out` after 3.15 s. Reason: the joystick server had been running since 14:55, so the 8 s posture timeout fix was never loaded.
- The joystick's new Speaker & Microphone panel did nothing for the same reason: the page (re-read from disk) had the new buttons, but the server process predated the audio code (written 15:14–15:24). No audio events in `joystick.jsonl`.
- 15:41:46: joystick stopped with Ctrl+C (SIGINT) → soft lie-down, as designed.
- 15:41:59 `real_selftest --step audio --volume 5`: connected in 2.44 s, volume 0 → 5, chime at 1.5 s, volume restored to 0, dog lying and still at connect and at the end. **Leonardo heard the chime at the dog.** Mic: 200 of 200 frames, 48 kHz stereo.
- The step's loudness check said `loopback_rise_db: -1.2` (not heard), which was wrong: a noise burst at 0.3–0.6 s, before the chime, was louder than the chime. Frequency analysis of the WAV: 660 Hz +28.6 dB at 1.7–1.9 s and 990 Hz +17.7 dB at 2.0–2.3 s, so the mic heard it ~0.2 s after sending. **Fixed:** the step now reports `loopback_tone_rise_db` + `loopback_heard` (`audio.loopback_check`, 3 new tests); re-checked on this WAV: heard.
- `pytest tests/dog`: **132 passed**. `selftest --mode fake`: PASS.

### 2026-11-04 15:00–15:04 local: First joystick session on the real dog (Leonardo, staff present)
- Joystick started before the cable was in → `connect_failed`; after plugging in, **Re-arm** connected in 2.4 s. Home set automatically.
- Drove with keys/sticks at ≤ 0.3 m/s. **15 stick releases → StopMove: dog stationary after median 0.08 s, max 0.91 s** (this covers the skipped "halt mid-walk" test). Peak measured speed 0.39 m/s (gait peaks above the 0.3 command cap; safety limit is 0.6).
- **STOP / REST → soft lie-down worked 3 of 3.** The StandDown reply arrives only after > 3 s, so each logged a timeout and the backup send went out. Fix: posture commands (StandUp/StandDown/BalanceStand) now wait up to 8 s (`POSTURE_TIMEOUT_S`). **Restart the joystick to load it.**
- Re-arm → **Stand up** worked (StandUp + BalanceStand). Head light 0 → 5 → 6 → 0 worked. Live camera worked.
- Stop latency log: `evidence/dog/joystick.jsonl`. No safety trip (stayed inside the 3 m fence).
- Still untested on the real dog: command expiry (link loss while walking), safety trips, routes.

### 2026-11-04 afternoon: Browser joystick, tests, docs (Leonardo + agents)
- Built `patrol/dog/joystick.py` + `joystick.html` and the simulated connection `patrol/dog/sim_conn.py` (used by `--fake` and by the tests). Added head light control (VUI 1005/1006) and the rule **every operator STOP = StopMove + StandDown** (`RealDog.rest()`), never Damp.
- A separate high-effort reviewer went over it. Fixes applied: stuck keys, cross-site control (403), STOP during re-arm, NaN route values, dead link reported as disconnected, selftest cancellation, startup cleanup. Two harmless issues left (see §2c).
- `aiohttp` added to `requirements/dog.txt`.
- `pytest tests/dog`: **69 passed** (30 FakeDog, 17 RealDog logic, 22 joystick). `selftest --mode fake`: PASS.
- **Not done:** joystick not opened in a real browser, not run against the real dog. StandDown not sent to the real dog.

### 2026-11-04 13:33–13:37: First supervised session, steps 1–4 (Leonardo, staff present)
- Fixed before the run: the photo temp file was named `.jpg.tmp` and OpenCV refused it, so it's now `.tmp_<name>.jpg`. Unexpected errors now halt the dog instead of crashing the script.
- **1 read** ✅ connected in 2.1 s, standing (mode 1, 0.32 m), still, motion mode `normal`, avoidance on (service query + `multiplestate`), photo OK. Dog in open floor facing a corridor. Battery not captured (fixed in code afterwards: connect now waits up to 4 s for `lowstate`, sport state and `multiplestate`; not re-run on the dog). A second `read` run (no terminal keys) also passed.
- **2 prepare** ✅ no action needed; all readbacks `true`.
- **3 halt (still)** ✅ StopMove accepted in 0.154 s; stayed standing.
- **4 move** ✅ 0.2 m/s for 1.0 s → **0.214 m**, ~4 cm sideways, `completed; stop verified`.
- Not run: **5 halt-mid-move**, **6 expiry**. **Team decision: skipped, assumed to work.** Mitigation: low speeds (≤0.3 m/s), staff controller always ready, and the joystick tool logs stop latency whenever it's used (it does not measure command expiry).
- Keyboard hard stops were active in Leonardo's Terminal; not needed. (At that time Q = rest and Enter = halt. Since then both are STOP = soft lie-down.)
- 5 connects in the session, all OK, 2.05–2.69 s. No rest/StandDown step was run.

### 2026-11-04 13:07–13:08: First `real_selftest` tries (Leonardo)
- Two `read` runs failed at once: `unitree_webrtc_connect is not installed` (the interpreter used did not have the library; probably not the venv).
- Third run failed: `LocalSignalingPortError` (neither 9991 nor 8081 reachable). Cause not recorded. The next attempts at 13:33 connected fine.

### 2026-11-04 12:54: First WebRTC connection, read-only (Leonardo)
- Phone app confirmed closed. Ran `scripts/dog_probe_readonly.py` 3 times.
- Try 1: `DataChannelTimeoutError` (ice completed, peer stuck connecting). Tries 2 and 3 worked: connected in 1.7 s via legacy `/offer` on 8081, **no AES key needed**.
- Status: standing (mode 1, 0.32 m), battery 59 %, avoidance on, volume 0.
- Saved 1280×720 frames in `evidence/dog/` (dog was under a table: backpack, table leg, a person's legs visible).
- Sent only: handshake/heartbeat and the session-only video on/off switch. No motion, no settings.

### 2026-11-04: First network contact (Leonardo)
- Wi-Fi ping to `192.168.123.161` failed: that subnet is the dog's wired network.
- Plugged in Ethernet via USB LAN adapter (en5), set static `192.168.123.222/24`, no router.
- Ping 4/4 replies, ~0.5 ms.
- Ports: **8081 open** (aiohttp, legacy WebRTC `/offer`), **22 open**, 1234 refused, 9991 refused.
- Conclusion: connect with `LocalSTA` + `ip="192.168.123.161"`; probably no AES key (confirmed at 12:54).
- Nothing sent to the dog beyond ping, TCP port checks and one HTTP `GET /` (returned 404).
