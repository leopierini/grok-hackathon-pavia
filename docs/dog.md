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
| Browser joystick | ✅ Used on the real dog in Chrome (15:00–15:04): drive, live camera, STOP, Re-arm, Stand up, head light |
| Safety thresholds | 🟡 Built + 2 reviews, tested on the simulator; no trip seen on the real dog yet (never left the fence) |
| room_2 route | ⏳ Route file exists but `calibrated: false` |
| FakeDog (HAC-1) | ✅ Done, 30 tests |
| RealDog adapter + session script | ✅ 17 logic tests (fake connection). Steps 1–4 run on the real dog |
| `pytest tests/dog` | ✅ 105 passed, 2026-11-04 |

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
.venv/bin/python -m pytest tests/dog -q                  # 69 passed
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
| 2 | `--step prepare --arm` | Stand up only if not standing, avoidance on if off, read back | `status_after_prepare` all `true` | ✅ no action needed, all `true` |
| 3 | `--step halt --arm` | StopMove while stationary | accepted, still standing | ✅ 0.154 s, stayed standing |
| 4 | `--step move --arm` | 0.2 m/s forward for 1.0 s (route control path) | `moved_m` ≈ 0.2, `stopped: true` | ✅ 0.214 m, ~4 cm sideways, stop verified |
| 5 | `--step halt-mid-move --arm` | 0.2 m/s for 3 s, `halt()` after 0.8 s | `stationary_after_halt_s`, `moved_m` < 0.4 | **Skipped by team decision. Assumed to work, NOT tested.** |
| 6 | `--step expiry --arm` | ONE Move at 0.2 m/s, nothing else, watch 2 s, then halt | `stopped_by_itself_after_s` (= command expiry) | **Skipped by team decision. Assumed, NOT tested.** |
| any | `--step rest --arm` | Lie down on demand: StopMove, then StandDown (same as pressing Q). Stand up again with `--step prepare --arm`. | `standdown_sent: true`, dog lying | Not run on the real dog |

Stop after any FAIL and look at the error before going on. Never re-run a motion step that timed out without checking the dog first.
Mitigation for the skipped steps: speeds ≤ 0.3 m/s, staff controller always ready, and the joystick logs stop latency to `evidence/dog/joystick.jsonl` (see §2c).

`python -m patrol.dog.selftest --mode real --config config/dog.local.json --arm` only **delegates** to real_selftest and runs the `read` step. To run any other step, call `real_selftest` directly as above.

**Sport API calls we send** (topic `SPORT_MOD`): StopMove 1003, StandUp 1004, BalanceStand 1002, Move 1008, StandDown 1005. **Damp (1001, motors go limp, rough drop) is never sent.** Other topics: obstacle-avoid get/set (1002/1001), motion switcher read (1001, read only), VUI head light get/set (1006/1005).

**Movement path:** sport `Move` (api 1008), re-sent at 10 Hz. We do **not** use the obstacle-avoid service's own move API: it needs `USE_REMOTE_COMMAND_FROM_API`, which may take control away from the staff controller. Whether plain `Move` respects avoidance is untested; ask staff.

**Hard caps in RealDog** (applied after any route file): 0.5 m/s forward/back, 0.3 m/s sideways, 0.8 rad/s yaw, 10 s per segment. `drive()` and routes refuse unless connected, not locked, standing and avoidance confirmed on (routes also need stationary). Unknown = refused.

## 2c. Browser joystick (`patrol/dog/joystick.py`)

Local web page to drive the dog by hand. It serves on `127.0.0.1` only, opens nothing by itself, and one process owns the single WebRTC connection (close the phone app).

```bash
.venv/bin/python -m patrol.dog.joystick --fake            # 1st: simulated dog, no network at all
.venv/bin/python -m patrol.dog.joystick --config config/dog.local.json   # then the real dog
# open http://127.0.0.1:8765/   (--port to change, --out for photos and logs)
```

`--fake` runs the real RealDog code on a simulated body (`patrol/dog/sim_conn.py`). The simulator's own behaviour (for example a Move that expires after 1.0 s) is an assumption, **not** a measurement of the real dog.

Connecting never moves the dog. Run it in your own Terminal so the terminal keys work.

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
| Head light | On/off + brightness 0–10 (VUI api 1005, read with 1006 on connect). Not yet tried on the real dog |
| Photo | `capture_frame` → JPEG in `evidence/dog/`, path shown on the page |
| Set home here | Centres the safety fence on the dog's current spot. Controller only, stationary only. Logged (`set_home`). See §7 "Automatic safety thresholds" |
| Safety thresholds checkbox | Fence / speed / tilt / overshoot trips. **Checked at every server start.** Unchecking: controller only, stationary only, logged (`safety_envelope_off`), red "SAFETY THRESHOLDS OFF" banner + terminal line. **Back ON after every Re-arm and every restart** (never carried over). Can't be changed while connecting; the checkbox shows the dog adapter's real setting (greyed out while unknown) |
| Take control | Shown on every view-only tab. Moves control to this tab: the server sends StopMove first (dog stays standing), demotes the old tab, logs `control_taken`. A view-only tab that touches a stick or move key gets a "press Take control" hint |
| Live video | MJPEG, ~10 fps, downscaled to 640 px wide |
| Status panel | 4 Hz: safety envelope state (OK / TRIPPED: reason / OUTSIDE FENCE / OFF), distance from home / radius, tilt, standing, stationary, avoidance, battery, speed, lock reason, last stop latency, event log |

