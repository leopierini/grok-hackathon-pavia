# Assistive Robotic Guide Dog — System Plan

**Audience:** Ayush (software engineer)  
**Goal:** How it works + how to build it (MVP → pilot → production)  
**Scope:** Walking assistance + everyday task assists for a blind user  
**Status:** Brainstorm / architecture plan — not a product claim  

> **Assumptions (mark these as open until validated):**  
> - Single primary user, urban/suburban sidewalks + indoor home/office  
> - Indie / small-team budget (not a funded robotics lab)  
> - Phone/wearable always available as companion UI  
> - English voice UI first; expand languages later  
> - Not a medical device for v1 (regulatory path TBD — see §11)

---

## 1. Product vision & user journeys

### Vision
A quadruped (or cart-proxy early) that acts as a **mobile sensing + guidance layer**: keep the user on a safe path, describe the scene on demand, and help with everyday locating/reading tasks — with **fail-safe stop** and **offline-first** behavior.

### Primary journeys

**A. Outdoor walking (sidewalk / crosswalk)**
1. User says destination or picks a saved place on phone.
2. Robot leads at leash/handle distance (or user follows haptic “tug” cues).
3. System detects curb cuts, poles, overhangs, moving people/vehicles.
4. At intersections: stop, announce light/crosswalk state (OCR + traffic heuristics), wait for confirm.
5. Replan on blockage; emergency stop on sudden hazard.

**B. Indoor navigation (home / office / mall)**
1. Pre-mapped floor plan or SLAM map of frequent spaces.
2. Voice: “kitchen”, “elevator”, “restroom”.
3. Doorways, stairs, glass doors flagged; elevators/escalators require explicit confirm.
4. Room-level localization when GPS is useless (UWB tags / visual landmarks / BLE beacons — optional).

**C. Everyday assists**
- Find object: “where’s my water bottle?” (open-vocab detection + pointing haptic/audio).
- Read sign / label / menu (OCR → TTS).
- Person find / follow (authorized contacts only).
- Door/threshold announce; sit/stand height cues for chairs (stretch goal).
- Carry light bag / hold door open (hardware-dependent; **do not promise** without manipulator).

### Non-goals (v1)
- Fully autonomous street crossing without user confirmation  
- Climbing stairs with user attached (high injury risk)  
- Medical diagnosis or “certified guide dog replacement” claims  
- Crowd surfing / dense festival navigation without human oversight  

---

## 2. High-level system architecture

```
┌─────────────────────────────────────────────────────────┐
│  User: bone-conduction headset + phone/watch + leash    │
└─────────────┬───────────────────────────┬───────────────┘
              │ BLE / Wi‑Fi / audio       │ haptics
┌─────────────▼───────────────────────────▼───────────────┐
│  Companion app (Flutter or RN)                          │
│  voice UX, maps UI, settings, emergency contacts        │
└─────────────┬───────────────────────────────────────────┘
              │ local LAN / BLE GATT / WebRTC data
┌─────────────▼───────────────────────────────────────────┐
│  Edge computer on robot (Jetson Orin / NUC / RK3588)    │
│  ROS2 graph: drivers → perception → Nav2 → control      │
│  local LLM/VLM optional; Whisper/TTS; safety supervisor │
└──────┬───────────────┬──────────────────┬───────────────┘
       │               │                  │
   sensors         actuators          optional cloud
 (cam/depth/IMU)  (legs/wheels)    (maps, model updates,
  mic/GPS/UWB)                     analytics with consent)
```

**Nodes of truth**
| Layer | Owns | Latency budget |
|-------|------|----------------|
| Safety supervisor (on robot) | E-stop, cliff, collision | &lt;50 ms |
| Perception + Nav2 (edge) | obstacles, path, follow | 50–200 ms |
| Companion app | UX, cloud sync, voice wake | human scale |
| Cloud (optional) | map tiles, heavy VLM, backups | seconds OK |

---

## 3. Sensing stack — what each is for

| Sensor | Role | Notes for indie build |
|--------|------|------------------------|
| **Stereo / RGB cameras** (front + optional side) | obstacles, OCR, scene describe, person detect | RealSense D435i/D455 or OAK-D Pro; protect lenses |
| **Depth (ToF/stereo)** | free-space, curb height, overhangs | Do not rely on RGB alone outdoors |
| **IMU** | attitude, fall/slip detect, dead reckoning | On robot + optionally on leash handle |
| **GPS / GNSS** (u-blox F9P if budget) | outdoor coarse localization | Sidewalks need map-matching; GPS alone ≠ curb |
| **Microphone array** | voice commands, siren/horn heuristics | Noise-robust wake word on-device |
| **Wheel/leg odometry** | local motion estimate | Fuse with IMU (EKF in ROS2) |
| **Optional LiDAR** (mid-360 / RPLiDAR) | robust outdoor free-space | Cost↑; strong for MVP quality |
| **Optional UWB / BLE beacons** | indoor room tags | Cheap indoor “GPS” for home |
| **Force/torque or leash tension** | follow-user / lead-user mode | Critical HRI signal |
| **Haptic actuators** (handle + watch) | direction, stop, urgency | Primary non-visual channel |
| **Ultrasonic** (cheap) | low bumper redundancy | Backup only |

