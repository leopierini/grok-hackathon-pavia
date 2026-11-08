# Hardware bring-up — Go2 and Tello EDU

Run every command from `ground base`. Ground is the only process that turns a
story step into a dog or drone command. The dog speaker and the Tello SDK are
reached only from the adapters after that command exists.

Nothing in this repository has been executed on the museum robots. The checks
below are what the software does with a mocked socket. Treat every real-device
result as untested until someone writes it down.

Connection values come from the environment or from `--config`. The process
does not invent a host, a port, or a key. `config/museum.example.json` leaves
both hosts null. A null value still exits 2.

```bash
export PATROL_DOG_HOST="<measured Go2 address>"
export PATROL_DOG_PORT="<measured port>"
export PATROL_DRONE_HOST="<measured Tello address>"
export PATROL_DRONE_PORT="<measured Tello command port>"
```

`PATROL_DOG_PORT` is required so the entry point never assumes one. Leo's
`RealDog` session is WebRTC `LocalSTA` and reads the host as `interface`. It
has no port field, so the port is checked and then not sent. TODO Leo: confirm
whether this robot's WebRTC session needs that port.

`PATROL_DRONE_HOST` and `PATROL_DRONE_PORT` are passed into Federico's
`TelloSDK`. The constants in `patrol/drone/tello_sdk.py` stay in place for his
direct scripts. This entry point does not use them.

`XAI_API_KEY` is read only inside the signal connector, and only for
`--grok real`. Do not put it in a file, a command line, or a report.

## Preflight

```bash
python -m patrol.ground.museum --preflight
```

Fake peers should print a table of `PASS` rows and exit 0. The camera rows
include `sha256` of the JPEG that was read. Halt is validated and not sent.

With a real peer, set that peer's variables first. Preflight opens a session
and does not pass `--i-understand-this-moves-hardware`:

- Dog: WebRTC connect, status, battery from the low-state message if it is
  present. No `StandUp`, no `Move`, no `StopMove`.
- Drone: SDK `command` and `battery?`. No `takeoff`, `land`, `rc`, or
  `emergency`.
- A battery under 20 fails that row.
- Camera: one JPEG, hashed. TODO Federico: on the museum network this uses a
  short UDP read of port 11111 after `streamon` when `av` is installed. If
  that read fails, the camera row is `FAIL` and no flight command is added.
- Grok: `--grok real` checks that `XAI_API_KEY` is set and does not print it.
- Halt path: the dog `halt` callable and the drone `halt` callable are present,
  and a `dog.command` halt validates. Neither is invoked.

```bash
python -m patrol.ground.museum --preflight --dog fake --drone real --grok fake
python -m patrol.ground.museum --preflight --dog real --drone fake --grok fake
python -m patrol.ground.museum --preflight --dog real --drone real --grok real
```

Stop if a preflight row says `FAIL`, or if the aircraft moves, the dog stands,
or a speaker plays.

Confirm these on the day. Leave an unconfirmed item as TODO.

