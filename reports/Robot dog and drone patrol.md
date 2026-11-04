# Let Grok run the patrol

> **Team decision update (Wed 4 Nov, after this report):** we chose the **dog-carried drone** design. The Tello EDU rides on the Go2's back, and Grok launches it when the dog's own view is blocked. We rejected the "drone scouts, dog responds" design: Asylon already sells it, it makes the drone a single point of failure, and it slows event-to-arrival time. This report's conclusion still holds (Track D, Grok as operator, drone outside the core loop). The drone moves from the start of the pipeline to an escalation step inside the dog's "check". See [`project-plan.md`](../project-plan.md) for the current plan.

A robot dog plus drone patrol is a good project, but only in a specific form. Build it as a Track D "Robot Dog Patrol" entry. Make Grok the AI night-shift operator: it triages camera events, decides which asset to send, checks what the asset sees, and calls the caretaker in Italian. The drone, now confirmed as a **Tello EDU**, stays an optional "second look" add-on, never part of the core demo. It is the easiest drone to program from Python and it has mission pads for indoor positioning, but its video works only on its own Wi-Fi network, which forces a second network interface. The basic idea, a drone spotting something and a dog going to check, is already sold. Asylon has a reported **$17M, 5-year Securitas contract** for dogs plus drones. What nobody has productised is having an AI, not a human control room, make the dispatch decision, and that is where you can stand out. Track D scores five control-room numbers: time from event to the dog's arrival, staged anomalies verified, false alarms forwarded, alert clarity, and log completeness. The brief provides **a dog and smartphones as cameras, not drones**, and a drone improves none of those five numbers directly. So the plan that can win is a reliable phone-camera, dog and Grok loop that handles the jury's new case and is measured against a baseline. Add the drone only if it passes a go/no-go check on Thursday morning.

## "Drone spots, dog investigates" already ships; the dispatcher is the open seat

**Commercial prior art.** The concept is not new.