**Assumption:** Front depth + RGB + IMU + mic is the minimum viable sensing set; LiDAR is the biggest quality jump per dollar after that.

---

## 4. Perception & AI

### Capabilities → candidate stack

| Capability | Approach | Candidates | Runs where |
|------------|----------|------------|------------|
| Obstacle / free-space | depth + occupancy grid | Nav2 costmaps, elevation maps | Edge |
| Semantic obstacles | detect people, bikes, vehicles | **YOLOv8/v11**, RT-DETR | Edge (TensorRT) |
| Curb / stair | depth discontinuity + classifier | custom CNN or elevation mapping | Edge |
| Path finding | global + local planner | **Nav2** (Smac/MPPI), DWB | Edge |
| Person following | track + keep distance | ByteTrack + YOLO; MediaPipe Pose | Edge |
| Scene description | VLM on demand | **Moondream**, LLaVA, GPT-4o/Claude vision (cloud) | Edge small / cloud large |
| OCR / signs | detect text → read | **PaddleOCR**, EasyOCR, Apple Vision (phone) | Edge or phone |
| Speech-to-text | commands | **Whisper** (faster-whisper / whisper.cpp), Picovoice | Edge |
| TTS | announcements | Piper, Coqui, device TTS | Edge / phone |
| Open-vocab “find X” | grounded detection | OWL-ViT, Grounding DINO, YOLO-World | Edge if quantized |

### Design rules
- **Always-on safety perception** stays on-device; never waits on cloud.
- Cloud VLMs only for **on-demand** “what’s around me?” with explicit user trigger + consent.
- Prefer TensorRT / ONNX Runtime / OpenVINO over Python-only loops on the hot path.
- MediaPipe is fine for hands/pose prototypes; swap to YOLO+tracker for outdoor robustness.

---

## 5. Control & locomotion

### Platform choice

| Option | Pros | Cons | Indie realism |
|--------|------|------|---------------|
| **Unitree Go2 / B2 Edu** | Real dog form, SDK, ROS support | Cost ($1.6k–$10k+), payload/compute limits | Best “real dog” path |
| **DeepRobotics / Ghost** etc. | Similar | Availability, support | Evaluate vs Unitree |
| **Boston Dynamics Spot** | Mature | Very expensive, lease-heavy | Unrealistic for indie v1 |
| **Custom quadruped** | Full control | Years of mech/controls | **Avoid** for product MVP |
| **Wheeled cart / rover** (TurtleBot4, Clearpath Jackal, DIY) | Cheap, stable Nav2 | Not “dog”; stairs fail | **Best learning MVP** |
| **Phone-on-cart** | Almost free | No locomotion autonomy | Perception/HRI first |

**Recommendation:** Fake locomotion with a **phone/cart** → **wheeled ROS2 robot** → **lease/buy Edu quadruped** once Nav2 + HRI work.

### ROS2 role
- **Use ROS2** as the middleware for sensors, TF, Nav2, lifecycle nodes, and simulation (Gazebo / Isaac Sim).
- Keep companion app **outside** ROS; bridge via `rosbridge` / custom gRPC / MQTT gateway.
- Safety supervisor as a **hard realtime-ish** node (or microcontroller watchdog) that can cut motor enable **independent of AI**.

### Control modes
1. **Lead mode:** robot walks ahead; haptic leash tension = follow vector  
2. **Guide-cane hybrid:** robot sets heading; user walks; soft corrections  
3. **Follow-me:** robot behind carrying bag (secondary)  
4. **Stationary assist:** OCR / describe / find object  

---

## 6. Human–robot interface (blind-first)

### Channels (priority)
1. **Haptics** — leash handle vibes / pull: left, right, stop, slow, hazard pulse patterns  
2. **Audio** — bone conduction (Shokz-class) so ears stay open for traffic  
3. **Voice commands** — short grammar + free-form when connected  
4. **Phone TalkBack / VoiceOver** — settings, maps, history (accessible UI mandatory)  
5. **Watch haptics** — redundant stop / turn cues if leash hand busy  

### Safety cue vocabulary (keep tiny & consistent)
| Cue | Meaning |
|-----|---------|
| Continuous buzz | **Stop / freeze** |
| Double pulse left/right | Turn that way |
| Rising intensity | Hazard approaching |
| Single click | Acknowledgement |
| Voice “STOP” | Same as continuous buzz |