- [ ] Gallery is closed to the public and a person is on the halt control.
- [ ] Go2 variant and firmware (AIR / PRO / EDU). TODO: not confirmed in this repo.
- [ ] Unitree account and AES key for firmware that requires it. TODO: not stored here.
- [ ] Dog host and port measured on this robot. TODO: do not copy an address out of `PLAN.md`.
- [ ] Tello host and port measured on this aircraft. TODO: the museum SSID is not configured.
- [ ] Tello battery above 20. TODO: confirm the pack on the aircraft that will fly.
- [ ] Prop guards on. Takeoff area is the floor mark in `config/profiles/room_2_view_v1.json`. TODO: plate-on-dog landing is not a tested Tello procedure (issue #72).
- [ ] Laptop is not joined to the Tello access point. TODO: confirm the network plan with the person who has the Pi.
- [ ] `XAI_API_KEY` is in the environment only when a live presence call is intended.

## Fake, then one real peer

Motion with a real peer also needs:

```bash
--i-understand-this-moves-hardware
```

Without that flag the process exits 2 before it opens a socket, even when the
host and port are set. `--scenario all` with a real peer runs every script,
including takeoff. Use one scenario until that scenario's report is understood.
`halt` is the one to run first.

1. Both peers fake, scripted Grok.

   ```bash
   python -m patrol.ground.museum --dog fake --drone fake --grok fake --scenario all
   ```

   Expect exit 0. Each scenario prints `ok: true` and `detail: passed`. Reports
   land in `artifacts/museum/<scenario>/report.json`. The dog fake's `spoken`
   list is `go away` only when Ground authorized `play_warning`. The drone
   fake's trace contains `inspect`. `land_on_dog` is recorded as that action.
   It is not a call to floor `land()`.

2. Preflight, still fake.

   ```bash
   python -m patrol.ground.museum --preflight
   ```

   Expect exit 0 and a pass table. `motion_sent` in `preflight.json` is false.

3. Drone real, dog and Grok fake. Unset the drone variables first.

   ```bash
   unset PATROL_DRONE_HOST PATROL_DRONE_PORT
   python -m patrol.ground.museum --dog fake --drone real --grok fake --scenario halt
   ```

   Expect exit 2 and `PATROL_DRONE_HOST` / `PATROL_DRONE_PORT`. No socket.

   Set the measured values. Run preflight, then the motion gate, then one scenario.

   ```bash
   python -m patrol.ground.museum --preflight --dog fake --drone real --grok fake
   python -m patrol.ground.museum --dog fake --drone real --grok fake --scenario halt
   python -m patrol.ground.museum --dog fake --drone real --grok fake --scenario halt \
     --i-understand-this-moves-hardware
   ```

   The command without the flag exits 2 and names `--i-understand-this-moves-hardware`.
   With the flag, `halt` connects, runs the floor profile once (`takeoff`, a
   still, `land`), then the story. Look at `drone_commands` in the report:
   one `takeoff`, one `land`, no translation (`forward`, `go`, nonzero `rc`).
   `land_on_dog` is a gap for Federico, issues #72, #53, and #73. It does not
   add another `land`. After the profile has landed, halt sends `rc 0 0 0 0`.
   `emergency` is reserved for an airborne or unknown halt.

   The profile ceiling in this entry point is 8 seconds, settle 1 second, hold
   1 second, battery minimum 20. The profile does not translate.

4. Dog real, drone returned to fake. Unset the dog variables first.

   ```bash
   unset PATROL_DOG_HOST PATROL_DOG_PORT
   python -m patrol.ground.museum --dog real --drone fake --grok fake --scenario halt
   ```

   Expect exit 2 and `PATROL_DOG_HOST` / `PATROL_DOG_PORT`. No socket.

   ```bash
   python -m patrol.ground.museum --preflight --dog real --drone fake --grok fake
   python -m patrol.ground.museum --dog real --drone fake --grok fake --scenario halt
   python -m patrol.ground.museum --dog real --drone fake --grok fake --scenario halt \
     --i-understand-this-moves-hardware
   ```

   With the flag, connect uses Leo's `RealDog` and the measured host. The story
   does not call `prepare`, so it does not send `StandUp`. `follow` and
   `return_home` are gaps for Leo, issues #28 and #78. They do not send `Move`,
   and they do not call `robot/go2/goal.py`. `stop` calls `stop_move`
   (`StopMove`, the dog stays in its current posture, the motion lock is not
   latched). `halt` calls `RealDog.halt` (`StopMove`, then the lock). The fence
   passed into that session is 1.5 m, the sustained speed cap is 0.25 m/s, and
   the route cap is 8 s. `play_warning` calls `RealDog.play_warning`. If that
   session cannot speak, the report lists a gap for Leo, issue #28, and nothing
   else calls the speaker.

5. Both real, Grok still fake. Run `halt` before `happy_path`.

   ```bash
   python -m patrol.ground.museum --preflight --dog real --drone real --grok fake
   python -m patrol.ground.museum --dog real --drone real --grok fake --scenario halt \
     --i-understand-this-moves-hardware
   python -m patrol.ground.museum --dog real --drone real --grok fake --scenario happy_path \
     --i-understand-this-moves-hardware
   ```

   Expect `ok: true` with `passed with known gaps` when an action is in the
   gap table below. A missing gap for `follow`, `return_home`, or `land_on_dog`
   means the report is claiming a motion the adapter did not perform. Stop.

6. One live presence call. Do this with both robots fake before any real peer.

   ```bash
   python -m patrol.ground.museum --dog fake --drone fake --grok real --scenario happy_path
   ```

   Unset key: exit 2, `XAI_API_KEY is unset`, no model request. `--scenario all`
   is refused in real Grok mode. A live reply is not permission to move a robot.
   Uncertain or timeout adds no command after the YOLO hover and follow.
   Repeat with a real peer only after steps 3–5, and only with the motion flag.

## What to verify at each step

| Step | Verify | Stop if |
| --- | --- | --- |
| 1 | Exit 0. `play_warning` text is `go away`. `land_on_dog` primitive is `land-on-dog-v1` with `beacon_epoch` null. Uncertain and timeout deliver only the YOLO hover and follow. Halt latches and later presence is skipped. | Any scenario `ok: false`, or the dog spoke without a `play_warning` command |
| 2 | Exit 0. Table is all `PASS`. `preflight.json` has `motion_sent: false` and a sha256. | A motor command, a spoken warning, or the key printed |
| 3 | Unset variables: exit 2 names `PATROL_DRONE_HOST`. Flag missing: exit 2 names the flag and opens no socket. With the flag: one `takeoff`, one `land`, `land_on_dog` listed as Federico's gap. | A second takeoff, a translation command, `land` caused by `land_on_dog`, or the host printed |
| 4 | Unset variables: exit 2 names `PATROL_DOG_HOST`. With the flag: no `StandUp` (`api 1004`) and no `Move` (`api 1008`). `follow` and `return_home` name Leo. | The dog stands or walks, `goal.py` runs, or the host printed |
| 5 | Same motor log as 3 and 4 together. Link-loss and `halt` scenarios end with halt latched and no later `cmd:`. | Motion after halt, or `emergency` while the post-profile state is grounded |
| 6 | Exit 2 with no key. With a key, decisions are `vision.decision` only, prompt `patrol-presence-v1`. | A command whose `source` is `vision`, or the key appearing in `report.json` |

YOLO in this run is a scripted person count, not a weight file. It runs before
any Grok call and only asks Ground to hover and to send the dog (`follow` at
standoff 2.0). On a real dog that `follow` is the gap above, not a walk.
Grok is not in that dispatch.

## Abort

Software halt is scenario `halt`: one `dog.command` action `halt`, then no
further presence command. The drone adapter is halted in the same step. Link
loss latches the same way and stops the other peer. Halt wins over a later
"still there" or "gone". Grok uncertain, Grok timeout, and a Grok reason that
contains a motor phrase produce no further command.

On a real drone that is airborne or whose flight state is unknown, drone halt
sends Tello `emergency` once. On a drone that has already landed, halt sends
`rc 0 0 0 0`. On the dog, halt sends `StopMove` through the WebRTC session this
process opened. `robot/go2/stop.py` is not launched. That script publishes ROS
`/joy` and `/stop` on a different graph, which would move the dog beside Ground.

TODO: the physical kill control (controller, Tello palm stop, and who holds
them) is not specified in this repository. Until that is written down by the
person flying:

- Do not arm a live peer until preflight is all `PASS` and a person is holding the halt control.
- Do not treat this process's exit code as a hardware e-stop.
- If a live session is already moving, run scenario `halt` with the motion flag, then power the robots down from the vendor control that person is holding.
- TODO: the exact key chords are owned by the dog and drone adapters, not by this runbook.

## Still blocked on the owners

These are reported as gaps in `report.json`. The story does not skip Ground to
perform them.

| Gap | Who | Issues | What this entry point does |
| --- | --- | --- | --- |
| `follow` | Leo | #28, #78 | `RealDog.execute` refuses it. Not the RSSI follower. No `Move`. |
| `return_home` | Leo | #28, #78 | No confirmed path. `robot/go2/goal.py` is not called. |
| `play_warning` when the session cannot speak | Leo | #28 | The call goes to `RealDog.play_warning` and nowhere else. A failure is a gap, not a second speaker path. |
| `stop` | Leo | #28 | Implemented as `stop_move` (`StopMove` without latching halt). It is not `halt`. |
| Dog stand-up | Leo | #28 | `prepare` / `StandUp` is not called. TODO: a confirmed route has to exist before the dog is stood up for this story. |
| `PATROL_DOG_PORT` unused on the wire | Leo | TODO | Required, then not sent, because `RealDog` has no port field. |
| `land_on_dog` | Federico | #72, #53, #73 | Not sent. Not aliased to floor `land()` or to marker land. |
| Real Tello camera on the museum network | Federico | TODO | Preflight records a hash when a JPEG comes back. A missed frame fails the row. |
| `g23` still refuses `play_warning`, `follow`, `stop`, and `return_home` as leased steps, and it still turns proposal action `approach` into `move_local` | Ayush | #22, #23, #24 | The museum path uses `g16` and `g17`, not `g23`. Do not loosen `g23` so a warning becomes a walk. |
| `/ws/robot/v2` host, port, and auth are unset | Ayush | #33 | This entry point does not bind that socket. |
| `patrol` package name collision. `patrol.drone` is not importable beside Ground | All | #27, #26 | Real and fake adapters are loaded by file path. Do not put all three trees on one `PYTHONPATH`. |
| Physical e-stop chords | Whoever flies | TODO | Not in this repo. |

`person3-grok` probe tests still expect the older rejections (issues #4–#21).
Ground's schema, `g16`, `g17`, and `g24` on this branch accept the presence
actions. Those probe tests are not part of the Ground pytest run. They were
left as they are.
