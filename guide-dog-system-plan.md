# Assistive Robotic Guide Dog — 4-Person Collaboration Plan

**Audience:** four people brainstorming in parallel  
**Goal:** Split the system so each person can explore one track without waiting on the others  
**Scope:** Walking assistance + everyday task assists for a blind user  
**Status:** Brainstorm / architecture plan — not a product claim  

> **Assumptions (mark these as open until validated):**  
> - Single primary user, urban/suburban sidewalks + indoor home/office  
> - Indie / small-team budget (not a funded robotics lab)  
> - Phone/wearable always available as companion UI  
> - English voice UI first; expand languages later  
> - Not a medical device for v1 (regulatory path TBD — owned with Track 4)

**How to use this doc.** One person owns one track. Stay inside your scope, write down open questions, and drop starter ideas. Do not block on another track. The shared picture below is the architecture everyone is designing against. Track 4 owns the contracts that join the four tracks.

---

## Shared picture (do not redesign alone)

### Vision
A quadruped (or cart-proxy early) that acts as a **mobile sensing + guidance layer**: keep the user on a safe path, describe the scene on demand, and help with everyday locating/reading tasks — with **fail-safe stop** and **offline-first** behavior.

### Primary journeys

**A. Outdoor walking (sidewalk / crosswalk)**
1. User says a destination or picks a saved place on the phone.
2. Robot leads at leash/handle distance (or the user follows haptic “tug” cues).
3. System detects curb cuts, poles, overhangs, moving people/vehicles.
4. At intersections: stop, announce light/crosswalk state, wait for confirm.
5. Replan on blockage; emergency stop on a sudden hazard.

**B. Indoor navigation (home / office / mall)**
1. Pre-mapped floor plan or SLAM map of frequent spaces.
2. Voice: “kitchen”, “elevator”, “restroom”.
3. Doorways, stairs, and glass doors flagged; elevators and escalators need an explicit confirm.
4. Room-level localization when GPS is useless (UWB tags / visual landmarks / BLE beacons — optional).

**C. Everyday assists**
- Find an object: “where’s my water bottle?” (open-vocab detection + pointing haptic/audio).
- Read a sign, label, or menu (OCR → TTS).
- Person find / follow (authorized contacts only).
- Door/threshold announce; sit/stand height cues for chairs (stretch).
- Carry a light bag or hold a door (hardware-dependent; **do not promise** without a manipulator).

### Non-goals (v1)
- Fully autonomous street crossing without user confirmation
- Climbing stairs with the user attached
- Medical diagnosis or “certified guide dog replacement” claims
- Dense crowd navigation without a person in the loop

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  User: bone-conduction headset + phone/watch + leash    │
└─────────────┬───────────────────────────┬───────────────┘
              │ BLE / Wi‑Fi / audio       │ haptics
┌─────────────▼───────────────────────────▼───────────────┐
│  Companion app                                          │
│  voice UX, maps UI, settings, emergency contacts        │
└─────────────┬───────────────────────────────────────────┘
              │ local LAN / BLE GATT / WebRTC data
┌─────────────▼───────────────────────────────────────────┐
│  Edge computer on robot (Jetson Orin / NUC / RK3588)    │
│  ROS2 graph: drivers → perception → Nav2 → control      │
│  local models optional; speech; safety supervisor       │
└──────┬───────────────┬──────────────────┬───────────────┘
       │               │                  │
   sensors         actuators          optional cloud
 (cam/depth/IMU)  (legs/wheels)    (maps, vision API,
  mic/GPS/UWB)                     analytics with consent)
