# Hardware bring-up — Go2 and Tello EDU

This is the path from the offline museum simulation to one real peer at a time.
The simulation does not open a socket. Real mode fails closed when the host or
port is unset, and it still fails closed when they are set, until a later change
wires the live transport. Do not invent a host, a port, or a key to get past that.

Software entry point, from `ground base`:

```bash
python -m patrol.ground.museum --dog fake --drone fake --grok fake --scenario all
```

Ground authorizes every motor effect in that run. `--grok fake` does not read
`XAI_API_KEY`. `--grok real` reads that variable and nothing else; do not put the
key in a file or a command-line argument.

## Preflight

Confirm each item on the day. If it is not confirmed, leave it as TODO and do
not guess.

- [ ] Gallery is closed to the public and a person is on the halt control.
- [ ] Go2 variant and firmware (AIR / PRO / EDU). TODO: not confirmed in this repo.
- [ ] Unitree account and AES key for firmware that requires it. TODO: not stored here.
- [ ] Dog control host and port. The sim reads `PATROL_DOG_HOST` and `PATROL_DOG_PORT` only. TODO: do not copy an address out of `PLAN.md` until someone measures it on this robot.
- [ ] Tello EDU host and port. The sim reads `PATROL_DRONE_HOST` and `PATROL_DRONE_PORT` only. TODO: the museum SSID and address are not configured.
- [ ] Tello battery above the floor profile minimum (the checked-in profile says 20). TODO: confirm the pack on the aircraft that will fly.
- [ ] Prop guards on. Takeoff area is the floor mark in `config/profiles/room_2_view_v1.json`, not the dog's back. TODO: the plate-on-dog landing is not a tested Tello procedure (issue #72).
- [ ] Laptop is not joined to the Tello access point. TODO: confirm the network plan with the person who has the Pi.
- [ ] `XAI_API_KEY` is in the environment only if a live presence call is intended. It is not required for `--grok fake`.

`ground base/config/museum.example.json` leaves both hosts null. Passing that file
with `--config` still fails closed.

## Fake, then one real peer

Run these from `ground base`. Stop at the first exit code 2. Nothing in this
list connects to a robot.

1. Both peers fake, scripted Grok.

   ```bash
   python -m patrol.ground.museum --dog fake --drone fake --grok fake --scenario all
   ```

   Expect exit 0. Each scenario prints `ok: true`. Reports land in
   `artifacts/museum/<scenario>/report.json`. The dog fake's `spoken` list is
   `go away` only when Ground authorized `play_warning`. The drone fake's trace
   contains `inspect`. `land_on_dog` is recorded as that action. It is not a call
   to floor `land()`.

2. Dog real, drone and Grok still fake. Leave the dog variables unset.

   ```bash
   python -m patrol.ground.museum --dog real --drone fake --grok fake --scenario happy_path
   ```

   Expect exit 2 and `PATROL_DOG_HOST` / `PATROL_DOG_PORT` unset. No socket.

3. Set only the dog variables to the values measured in preflight, then repeat
   the same command. Expect exit 2 and `does not open a socket`. TODO: replace
   that refusal with Leo's `RealDog` only after the host and port are confirmed
   and a person is on the halt control. Ground still must not import the dog SDK.