### UX principles
- Confirm before road crossing, stairs, elevators.  
- Never dump long prose while moving; defer scene descriptions to pause.  
- Local-first wake word; push-to-talk button on handle as backup.  
- Emergency: long-press handle or voice “help” → stop + call contact / 911 (jurisdiction TBD).

---

## 7. Communication layers

| Link | Tech | Use | Offline behavior |
|------|------|-----|------------------|
| Robot ↔ phone (local) | **Wi‑Fi AP on robot** or LAN | High bandwidth (video optional, state, voice) | Primary path |
| Robot ↔ phone (near) | **BLE GATT** | Heartbeat, e-stop, low-rate haptics when Wi‑Fi down | Must work |
| Robot ↔ cloud | HTTPS / **gRPC** / MQTT over TLS | maps, model updates, optional VLM | Queued; app degrades |
| Live A/V assist (optional remote human) | **WebRTC** | Sighted helper session | Explicit opt-in |
| Telemetry | **MQTT** (HiveMQ / Mosquitto) or NATS | sparse status | Buffer on disk |

### Protocols — when to use what
- **gRPC:** typed robot API (commands, nav goals, battery)  
- **MQTT:** pub/sub telemetry, multi-device watches  
- **WebRTC:** remote vision assistance only  
- **BLE:** safety keepalive; if BLE lost → controlled stop or “hold position”

### Offline-first requirements
- Nav within known maps without internet  
- STT/TTS on-device for core commands  
- No cloud required for walk / stop / turn / home  
- Cloud features clearly labeled “needs connection”

---

## 8. Software frameworks & stack options

### Recommended indie stack (opinionated)

| Layer | Choice | Why | Tradeoff |
|-------|--------|-----|----------|
| Robot middleware | **ROS2 Humble/Jazzy** | Nav2 ecosystem, drivers | Learning curve |
| Navigation | **Nav2** | Production-ish planners, behavior trees | Tune heavily outdoors |
| Vision | **OpenCV** + **Ultralytics YOLO** | Fast to ship | Custom curb models still needed |
| Depth foundation | **Depth Anything V2** (optional) | Monocular depth fill | Not a LiDAR replacement |
| On-device speech | **whisper.cpp** + **Piper** | Offline, small | Accent robustness varies |
| Companion app | **Flutter** | One codebase, solid a11y widgets | Native iOS a11y quirks |
| Alt app | **React Native** | JS team familiarity | BLE/Wi‑Fi native modules more glue |
| Edge HW | **Jetson Orin Nano / NX** | CUDA + TensorRT | Power/thermals on dog |
| Alt edge | **Intel NUC / RK3588** | Cheaper, cooler | Weaker GPU |
| Sim | Gazebo + Nav2; later Isaac | Iterate without hardware | Sim-to-real gap |
| ML ops | ONNX + TensorRT export | Deterministic deploy | Export pain |

### What to skip early
- Custom RL locomotion (use vendor SDK gait)  
- Training large VLMs from scratch  
- Building your own mobile OS / mesh radio stack  

### Cost/complexity realism (order-of-magnitude)
| Stage | Hardware spend | Team shape |
|-------|----------------|------------|
| Phone-on-cart MVP | $50–300 | 1 engineer nights/week |
| Wheeled Nav2 pilot | $1k–5k | 1–2 engineers |
| Quadruped pilot | $3k–15k + compute | 2–4 + ME advisor |
| Production | $$$ + liability insurance + regulatory | Company |

---

## 9. Safety, reliability, privacy

### Safety
- **Independent e-stop:** hardware button + BLE deadman + watchdog MCU that cuts motor power  
- **Fail-safe default:** loss of user link, tipped robot, or perception heartbeat miss → **stop**  
- **Redundancy:** depth + ultrasonic bumper; haptic + audio for critical stops  
- **Speed caps** near roads; geofence optional  
- **No silent autonomy** at crosswalks — user confirm  
- Log black-box ring buffer (local) for incident review  

### Reliability
- Lifecycle-managed ROS nodes; auto-restart non-critical; never auto-restart without safety clear  
- Battery SOC gates (“won’t start route &lt; X%”)  
- Thermal throttling → reduce AI, keep safety  

### Privacy
- Default: **on-device** processing; no continuous cloud video  
- Cloud/VLM/WebRTC: **explicit consent**, visible recording indicator (audio cue)  
- Faces of strangers: prefer blur / embeddings not stored  
- Data retention knobs in app; export/delete account  
- Assume cameras are socially sensitive — physical shutter or LED  

### Liability (assumption)
v1 is an **assistive prototype**, not a certified medical/guide device. Legal review before any public pilot.

---

## 10. Phased build plan