```

| Layer | Owns | Latency budget | Track |
|-------|------|----------------|-------|
| Safety supervisor (on robot) | E-stop, cliff, collision | <50 ms | 2 builds it, 4 specifies the fail-safe policy |
| Perception (edge) | obstacles, scene, describe-on-demand | 50–200 ms for safety; seconds OK for describe | 1 |
| Navigation + control (edge) | path, follow, motor enable | 50–200 ms | 2 |
| Human interface | haptics, audio, confirms | human scale | 3 |
| Companion app + links | UX shell, phone link, consent, offline policy | human scale; cloud seconds OK | 4 |

**Design rules that bind every track**
- Always-on safety perception and the stop path stay on the robot. They never wait on a cloud API.
- A vision API is for **on-demand** description, with an explicit user trigger and consent.
- The companion app stays **outside** ROS. Bridge with rosbridge, a small gRPC API, or MQTT.
- Same haptic/voice vocabulary from the cart prototype through a quadruped. Do not reinvent UX when the base changes.
- v1 is an **assistive prototype**, not a certified medical or guide device. Legal review before any public pilot.

### Shared build sequence
Fake locomotion first. Each phase has a lead track; the others supply a thin slice so the demo still joins up.

| Phase | What we actually build | Lead | Others bring |
|-------|------------------------|------|----------------|
| 0 — cart | Human pushes a phone/cart. Voice describe / read sign, haptic left-right-stop, offline speech. Exit: a hallway walk on haptics + audio only. | 3 | 1: camera + one detector or a vision-API describe. 4: phone link + consent toggle. |
| 1 — wheeled Nav2 | TurtleBot-class rover, indoor SLAM, Nav2 to named poses, BLE haptic handle. Exit: “kitchen → door” with stops; e-stop still works with Wi‑Fi killed. | 2 | 1: depth costmap. 3: confirm prompts. 4: offline heartbeat. |
| 2 — outdoor pilot | GNSS, better depth or LiDAR, crosswalk confirm, supervised routes only. Exit: supervised blocks with zero uncommanded road entries. | 2 | 1: curb/sign experiments. 3: crossing confirm UX. 4: logging + consent. |
| 3 — quadruped | Vendor SDK ↔ ROS2, lead/follow, handle mount, safety MCU. Same app and cue vocabulary. | 2 | All tracks keep their Phase 1 contracts. |
| 4 — harden | Soak tests, a11y audit, privacy review, signed OTA, regulatory/insurance path. | 4 | Each track brings its hazard list. |

**Fake with a phone or cart:** scene describe, OCR, voice, haptic language, app UX, person-follow algorithms.  
**Do not fake for long:** a real motor-cut e-stop, outdoor depth in sun, legged locomotion, field liability.

---

## Track 1 — Sensing and vision

**Owner:** person 1

### Scope
Cameras, depth, and the perception that turns pixels into “what is around the user.” Includes a **high-level, exploratory** idea: connect a vision API so the dog can “see” and describe the environment (signs, obstacles, people, indoor scenes). This is a brainstorm, not a committed design. On-device models remain the default for anything that must be fast, offline, or private.

### Why it matters
Every other track consumes what this track sees. Navigation needs free space and obstacles. The human interface needs short, trustworthy descriptions. The phone link needs a clear rule for when an image is allowed to leave the robot. If sensing is wrong or late, the dog either freezes or walks someone into a hazard.

### Open questions
- Is front RGB + depth + IMU the minimum, and is a cheap LiDAR the next quality jump?
- Which descriptions are safe to outsource to a vision API, and which must never leave the device?
- What does the API actually return that an on-device detector cannot (open-vocab “find my bottle”, unusual signs, indoor scene summary)?
- How do we show the user that a cloud describe is in progress, failed, or refused offline?
- Do we store images at all, or only the text/events the other tracks need?
- Outdoor sun, glass, and night: where does depth fail, and what is the backup?

### Starter ideas
- **Minimum set:** front stereo or RGB-D (RealSense D435i/D455 or OAK-D), IMU, mic. Optional later: side camera, wheel/leg odometry, ultrasonic bumper, UWB/BLE beacons indoors, GNSS outdoors.
- **Always on device:** free-space and obstacles (depth → occupancy / elevation), people/bikes/vehicles (YOLO or RT-DETR), curb and stair discontinuities, person track if follow-mode is in scope. Hot path prefers TensorRT / ONNX, not a Python loop.
- **Vision API (exploratory):** on explicit “what’s around me?” / “read that” / “find X”, send a still (or a short clip) to a vision API and speak the result. Good for rich scene language, odd signs, and indoor “describe this room” while we learn what users ask. Not the obstacle detector.
- **API helps when:** the question is open-vocab, the user is stopped or paused, a second or two of latency is acceptable, and they have consented to the upload.
- **On-device is safer when:** the robot is moving, the cue is stop/obstacle/curb, the link is down, or the frame contains strangers’ faces. Latency budget for safety perception is 50–200 ms. No continuous cloud video.
- **Split the output:** a local event stream (`obstacle`, `curb`, `person`, `free_space`) for Track 2, and a separate on-demand `description` text for Track 3. Track 4 carries consent and the upload.
- **OCR:** on-device PaddleOCR / EasyOCR for signs and labels; phone vision APIs as a fallback experiment. Crosswalk state is an experiment, not a promise of autonomous crossing.
- **Skip early:** training a VLM from scratch, monocular depth as a LiDAR replacement, storing raw face crops.

---

## Track 2 — Navigation and robot control

**Owner:** person 2

### Scope
How the robot moves and when it refuses to move. Paths for sidewalk and indoor space, ROS2/Nav2, a fail-safe stop that does not depend on AI, and a wheeled (or pushed-cart) MVP before any quadruped.

### Why it matters
This is the part that can injure someone. A good description is useless if the base steps off a curb or keeps walking after the link drops. Proving guide behavior on a stable wheeled robot is how the team learns Nav2, maps, and the stop path before paying for legs.

### Open questions
- Wheeled learning robot first, or a Unitree Go2 early because demos need a dog shape?
- Lead (robot ahead, user follows the handle) vs guide-cane hybrid vs follow-me — which do we prototype first?
- Home routes first, or sidewalk navigation as the north star?
- What, exactly, cuts motor power: a MCU watchdog, a BLE deadman, a hardware button, or all three?
- Indoor named poses only for the hackathon slice, or a real outdoor map-match experiment?
- Jetson Orin Nano/NX vs a cooler RK3588 / NUC once the vision load is real?

### Starter ideas
- **Order of platforms:** phone or push-cart (perception + HRI) → wheeled ROS2 rover (TurtleBot4 or similar) → lease or buy an Edu quadruped (Unitree Go2 / B2 class) only after Nav2 and the stop path work. Skip a custom quadruped and Spot-class machines for v1. Do not train custom RL gaits; use the vendor SDK.
- **ROS2:** Humble or Jazzy. Drivers, TF, Nav2, lifecycle nodes, Gazebo (Isaac later). Global + local planners (Smac / MPPI or DWB). Indoor SLAM via Slam Toolbox to named poses (“kitchen”, “door”).
- **Modes:** (1) lead, haptic leash = follow vector, (2) guide-cane hybrid, heading with soft corrections, (3) follow-me as a secondary bag-carry idea, (4) stationary assist while motors are idle.
- **Fail-safe stop:** hardware e-stop + BLE deadman + watchdog. Loss of user link, tip, or missed perception heartbeat → **stop**. The supervisor can cut motor enable **independent of the vision API and of Nav2**. Speed caps near roads. No silent autonomy at crosswalks — Track 3 asks, the user confirms, then Track 2 moves.
- **Map facts Track 1 must supply:** a costmap / free-space update the planner can consume at 50–200 ms. Semantic labels are helpful; they are not a substitute for depth.
- **What this track publishes:** `nav_state` (idle, following, blocked, waiting_confirm, stopped), a short reason string, and battery/thermal gates (“won’t start a route under X%”).
- **Outdoor later:** GNSS map-matching, curb policy, weather. Exit bar for a pilot: supervised blocks and zero uncommanded road entries.

---

## Track 3 — Human interface

**Owner:** person 3

### Scope
Everything the blind user actually senses: audio, haptics, voice, and the confirmations required before a risky move. The phone’s screen-reader UI is Track 4’s shell; this track owns the language, timing, and cue set that shell must speak and vibrate.

### Why it matters
The user cannot watch a debug view. Trust comes from a tiny, consistent set of cues and from never talking over traffic. A wrong or chatty interface is as dangerous as a wrong path, because the user will miss the stop.

### Open questions
- Which three cues must work with no speech at all (so a noisy street still works)?
- Bone conduction vs a speaker on the robot vs an earpiece that blocks traffic noise?
- Push-to-talk on the handle vs a local wake word vs both?
- When is a spoken sentence allowed while moving, and when must we wait for a pause?
- Lead-with-handle vs robot-ahead: which cue pattern matches which control mode from Track 2?
- How does a cloud vision-API answer get introduced so the user knows it is slower and optional?

### Starter ideas
- **Channel order:** (1) haptics on the leash handle, (2) bone-conduction audio (Shokz-class) so ears stay open, (3) short voice commands, (4) watch haptics as a redundant stop/turn if the leash hand is busy, (5) phone VoiceOver/TalkBack only for settings, maps, and history.
- **Keep the vocabulary tiny:**

  | Cue | Meaning |
  |-----|---------|
  | Continuous buzz | **Stop / freeze** |
  | Double pulse left or right | Turn that way |
  | Rising intensity | Hazard approaching |
  | Single click | Acknowledgement |
  | Voice “STOP” | Same as the continuous buzz |

- **Confirm before:** road crossing, stairs, elevators, escalators. Never dump a paragraph while moving. Scene descriptions wait until the user pauses or asks.
- **Speech:** on-device wake word plus a handle push-to-talk backup. Core commands (“stop”, “kitchen”, “describe”, “help”) work offline via whisper.cpp (or faster-whisper) and Piper or the phone’s TTS. Free-form questions can use a connected model later; they are not the safety channel.
- **Emergency:** long-press the handle or voice “help” → Track 2 stops, Track 4 offers to call a contact. Jurisdiction and whether that call is in v1 stay open.
- **Copy the API answers into the same style:** one sentence, then silence. If Track 1’s vision API is slow or offline, say so in a few words and fall back to the local detector (“person ahead”, “blocked”) instead of improvising.
- **Phase 0 exit:** a blindfolded hallway walk using only this cue set.

---

## Track 4 — Comms, companion app, and safety policy

**Owner:** person 4

### Scope
The phone link, offline-first behavior, privacy, and **how the four tracks integrate**. This track does not invent a second navigation stack or a second cue language. It defines the pipes, the consent rules, and the one place a teammate looks to see what the others publish.

### Why it matters
Four people brainstorming in parallel will drift unless the messages between tracks are boring and explicit. The walk has to survive a dead network. Cameras on a sidewalk are socially sensitive, so “send the frame to an API” is a product decision, not a default.

### Open questions
- Strict offline-only v1, or opt-in cloud vision API from the first demo?
- Flutter vs React Native vs native, judged by VoiceOver and TalkBack quality?
- Is a remote sighted helper (WebRTC) in scope, or out for privacy and liability?
- Research prototype indefinitely, or an assistive-tech / medical path later?
- What is the budget ceiling before anyone buys a quadruped?
- Who are the first evaluation users, and can an orientation-and-mobility specialist review the cue set?

### Starter ideas
- **Links:**

  | Link | Tech | Use | If it dies |
  |------|------|-----|------------|
  | Robot ↔ phone, local | Wi‑Fi AP on the robot | state, voice, optional stills | fall back to BLE |
  | Robot ↔ phone, near | BLE GATT | heartbeat, e-stop, low-rate haptics | Track 2 stops or holds |
  | Robot ↔ cloud | HTTPS / gRPC / MQTT over TLS | map tiles, model updates, **opt-in vision API** | queue or disable; walk/stop/turn still work |
  | Remote sighted helper | WebRTC | explicit session only | not required for guidance |
  | Telemetry | MQTT or NATS | sparse status | buffer on disk |

- **Protocols:** gRPC (or a small typed API) for commands, nav goals, and battery. MQTT for telemetry and a watch. BLE for the safety keepalive. WebRTC only for an opted-in helper. The vision API call is a Track 4 client that Track 1 requests; it does not sit on the Nav2 hot path.
- **Offline-first:** known-map nav, on-device STT/TTS for core commands, and stop/turn/home with no cloud. Any cloud feature is labeled “needs connection,” including vision-API describe.
- **Privacy:** on-device by default, no continuous cloud video, explicit consent and an audio cue when a still is uploaded, blur or drop stranger faces, retention/export/delete in the app, a camera LED or shutter. Local black-box ring buffer for incidents, not a cloud video archive.
- **App shell:** maps, saved places, settings, emergency contacts, a consent switch for the vision API, and a visible “offline / API unavailable” state. Accessible UI is mandatory. Flutter is the default bet; React Native if the team is already in JS. Native modules will be needed for BLE and the robot Wi‑Fi.
- **Integration contract** (the only shared interface the other tracks must honor):

  | From | To | Message |
  |------|----|---------|
  | Track 1 | Track 2 | local obstacle / free-space / curb events at 50–200 ms, no network |
  | Track 1 | Track 3 | short on-device cues (“blocked”, “person”) plus optional description text |
  | Track 1 | Track 4 | “please describe this still” only after the user asked and consent is on |
  | Track 2 | Track 3 | `nav_state` + reason, so speech matches motion |
  | Track 3 | Track 2 | stop, turn ack, destination, **confirm** before crossing / stairs / elevator |
  | Track 3 | Track 4 | help / call-contact request |
  | Track 4 | all | link health, consent flags, offline mode; loss of BLE heartbeat means stop |

- **Safety policy this track writes down:** independent e-stop, fail-safe default is stop, depth plus a bumper, haptic plus audio for critical stops, no auto-restart of motion without a safety clear, thermal throttle drops AI before it drops the supervisor.
- **Suggested layout once code starts:** `robot_ws/` (ROS2), `perception/` (detectors + vision-API client), `safety_mcu/`, `app/`, `docs/`, `eval/`.

### Phase 0 shopping list (shared, not a second project)
Bone-conduction headset, phone and battery pack, USB or RealSense/OAK-D camera, a few coin vibe motors and an ESP32 for the handle, then a TurtleBot-class rover. Jetson when on-device vision needs it. Optional 2D LiDAR. Quadruped only after the Phase 1 exit criteria.

---

*Document type: collaboration plan on top of the engineering sketch. No performance guarantees. Validate with real users before any “guide dog replacement” language.*