4. Drone real, dog returned to fake. Unset the drone variables first.

   ```bash
   python -m patrol.ground.museum --dog fake --drone real --grok fake --scenario happy_path
   ```

   Expect exit 2 and `PATROL_DRONE_HOST` / `PATROL_DRONE_PORT` unset. Then set
   the measured values and expect `does not open a socket`. TODO: Federico's
   `RealDrone.connect` currently raises unsupported (issue #53). Do not point
   this entry point at a Tello until that adapter accepts a `drone.command`
   and a checked `land_on_dog` that is not floor `land` (issues #72 and #73).

5. One live presence call, both robots still fake. This uses the network and
   the key. Skip it when the key is not on the machine.

   ```bash
   python -m patrol.ground.museum --dog fake --drone fake --grok real --scenario happy_path
   ```

   Unset key: exit 2, `XAI_API_KEY is unset`, no model request. The fixture JPEG
   is a person crop, so a live model will not reproduce the scripted "gone"
   timeline. Read the printed actions. Do not treat a live reply as permission
   to move a robot. `--scenario all` is refused in real mode so a key cannot
   fan out into every script.

Do not combine `--dog real` and `--drone real` on the first day. One peer at a
time, and only after steps 2–4 no longer stop at the socket refusal.

## What to verify at each step

| Step | Verify | Stop if |
| --- | --- | --- |
| 1 | Exit 0. `play_warning` text is `go away`. `land_on_dog` primitive is `land-on-dog-v1` with `beacon_epoch` null. Uncertain and timeout deliver only the YOLO hover and follow. Halt latches and later presence is skipped. | Any scenario `ok: false`, or the dog spoke without a `play_warning` command |
| 2 | Exit 2 names the missing dog variables. `artifacts/` has no new dog socket log. | The process waits, dials, or prints a host |
| 3 | Exit 2 says the socket was not opened. The host is not required in the message. | Any WebRTC session, stand, or audio |
| 4 | Same for the drone variables. | Any UDP session to the Tello, takeoff, or motor tone |
| 5 | Exit 2 with no key. With a key, decisions are `vision.decision` only, prompt `patrol-presence-v1`, and reasons contain no SDK sentence. | A command whose `source` is `vision`, or the key appearing in `report.json` |

YOLO in this sim is a scripted person count, not a weight file. It runs before
any Grok call and only asks Ground to hover and to send the dog (`follow` at
standoff 2.0). Grok is not in that dispatch.

## Abort

Software halt is scenario `halt`: one `dog.command` action `halt`, then no
further presence command. Link loss latches the same way. Halt wins over a
later "still there" or "gone".

On the real robots, TODO: the physical kill control (controller, Tello palm
stop, and who holds them) is not specified in this repository. Until that is
written down by the person flying:

- Do not arm a live peer.
- Do not treat this simulation's exit code as a hardware e-stop.
- If a live session exists anyway, stop the vendor session from that peer's own
  adapter (`halt` on the dog, land or emergency on the drone) and power down.
  TODO: the exact key chords are owned by the dog and drone adapters, not by
  this runbook.

## Still blocked on the owners

These are not simulated by skipping Ground. The museum policy sends only
schema-valid commands. The peers below do not yet perform them on hardware.

| Gap | Who | What has to be added |
| --- | --- | --- |
| `FakeDog` / `RealDog` have no `execute` for `play_warning`, `follow`, `stop`, or `return_home` (issues #28 and #78) | Dog | Map a Ground `dog.command` onto the existing adapter. `play_warning` can call `say("go away")`. `follow` is not the RSSI follower. `stop` is not `halt`. `return_home` needs a confirmed path. Do not let Ground import the Unitree SDK. |
| `RealDrone` raises unsupported. Nothing turns `drone.command` into a Tello call (issues #53, #69, #73). `land_on_dog` is not marker land and not floor `land` (issue #72) | Drone | Accept `hover` and `land_on_dog` (`primitive_id` `land-on-dog-v1`, `beacon_epoch` null) without aliasing them to `land()`. |
| `g23` still refuses `play_warning`, `follow`, `stop`, and `return_home` as leased steps, and it still turns proposal action `approach` into `move_local` (issues #22, #23, #24) | Ground | The museum path uses `g16` and `g17`, not `g23`. Mission Control will not run this story until it calls `patrol.ground.museum` or an equivalent policy. Do not loosen `g23` so a warning becomes a walk. |
| `/ws/robot/v2` host, port, and auth are unset (issue #33) | Ground | Agree the socket with the dog app. This sim does not bind one. |
| `patrol` package name collision (issue #27). `patrol.drone` is not importable from Ground (issue #26) | All | The sim loads the dog and drone fakes by file path. Do not put all three trees on one `PYTHONPATH`. |

`person3-grok` probe tests still expect the older rejections (issues #4–#21).
Ground's schema, `g16`, `g17`, and `g24` on this branch accept the presence
actions. Those probe tests are not part of the Ground pytest run. They were
left as they are.
