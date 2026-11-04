# Project plan: Grok night-shift operator with a dog-carried drone

> **Status:** current direction, agreed Wed 4 Nov. It replaces the guide-dog idea (`guide-dog-system-plan.md`).
> **Track:** D, "Robot Dog Patrol" (Riello). **Hardware:** Unitree Go2 + Tello EDU on its back + 2–3 phones as fixed cameras.
> Background research: [`reports/Robot dog and drone patrol.md`](reports/Robot%20dog%20and%20drone%20patrol.md) · Event info: [`hackathon info.md`](hackathon%20info.md)

## One-liner
**"Grok, the night-shift operator that asks before it alarms."** Fixed cameras spot something and Grok sends the dog. If the dog can't see well enough, Grok launches the drone from the dog's back for a look from above. The dog can also talk to the person it finds. Grok checks everything against plain-language site rules, and only then calls the caretaker in Italian.

## Why we dropped the earlier ideas
- **Guide dog for blind people:** already done on our exact hardware. Binghamton (AAAI 2026) built a Go2 + GPT-4 guide dog, and Glasgow's RoboGuide (2024, Go1 + an LLM) was trialled in a museum. Glidance sells a wheeled version. It also fits none of the 10 tracks.
- **"Drone scouts, dog responds":** already sold. Asylon pairs drones with a Spot-based dog, under a reported $17M Securitas deal, with humans in a remote control room deciding the dispatch. It also makes the drone a single point of failure, slows event-to-arrival time (a judged metric), drains the 13-min battery on patrol, and needs a map so the drone can tell the dog where to go.

## Why the dog-carried drone
| | Drone scouts, dog responds | **Dog carries and deploys the drone (chosen)** |
|---|---|---|
| Novelty | Asylon sells it | Research only (e.g. ANYmal + aerial robot, 2025), nothing commercial |
| Track D fit | Replaces the brief's phone cameras | Keeps the brief's flow; the drone becomes an escalation step inside "check" |
| Drone fails | The whole pipeline breaks | The core demo still works |
| Event → arrival time | Worse | Unaffected |
| Battery (~13 min) | Drained by patrolling | 30–60 s hops, many per battery |
| Handoff | Drone sightings must become floor coordinates (pads + map) | None: relative moves from the dog's position |
| Safety | Autonomous flight across rooms | A short, supervised hop next to the dog |
| Grok essential | Triages frames | **Decides** that the view is blocked and launches the drone |

## What makes it new compared with existing products
1. **AI dispatcher, not a human control room.** Grok decides whether to dismiss, look again, send the dog, launch the drone, or alert.
2. **Gathers more evidence before alerting.** When unsure, Grok asks for the observation that would settle it: a drone view, a dog close-up, or a question to the person.
3. **The dog talks to the person.** Through the Go2's speaker and mic with Grok Voice: *"Buonasera, quest'area è riservata. Lavora qui? Come si chiama?"* The answer is checked against the staff roster and shift schedule.
4. **Site rules in plain Italian.** For example, *"Dopo le 22 nessuno nella sala 2, tranne le pulizie il martedì."* The jury can add a rule live and stage a case that breaks it.
5. **Learns from dismissed alerts.** A false alarm the caretaker dismisses becomes a site exception, and the false-alarm rate drops across runs. This gives us our measured result against a baseline.
6. **Factory safety framing for Riello**, not just intruders: a person lying on the floor (lone worker), a blocked fire exit, an open door, and as a stretch goal a boiler or HVAC gauge read on patrol.
7. **Privacy built in (EU):** faces are blurred on the laptop before frames go to Grok, and Grok describes what is happening, not who.

## Demo flow (the museum stands in for the factory)
1. **Event:** a phone camera sees something staged, for example a person behind a display case or a moved exhibit. A local detector pre-filters, and Grok vision triages with structured output.
2. **Dispatch:** Grok calls `dispatch_dog(zone)`. The Go2 walks to that zone's waypoint (velocity commands + odometry; obstacle avoidance on).
3. **Check:** Grok reads the dog's front camera. If the target is clearly visible, verify it. If the view is **blocked**, Grok calls `launch_drone()`.
4. **Drone hop:** the dog is standing still. The Tello takes off from its back, climbs about 1.5 m, turns toward the target, streams frames, then **lands on the floor** (a teammate puts it back).
5. **Talk (optional):** if a person is found, the dog asks who they are and Grok checks the roster and rules.
6. **Decide:** dismiss (with a reason) or escalate.
7. **Alert:** an Italian voice call to a test number (Grok Voice + Twilio via `voice-agent-phone`) with an acknowledgement. Every step goes to the append-only incident log.
8. **End of shift:** the shift report, optionally delivered via Grok Bot. Luca Bianchi, a juror, gives the Thursday Grok Bots talk.