Safety:
- **Staff controller is always the primary stop.** This page is a backup.
- **Every operator STOP = stop walking + lie down softly.** Automatic stops (stick release, dead-man, WebSocket loss, tab hidden or window blur) = StopMove only; the dog stays standing.
- Speed caps in the server: **0.3 m/s** forward/back, **0.2 m/s** sideways, **0.6 rad/s** yaw (RealDog's own caps 0.5/0.3/0.8 apply too). `Move` ≤ 20 Hz (the page sends ~15 Hz).
- `RealDog.drive()` refuses unless connected, not locked, standing **and** avoidance confirmed on (unknown = refused). A failed or timed-out Move locks the adapter and is never retried.
- **Dead-man:** no stick message for 300 ms while moving → StopMove. Also StopMove on page close, tab switch, window blur, or WebSocket loss.
- One browser controls (the first to connect). Other tabs are view-only (STOP still works). No avoidance-off, no tricks, no mode or firmware commands.
- Localhost only: the server binds `127.0.0.1`, rejects any Host that is not `127.0.0.1`/`localhost`, and rejects foreign `Origin` headers with 403 (blocks other websites and DNS rebinding).

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
| Obstacle avoidance on/off + readback | readback supported | `multiplestate.obstaclesAvoidSwitch = true` and service query = true. Switching not tested (already on). |
| Does plain `Move` respect avoidance? | unknown | Not tested. Ask staff. |
| `halt` / `StopMove` while still | supported | Accepted in 0.154 s, stays standing |
| `halt` / `StopMove` mid-walk | supported | 15 joystick releases (StopMove): stationary after median 0.08 s, max 0.91 s; speed at release up to 0.39 m/s |
| Command expiry (commands stop arriving) | unknown | Skipped by team decision (step 6) |
| Odometry (`rt/sportmodestate`) | supported (read) | `position` [2.49, -1.52, 0.31], `velocity`, IMU `rpy` |
| Head light (VUI brightness) | supported | Joystick: set 0 → 5 → 6 → 0 (api 1005), read back on connect (api 1006) |
| Speaker / mic | unknown | |
| LiDAR | unknown | |

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
- [ ] Fill §4 with evidence (done for what we ran; speaker, LiDAR, command expiry, soft lie-down, light still unknown)

### HAC-3 · D3 · Prove connect, camera and halt on the real dog · 🟠 High · 3–10h (staff slot) · Linear: In Progress
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

### HAC-6 · D5 · Make halt and camera dependable · 🟠 High · 10–18h · Linear: In Progress
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

- **Project dashboard (view-only), separate from the joystick page.** Dog camera (+ drone camera later), dog status, event log (camera event → Grok decision → dispatch → drone hop → alert), Grok reasons, KPIs from the plan, and a STOP button (= soft lie-down). The joystick server adds view-only endpoints (video, snapshot, status) and the dashboard embeds them; it never opens its own connection to the dog (one WebRTC client only). Check ownership with the Console workstream first. (Today the joystick server only has `/`, `/ws` and `/video.mjpg`.)
- **First real-dog use of the joystick** (staff present): try the page in a real browser, check stop latency in `evidence/dog/joystick.jsonl`, and try one soft lie-down + Re-arm + Stand up.

## 6. Open questions for staff

1. Edition (AIR/PRO/EDU) and firmware version?
2. Port 1234: what was it meant to be? It's closed. Is it a service of theirs that should be running?
3. What exactly did they change (ROS removal)? Anything running on the dog we mustn't stop?
4. Is wired Ethernet OK to use during the demo, or should we use Wi-Fi?
5. Can we strap a small plate on its back for the Tello? (Shared with the drone project.)
6. Booked slot times for supervised tests (dog + drone together if possible).
7. What is the emergency button combo on their controller?
8. Is `StandDown` the "slow rest" they mean, or do they want `Sit`?
9. Does plain `Move` respect obstacle avoidance?

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

Automatic stops (stick release, dead-man 300 ms, WebSocket loss, page blur, Take control) send **StopMove only**; the dog stays standing. **Safety threshold trips** (fence, speed, tilt, route overshoot; below) lie the dog down softly.

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

| Config key | Default | Trips when |
|---|---|---|
| `fence_radius_m` | 3.0 | horizontal distance from **home** > radius, while motion is possible (route running, a Move in the last 1 s, or measured motion) |
| `max_speed_mps` | 0.6 | measured horizontal speed > limit for ≥ 0.3 s (short gait peaks don't trip; our caps are 0.3–0.5) |
| `max_tilt_deg` | 25 | abs(roll) or abs(pitch) > limit for ≥ 0.2 s |
| `route_overshoot` | `{"factor": 1.3, "margin_m": 0.3}` | during `run_route` / `run_segments`: odometry travel since route start > planned × factor + margin (planned = Σ hypot(vx, vy) · duration) |
| `safety_envelope_enabled` | `true` | `false` = no automatic trips (values still measured and shown) |
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
| `--step ...` says "re-run with --arm" | The step moves or commands the dog. Check the preflight (staff, 2 m clear, app closed), then add `--arm`. |

---

## 9. Session log

Newest first. Date, who, what was done, result.

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