| Player | What exists | Who decides to dispatch |
|---|---|---|
| **Asylon Robotics** (US) | DroneDog (on Boston Dynamics Spot) plus Guardian drones, with docks and battery swap; more than 250,000 missions (company-reported) ([Asylon](https://asylonrobotics.com/250k-missions-150k-miles-dronedog-asylon-robotics/)) | A 24/7 human remote operations centre (RSOC). "A drone might spot something from the air, and the 24/7 RSOC might send in a robot dog" ([Forbes](https://www.forbes.com/sites/johnkoetsier/2026/10/22/this-17-million-robot-security-deal-might-be-the-biggest-ever/)) |
| **Percepto + Boston Dynamics** (2020) | Drone and Spot in one inspection platform ([TechCrunch](https://techcrunch.com/2020/11/24/industrial-drone-maker-percepto-raises-45m-and-integrates-with-boston-dynamics-spot)) | Platform rules |
| **DroneDeploy + Rocos** (2021) | A drone finds solar hotspots and "automatically activat[es] Spot" ([The Robot Report](https://www.therobotreport.com/dronedeploy-acquires-robotics-software-startu-rocos/)) | Fixed trigger |
| **DEEP Robotics** (China) | Dog plus drone inspection of substations and wind farms ([Newsfile](https://www.newsfilecorp.com/release/273102)) | Not disclosed |
| **Boston Dynamics Orbit** | Spot answers natural-language questions about its photos; Gemini Robotics-ER added in April 2026 ([Robotics & Automation News](https://roboticsandautomationnews.com/2026/04/15/boston-dynamics-integrates-google-deepminds-gemini-robotics-model-into-spot-inspection-platform/)) | Ground robot only; no coordination with other assets |

Asylon is the direct competitor, and it is mature. It has a **$26M Series B** ([TechCrunch](https://techcrunch.com/2025/07/22/robot-guard-dogs-help-asylon-raise-a-26m-series-b/)) and customers including Ford, Mercedes-Benz Stadium, Bayer and the US Air Force ([DroneLife](https://dronelife.com/2026/10/14/robot-dogs-and-drones-asylon-robotics-guards-critical-infrastructure/)). Its reported **$17M, 26-system Securitas deal** may be the largest robotic-security contract to date, but Forbes is the only source for its terms ([Forbes Argentina](https://www.forbesargentina.com/innovacion/dos-empresas-firman-acuerdo-us-17-millones-podria-ser-mayor-historia-seguridad-robotica-n100975)). Its robots can trigger one another ("One can trigger a launch of the other"), but **the judgement still sits with humans**.

**Research prior art.** Academic work covers the coordination layer but not the full security loop:

- **COHERENT** (ICRA 2025) uses an LLM to plan tasks for teams of quadrotors, robot dogs and arms, with public code ([arXiv 2409.15146](https://arxiv.org/html/2409.15146v3)).
- **Cladera et al. (2025)** run a UAV and a UGV on natural-language missions over shared semantic maps ([arXiv 2505.09108](https://arxiv.org/abs/2505.09108)).
- **Training-free VLM anomaly detection** (LAVAD, Cerberus) is an active field ([arXiv 2510.16290](https://arxiv.org/pdf/2510.16290)).
- Terrain-aware ground-to-air work notes that teams "mostly rely on pre-defined scenarios" to decide when to deploy the aerial robot ([arXiv 2505.14859](https://arxiv.org/pdf/2505.14859)).

Our research found no published system or product that closes the full security loop: VLM triage of an event, an LLM decision on which asset to send, ground verification, and an evidence-backed alert written for a guard. That combination is the defensible novelty. It is novel as an *integration and decision layer*, not as a new robot or a new sensor pairing.

**Market and regulation.** Both point the same way. Estimates for security robots cluster around **$15–18B in 2025, growing 12–14% a year** ([GII/Mordor](https://www.giiresearch.com/report/moi1851293-security-robot-market-share-analysis-industry.html)). The drone-in-a-box segment is about **$1.5B, heading to about $7B by 2034** ([Fortune Business Insights](https://www.fortunebusinessinsights.com/drone-in-a-box-markt-108470)). These are publisher estimates and their scopes differ.

Our research found no Asylon-style managed dog-and-drone service in Europe. Automated drone patrols over a real Italian factory would fall under EASA's **specific category**, which needs an ENAC authorisation via SORA, STS or PDRA ([EASA](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones)). That makes an "AI recommends, human approves" design both safer and closer to what the rules expect. It is a pitch line Riello can take straight to a real deployment.

**Caveat on the site.** Riello's own material puts its Legnago production site at 22,000 m² inside a larger complex ([Riello presentation](https://www.storicoeventi.este.it/images/file-pdf/Presentazione%20Riello_Este_205.pdf)). We found no public information on how Riello secures it today, so ask the mentor.

## Track D rewards five control-room numbers, and a drone moves none of them directly

**The brief.** Track D asks for a single flow: **event → mission → check → alert**, with a control console and a complete log. The minimum demo has three parts:

1. A scheduled patrol between three spots in one room.
2. A smartphone acting as a camera detects a staged anomaly (a person in a restricted area or an abandoned object), and Grok sends the dog.
3. The dog frames the scene, Grok describes it, and an alert goes to a test number.

A simulated dog is explicitly allowed if no slot is free. Out of scope are modules on the dog, footage of the real site, real calls to security or police, and autonomous navigation over 55,000 m² ([Grok Hackathon tracks](https://pavia.grokbot.it/tracks)).

**Rules for all tracks** ([Grok Hackathon rules](https://pavia.grokbot.it/rules)):

- The minimum demo runs on **a new case chosen by the jury**.
- The repo must include **at least one result measured against a baseline**.
- A **~2-minute video** is due Thursday at 16:00.

**Hardware and the drone.** Track D's listed hardware is "Dog, smartphones as cameras". Drones appear only in the general inventory ("a few drones"), and the code of conduct allows drones "only in your slot and with staff". Drones are therefore **not prohibited, but not provided for this track**. The team has confirmed the unit on site as a Tello EDU (Global), so the drone is technically viable. Whether Track D may book it is still an open question for staff.

**Jury.** It includes Ralph Johnson, an xAI/SpaceXAI field engineer, and lead organiser Luca Bianchi, who gives the "Using Grok Bots for everything" talk. No Riello person is named on the jury.

The five metrics map directly onto design choices.

| Judged metric | Design that moves it | Where the drone helps |
|---|---|---|
| Event → dog arrival time | Local detection on phone streams (YOLO or Frigate) with no LLM in the detection loop. Routes from each zone to waypoints are pre-computed and calibrated in the first dog slot. Optional **optimistic dispatch**: the dog starts walking while Grok triages, and Grok can recall it. | It does not. A "drone checks first" policy *adds* latency to the dog's arrival. |
| Staged anomalies verified correctly | Two stages: Grok triages the camera frame with zone context, then compares the dog's camera frame with a **reference frame** captured on patrol ("what changed?"). Open-vocabulary prompts handle the jury's new object. | Only for blind spots the phones cannot see. |
| False alarms forwarded | Alert only after stage-two confirmation, or after high confidence that persists across frames. Test on hard negatives: a staff vest, a printed photo of a person, a mannequin, a bag next to its owner. | A fast aerial second opinion can dismiss a false alarm before the dog walks. |
| Alert clarity | A structured alert: what, where (room and spot on the map), when, two evidence images, confidence, recommended action. Delivered as an Italian voice call with an `acknowledge_alert` tool. | None |
| Log completeness | An append-only JSONL store keyed by incident: every state change, timestamps, model and prompt versions, raw Grok output, operator commands. Replayable, and fed into the end-of-shift report. | Adds one more source to log. |

The Grok capabilities that make it **essential rather than decorative** are all documented:

- **Image input with structured outputs**, for triage and verification against a schema ([xAI structured outputs](https://docs.x.ai/docs/guides/structured-outputs)).
- **Function calling** with `tool_choice="required"`, for the dispatch decision. Example tools: `dispatch_dog`, `task_camera`, `task_drone`, `hold_and_watch`, `dismiss`, `escalate_alert` ([xAI function calling](https://docs.x.ai/docs/guides/function-calling)).
- **The real-time voice agent**, with function tools, Italian support and the G.711 telephony codec ([xAI voice agent](https://docs.x.ai/docs/guides/voice/agent)).
- **The `voice-agent-phone` cookbook**, whose outbound mode places the alert call through Twilio ([xai-cookbook](https://github.com/xai-org/xai-cookbook/tree/main/examples/voice-agent-phone/xai)).

Cost does not matter here. `grok-4.7` is $2 per million input tokens, and voice costs **$0.08/min**. The one real limit is **10 concurrent voice sessions** on the lowest (T0) API tier ([xAI models and pricing](https://docs.x.ai/docs/models)). xAI publishes no latency figures, so measure p50/p95 on the venue Wi-Fi and put the table in the README.

**Grok Bot** has no documented developer API ([xAI](https://x.ai/news/introducing-grok-bot)). Use it only off the critical path, for example to deliver the shift report to the caretaker's phone. Luca Bianchi will notice it.

**Is the drone worth it?** Judged strictly on these five metrics, the drone earns its place only if it measurably improves verification (by covering blind spots) or false alarms (by giving a fast second look). The improvement then has to appear in a baseline table. With only 1–2 teams on Track D, **reliability on the jury's new case will decide the prize more than breadth will**. A drone that fails live in front of the jury costs more than having no drone.

## Feasibility hinges on the Go2 handshake, the Wi-Fi topology and staff permission

### The dog

**Go2 control route.** The fastest route is `unitree_webrtc_connect`:

- Pure Python over Wi-Fi.
- Works on Go2 AIR, PRO and EDU "with no jailbreak".
- Exposes velocity `Move`, an obstacle-avoidance service, odometry topics, LiDAR, the front camera, and two-way audio ([unitree_webrtc_connect](https://github.com/legion1581/unitree_webrtc_connect)).

**Blockers to clear before the first slot:**

- **AES key.** Firmware **1.1.15 and later needs a per-device AES-128 key**. It can only be fetched with the credentials of the Unitree account the dog is bound to. Without it, "the connection never starts".
- **One client at a time.** Only **one WebRTC client** may connect, so the staff's phone app must be disconnected.
- **No "go to (x, y)" command.** There is no supported high-level command for it. You close the loop yourself: turn to a bearing, walk a distance, re-check, all on odometry that drifts. The obstacle-avoidance `MoveToAbsolutePosition` (mode 2) exists in the official SDK but is undocumented ([unitree_sdk2_python](https://github.com/unitreerobotics/unitree_sdk2_python)). Treat it as a bonus to test in slot 1.

**Accuracy.** Expect accuracy of about a metre, so plan legs of 5–15 m in one cleared room. Start every run from a taped dock, and finish with a visual check by Grok instead of trusting odometry.

**ROS2/Nav2 SLAM.** It is too heavy for 30-minute slots. The go2_ros2_sdk README itself warns that the planner may "route your dog through walls" ([go2_ros2_sdk](https://github.com/abizovnuralem/go2_ros2_sdk)).

**The Go1** is a fallback, not a choice:

- Position mode is marked "reserve" (not implemented), and odometry "usually drift[s]".
- The prebuilt SDK libraries are Linux-only.
- Camera access means SSH-ing into the onboard Jetsons and killing vendor processes ([unitree_legged_sdk](https://github.com/unitreerobotics/unitree_legged_sdk)).

### The drone: a confirmed Tello EDU

The team has confirmed the drone on site: a **DJI/Ryze Tello EDU (Global), manufactured December 2020**. That is the best-case model for a 30-hour build, because it is the only common drone a team can program from a laptop in hours. (The other candidates the research covered, the DJI Mini and the Crazyflie, would have needed a mobile SDK app or extra positioning decks.)

**Specs.** About **80 g**, about **13 minutes of flight** per battery, **720p30 video** with an 82.6° field of view, and a built-in vision positioning system ([Ryze specs](https://www.ryzerobotics.com/tello/specs)). Expect about 8–10 usable minutes per battery indoors, so plan routes of 2–3 minutes and keep several charged batteries in rotation.

**Control library.** `djitellopy` (`pip install djitellopy`) gives you everything the plan needs ([DJITelloPy](https://github.com/damiafuentes/DJITelloPy); [djitellopy docs](https://djitellopy.readthedocs.io/en/latest/tello/)):

- `connect()`, `takeoff()`, `land()`;
- `streamon()` and `get_frame_read()` for video;
- `move_*` moves and `go_xyz_speed(_mid)` to fly to coordinates;
- `get_battery()` for an auto-land below 20%;
- `set_video_resolution` / `set_video_fps` / `set_video_bitrate` to lower Wi-Fi load.

**Mission pads (EDU only) are the indoor localisation plan.**

- There are eight pads, m1–m8. `get_mission_pad_id()` and `get_mission_pad_distance_x/y/z()` return which pad the drone sees and its offset from it in cm.
- `go_xyz_speed_mid(x, y, z, speed, mid)` flies to coordinates in a pad's frame. Place pads at taped floor positions, one per zone, and the drone's route becomes repeatable.
- Detection runs at 20 Hz looking down only, or 10 Hz with both directions enabled.
- The library warns that pads "need a bright environment to work reliably". Museum lighting, or glossy or uniform floors, may defeat them. Test them in the first drone slot, and fall back to timed `move_*` legs plus zone tagging if they fail.

**The networking constraint shapes the architecture.** Video streaming works **only in AP mode**, when the laptop joins the Tello's own Wi-Fi network. Once an EDU joins an existing network (station mode), video is unavailable ([djitellopy docs](https://djitellopy.readthedocs.io/en/latest/tello/)). The laptop on the Tello's network therefore loses the internet that Grok needs, and the Go2's network too. Two ways around it:

- one laptop with a **second network interface** (USB Wi-Fi adapter, or Ethernet or a phone tether for internet and the dog);
- a dedicated **"drone laptop"** that joins the Tello network and forwards frames to the main laptop over Ethernet or a local socket.

Test the full network setup with `SimDog` before any hardware slot.

**Station mode and swarms.** Station mode (`connect_to_wifi`, EDU only; the drone reboots) would let the drone share the venue or dog network, and it is what `TelloSwarm` needs. But it gives up video, which is the only reason the drone is in the system. **Stay in AP mode, use one drone, and skip swarms.** A second Tello EDU is useful as a spare, or for battery hot-swap, not as a swarm.

**Hand-off from drone to dog.** The robust method without GPS is a **shared floor plan with named zones**, anchored by the mission pads. Each segment of the drone's route (`go_xyz_speed_mid` over pad k) is tagged with the zone it overlooks. A detection is reported as `{zone, waypoint, evidence, description}`, and the dog walks to that waypoint. This tolerates a couple of metres of drone drift and takes about 2–3 hours to build. The pads tell you where the *drone* is, not where the *anomaly* is, so zone tagging stays the primary mechanism. The Tello's main camera faces forward, so it sees the floor ahead and below rather than straight down. ArUco floor markers with a homography give a metric upgrade if the floor is visible.

**Drone risks and mitigations:**

| Risk | Mitigation |
|---|---|
| Losing internet or the dog while on the Tello's AP | Second network interface or a second laptop |
| Pads not detected in dim light | Ask for bright lighting in the flight box; fall back to timed legs |
| Drift near exhibits | Enforce the flight box in software, fly low and slow, keep a `land`/`emergency` hotkey |
| Short batteries | Several charged packs, a charging hub, auto-land below 20% |
| Firmware or SDK mismatch on a 2020 unit | Check `command` / `sdk?` and pad support in the first minutes of the first slot |

### Grok vision and safety

**Gating Grok vision.** Grok vision accepts JPEG and PNG up to 20 MiB as base64 ([xAI image understanding](https://docs.x.ai/docs/guides/image-understanding)). Its latency is undocumented, so budget seconds per call. Gate it behind a fast local detector or a frame difference, and call it asynchronously.

**Indoor flight rules.** EU drone regulation 2019/947 is described as **not applying to UAS operated exclusively indoors** ([EASA slides](https://uic.org/events/IMG/pdf/2_drone_regulation_easa.pdf)). The real gate is **museum permission**. Ask for:

- a cleared flight box;
- a maximum height of about 2 m;
- 2–3 m of clearance from exhibits;
- no flights over visitors;
- the box enforced in software;
- a dedicated `land`/`emergency` key.

**Privacy.** Frames sent to xAI may contain visitors' faces. Blur faces or avoid storing frames, and tell staff.

### What is realistic in 30 hours

The research notes' overall judgement:

- **Realistic:** the Tello EDU on a scripted, pad-anchored patrol in one room; YOLO plus Grok detection on staged anomalies; hand-off by zone; the Go2 reaching a waypoint to within about 1 m in one room; Grok confirming from the dog's camera; a dashboard; simulated and replay fallbacks (recorded Tello video played back through the same interface).
- **Too risky:** multi-room SLAM, autonomous drone navigation across rooms, the dog visually tracking the drone, sub-20 cm hand-off, and Tello swarms or station mode (both disable video).

## Win by making Grok the operator that asks for more evidence

The differentiator is not the robots. It is visible judgement. Build an **"active perception" operator**. Grok does not just label a frame. When it is unsure, it calls tools to *get more evidence*:

- `look_again(cam)`
- `send_dog(zone)`
- `send_drone(zone)`
- `ask_guard(question)`

The moment to stage for the jury: a person half-visible at the edge of a restricted zone. Grok says "uncertain, sending the dog". The dog arrives and Grok compares the dog's view with the patrol reference frame. Then the caretaker's phone rings with an Italian alert, the caretaker asks "is the person still there?", and Grok answers from the log. That one sequence covers all five metrics.

**Patrol-time reference frames.** During scheduled patrols the dog records a reference frame at each spot. On a dispatch, Grok compares that frame with the live dog frame. This handles "abandoned object" cases and the jury's unseen object types, which fixed rules cannot do.

**Scoreboard.** Put a live **KPI scoreboard** in the console header showing Riello's five metrics and the time to acknowledgement. That way the judges read your score from the screen in the proposer's own terms.

**Approval gate.** Add a **one-tap human-approval gate** for high-risk actions. This mirrors the cookbook's `refund-agent-human-approval` pattern ([xai-cookbook](https://github.com/xai-org/xai-cookbook)), the human control rooms that run real systems (Asylon), and ENAC's specific-category expectations.

**Baselines.** Prove the claims with two baselines that reuse the judged metrics.

| Baseline | Compare | Data | Report |
|---|---|---|---|
| **1. Triage quality** | Frigate/YOLO rules only ("person in restricted zone" or "backpack stationary > T") vs Grok triage vs Grok triage plus dog verification. Frigate exposes `label`, `score`, zones and `stationary` per object ([Frigate MQTT](https://docs.frigate.video/integrations/mqtt/)), so the rules baseline is honest. | About 30–40 staged and synthetic events with hard negatives. Real staged events reported separately from Grok Imagine images. | Precision, recall and false alarms forwarded |
| **2. Response time** | Scheduled patrol only (expected detection time is about half a loop) vs event-triggered dispatch vs optimistic dispatch | Measured patrol loop and dispatch runs | Seconds from event to arrival |
| **3. Coverage** (only if the drone flies) | Cells visible to the phones alone vs phones plus a drone vantage point | Floor-plan grid, with five anomalies placed in blind spots | Count of anomalies detected |

Log the jury's new case as a held-out row in the evaluation table.

**The drone, in its best role.** Frame it as a **blind-spot "first look"**, not as a co-equal patrol robot. Grok tasks it when an event comes from the edge of camera coverage, then decides whether the dog must go. It is a configurable policy, and its latency cost is measured and reported honestly.

**The pitch line:** "Asylon proved buyers pay for dogs plus drones, but a human still decides. We made that decision auditable, measured, and Grok's."

## Conclusion: build the Track D operator, keep the drone behind a gate

The dog-and-drone idea succeeds only after a reframing. Industry has already shown that the hardware pairing works. The unclaimed part is the cognition between the two machines: deciding what an event means, which asset to send, and when to bother a human. That is exactly what Grok must be essential for, and exactly what Riello's five metrics measure.

**Recommendation.** Enter Track D with a phone-camera → Grok triage → Go2 dispatch → Grok verification → Italian voice-alert loop. Build it simulation-first, with a simulated dog behind the same interface. Treat the drone as a module behind a hard go/no-go gate at about **Thursday 09:00**. If by then the Tello EDU has not streamed frames into triage while the main laptop kept internet and dog access, and flown one supervised pad-anchored route, it appears only as labelled recorded footage in the video, or not at all.

### Next-steps checklist

**Wednesday (today)**
- [ ] Register for Track D and **book dog slots now**; Track A competes for the same dogs.
- [ ] Get the Go2 firmware version, serial number and AES key (or account access for `unitree-fetch-aes-key`) before the first slot.
- [ ] Stream 2–3 phones (RTSP or MJPEG) into YOLO or Frigate, with zones drawn on the provided floor plan.
- [ ] Build Grok triage with structured outputs, plus the dispatch tool set (`dispatch_dog`, `hold_and_watch`, `dismiss`, `escalate_alert`, `recall_dog`, and optionally `task_drone`).
- [ ] Build the append-only incident log and the console: floor plan, incident pins, KPI header, STOP button.
- [ ] Build `SimDog`, a 2D unicycle model with the same `goto` / `get_pose` interface as the real dog, so the full loop runs without a slot.
- [ ] First dog slot. Confirm `connect()`, `Move` and a state read. Test obstacle-avoid mode 2. Calibrate the 3-spot patrol and the zone → waypoint routes. Measure walking speed. Record reference frames and video for the film.
- [ ] Benchmark Grok latency, p50/p95 over 20 calls each: one image; two images; time to first audio from the voice agent.
- [ ] Wednesday night. Set up `voice-agent-phone` outbound to a test number, with the alert schema and an `acknowledge_alert` tool. Pre-warm ngrok. Label the evaluation set and build a `make eval` script for both baselines.
- [ ] Drone prep, without the drone: install `djitellopy`; write `TelloDrone` and `ReplayDrone` behind one `frames() → (frame, zone_id, t)` interface; set up the second network interface (USB Wi-Fi adapter or Ethernet/tether) or the dedicated drone laptop; print or place mission pads at taped positions, one per zone.
- [ ] First drone slot, with staff:
  - `connect()`, then check the battery and SDK version;
  - `streamon()` at reduced resolution and fps, with frames flowing into triage while the main laptop keeps internet and dog access;
  - test pad detection under the room's actual lighting;
  - fly one `go_xyz_speed_mid` route inside the agreed flight box, recording all video for the replay fallback.
- [ ] Charge every Tello battery overnight and label them.

**Thursday**
- [ ] About 09:00: drone go/no-go. Go only if both are true: (a) Tello frames reached Grok triage while the dog and internet stayed connected; (b) one supervised route flew inside the flight box.
- [ ] Second dog slot: timed runs for the scoreboard, plus final video footage.
- [ ] Attend Ralph Johnson's 10:00 talk (Voice) and Luca Bianchi's 11:00 talk (Grok Bot). Optionally add the Bot as the shift-report deliverer.
- [ ] 13:00: freeze features. Rehearse the jury's "new case" with a teammate staging unseen objects.
- [ ] 14:00–15:30: cut the 2-minute video:

  | Time | Content |
  |---|---|
  | 0:00–0:15 | The problem |
  | 0:15–1:20 | One uncut incident with an on-screen timer |
  | 1:20–1:45 | The baseline table |
  | 1:45–2:00 | The voice console and the shift report |

- [ ] Before 16:00: submit the README with the baselines, the latency table and known limitations. Credit sources, including Asylon as prior art.
- [ ] Keep a phone hotspot as an internet fallback for the live demo.

### Questions to ask museum staff today

**About the dogs**
- Which dog can Track D use, the Go2 or the Go1?
- Is the Go2 an AIR, PRO or EDU?
- What firmware is it on? Can you give us the AES key or log in to the Unitree account it is bound to?
- How many 30-minute slots will Track D get, and can we book them now?
- Who holds the physical remote, and must the Unitree phone app be disconnected while we control the dog?
- Is a dog simulator being provided, as the brief says "to be confirmed"?

**About the drones (Tello EDU)**
- How many Tello EDUs are there, and can Track D book one, ideally with a spare?
- How many batteries are there, and is there a multi-battery charging hub?
- Are prop guards fitted?
- Are mission pads (m1–m8) in the kit? If not, may we print them, and may we tape them to the floor?
- Which room or flight box is allowed, at what maximum height, and with what clearance from exhibits and visitors?
- Can the lighting in that room be kept bright for the vision positioning and pad detection?
- Has the drone's firmware been updated, and has anyone switched it to station mode? We need it in AP mode for video.
- May we use a USB Wi-Fi adapter or Ethernet, given that the drone creates its own Wi-Fi network?

**About the venue**
- Which rooms and floor plan are available for Track D?
- Can we tape a dock and zone markers on the floor?
- What is the lighting like?
- Is there a separate Wi-Fi network or band for robots, and is internet access available there?
- Are visitors present during slots, given that frames go to a cloud API?

**About the track and jury**
- Who is the Riello mentor, and which of the five metrics matters most to Riello?
- Will the jury measure "arrival" as the dog reaching its position, or as the target appearing in the dog's frame?
- What kind of "new case" will the jury stage?
- Is calling a team member's phone through Twilio acceptable as the "test number"?
- Will the common evaluation rubric be published before Thursday?
