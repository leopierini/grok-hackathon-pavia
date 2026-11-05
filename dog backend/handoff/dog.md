# Dog (Go2) handoff

Linear project: **P-HAC-1 · Dog (Go2)** (https://linear.app/federico-navoni/project/1-dog-go2-ead712b89878)
Issues: HAC-1 (D1) … HAC-7 (D6), HAC-46, HAC-47 (D7) … HAC-51 (D11). Owner: Leonardo.
Last updated: 2026-11-04 (~22:15). **Status: proven on the real dog with staff present: connect, camera, status, a short move, halt (joystick, median 0.08 s from near-still), soft lie-down, stand up, head light, speaker + mic, one-click joystick workflow, LiDAR live panel (18:08). Found: plain `Move` ignores obstacle avoidance; sticks-mode turn was mirrored (fixed). Follow demo tried on the real dog 19:30 (turned the wrong way, never walked → fixed). Built + reviewed but NOT yet on the real dog: sticks drive mode (dog's own avoidance), LiDAR brake, **follow with LiDAR dodge**, map/planning module (not wired). NOT tested: command expiry, safety trips, routes.**

**➡ Next session starts here: §0 below.**

**Real-dog follow test 21:48–21:58 (latest):** STOP lie-down confirmed every time; turn sign correct in Move and sticks mode; `turn_room` `[90, 90]` throughout; a live dodge fired once. Follow works but is **slow and not smooth**: it only has RSSI, so it starts with a blind 75° probe and re-estimates every ~1 m leg (median ~35 s in sim). Arrive circle shrunk 1.3 → 0.8 m, demo noise 3 → 2 dB. How to run it: Set home in the middle, point 1.5 m one side, dog 1.5 m the other side, Start following, **don't touch anything or switch tabs**, wait up to 60 s. Details: `docs/dog.md` §9.

Details, runbooks, troubleshooting and the session log are in [`docs/dog.md`](../docs/dog.md). This file keeps the verified summary.

Linear status (2026-11-04 22:20): HAC-1, HAC-3, HAC-6, HAC-7, HAC-47 (LiDAR panel + brake), HAC-50 (audio) Done · HAC-2, HAC-48 (sticks mode), HAC-49 (follow + dodge, Urgent) In Progress · HAC-4 Todo · HAC-5, HAC-46, HAC-51 (mapping) Backlog.

> No credentials in this file. Real values go in `config/dog.local.json` (git-ignored) or env vars only. This dog needs no AES key and no Unitree login to connect.

## 0. Where we are / what to do next (2026-11-04 evening)

**Read first:** [`docs/Lidar + SLAM.md`](../docs/Lidar%20+%20SLAM.md) (plan: LiDAR → dodge → follow the drone's signal, demo mode §8b), [`docs/pi-bridge.md`](../docs/pi-bridge.md) (Raspberry Pi 5 on the dog, not Leonardo's task now), `docs/dog.md` §2c (joystick: LiDAR panel, sticks mode, brake, follow panel, runbooks).

**Built today (all uncommitted on branch `dog-go2` — commit when Leonardo asks):**
- `patrol/dog/lidar.py`: LiDAR processing (top-down view, nearest obstacle ahead, brake helper, synthetic room for the sim).
- Joystick: LiDAR panel; "Drive via remote-controller path" (sticks on `rt/wirelesscontroller`, so the dog's own avoidance applies; zero sticks on every stop and after every reconnect); "LiDAR brake (0.5 m)"; "Follow signal (demo)" panel (place a simulated signal point on the LiDAR panel, live RSSI + sparkline, direction arrow, state, 60 s limit, start once / STOP to end, follow keepalive, point must be ≥ 1.5 m inside the fence); `--no-lidar` flag.
- `patrol/dog/follow.py`: VirtualBeacon (simulated RSSI) + Follower (plane fit, probing, stuck rule, arrive −38 dBm ≈ 0.8 m / resume −43 dBm; was −43/−48 until the 21:50 test).
- `patrol/dog/mapping.py`: occupancy grid + A* planning (not wired).
- `real_selftest --step lidar`.
- Safety-review fixes: avoidance switch is now **read-only** (Stand up never writes it; motion refused if not confirmed on); "Turn LiDAR on" only while standing; StandDown 4201 confirmed via body height (no false "STOP may not have arrived"); dropped zero-sticks are logged; `_tick` isolation so the dead-man always runs.

**Leonardo's next real-dog test** (checklist also in his Notion page "test" under Cursor Hackathon / Blind people dog, updated late 2026-11-04): restart the joystick (code changed) → staff soft-stop agreed (not L2+B) → Stand up, checks → STOP once (log: `lying_confirmed: true`, `posture_after`) → sticks mode: staff stop while pushing (must stop), directions W / A-D / **J must turn left** / L right, box with brake off then on → follow in open space (Set home in the middle, dog 1.5 m one side, point 1.5 m other side; log `turn_room` must be `[90, 90]`) → **dodge test** (soft box ~1 m ahead on the line to the point) → STOP, Shut down. He'll bring the screen recording + `evidence/dog/joystick.jsonl` to the new chat.

**Real follow test 2026-11-04 19:30 (sticks mode), result:** the dog turned the wrong way and never walked. Log (`evidence/dog/joystick.jsonl` 19:30–19:34) shows it in every run that didn't arrive at once: commanded turn `+0.5` → yaw *decreased*, `−0.5` → increased; each run settled at its leg heading + 180°. So in sticks mode **`rx +` = turn RIGHT** (vendor example is wrong). The follower kept turning away from its leg heading until it sat at heading + 180°, where the error flips sign every tick (dither, stepping in place, `vx` = 0). **Fixed:** `_to_sticks` sends `rx = −vyaw`; sim matches the real dog; new test `test_follow_in_sticks_mode_turns_toward_its_leg_and_arrives`. Manual J/L in sticks mode was mirrored too (same function). Not yet re-tested on the dog.

**Whole-change safety review (same evening), no blockers. Fixed:** (a) STOP's lie-down check: the dog's `body_height` doesn't drop when lying, so every STOP showed a false "STOP MAY NOT HAVE ARRIVED". It now also confirms from sport mode 5 (lie down) / 7 (damping), and the rest report logs `posture_after` {mode, body_height} so the next STOP shows the real values. (b) `close()` zeroes the sticks even when the dog reads stationary (a stick blocked by the dog's own avoidance). **Open:** in sticks mode the dog went up to 0.44 m/s (Move: 0.39), so the follow cap of 0.3 may come out at ~0.45 m/s; watch the measured speed (the speed trip at 0.6 is the backstop). Strafe/forward stick signs not measured. Whether the dog holds the last stick on link loss: unknown. After arriving, the follower resumes by itself if the signal drops below −48 dBm (within the 60 s). Also note: the first move of a run is a sideways *probe* (±75° from the current heading), not a turn toward the point (the follower only knows RSSI); a point within ~1.3 m of the dog arrives at once.

**LiDAR dodge for follow mode (same evening, Leonardo asked for it as a main feature):** the follower now steers round obstacles from the LiDAR's free distance per direction instead of driving up to them and waiting on the brake (details: `docs/dog.md` §2c follow row). Works in Move and sticks mode; the 0.5 m brake stays as backstop; swept-footprint turn guard so it never spins a corner into something next to it (found in sim). Two independent safety reviews: no blockers; their should-fixes (unbounded step-out, unbounded wall-following, thin turn margin, bad-field fail-open) are fixed with tests. **First real run: check `turn_room` in `follow_sample` reads `[90, 90]` in open space** (own legs seen as obstacles → `[0, 0]` → never turns). Test: §2c "Follow demo" step 7 (box between dog and point). Known limit: behind wide obstacles (≥ 1 m) the signal-strength estimate itself wanders (also without the dodge), so arrival there is ~50–80 % in sim within 60 s.

**What to check in his results:**
- Did the staff stop beat our sticks? Directions correct (turn sign is the likeliest to be mirrored)? Speed per stick unit (`STICK_MAX = 0.3`)?
- Did sticks mode dodge the box (dog's own avoidance)? Brake stopping distance?
- Follow: arrived? time, wandering vs fence, clearance near obstacles.
- LiDAR: do walls stay put in the panel when the dog turns (confirms the voxel map is in the odom frame)? Is each message one sweep or an accumulated map (people lingering)?
- Stop latency with LiDAR on vs `--no-lidar` if anything looks slow.

**Open risks:** unknown whether the dog keeps the last stick value on link loss (staff controller covers it); follow in sticks mode depends on correct stick signs (backward isn't braked) — use Move mode until the sticks test passes.

**After that (priority order):** fix whatever the test shows → Pi bridge (someone else) → real drone RSSI source replacing VirtualBeacon → wire `mapping.py` (live map + planning) only if time is left. Deadline: **Thursday 5 Nov, 16:00** video.

**Process rule (Leonardo):** after any dog change, per-task review + a whole-system safety review before real-dog tests; never touch firmware; STOP = StopMove + StandDown.

## 1. Commands

Run from the repo root with the venv Python.

```bash
# Tests and fake mode (no robot). 361 passed on 2026-11-04 (late evening).
.venv/bin/python -m pytest tests/dog -q
.venv/bin/python -m patrol.dog.selftest --mode fake

# Read-only probe of the real dog (no motion, no settings)
.venv/bin/python scripts/dog_probe_readonly.py

# Supervised real-dog steps, one per run. Steps that move the dog need --arm.
.venv/bin/python -m patrol.dog.real_selftest --step read                 # no motion
.venv/bin/python -m patrol.dog.real_selftest --step prepare --arm        # stand up if needed
.venv/bin/python -m patrol.dog.real_selftest --step halt --arm
.venv/bin/python -m patrol.dog.real_selftest --step move --arm           # 0.2 m/s for 1 s
.venv/bin/python -m patrol.dog.real_selftest --step halt-mid-move --arm  # NOT run yet
.venv/bin/python -m patrol.dog.real_selftest --step expiry --arm         # NOT run yet
.venv/bin/python -m patrol.dog.real_selftest --step rest --arm           # lie down softly (NOT run on the real dog yet)
.venv/bin/python -m patrol.dog.real_selftest --step audio --volume 5     # no motion: chime + mic loopback, volume restored after

# Browser joystick: http://127.0.0.1:8765/   Easiest: double-click scripts/dog_joystick.command
scripts/dog_joystick.command                                             # real dog: start + open page; connects by itself when the dog answers
.venv/bin/python -m patrol.dog.joystick --fake                           # simulated dog, always try this first
.venv/bin/python -m patrol.dog.joystick --config config/dog.local.json   # real dog (add --open to open the page)
```

- `selftest --mode real --config config/dog.local.json --arm` only delegates to the `read` step of `real_selftest`. Use `real_selftest` for the other steps.
- Before any `--arm` step or the real joystick: staff present holding their controller, 2 m clear in front of the dog, Unitree phone app closed. Run in your own Terminal so the stop keys work.
- STOP keys: `Q` or `Enter` = stop walking + lie down softly. `Ctrl+C` in `real_selftest` = stop walking, stay standing, exit. `Ctrl+C` in the joystick = lie down softly, exit.
- **Restart the joystick after changing any `.py` file.** The page HTML is re-read on every page load, the Python code only at start. A stale server shows new buttons but ignores them (happened with the audio panel on 2026-11-04).
- Joystick page extras: **Run test** (read / audio, no motion; runs the real_selftest code on a fresh connection, saves to `session.jsonl`, then re-arms by itself; STOP works meanwhile; audio never runs at volume 0 and is FAIL unless the mic hears the chime). Used on the real dog 17:20–17:24: auto-connect, read check, auto re-arm, shut down all worked and **Shut down server** (click twice; = Ctrl+C). Motion steps stay terminal-only.
- Step table with results: `docs/dog.md` §2b. Joystick controls and safety: §2c.

## 2. Environment

| | |
|---|---|
| Dev machine | macOS 27.0.1 (Darwin) |
| Python | **3.12.15** in `.venv` (tested). 3.14 not tried. |
| Library | `unitree_webrtc_connect` **2.2.0** (local clone `robot-docs/sdks/go2_webrtc_connect`, commit `e0abc57`, 2026-08-16). Non-editable install, on purpose: macOS flags editable `.pth` files hidden and Python skips them. |
| Pinned deps | `requirements/dog.txt`: aiortc 1.15.0, aioice 0.12.1, av 17.1.0, cryptography 50.0.2, pyOpenSSL 26.4.0, opencv-python 5.0.0.93, numpy 2.5.4, pytest 9.2.0, aiohttp 3.14.5 (joystick) |
| System dep | `portaudio` (macOS: `brew install portaudio`; Linux: `sudo apt install portaudio19-dev`) |

Setup:

```bash
bash robot-docs/fetch-sdks.sh        # library clone (robot-docs/sdks/ is git-ignored)
brew install portaudio
python3.12 -m venv .venv
.venv/bin/pip install -r requirements/dog.txt
```

## 3. How to connect

Wired Ethernet, verified 2026-11-04:

- Cable from the dog's port to the Mac's USB LAN adapter ("USB 10/100/1000 LAN", **en5**).
- Mac static IP `192.168.123.222/255.255.255.0`, no router: `networksetup -setmanual "USB 10/100/1000 LAN" 192.168.123.222 255.255.255.0`. Undo: `networksetup -setdhcp "USB 10/100/1000 LAN"`.
- Dog at `192.168.123.161`. Wi-Fi stays the default route, so the laptop keeps internet (Grok).
- Check: `ping -c 3 192.168.123.161` and `nc -vz -G 3 192.168.123.161 8081`.

```python
from unitree_webrtc_connect import UnitreeWebRTCConnection, WebRTCConnectionMethod

conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, ip="192.168.123.161")
await conn.connect()   # legacy /offer on 8081, no AES key
```

Rules:
- **Close the Unitree phone app first.** Only one WebRTC client can be connected (`RobotBusyError` otherwise). The joystick and `real_selftest` each hold that one connection, so run only one at a time.
- Connecting never moves the dog.
- The first-ever connect attempt timed out (`DataChannelTimeoutError`). Retries worked: 7 of 7 successful connects since, in 1.7–2.7 s.
- AP mode and AES-key fetching are not needed here. We do not switch AP/Network mode.
- Examples in `robot-docs/sdks/go2_webrtc_connect/examples/go2/`: `video/camera_stream`, `data_channel/sportmode`, `data_channel/obstacles_avoid`, `data_channel/lidar`, `audio/*`.

## 4. Known facts about this dog

Staff told us the dog was **modified**: it originally needed ROS, and they changed it so ROS isn't needed any more. **Nothing may be updated**, or it may break. The setup is fragile.

| Item | Value |
|---|---|
| Wired IP / MAC | `192.168.123.161` / `7e:1d:75:60:f5:89` |
| Connection | `LocalSTA` over wired Ethernet (verified) |
| Signaling | Legacy `/offer` on port **8081** (verified: connects). Port 9991 closed. |
| AES key needed? | **No** (verified: connects without one) |
| Firmware version | Probably older than 1.1.11 (only the legacy port is open). Inferred, not confirmed. |
| Edition (AIR/PRO/EDU) | TBD, ask staff |
| Motion mode | `normal` |
| Open ports | 8081 (aiohttp, WebRTC `/offer`), 22 (SSH: read-only at most). 1234 (the port staff mentioned) and 9991 closed. |
| Battery (12:55) | 59 %, 28.6 V, 11 charge cycles |
| Settings readback | avoidance **on**, volume 0 (speaker silent until you set it), brightness 0, speed level 0, UWB on |
| Posture | standing, body height 0.32 m |
| Odometry | origin not fixed between sessions (probe (2.49, -1.52) m, session near (0.18, 0.00) m). Use deltas. |
| Unitree account holder | TBD, probably irrelevant (no key needed) |
| What exactly was modified | TBD, ask staff |

## 5. Capabilities (HAC-2): supported / unsupported / unknown

| Capability | Status | Evidence |
|---|---|---|
| Connect (no motion) | supported | Probe 12:54/12:55 (1.73 s); 5 of 5 in session 13:33–13:37 (2.05–2.69 s) |
| Video / front camera | supported | 1280×720 frames, `evidence/dog/go2_frame_20261104-125502.jpg`, session photos `hac3-133322_*` |
| Fresh status reading | supported | sport state 161 msgs in 8 s (~20 Hz); `lowstate`, `multiplestate` ~1 Hz |
| Stand up / lie down | supported | Joystick 15:00–15:04: StandDown (soft lie-down) 3 of 3, StandUp + BalanceStand after Re-arm. StandDown replies after > 3 s (posture timeout now 8 s). |
| Velocity move (`Move`) | supported | `--step move`: 0.2 m/s × 1 s → 0.214 m, ~4 cm sideways, stop verified (13:37) |
| Obstacle avoidance on/off + readback | readback supported | `obstaclesAvoidSwitch = true` (state) and service query = true. Switching not tested. |
| Plain `Move` respects avoidance | **no** | 18:08: avoidance on, dog walked into person/box. Use sticks mode |
| `halt` / `StopMove` while still | supported | Accepted in 0.154 s, stays standing |
| `halt` / `StopMove` mid-walk | supported | Joystick 15:00–15:04: 15 stick releases → stationary after median 0.08 s, max 0.91 s. The route-path step 5 (`halt-mid-move`) itself was not run. |
| Command expiry (commands stop arriving) | unknown | Step 6 skipped by team decision |
| Odometry (`rt/sportmodestate`) | supported (read) | `position`, `velocity`, IMU `rpy` |
| Head light (VUI brightness) | supported | Joystick 15:00–15:04: set 0 → 5 → 6 → 0 (api 1005), readback api 1006 |
| Speaker | supported | `--step audio --volume 5`, 15:41: chime sent over the WebRTC audio track, **heard at the dog** by Leonardo. Volume get/set works (api 1004/1003): 0 → 5 → restored to 0. Nothing is uploaded to the dog. |
| Microphone | supported | Same run: 4 s at 48 kHz stereo, 200 of 200 frames. The mic heard the chime ~0.2 s after sending: 660 Hz +28.6 dB, 990 Hz +17.7 dB over the background. `evidence/dog/audio_selftest_20261104T144159932871Z.wav` |
| LiDAR | supported | Live panel works (18:08); streams only while standing |

Rule from HAC-3: **unknown standing / stationary / avoidance state must block walking. Never default to true.** Implemented in `RealDog` and covered by tests on a fake connection; not provoked on the real dog.

## 6. Real-dog evidence (HAC-3)

Session 2026-11-04 13:33–13:37, Leonardo, staff present. Raw lines: `evidence/dog/session.jsonl` (git-ignored, UTC times; photos may show people).

- [x] Connected with no motion: 2.05–2.69 s, motion mode `normal`
- [x] Fresh status read: standing, stationary, avoidance on
- [x] One live photo saved: `evidence/dog/hac3-133322_dog_room_2_20261104T123324344517Z.jpg` (and a second one)
- [ ] `halt` stops the dog (staff holds their own controller): **still ✅ 0.154 s**; mid-walk skipped by team decision, assumed, NOT tested
- [x] Stand, avoidance on, readback: already standing and on, `prepare` confirmed, no action sent
- [x] One short supervised move: 0.2 m/s × 1.0 s → **0.214 m**, ~4 cm sideways, `completed; stop verified`
- [ ] Behaviour when commands stop arriving (command expiry): skipped by team decision, NOT tested

Mitigation for the skipped steps: speeds ≤ 0.3 m/s, staff controller always ready, and the joystick logs stop latency (stop command → stationary) to `evidence/dog/joystick.jsonl`. The joystick does not measure command expiry.

Bug found and fixed before the session: the photo temp file `.jpg.tmp` was rejected by OpenCV; it is now `.tmp_<name>.jpg`.

Done on the real dog (15:00–15:04): browser joystick driving, live camera, STOP → soft lie-down (3 of 3), Re-arm → Stand up, head light, **stop after stick release: median 0.08 s, max 0.91 s (15 stops)**.

Done on the real dog (15:41): `--step audio --volume 5`: speaker and mic both work (chime heard at the dog and in the recording). No motion.

Not yet on the real dog: command expiry (link loss while walking), a safety trip, routes, the joystick's audio panel (the server was not restarted after the audio code was added; see §10).

## 7. Safety

- Dog only in our booked slot, **with staff present**, staff controller ready. **The staff controller is the primary stop.**
- **Every operator STOP = stop walking + lie down softly** (StopMove, then StandDown, sport api 1005). **Damp (api 1001, rough drop) is never sent.** The soft lie-down works on the real dog (3 of 3).
- Automatic stops (stick release, 300 ms dead-man, WebSocket loss, page blur) = StopMove only; the dog stays standing.
- **Automatic safety thresholds** (on by default): fence 3 m around home, speed > 0.6 m/s for 0.3 s, tilt > 25° for 0.2 s, route travel > planned × 1.3 + 0.3 m → soft lie-down (rest) + motion lock. Home is kept across Re-arm; outside the fence, driving is refused until "Set home here". Joystick checkbox can switch them off (logged, banner); they come back ON after every Re-arm and restart. Odometry jumps > 0.5 m block motion until "Set home here". Odometry drifts; untested on the real dog. Details: `docs/dog.md` §7.
- Speed caps: joystick 0.3 m/s forward/back, 0.2 m/s sideways, 0.6 rad/s yaw; RealDog 0.5 / 0.3 / 0.8. Unknown state refuses to walk. A timed-out move is never retried and locks the adapter. Every vendor call has a timeout.
- Capture photos only after the request starts. Reject frames older than 5 s.
- Pulling the Ethernet cable is **not** a stop (command expiry is untested).
- A second script cannot stop the dog while the first is connected.
- **Firmware: never overwrite, update or flash it. No OTA, no re-bind, no factory reset, no AP ↔ Network mode switch, no motion-mode switching.** SSH is read-only at most.
- If it misbehaves: staff controller stop first, then `halt`, then power cycle only with staff.

Full rules and stop layers: `docs/dog.md` §7.

## 8. Config

- `config/dog.example.json`: template. `config/dog.local.json`: real values, git-ignored (so is `evidence/`).
- Keys: `connection_mode` (`LocalSTA` only), `interface` (the dog's **IP**, `192.168.123.161`), `routes_path`, `max_route_s` (30), `command_timeout_s` (3.0). Optional: `connect_timeout_s` (25), `move_rate_hz` (10). The example also has a `scenario` key, used by FakeDog only.
- `routes_path` is relative to where you run Python (use the repo root). Local file uses `config/dog_routes.example.json`; the example config says `dog_routes.example.json`, which only works from inside `config/`.
- `config/dog_routes.example.json`: `room_2` template with `calibrated: false`. Routes run only when `calibrated: true`; `entrance` and `display` have no entry, so they are `unsupported`. Route caps: vx 0.5, vy 0.3, vyaw 0.8, segment 10 s.
- `create_dog(mode="fake"|"real", config, output_dir)` is in `patrol/dog/__init__.py`. Creating a dog never connects or moves.

## 9. Blockers / open questions

For staff:
1. Edition (AIR/PRO/EDU) and firmware version.
2. Port 1234: what was it meant to be? It is closed.
3. What exactly was changed (ROS removal)? Anything running on the dog we mustn't stop?
4. Is wired Ethernet OK for the demo?
5. Emergency button combo on their controller.
6. Is `StandDown` the "slow rest" they mean, or `Sit`?
7. Does plain `Move` respect obstacle avoidance?
8. Can we strap a small plate to its back? (Tello mount, owned by project 2.)
9. Booked slots for supervised tests (dog + drone together if possible).

For us:
- Run steps 5 and 6 (or collect the same data with the joystick) and try `--step rest --arm` once with staff present.
- Restart the joystick and try its audio panel on the real dog (volume, Say, Test chime, Listen, Record, Hold to talk).
- HAC-46: look into STOP at 15:29: two page STOPs failed with `Data channel is not open` (WebRTC link dead, StandDown not delivered); Re-arm fixed it. Cause not known. The staff controller remains the primary stop.
- Calibrate the `room_2` route (HAC-4).
- How do dog and Tello share a network? (Dog is on Ethernet, so Wi-Fi stays free; the Tello side is project 2's call.)

Resolved today: connection mode (wired works), AES key (not needed), Python version (3.12 works; 3.14 untested), deps pinned, speaker + mic (work).

## 10. Recovery

| Symptom | Likely cause / fix |
|---|---|
| `AesKeyRequiredError` | Not expected on this dog. Would mean firmware changed. Ask staff for the key. |
| `AesKeyRejectedError` | Wrong key or another dog's key. |
| `RobotBusyError` | Phone app, a joystick or another script is connected. Close it. |
| `LocalSignalingPortError` | Wrong IP, cable out, dog off, or 8081 closed. Run the `ping` and `nc` checks in §3. Seen once, then fine. |
| `DataChannelTimeoutError` | Seen once on the first connect. Wait 10–20 s and run again. |
| `NoSdpAnswerError` | Reconnect. If it keeps failing, ask staff what they changed. |
| `unitree_webrtc_connect is not installed` | Not running the venv Python, or editable install. Use `.venv/bin/python`; reinstall non-editable. |
| Joystick "MOTION LOCKED" | STOP, halt or a failed Move latched the lock. Release sticks, press Re-arm, then Stand up if lying. |
| Step refuses to run | Needs `--arm`. Check the preflight first. |
| Joystick buttons enabled but nothing happens; Volume shows `?` | The server is older than the code (the page HTML reloads, the Python doesn't). Ctrl+C the joystick and start it again. |
| Joystick STOP logs `Data channel is not open` | The WebRTC link is dead, so the stop did not reach the dog. Use the staff controller, then Re-arm. |
| Audio selftest: `loopback_heard: false` | Volume 0 (see `note`), or the mic didn't hear the chime. Listen at the dog, try `--volume 7`. |
| Dog misbehaves | Staff controller stop first. Then `halt` (or Q to lie down). Then power cycle only with staff. |

More rows: `docs/dog.md` §8.

## 11. Handoff to the others

- **Ground (project 4):** use `create_dog(mode="fake", ...)` for development. `RealDog` follows the same contract: `halt()` latches and the adapter refuses new routes until it is recreated; unknown state is `None`, never `True`. Real extras: `rest()` (soft lie-down), `drive()`, `stop_move()`. `run_route("room_2")` raises `unsupported` until the route file is calibrated (HAC-4).
- **Grok (project 3):** voice out with `RealDog.play_pcm(pcm, rate, channels)` (s16 PCM, any rate, streamed live; `max_lag_s` for live talk) or `say(text)` (macOS TTS stand-in). `stop_audio()` cuts it; every STOP also cuts it. Voice in with `mic_subscribe(rate)` → `asyncio.Queue` of mono s16 chunks, then `mic_unsubscribe(q)`. Set `set_volume(5)` first: the dog starts at 0. Audio never affects motion.
- **Drone (project 2):** the mount plate on the dog is shared work. Needs staff approval (question 8).
- **Console / dashboard:** a view-only project dashboard is in the backlog (`docs/dog.md` §5b). It must reuse the joystick server's video and status. It must not open a second WebRTC connection to the dog. Agree ownership first.
- **LiDAR / SLAM / Pi:** plan in `docs/Lidar + SLAM.md` and `docs/pi-bridge.md` (design only, nothing built yet).