## Architecture (minimal)
- **Orchestrator** (Python): a state machine `PATROL → DISPATCH → ARRIVE → CHECK → (LAUNCH_DRONE) → (TALK) → DECIDE → ALERT`.
- **Grok tools** (function calling): `dispatch_dog`, `recall_dog`, `launch_drone`, `land_drone`, `speak_via_dog`, `hold_and_watch`, `dismiss`, `escalate_alert`, `add_site_rule`.
- **Adapters** behind shared interfaces, so everything runs without hardware:
  - `Go2Dog` (unitree_webrtc_connect) / `SimDog` (2D floor-plan sim)
  - `TelloDrone` (djitellopy) / `ReplayDrone` (recorded video)
  - `PhoneCam` (RTSP/MJPEG) / `ReplayCam`
- **Console:** floor plan, incident pins, live KPI header (Riello's 5 metrics + "blocked views resolved by drone"), a STOP button for both robots.
- **Log:** append-only JSONL. Every Grok decision is stored with the frames and evidence it was based on.

## Hard limits for the drone
- Take off **only while the dog is standing still**. Never launch while walking.
- **Land on the floor**, never back on the dog.
- Mount a flat plate about 20 × 20 cm on the dog's back (velcro or straps), clear of the head LiDAR. Test take-off from about 40 cm, and check that the downward sensor the drone uses to hold position works above the dog's back.
- Moves are **relative to the take-off point only** (`up`, `cw`, `forward`). No mission pads and no map conversion.
- **Network:** Tello video needs the laptop on the Tello's own Wi-Fi, so use a second interface (USB Wi-Fi or Ethernet) or a dedicated drone laptop.
- **Go/no-go at Thu ~09:00:** if the drone hop hasn't worked in a supervised slot with frames reaching Grok, the drone appears only as recorded footage in the video.

## What we measure (results against a baseline)
1. **False alarms forwarded:** rule-based triage vs Grok vs Grok + evidence gathering (dog/drone/talk), on about 30–40 labelled events including hard negatives (staff in a vest, a photo of a person, exhibits).
2. **Event → arrival time:** scheduled patrol vs event-triggered dispatch.
3. **Blocked views resolved:** dog camera only vs dog + drone hop.
4. **Learning from dismissals:** false-alarm rate before vs after dismissals become site exceptions.

## Ask museum staff today
- **Go2:** AIR, PRO or EDU? Firmware version? The AES key, or access to the Unitree account it's bound to (needed on firmware 1.1.15+)?
- **Slots:** can we book **dog + drone in the same slot**? How many Track D slots, and can we book now? (Track A also wants the dogs.)
- **Mounting:** may we strap a small plate to the Go2's back?
- **Tello EDU:** how many units and batteries, is there a charging hub, are prop guards fitted? Is it in AP mode (needed for video)?
- **Flying:** which room, what maximum height, how far from exhibits and visitors? Can the lighting be kept bright?
- **Riello mentor:** which of the 5 metrics matters most to them? How will the jury define "arrival"?

## Team split (proposal; adjust to who's who)
| Workstream | Owner | Scope |
|---|---|---|
| Dog | _tbd_ | Go2 connection, `goto(zone)`, camera frames, speaker/mic, `SimDog` |
| Drone | _tbd_ | Back mount, `TelloDrone` hop routine, frames to Grok, `ReplayDrone`, network setup |
| Brain | _tbd_ | Grok triage/verify prompts, tool calls, site rules, dismissal memory, eval set + baselines |
| Console + alert + video | _tbd_ | Dashboard, KPIs, log, Twilio voice alert, 2-min video, README |

⏰ **Thursday 16:00:** 2-min video + minimum demo on a jury case + repo README (data, baseline result, limitations). Pitches 16:00–19:00.