### Phase 0 — HRI & perception on a cart (2–6 weeks of focused work)
**Buy/build:** smartphone tripod/cart, bone-conduction headset, cheap vibe motor on a cane/handle, optional USB cam.  
**Fake:** locomotion (human pushes cart), mapping, legs.  
**Ship:** voice “describe / read sign / find door”, haptic left-right-stop language, offline Whisper+TTS, YOLO people/obstacles overlay.  
**Exit criteria:** Blindfolded or blindfolded-partner walk along a hallway using **only** haptics+audio.

### Phase 1 — MVP wheeled guide (Nav2)
**Buy:** TurtleBot4 / differential rover, RPi or Jetson, RealSense or OAK-D, optional 2D LiDAR.  
**Build:** ROS2 bringup, indoor SLAM (Slam Toolbox), Nav2 to named poses, BLE haptic handle, Flutter app skeleton.  
**Fake:** outdoor curb logic, stairs, quadruped balance.  
**Exit criteria:** Indoor “kitchen → door” with stops for obstacles; e-stop works with Wi‑Fi killed.

### Phase 2 — Outdoor pilot (still wheeled or leased quadruped)
**Buy/add:** GNSS, better depth/LiDAR, traffic-light OCR experiment, leash tension sensor.  
**Build:** sidewalk map-matching, crosswalk confirm UX, weather cases, logging.  
**Pilot:** 1–3 trusted users, supervised routes only.  
**Exit criteria:** N supervised outdoor blocks with zero uncommanded road entries.

### Phase 3 — Quadruped integration
**Buy:** Unitree Go2 Edu (or equiv.) + Orin payload if needed.  
**Build:** vendor SDK ↔ ROS2 bridge, lead/follow modes, handle mount, safety MCU.  
**Keep:** same app + haptic vocabulary (do not reinvent UX).  
**Exit criteria:** Same indoor/outdoor behaviors as wheeled, plus rough-ground.

### Phase 4 — Production readiness
- Reliability soak tests, red-team hazards, a11y audit, privacy review  
- Support tooling, OTA with signed images  
- Regulatory/insurance path (see open questions)  
- Everyday assists: object find, menu OCR polish, optional remote WebRTC helper  

### What to fake before buying a robot dog
| Fake with phone/cart | Don’t fake forever |
|----------------------|--------------------|
| Scene describe, OCR, voice | Real e-stop cut of motors |
| Haptic language | Depth outdoors in sun |
| App UX / offline mode | Legged locomotion |
| Person follow algorithms | Liability & field safety |

---

## 11. Open questions / decisions for Ayush

1. **Form factor bet:** Commit to wheeled-first learning, or buy Go2 early for demos/fundraising?  
2. **Lead vs follow biomechanics:** Handle-in-hand guide (classic dog) vs robot-ahead with haptic leash — which feels safer in user tests?  
3. **Target environment:** Home-only assist first, or sidewalk navigation as the north star?  
4. **Edge hardware:** Jetson Orin Nano vs cheaper RK3588 — CUDA need vs battery life?  
5. **Companion app stack:** Flutter vs React Native vs native iOS/Android for best VoiceOver/TalkBack?  
6. **Cloud policy:** Strict offline-only v1, or allow opt-in cloud VLM from day one?  
7. **Remote human assist:** In-scope (WebRTC) or explicitly out for privacy/liability?  
8. **Regulatory stance:** Research prototype indefinitely, or pursue assistive-tech / medical pathways?  
9. **Language & locale:** Single-language STT OK? Which city’s sidewalks for first map?  
10. **Budget ceiling:** Cap before quadruped purchase (suggest: don’t buy dog until Phase 1 exit criteria met)?  
11. **Team:** Solo nights vs need a ME for mounts/leash strain relief?  
12. **Evaluation users:** Access to blind/low-vision testers and orientation-&amp;mobility (O&amp;M) specialist feedback?

---

## Appendix A — Suggested repo layout (when coding starts)

```
guide-dog/
  robot_ws/          # ROS2 packages
  perception/        # YOLO, OCR, VLM wrappers
  safety_mcu/        # watchdog firmware
  app/               # Flutter companion
  docs/              # architecture, hazard log
  eval/              # route bags, metrics
```

## Appendix B — First shopping list (Phase 0–1)

- Bone-conduction headset  
- Phone + spare battery pack  
- USB / RealSense or OAK-D camera  
- 3–4 coin vibe motors + ESP32 for haptic handle prototype  
- TurtleBot4 or equiv. rover (Phase 1)  
- Optional: RPLiDAR A2/A3 or Mid-360  
- Jetson Orin Nano developer kit (when vision load demands it)

---

*Document type: engineering plan. No performance guarantees. Validate with real users before any “guide dog replacement” language.*
