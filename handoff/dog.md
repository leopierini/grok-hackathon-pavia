# Dog (Go2) handoff

Linear project: **P-HAC-1 · Dog (Go2)** (https://linear.app/federico-navoni/project/1-dog-go2-ead712b89878)
Issues: HAC-1 (D1) … HAC-7 (D6). Owner: Leonardo.
Last updated: 2026-11-04. **Status: connect, camera, status, halt-while-still and one short move are proven on the real dog (13:33–13:37, staff present). Halt mid-walk, command expiry and the soft lie-down are NOT tested.**

Details, runbooks, troubleshooting and the session log are in [`docs/dog.md`](../docs/dog.md). This file keeps the verified summary.

Linear status: HAC-1 Done · HAC-2, HAC-3, HAC-6, HAC-7 In Progress · HAC-4 Todo · HAC-5 unchanged.

> No credentials in this file. Real values go in `config/dog.local.json` (git-ignored) or env vars only. This dog needs no AES key and no Unitree login to connect.

## 1. Commands

Run from the repo root with the venv Python.

```bash
# Tests and fake mode (no robot). 69 passed on 2026-11-04.
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

# Browser joystick: http://127.0.0.1:8765/
.venv/bin/python -m patrol.dog.joystick --fake                           # simulated dog, always try this first
.venv/bin/python -m patrol.dog.joystick --config config/dog.local.json   # real dog (not used yet)
```

- `selftest --mode real --config config/dog.local.json --arm` only delegates to the `read` step of `real_selftest`. Use `real_selftest` for the other steps.
- Before any `--arm` step or the real joystick: staff present holding their controller, 2 m clear in front of the dog, Unitree phone app closed. Run in your own Terminal so the stop keys work.
- STOP keys: `Q` or `Enter` = stop walking + lie down softly. `Ctrl+C` in `real_selftest` = stop walking, stay standing, exit. `Ctrl+C` in the joystick = lie down softly, exit.
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
| Settings readback | avoidance **on**, volume 0, brightness 0, speed level 0, UWB on |
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
| Stand / sit | readback supported | Standing confirmed (mode 1, 0.32 m). StandUp not exercised (already standing). **StandDown never sent to the real dog.** |
| Velocity move (`Move`) | supported | `--step move`: 0.2 m/s × 1 s → 0.214 m, ~4 cm sideways, stop verified (13:37) |
| Obstacle avoidance on/off + readback | readback supported | `obstaclesAvoidSwitch = true` (state) and service query = true. Switching not tested. |
| Plain `Move` respects avoidance | unknown | Not tested, ask staff |
| `halt` / `StopMove` while still | supported | Accepted in 0.154 s, stays standing |
| `halt` / `StopMove` mid-route | unknown | Step 5 skipped by team decision, assumed to work |
| Command expiry (commands stop arriving) | unknown | Step 6 skipped by team decision |
| Odometry (`rt/sportmodestate`) | supported (read) | `position`, `velocity`, IMU `rpy` |
| Head light (VUI brightness) | readback only | `multiplestate.brightness = 0`; set not tried on the real dog |
| Speaker / mic | unknown | |
| LiDAR | unknown | |

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

Not on the real dog yet: the browser joystick (built and reviewed, 22 tests on a simulated dog), `--step rest`, any StandDown.

## 7. Safety

- Dog only in our booked slot, **with staff present**, staff controller ready. **The staff controller is the primary stop.**
- **Every operator STOP = stop walking + lie down softly** (StopMove, then StandDown, sport api 1005). **Damp (api 1001, rough drop) is never sent.** The soft lie-down is untested on the real dog.
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
- Open the joystick in a real browser, then on the real dog.
- Calibrate the `room_2` route (HAC-4).
- How do dog and Tello share a network? (Dog is on Ethernet, so Wi-Fi stays free; the Tello side is project 2's call.)

Resolved today: connection mode (wired works), AES key (not needed), Python version (3.12 works; 3.14 untested), deps pinned.

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
| Dog misbehaves | Staff controller stop first. Then `halt` (or Q to lie down). Then power cycle only with staff. |

More rows: `docs/dog.md` §8.

## 11. Handoff to the others

- **Ground (project 4):** use `create_dog(mode="fake", ...)` for development. `RealDog` follows the same contract: `halt()` latches and the adapter refuses new routes until it is recreated; unknown state is `None`, never `True`. Real extras: `rest()` (soft lie-down), `drive()`, `stop_move()`. `run_route("room_2")` raises `unsupported` until the route file is calibrated (HAC-4).
- **Drone (project 2):** the mount plate on the dog is shared work. Needs staff approval (question 8).
- **Console / dashboard:** a view-only project dashboard is in the backlog (`docs/dog.md` §5b). It must reuse the joystick server's video and status. It must not open a second WebRTC connection to the dog. Agree ownership first.
