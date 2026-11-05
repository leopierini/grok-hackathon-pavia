# Live museum demo — integration, runbook, evidence

Branch `integration/demo`, 5 Nov 2026. This page is the source of truth for the
**live** run. The offline rehearsals (`patrol.ground`, `patrol.ground.museum`,
Mission Control) are unchanged.

## What was missing (gap analysis)

| # | Gap that blocked the demo | Fix |
|---|---|---|
| 1 | `dog backend/patrol/dog/ground_bridge.py` never existed in the repo. Ground's `EthernetDogLink` spawns it, so every Ground→dog path (Mission Control direction test, dog view, halt) failed | Written: JSON lines on stdin/stdout. `stand`, bounded `move`, `stop`, `halt` = StopMove + soft StandDown (never Damp), `say`, `frame`, `lidar`, `status` |
| 2 | Start/Stop patrol (`operator/public_patrol.py`) only records calls; nothing reaches the drone or dog | New `patrol.ground.live` mission that actually drives the peers |
| 3 | `--drone real` / museum real peers fail closed; `RealDrone` is a stub (issues #53, #73) | Ground talks to the drone teammate's flight server `patrol.drone.manual` over its local HTTP API (state, frame, hover/land/takeoff, yaw sticks) |
| 4 | Grok only accepts hashed fixture JPEGs with `simulated: true` (issue #62) | `signal/live.py`: presence reading on real camera bytes, labelled `simulated: false`; plus a text-only Grok alert (operator alert + spoken sentence) |
| 5 | No drone person detection reachable from Ground (drone detector needs uncommitted torch weights; flight brain uses OpenRouter) | Grok is the detector on drone frames: one request in flight, newest frame, 2 consecutive positives to confirm |
| 6 | No voice on the live path | Dog speaker via the bridge (`say`, macOS TTS stand-in, volume set on first use) |
| 7 | Tello SDK hard-codes AP-mode IP 192.168.10.1 | `TELLO_IP` env override (station mode keeps the laptop online for Grok) |
| 8 | No live console showing all components | `patrol.ground.live` serves one page: both cameras + Grok boxes, per-peer status, alert, event log, Start/Stop/Halt (Q) |

Still open and not needed for this demo: RSSI homing, `land_on_dog` (#72),
dog `follow` / `return_home` on the real dog, Mission Control showing the live run.

## Architecture (live)

```text
             operator browser  http://127.0.0.1:8770  (Ground live console)
                          │  Start / Stop / Halt(Q) / dog Stand / Step / Speak
                          ▼
   ┌──────────────── Ground: python -m patrol.ground.live ────────────────┐
   │ LiveMission: phases standby→patrol→detected→tracking→stopped|halted   │
   │ journal artifacts/live/<run>/events.jsonl (+ frames/, summary.json)   │
   └───┬───────────────────────┬───────────────────────────┬──────────────┘
       │ HTTP 127.0.0.1:8766   │ stdin/stdout JSON lines   │ HTTPS api.x.ai
       ▼                       ▼                           ▼
 patrol.drone.manual     patrol.dog.ground_bridge       Grok grok-4.20-non-reasoning
 (drone tree; owns       (dog tree venv; one WebRTC     presence + box + reason on
 Tello UDP, deadman,     to Go2 192.168.123.161:8081    drone & dog JPEGs; alert text
 land-always, video)     over the Ethernet cable)
       │ UDP 8889/8890/11111
       ▼
 Tello EDU (station mode on venue Wi-Fi, TELLO_IP) — pilot page :8766 stays open
```

Dock: the "dock" is the dog's back / the floor patch. There is no dock software
in the repo beyond the drone's `marker_land`/`pad_land`; landing in this demo is
the drone server's normal `land`, supervised by the pilot.

## Event sequence (what the journal shows)

1. `phase standby`, `drone_link`, `dog_connected` — nothing moves.
2. `phase patrol` — every ~1.2 s a drone frame → `grok/vision`.
3. two consecutive `person_visible` → `drone_target_acquired` (new `incident_id` on every later event),
   `drone_command hover`.
4. `dog_alert` (dog stands: alert/ready), `alert` (Grok text), `dog_voice` (spoken warning).
5. `phase tracking` — `track_nudge` (yaw only, |axis| ≤ 0.35, 0.4 s, ±90° budget, only when airborne);
   dog frames → `grok/vision`; first positive → `dog_target_acquired` + second spoken line.
6. Stop → `drone_command land`, `dog_rest`, `report` (summary.json). Halt → `halt`, `halt_sent`, latched.

Safety: the mission never walks the dog. Dog steps are operator buttons, clamped by
Ground's `dog_limits` and the dog's own checks (standing, avoidance confirmed, fence).
Drone link lost while tracking → dog StopMove. Grok errors never trigger anything.

## Run it

Setup once (done on this laptop):

```bash
cd "ground base" && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cd .. && .venv/bin/pip install av pillow           # root venv: drone + dog libraries
ln -sfn ../.venv "dog backend/.venv"                # Ground spawns the bridge with this interpreter
mkdir -p ~/.config/patrol && echo 'XAI_API_KEY=…' > ~/.config/patrol/xai.env && chmod 600 ~/.config/patrol/xai.env
```

Simulation (no hardware, no key): `scripts/live-demo.sh sim`, open http://127.0.0.1:8770,
take off in the pilot page http://127.0.0.1:8799 (or "Start + takeoff"), press Start patrol.

Real (from `ground base`):

```bash
TELLO_IP=192.168.5.137 scripts/live-demo.sh real     # Tello station mode + dog on cable + Grok
```

Preflight, in order:
1. Gallery closed, consenting participant briefed, staff on the dog controller, pilot on the pilot page (L = land).
2. Dog cable in, Mac USB-LAN `192.168.123.222/24`, phone app and joystick closed (one WebRTC client).
3. Tello battery ≥ 30 %, prop guards on, takeoff patch clear.
4. Console shows drone `up`, dog `up`, Grok calls succeeding.
5. Pilot takes off and holds; operator presses **Start patrol**. Participant walks in.
6. Watch: detection → dog stands + speaks → drone yaw-tracks → dog camera sees person → second line.
7. **Stop patrol** (drone lands, dog lies down). Halt = red button / Q at any time.

## Verification evidence

| Requirement | Status | Evidence |
|---|---|---|
| Ground observes drone/dog/Grok state | verified in simulation | console screenshot; `/api/state` |
| Drone detection workflow (2-frame confirm, hover) | verified in simulation | `tests/ground/live`, multi-process sim journal |
| Dog alert/ready + voice | verified in simulation (bridge on simulated body: stand, say) | bridge op transcript, journal `dog_alert`, `dog_voice` |
| Dog camera detection | verified in simulation | journal `dog_target_acquired` |
| Drone visual tracking, bounded | verified in simulation (fake drone yawed, budget held) | `track_nudge`, `track_budget`, drone fake yaw |
| Stop / halt | verified in simulation; halt ≈150 ms | journal `halt_sent`, drone fake `landed` |
| Real Grok on real bytes | implemented, unit-tested with a fake transport; **live call not yet run (no key on this machine)** | `test_live_assess_*` |
| Real Tello / real Go2 | **not yet verified** (Tello off, dog cable not connected at time of writing) | — |
