# Track D "Robot Dog Patrol" (Riello): winning strategy, drone add-on, and the Grok capabilities that make Grok essential

> Research date: 2026-11-04 (day 1 of the hackathon). Local sources: `/Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI Hackathon/hackathon info.md` (scraped from https://pavia.grokbot.it/tracks and /rules), `slides/Grok-Hackathon-kickoff.txt`, `robot-docs/README.md`. Web sources: docs.x.ai, x.ai, github.com/xai-org/xai-cookbook, docs.frigate.video, DJITelloPy, plus hackathon and industry write-ups.

## Q1. What exactly does Track D require (minimum demo, stretch goals, scope, judging), what rules apply to all tracks, who is on the jury, and what hardware is reserved?

### Takeaway
Track D asks for one end-to-end flow, **event → mission → check → alert**, with a control console and a complete log. It is judged on five measurable things: event-to-arrival time, staged anomalies verified correctly, false alarms forwarded, alert clarity and log completeness. Dog time is scarce: there are two Unitree dogs, 30-minute slots with staff, "1–2 teams" on the track, and 1–2 dog slots reserved for Track A. A simulated-dog fallback is explicitly allowed.

### Cited Findings
**Track D brief (verbatim substance)** — [hackathon info.md, Track D](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md) (source: https://pavia.grokbot.it/tracks)
- One-sentence goal: "Can a robot dog become the patrol that goes to check when a camera sees something strange?" Hardware: **Dog, smartphones as cameras**. On the kickoff slide, Track D's tags are "Dog, Phone cameras" ([slides/Grok-Hackathon-kickoff.txt, slide 11](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/slides/Grok-Hackathon-kickoff.txt)).
- Context: a company with a site of about 55,000 m² wants to pair a robot dog with its video surveillance: "programmable patrols, targeted checks when a camera flags an anomaly, control from the guardhouse, a PC or a smartphone, and automatic alerts to security or the caretaker. The museum rooms stand in for the site."
- What to build: "the **event → mission → check → alert** flow, with a control console and a log of everything that happens."
- Inputs: the museum's robot dog (in slots); "2–3 smartphones or laptops used as surveillance cameras, plus the dog's camera if it has one"; a floor plan of the available rooms; a dog simulator "if the model allows it (to be confirmed)". Public resources: `unitree_sdk2_python` and `go2_ros2_sdk`; camera events with **Frigate**; alert calls with the xAI **voice-agent-phone** example (needs Twilio).
- Use of Grok: "A natural-language console, typed or with Grok Voice ('patrol room 2'); assess the camera event and decide whether to send the dog; describe what the dog frames; compose the alert, also as a voice call."
- **Minimum demo:** (1) a scheduled patrol between 3 spots in a room; (2) a smartphone used as a camera detects a staged anomaly ("a person in a restricted area, an abandoned object") and Grok sends the dog to the spot; (3) the dog frames the scene, Grok describes it, and an alert goes out to a test number. Every event is logged. "Without a slot on the dog, the same flow runs with a simulated dog."
- **Stretch goals:** a console on the smartphone; prioritising several events at once; recognising false alarms; an end-of-shift report.
- **Out of scope:** "sirens, deterrents or other modules on the dog; footage of the real site; real calls to security or police; autonomous navigation over 55,000 m²."
- **How it's judged:** "time between the event and the dog's arrival; staged anomalies verified correctly; false alarms forwarded; clarity of the alert; completeness of the log."
- **Seats:** "Robot dog for 1–2 teams, only with museum staff present; 1–2 dog slots are reserved for Track A. Mentor: someone from Riello (to be confirmed)."

**Track A overlap (competition for the dog)** — [hackathon info.md, Track A](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md)
- Track A gets "1–2 slots on the robot dog to search the museum rooms (to be confirmed)". Its out-of-scope list includes "autonomous dog navigation in unprepared spaces".

**Hardware** — [hackathon info.md, Hardware](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md)
- Two dogs, both Unitree: a **Go1** (`unitree_legged_sdk` v3.8.x) and a **Go2** (`unitree_sdk2_python`, which needs the EDU variant for full access; `go2_ros2_sdk`; `go2_webrtc_connect`, which also works on AIR/PRO).
- "Also: a few drones." Drone models are not listed. Arms and the dog run in 30-minute slots, "always with staff alongside. Outside your slots you work in simulation or on video."
- Go2 WebRTC route: the front camera is at `examples/go2/video/camera_stream`, two-way audio through the dog's speaker and mic at `examples/go2/audio/live_audio`, and walking at `.../sportmode`. ⚠️ "Go2 firmware ≥ 1.1.15 needs a per-device AES-128 key" (`fetch_aes_key.py`, using the Unitree account the dog is bound to) — [robot-docs/README.md](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/robot-docs/README.md). The same file says the Go1 has no easy two-way audio or camera from a laptop.
- Venue: 1,800 m² across three pavilions ([slides, slide 4](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/slides/Grok-Hackathon-kickoff.txt)).

**Rules for all tracks** — [hackathon info.md, Rules](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md); [slides, slide 12](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/slides/Grok-Hackathon-kickoff.txt)
1. Grok (API, Voice or Bot) "must be essential to how the solution works, not decorative."
2. The minimum demo is shown Thursday by 16:00, **on a new case chosen by the jury**.
3. Deliver a repo with a README, the data used, **at least one result measured against a baseline**, and known limitations.
4. Submit a **~2-minute video demo by Thu 16:00** (all tracks). Pitches and evaluation run 16:00–19:00; awards at 21:00.
5. Only public, synthetic or company-provided data. "Credit your sources."
- Code of conduct: "Robots, arms and drones only in your slot and always with staff"; "The exhibits are historic." Closing line: "Show something on Thursday that didn't work when you started."
- The common evaluation rubric is "To be announced". The field is 16 teams and 65 participants across 10 tracks (portal, 3 Nov).

**Jury** — [hackathon info.md, Jury](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md)
- Luca Bianchi (lead organiser, CTIO at MESA Group, Grok Bot and Cursor ambassador; gives the Thu 11:00 talk "Using Grok Bots for everything"); Lorenzo Cerri; Alessandro Rano; Alberto Giusti; Claudio Peroni (Track A mentor); **Ralph Johnson** (Field Engineer @ SpaceXAI; Thu 10:00 talk on Grok models, API, Voice and Bots); Federico Pellegrini. No Riello person is named on the jury; the Riello mentor is "to be confirmed".

### Inferences
- The five metrics are all **operational KPIs of a security control room**: latency, true positives, false positives, communication quality and auditability. Riello is evaluating whether this could become a product. A team that **reports those five numbers on a scoreboard** in the console and the README speaks the proposer's language directly.
- "New case chosen by the jury" for Track D most likely means the jury stages a different anomaly, location or object than the one rehearsed. Hard-coded single-spot demos are therefore risky. The system needs zone-to-waypoint mapping for **every** camera zone and must handle object or person types it has not seen before. Grok vision's open-vocabulary reasoning is the natural answer here.
- Dog time is the binding constraint. Expect 1–3 slots of 30 minutes in total, shared with Track A. The plan must be **simulation-first** (the brief allows a simulated dog), and hardware slots should be used only to (a) calibrate waypoints and walking speed, (b) record the dog-camera footage for the video, and (c) run the final timed trials.
- The Go2 is the realistic dog: camera and audio over WebRTC with no jailbreak. Ask staff on Wed for the firmware version and the Unitree account (the AES key), or the first slot can be lost to the handshake.

### Gaps
- The common rubric is not published ("To be announced"). Its weighting against the track metrics is unknown.
- Whether a Go2 simulator is provided ("to be confirmed") and whether the Go2 is EDU (low-level DDS access) is unknown; ask staff.
- Which drones are on site, and whether drones are bookable by Track D teams at all, is not documented anywhere.
- I could not confirm which Riello entity proposes the track (Riello Group heating vs Riello Elettronica/UPS), or who the Riello mentor is.

---

## Q2. How does each Track D judging metric map to concrete design choices?

### Takeaway
Keep Grok **off the motion loop and on the decision loop**. Pre-compute camera-zone → waypoint routes so the dog starts walking within about a second of a "dispatch" decision. Use a fast Grok vision triage with a structured output schema. Put a **two-stage verification gate** (fixed-camera triage, then dog-camera confirmation) in front of any alert. Write every step to an append-only, timestamped log that also feeds a live KPI scoreboard.

### Cited Findings
- The metrics: "time between the event and the dog's arrival; staged anomalies verified correctly; false alarms forwarded; clarity of the alert; completeness of the log" — [hackathon info.md, Track D](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md).
- Frigate publishes `frigate/events` per tracked object with `type` = `new`/`update`/`end`, plus `label`, `score`/`top_score`, `box`, `current_zones`/`entered_zones`, `snapshot`, `stationary` and `start_time`/`end_time`. It also publishes `frigate/reviews` (severity `detection`/`alert`) and a JPEG per camera and object at `frigate/<camera_name>/<object_name>/snapshot` — [Frigate MQTT docs](https://docs.frigate.video/integrations/mqtt/).
- Grok image input: JPG/JPEG or PNG, max 20 MiB per image; text and images in any order. The `detail` parameter appears in examples (`"high"`) but its values and per-image token cost are not documented — [docs.x.ai image understanding](https://docs.x.ai/docs/guides/image-understanding).
- Structured outputs: `chat.parse(PydanticModel)` returns `(response, parsed)`. `response_format` supports `json_schema`, and enums, `const` and date-time formats are enforced. "With tools defined, tool call arguments are always generated to match the tool's input schema, with `strict` implicitly set to true" — [docs.x.ai structured outputs](https://docs.x.ai/docs/guides/structured-outputs).
- Function calling: `tool_choice` accepts `"auto"`, `"required"`, `"none"` or a forced function; parallel calls are on by default (`parallel_tool_calls: false` turns them off) — [docs.x.ai function calling](https://docs.x.ai/docs/guides/function-calling).
- Industry analogue: Asylon's DroneDog (on Boston Dynamics Spot) "can follow preprogrammed routes or respond to alarms using AI detection". Asylon pairs it with aerial drones and reports a combined 250,000+ automated missions (vendor claim) — [SecurityInfoWatch](https://www.securityinfowatch.com/perimeter-security/robotics/news/55397352/asylon-highlights-automated-ground-security-with-dronedog); [TechCrunch](https://techcrunch.com/2025/07/22/robot-guard-dogs-help-asylon-raise-a-26m-series-b/). GXO reports more than 12,000 alarm-response and patrol missions with Asylon — [GXO release](https://investors.gxo.com/news-releases/news-release-details/gxo-enhances-security-and-safety-high-tech-dronedog-and-aerial).
- An LLM-agent dog patrol (Dimensional DimOS): robot skills are Python methods with a `@skill` decorator, exposed as tool schemas. YOLO runs per frame, visual servoing at 10 Hz, and the agent calls `trigger_alert` via webhook, SMS or a simulated call. The source is promotional, with no measured latency or failure data — [DEV / Dimensional](https://dev.to/dimensional/made-a-robot-dog-run-security-patrols-at-our-sf-office-in-one-prompt-3pbe).

### Inferences (design map)
| Metric | Design choices that move it |
|---|---|
| **Time event → dog arrival** | (1) Detection on the phone side runs locally and fast: Frigate or YOLO on an RTSP/MJPEG stream from each phone, with zones drawn on the floor plan, so there is no LLM in the detection loop. (2) A **pre-computed route table** `zone_id → [waypoints]` per camera, measured during the first dog slot; dispatch is just "execute route R". (3) The triage call uses a small JPEG crop plus a full-frame thumbnail, a non-reasoning or low-effort model, and a structured output schema. Measure p50/p95 on the venue Wi-Fi; latency is undocumented. (4) **Optimistic dispatch** as an option: start the dog toward the zone the moment a high-score local detection fires and Grok triage runs in parallel. Grok can then recall the dog (`recall_dog`) if it judges a false alarm. This trades wasted walks for latency. Report both modes. (5) Log `t_event`, `t_triage_done`, `t_dispatch`, `t_arrival` (arrival = route complete, or the target is in the dog's frame) and show the delta live. |
| **Staged anomalies verified correctly** | A two-stage check. (a) Fixed-camera triage: Grok gets the frame plus **zone context** (restricted area? opening hours? allowed objects such as exhibits and staff carts?) and returns `{anomaly_type, confidence, rationale, recommended_action}`. (b) On arrival, the dog camera frame plus the **reference frame of that patrol point** (captured during the scheduled patrol) go to Grok for a before/after comparison: "what changed, is the person or object still there?" This also covers "abandoned object" cases the camera saw only briefly. Use open-vocabulary prompting so the jury's new object type still works. |
| **False alarms forwarded** (lower is better) | Alert only after the stage-(b) confirmation, or after a stage-(a) confidence ≥ threshold AND persistence across N frames or seconds. Grok "recognising false alarms" is a stated stretch goal; build a labelled benign set (staff in vest, a poster or photo of a person, a museum mannequin or screen showing a face, a person passing outside the zone line, a bag held by its owner). Count forwarded false alarms as the headline number. |
| **Clarity of the alert** | A fixed alert schema via structured outputs: `what` (one sentence), `where` (room + spot name from the floor plan + map thumbnail), `when`, `evidence` (camera snapshot + dog snapshot), `confidence`, `recommended_action`, `ack_required`. Render it three ways: an SMS/console card, a ≤20-second **Italian** voice call (Riello is Italian; Grok Voice lists `it`), and the log entry. The voice call asks for acknowledgement through a tool (`acknowledge_alert`), which closes the loop and logs `t_ack`. Ask the Riello mentor to rate alert clarity on a 1–5 scale for the README. |
| **Completeness of the log** | An append-only JSONL or SQLite event store keyed by `incident_id`, with every state transition (`detected → triaged → dispatched → arrived → verified/dismissed → alerted → acknowledged`), timestamps, camera/dog/drone IDs, image paths, model ID, prompt version, Grok raw JSON output and tool calls, and operator commands (typed and voice transcripts). Make the log **replayable** in the console and generate the **end-of-shift report** (stretch goal) from it with Grok. Show a "log completeness" check: every incident has every required field. |

- Minimum-demo step 1 (scheduled patrol between 3 spots) needs no SLAM. Open-loop `sportmode` moves calibrated in a slot, or the `go2_ros2_sdk` Nav2 stack if time allows, are enough for 3 spots in one room. The out-of-scope list explicitly excludes large-area autonomy, so judges will not penalise a taped-floor, calibrated route.
- Safety in the motion layer: a console "STOP" button and a voice "stop" both map to a stop command independent of Grok. Staff are present anyway, but showing it signals maturity.

### Gaps
- No documented Grok vision latency or per-image token cost; both must be measured on site. Run a quick benchmark Wed evening: 20 triage calls per candidate model.
- Go2 walking speed and WebRTC camera latency on the museum Wi-Fi are not documented in the local SDK index; measure during the first slot.
- Whether the jury measures "arrival" as dog-in-position or target-in-frame is not specified; define it explicitly in the README and on the scoreboard.

---

## Q3. Does adding a drone fit the brief, and what is the over-scoping risk?

### Takeaway
A drone is **not prohibited but not provided for Track D**. The brief's hardware is "Dog, smartphones as cameras", drones appear only in the general hardware list, and the code of conduct restricts drones to supervised slots. A drone does not improve the headline metric (the dog's arrival time). Its real value is **coverage of fixed-camera blind spots** and **faster first visual confirmation**. Treat it as a gated stretch module behind the same "sensor" interface, never on the critical path of the minimum demo.

### Cited Findings
- Track D hardware: "Dog, smartphones as cameras"; inputs: "2–3 smartphones or laptops used as surveillance cameras, plus the dog's camera if it has one" — [hackathon info.md, Track D](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md). The slide tag is "Dog, Phone cameras" ([slides, slide 11](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/slides/Grok-Hackathon-kickoff.txt)).
- The out-of-scope list ("sirens, deterrents or other modules **on the dog**; footage of the real site; real calls to security or police; autonomous navigation over 55,000 m²") does not mention drones — [hackathon info.md](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md).
- Drones on site: "Also: a few drones"; Wed 10:00 talk "Intro to cobots, dogs, drones and rovers"; code of conduct: "Robots, arms and drones only in your slot and always with staff"; "The exhibits are historic. Handle with care" — [hackathon info.md](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md); [slides, slides 6 and 13](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/slides/Grok-Hackathon-kickoff.txt).
- Industry precedent for dog + drone pairing: Asylon sells DroneDog (ground) alongside its Guardian (formerly DroneSentry) aerial drones with a base station for autonomous landing and battery swapping — [SecurityInfoWatch](https://www.securityinfowatch.com/perimeter-security/robotics/news/55397352/asylon-highlights-automated-ground-security-with-dronedog); [UAS Vision](https://uasvision.com/?p=102592); [GXO](https://investors.gxo.com/news-releases/news-release-details/gxo-enhances-security-and-safety-high-tech-dronedog-and-aerial).
- If the drone is a DJI Tello (a common hackathon drone; the actual model is unconfirmed): DJITelloPy supports video streaming, takeoff/land and move commands. "Mission pad detection and navigation is only supported by the Tello EDU"; "Connecting to an existing wifi network is only supported by the Tello EDU" and "When connected to an existing wifi network video streaming is not available" — [DJITelloPy](https://github.com/damiafuentes/DJITelloPy).

### Inferences
- **Fit:** the drone fits the *spirit* of the brief. A real 55,000 m² site has blind spots and Asylon proves the dog + drone pairing commercially. But it is outside the *letter* of the provided inputs. Judges score the five metrics; none rewards an extra sensor per se. The drone pays off only if it measurably improves "staged anomalies verified correctly" (blind-spot coverage) or "false alarms forwarded" (a fast aerial second opinion), and that improvement is shown in the baseline table.
- **Risks (high):** (1) slot availability: a drone needs its own supervised slot on top of the scarce dog slots; (2) indoor flight in a museum with historic exhibits, where staff may refuse or limit it; (3) networking: a non-EDU Tello is its own Wi-Fi AP, so the laptop controlling it loses the venue Wi-Fi and the internet needed for Grok, unless you add a second Wi-Fi adapter or USB tether. On an EDU in station mode, video is unavailable per DJITelloPy; (4) short battery and drift indoors without mission pads; (5) demo fragility on a jury-chosen case.
- **Recommendation:** build the core (phones + dog + Grok) to win on its own. Define a `Sensor` abstraction (`get_frame()`, `goto(zone)`) so the drone is a drop-in. Go/no-go gate: if by **Thu ~09:00** the drone has not (a) streamed frames into the triage pipeline and (b) flown one route under staff supervision, cut it from the live demo and at most show recorded footage in the 2-minute video, labelled honestly.
- **Lower-risk "drone" variants:** (a) the drone as a **"tethered/perched aerial camera"**: take off, hover or land at a vantage point (e.g. on top of a cabinet) to cover a blind spot, giving a static wide view rather than navigation; (b) the drone **only for the "verify first" leg**: it reaches the zone faster, Grok checks the frame, and the dog is dispatched only if confirmed. This directly attacks false alarms but adds latency to the dog's arrival, so present it as a configurable policy and measure it.
- Over-scoping perception: with only 1–2 teams on Track D, the competition is thin. **Reliability on the jury's new case** will likely decide the track prize more than breadth. A failed drone flight in front of the jury costs more than a missing drone.

### Gaps
- Drone models, count, battery and indoor-flight permissions at Ctrl+Alt Museum are undocumented; ask at the hardware tour and the Wed 10:00 talk.
- No source on how the Track D judges (or Riello) view extra hardware; the common rubric is unpublished.

---

## Q4. Which Grok features best support each function (triage, dispatch, dog-camera description, NL/voice console, voice alert calls, end-of-shift report)? Exact APIs, models, latency, pricing, rate limits.

### Takeaway
Use **Grok 4.x chat with image input + structured outputs** for triage and verification, **function calling** for dispatch (the decision of *which sensor to task* is where Grok is essential), the **Grok Voice real-time agent** (`wss://api.x.ai/v1/realtime`, function tools, Italian, G.711 μ-law telephony codec) for both the voice console and the Twilio alert call, and `xai-sdk-python` throughout. Grok Bot has **no documented API**: use it off the critical path, as the caretaker's teammate or reporter. Grok Imagine is best used to **generate synthetic test images** for the baseline set, which the data rule explicitly allows. Latency is undocumented everywhere, so measure it.

### Cited Findings
**Models, pricing, rate limits** — [docs.x.ai models/pricing](https://docs.x.ai/docs/models); [docs.x.ai rate limits](https://docs.x.ai/docs/key-information/consumption-and-rate-limits)
- `grok-4.7`: 500k context; $2.00 input / $0.50 cached / $6.00 output per 1M tokens (<200k prompt). `grok-4.6` and `grok-4.5` are similar. `grok-4.3`, `grok-4.20-0309-reasoning` and `grok-4.20-0309-non-reasoning`: 1M context, $1.25 / $0.20 / $2.50. `grok-build-0.1`: $1.00 / $0.20 / $2.00. `grok-4.20-multi-agent-0309`: $1.25 / $2.50. Requests at or above 200k prompt tokens are billed at the higher rate for all tokens.
- Image input: JPG/PNG, max 20 MiB, "no limit on the number of images". The pricing page does not state which models accept images. The image-understanding guide only shows `grok-4.7` — [docs.x.ai image understanding](https://docs.x.ai/docs/guides/image-understanding).
- Rate limits are listed as RPS/TPM by tier (RPS = RPM/48, min 2). For `grok-4.7`/`4.6`/`4.5`: T0 150 RPS / 50M TPM … T4 500 / 100M. For `grok-4.3` and the 4.20 variants: T0 37 / 10M. Tiers are based on spend since 1 Jan 2026 (T1 $50, T2 $250, T3 $1,000, T4 $5,000). Exceeding a limit returns HTTP 429; the docs use exponential backoff (2^attempt s, max 5 tries). Check limits at console.x.ai → Models.
- Voice: Speech-to-Speech `grok-voice-3.0` costs **$0.08/min ($4.80/hr)** plus $0.004 per text input (`grok-voice-2.0` same price, deprecated). STT $0.10/hr REST, $0.20/hr streaming; TTS $15 per 1M characters. Voice sessions: `grok-voice-3.0` T0 allows **10 concurrent sessions** (T4 200); TTS 50 RPS at T0; STT 10 RPS at T0.
- Imagine: `grok-imagine-image` $0.02/image, `grok-imagine-image-2.0` $0.04/image; video $0.02–0.08/s; image generation at T0 is 6 RPS.

**Function calling + structured outputs** — [function calling](https://docs.x.ai/docs/guides/function-calling); [structured outputs](https://docs.x.ai/docs/guides/structured-outputs)
- Tools are defined with `name`, `description` and a JSON-Schema `parameters` object (root must be an object). `tool_choice`: `"auto"` | `"required"` | `"none"` | a forced function. Parallel tool calls are on by default. The docs cite up to 350 tools. In `xai_sdk`: `from xai_sdk.chat import user, image, tool, tool_result`; `client.chat.create(model=..., tools=[...])`; `response.tool_calls`; `chat.append(tool_result(...))`. Built-in server tools `web_search()` and `x_search()` come from `xai_sdk.tools`.
- Structured outputs: `chat.parse(Model)` → `(response, parsed)`, or `response_format=Model` with streaming. Supported: enum, const, anyOf/oneOf, `$defs`, formats such as date-time and uuid. `additionalProperties` defaults to false. "Structured outputs with tools is only available for supported Grok 4 family models." Tool-call arguments are implicitly strict.
- Image call pattern: `chat.append(user("…", image(image_url=..., detail="high")))`, then `chat.sample()` — [image understanding](https://docs.x.ai/docs/guides/image-understanding). The guide also advises against storing response history server-side when sending images.

**Grok Voice real-time agent** — [docs.x.ai voice overview](https://docs.x.ai/developers/model-capabilities/audio/voice); [docs.x.ai voice agent guide](https://docs.x.ai/docs/guides/voice/agent)
- Endpoint: `wss://api.x.ai/v1/realtime?model=grok-voice-latest` (Bearer `XAI_API_KEY`; ephemeral tokens for browser clients). Configure with `session.update`: `voice` (default `eve`), `instructions`, `turn_detection: {"type":"server_vad"}`, `tools`. Audio arrives in `response.output_audio.delta`. Claims "sub-second latency", with no measured figures.
- Custom function tools: `{"type":"function","name","description","parameters"}` in `tools`. The server emits `response.function_call_arguments.done` (`name`, `call_id`, `arguments`). The client replies with `conversation.item.create` (`function_call_output`, `call_id`, `output`), then **one** `response.create` after all parallel outputs.
- Codecs: `audio/pcm` (default 24 kHz; 8–48 kHz), **`audio/pcmu` / `audio/pcma` (G.711, 8 kHz, telephony)**, `audio/opus`. Languages auto-detected, including **Italian (`it`)**. `audio.input.transcription.language_hint` biases transcription.
- Custom voices can be cloned from a reference clip of up to 120 s. Zero Data Retention option; SOC 2 Type II, GDPR claims.

**voice-agent-phone (Twilio)** — [xai-cookbook voice-agent-phone](https://github.com/xai-org/xai-cookbook/tree/main/examples/voice-agent-phone/xai)
- A Node/TypeScript Express server. Twilio's inbound webhook hits `/twiml`, which returns `<Stream/>`; a Media Stream websocket bridges call audio to the xAI Realtime API. **Outbound calls are supported**: `npm run outbound` with `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `TARGET_PHONE_NUMBER`; "the AI agent initiates the conversation". Needs `XAI_API_KEY`, `HOSTNAME` (an ngrok domain; `ngrok http 3000`). The README has no instructions for adding tools and warns it is "NOT PRODUCTION-READY WITHOUT ADDITIONAL HARDENING".
- Other cookbook voice examples: `examples/voice-agent-web` (React client; Python backend at `examples/voice-agent-web/xai/backend-python`), `examples/voice-agent-webrtc`, `examples/voice-agent-mobile/{swift,kotlin}`, `examples/live-interpreter`. A related pattern is `examples/refund-agent-human-approval` (an agent that waits for human approval) — [xai-cookbook](https://github.com/xai-org/xai-cookbook).

**Grok Bot** — [x.ai/news/introducing-grok-bot](https://x.ai/news/introducing-grok-bot) (dated Aug 11, 2026)
- "Always-on agents" that "share a computer of their own in the cloud", sign into existing tools and work in "apps, inboxes, and websites", including "platforms with no clean API or MCP". You can message a Bot from phone or desktop. Bots can message each other, learn a workflow as a "routine", and "keep working 24/7". Beta for SuperGrok tiers and Cursor Pro/Pro+/Ultra/Teams. Separate usage; no price given. **No developer API or messaging-platform integration is documented** on the page.

**Hackathon tool list** — [hackathon info.md, Tools](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md): Grok API ("Grok 4.7 … function calling and structured outputs"), search and code tools, Grok Voice, Grok Imagine, Grok Build, Grok Bot, Cursor. The track references `xai-sdk-python`, `voice-agent-web` and `voice-agent-phone`.

### Inferences (feature → function map)
| Function | Grok feature / model | Why it is essential, not decorative |
|---|---|---|
| **Event triage** from phone-camera frames | `grok-4.7` chat + `image()` + `chat.parse(TriageResult)`. Benchmark against `grok-4.20-0309-non-reasoning` / `grok-4.3` for speed (image support on those is unconfirmed; test it). | Decides *whether* something is an anomaly given zone rules, time of day and context (staff vs intruder, exhibit vs abandoned bag). A rule-based detector cannot do this; it is the false-alarm metric. |
| **Dispatch decision** | Same chat call with tools: `dispatch_dog(route_id, priority)`, `task_camera(cam_id)`, `task_drone(zone)`, `hold_and_watch(seconds)`, `dismiss(reason)`, `escalate_alert(level)`; `tool_choice="required"`. | Grok chooses *which sensor* to task and *in what order* when several events compete (stretch goal "prioritising several events at once"). This is the agentic core. |
| **Scene description / verification from the dog camera** | `grok-4.7` with two images (reference frame + live dog frame) → `VerificationResult{confirmed, what_changed, description_it, confidence}`. | Before/after reasoning on unseen objects is what "staged anomalies verified correctly" needs on a jury-chosen case. |
| **NL / voice console** ("pattuglia la sala 2") | Grok Voice realtime (`grok-voice-latest`) with function tools mapping to the same command API as the typed console (`start_patrol(room)`, `go_to(spot)`, `status()`, `stop()`). Start from `voice-agent-web` (browser) or a phone browser for the "console on smartphone" stretch goal. | Directly named in the brief. Italian supported. |
| **Voice alert call** | `voice-agent-phone` outbound mode: Twilio to a **test number** (real police or security calls are out of scope), G.711 `audio/pcmu`. Inject the structured alert into `instructions`; add the tool `acknowledge_alert(incident_id)` and possibly `request_redispatch()`. | The guard can ask follow-ups ("is the person still there?"), and the agent answers from the log. Two-way, not a TTS blast. |
| **End-of-shift report** | `grok-4.7` over the JSONL log (well within the 500k context) → `chat.parse(ShiftReport)` rendered to markdown or PDF. Optionally have **Grok Bot** deliver or post it and answer follow-ups from the caretaker's phone. | Turns the log into the manager-facing artefact; Grok Bot ties into Luca Bianchi's talk. |
| **Synthetic test data** | `grok-imagine-image` ($0.02/image) to generate benign and anomalous variants of the museum rooms for the baseline set (clearly labelled synthetic). | Allowed by rule 5; scales the evaluation beyond the few staged cases. |

- **Cost is negligible.** At $2/M input tokens, even a few hundred triage calls cost cents to a few dollars (assuming low-thousands of tokens per image; per-image token cost is undocumented). Voice at $0.08/min means a 1-minute alert call costs $0.08. API credits are provided.
- **Rate limits are a non-issue** at T0 for chat (150 RPS for grok-4.7). The one real cap is **10 concurrent voice sessions at T0**, which is fine for one console plus one alert call.
- **Latency plan:** the docs give no numbers, so measure p50/p95 for (a) a triage call with one image, (b) a triage call with two images, (c) voice first-audio after the end of speech. Pick the model per stage from data and publish that table in the README; it doubles as a baseline-style measurement.
- Ralph Johnson (xAI field engineer, juror) will likely notice correct use of Voice tool calls (`response.function_call_arguments.done` → `function_call_output` → `response.create`) and of structured outputs. Luca Bianchi will likely notice a Grok Bot integration.

### Gaps
- No documented latency for Grok vision or for Voice (only "sub-second" marketing).
- Which non-4.7 models accept images is not stated on the pages I fetched.
- Per-image token accounting and the `detail` parameter values are undocumented.
- Grok Bot: no API, webhook or chat-platform integration is documented, so wiring it into the live loop is unverified. Ask Luca Bianchi or Ralph Johnson at the Thu talks.
- Whether voice-agent-phone supports adding custom function tools out of the box is not stated in its README; the underlying Realtime API supports them.

---

## Q5. What would a strong "baseline comparison" look like?

### Takeaway
Report **two** baselines tied to the judged metrics. (1) **Rule-based triage vs Grok triage** on a labelled set of staged and synthetic events, scored on false alarms forwarded and anomalies verified. This is the cleanest proof that Grok is essential. (2) **Scheduled patrol only vs event-triggered dispatch**, scored on time from event to the dog's eyes on the scene. Add a third (fixed cameras vs fixed + drone blind-spot coverage) only if the drone works.

### Cited Findings
- Rule: "at least one result measured against a baseline" in the repo — [hackathon info.md, Rules](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md).
- Other tracks show how the organisers phrase baselines: Track B "better than the deterministic baseline"; Track 03 "a fix only counts if it improves a test without obvious regressions"; Track 05 "time and errors of the person with and without the tutorial" — [hackathon info.md](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md).
- Track A's measures, which a Track D team should mirror in form: "objects found out of 10 new jury requests; average time to find them; false alarms" — [hackathon info.md, Track A](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md).
- Frigate exposes `label`, `score`, `current_zones`/`entered_zones` and `stationary` per object, which is a natural deterministic baseline: "alert if label ∈ {person} and zone = restricted, or label ∈ {backpack, suitcase} and stationary > T" — [Frigate MQTT](https://docs.frigate.video/integrations/mqtt/).

### Inferences
- **Baseline 1 (headline): triage quality.**
  - Dataset: about 30–40 events. Mix real staged clips recorded on the phones in the museum room (team members as "intruders", a bag left behind) and Grok-Imagine or hand-made synthetic frames. Include **hard negatives**: a team member wearing a "STAFF" vest or lanyard in the restricted zone during "opening hours", a person walking past the zone boundary, a printed photo of a person, a museum mannequin or exhibit, a reflection or screen, and a bag next to its owner.
  - Systems: (A) Frigate/YOLO rules only; (B) Grok triage on the camera frame; (C) Grok triage plus dog-camera verification (full pipeline).
  - Metrics: precision, recall, false alarms forwarded per N events, and median decision latency. Present as a table plus a confusion matrix. Expected story (inference, to be confirmed by data): rules have high recall but many false alarms; Grok cuts false alarms; dog verification cuts them further at a latency cost.
- **Baseline 2: response time.**
  - (A) Scheduled patrol only: the anomaly is found when the dog's loop passes it. Expected time ≈ half the loop period on average. Compute it analytically from the measured loop time and verify with 3 runs. (B) Event-triggered dispatch with pre-computed routes. (C) Optimistic dispatch (move first, triage in parallel). Metric: seconds from event to dog arrival (p50 and max).
- **Optional Baseline 3 (only if the drone works): coverage.** Grid the floor plan into cells. Count % of cells visible to fixed phones vs phones + drone vantage point; then place 5 staged anomalies in blind spots and count how many each configuration detects.
- **Jury case:** run the jury's new case through the live system **and** log it as a row in the evaluation table. This proves generalisation and gives the README a "held-out" result.
- Keep the evaluation **reproducible**: commit the labelled frames, the prompt versions and a `make eval` script that replays frames through the rules baseline and the Grok pipeline. Rule 5 is satisfied because the data is synthetic or staged by the team.

### Gaps
- No published reference numbers exist for this setting; all expected effects above are hypotheses to be measured.
- Whether the jury will accept partly synthetic (Imagine-generated) evaluation frames as meaningful is unknown; keep a real-staged-only subset and report it separately.

---

## Q6. What alternative framings use the same hardware but stand out more?

### Takeaway
The strongest framing is **"Grok is the night-shift operator"**: one agent that watches the event bus, chooses which sensor to send (dog, drone, another camera), verifies, calls the caretaker, and writes the shift report, with a live KPI scoreboard showing Riello's five metrics. The drone works best framed as **an active "second opinion" for blind spots**, not as a co-equal patrol robot.

### Cited Findings
- The brief's own language supports a control-room product: "control from the guardhouse, a PC or a smartphone, and automatic alerts to security or the caretaker" — [hackathon info.md, Track D](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md).
- Commercial security robotics combines AI detection with human monitoring ("enhanced with 24/7 AI and human monitoring"; the dog "can follow preprogrammed routes or respond to alarms") — [SecurityInfoWatch](https://www.securityinfowatch.com/perimeter-security/robotics/news/55397352/asylon-highlights-automated-ground-security-with-dronedog); [TechCrunch](https://techcrunch.com/2025/07/22/robot-guard-dogs-help-asylon-raise-a-26m-series-b/).
- Prompt-driven patrol agents with skills exposed as tools already exist (Dimensional DimOS), including starting a 2 am patrol "from the prompt itself" — [DEV / Dimensional](https://dev.to/dimensional/made-a-robot-dog-run-security-patrols-at-our-sf-office-in-one-prompt-3pbe).
- Grok Bot: always-on, own cloud computer, messaged from a phone, routines, multi-bot group chats — [x.ai Grok Bot](https://x.ai/news/introducing-grok-bot). Luca Bianchi (lead organiser and juror) gives the "Using Grok Bots for everything" talk — [hackathon info.md](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md).
- The xAI cookbook has a human-approval agent pattern (`refund-agent-human-approval`) — [xai-cookbook](https://github.com/xai-org/xai-cookbook).

### Inferences
1. **"Active perception" operator (recommended core story).** Grok does not just label frames; it **asks for more evidence**. Its tools include `look_again(cam, seconds)`, `send_dog(zone)`, `send_drone(zone)`, `zoom/crop(region)` and `ask_guard(question)`. The demo moment: an ambiguous event (a person half-visible at the zone edge). Grok says "uncertain, sending the dog", the dog arrives, Grok confirms, and the phone rings in Italian. This makes Grok indispensable and visibly reasoning.
2. **Drone as a "flying camera" for blind spots / first look.** Map which floor-plan cells the phones cannot see. When an event comes from the edge of coverage, or a door sensor or audio cue fires in a blind spot, Grok tasks the drone for a quick look, then decides whether the dog must go. Quantify with Baseline 3. Keep it optional (see Q3).
3. **Grok Bot as the caretaker's teammate (off the critical path).** The caretaker messages the Bot from a phone: "anything tonight?", "show me incident 3". The Bot reads the console web page or log and hands over the end-of-shift report each morning as a routine. Low latency demands, high jury affinity (Luca Bianchi). Risk: no documented API, so make it a demo add-on, not a dependency.
4. **Human-in-the-loop escalation ladder.** Grok proposes the action; above a risk threshold (e.g. calling a phone), the console asks for one-tap operator approval. This mirrors Track B's "every decision above a threshold goes through a person" and the cookbook approval pattern, and signals responsible design to an industrial proposer.
5. **"Riello control room" polish.** An Italian voice, an Italian alert script, a floor-plan map with live dog and drone position and incident pins, and a KPI header (event→arrival, verified, false alarms forwarded, alert ack time, log completeness %). The judges read the score from the screen.

### Gaps
- No evidence on what Riello specifically values beyond the brief; ask the Riello mentor on Wed which metric matters most.
- No documented way to give Grok Bot programmatic access to the patrol system.

---

## Q7. What patterns from winning robotics and AI hackathon projects should this team copy?

### Takeaway
Winners show a **visible, working transformation on a fresh input**, make the **AI's judgement explicit**, and **prove it with a number against a baseline**. They protect the demo with a recorded fallback, because live hardware and Wi-Fi fail. This hackathon formalises all of it: a jury-chosen new case, a required baseline, and a 2-minute video.

### Cited Findings
- "Pick a problem that a judge can understand in one sentence"; show behaviour, show why the AI component matters, keep execution visible; winners "need to make [their] judgment surface clear"; "every builder needs a visible transformation" — [DEV, "What AI hackathon winners actually have in common"](https://dev.to/jsb-securedme/what-ai-hackathon-winners-actually-have-in-common-1kla). This is an opinion piece inferred from 2025 OpenAI Open Model Hackathon winners, with no count of projects analysed.
- Demo advice: keep a recorded backup because venue Wi-Fi and live APIs fail; rehearse the live walkthrough repeatedly ("Walk through the live demo five times to find the points where it breaks"); structure: problem → 1–2 min live demo → stack and hardest problem → next steps — search summary of [AngelHack demo tips](https://angelhack.com/blog/10-tips-to-help-you-rock-your-next-hackathon-demo/), [Reskilll pitch guide](https://blogs.reskilll.com/hackathon-demo-presentation-tips-pitch-3-minutes-win-2026/) and [Hack Upstate tips](https://medium.com/@hackupstate/8-tips-to-a-successful-hackathon-demo-and-presentation-4d1ae83415ad). Generic sources.
- Robotics judging values understanding "how the robot was developed and works as a system", plus "performance, creativity, and technical execution" — search summary of [RoboCup Junior interview guideline](https://robocup-junior.github.io/onstage/resources/teams/interview_guideline.html) and robotics event pages. Indirect sources.
- MLH's hardware hackathon guide exists as a primary resource, but I could not read its content — [MLH Hardware Hackathon Guide](https://guide.mlh.com/hardware-hackathon-guide).
- Event-specific: "Show something on Thursday that didn't work when you started"; the minimum demo is "on a new case chosen by the jury"; video of about 2 minutes by Thu 16:00 — [hackathon info.md](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/hackathon%20info.md); [slides, slide 16](file:///Users/leonardo/Desktop/Projects/Hackathons/SpaxeXAI%20Hackathon/slides/Grok-Hackathon-kickoff.txt).
- I found **no** public hackathon winner combining a robot dog, a drone and an LLM security patrol. The closest items are a promotional DimOS dog-patrol post and the Hacksmith drone + robot dog security demo, which was not a competition — search results: [DEV / Dimensional](https://dev.to/dimensional/made-a-robot-dog-run-security-patrols-at-our-sf-office-in-one-prompt-3pbe), [DigiKey / Hacksmith](https://www.digikey.ca/en/maker/blogs/2024/the-hacksmith-the-ultimate-security-drone-system-at-h-e-r-c).

### Inferences (applied to Track D)
- **The one-sentence pitch:** "A camera sees something odd. Grok decides whether it matters, sends the dog (or drone) to look, confirms it, and calls the caretaker in Italian, all logged and measured."
- **The 2-minute video** (due 16:00, before pitches): 0:00–0:15 problem (55,000 m² site, guards cannot be everywhere); 0:15–1:20 one uncut incident (phone detects → Grok triage card → dog walks → dog-cam + Grok verification → phone rings with Italian alert → acknowledgement), with a visible on-screen timer; 1:20–1:45 the baseline table (rules vs Grok false alarms; patrol-only vs dispatch times); 1:45–2:00 the voice console command plus the end-of-shift report. Record it from the best dog slot on Wed night or Thu morning; do not leave it to Thu 15:00.
- **Live demo resilience:** a simulated-dog mode (allowed by the brief) behind the same API, so a dog fault becomes "switching to sim". Pre-warm the Twilio/ngrok tunnel. Keep a second hotspot because Grok calls need internet and the venue Wi-Fi is shared by about 100 people.
- **Schedule given scarce slots** (the team is reading this on Wed): Wed: book dog slots immediately; get the Go2 AES key and firmware; get phones streaming into Frigate or YOLO; Grok triage with structured outputs; event log and console. First dog slot: calibrate 3-spot patrol and routes, record reference frames, measure speed. Wed night: dispatch tools, voice-agent-phone outbound with the alert schema, eval set and baseline script. Thu morning: second dog slot for timed runs and video; drone go/no-go at about 09:00; attend Ralph's 10:00 talk (Voice) and Luca's 11:00 talk (Bots) for last-minute tips. Thu 13:00 freeze features; 14:00–15:30 video; 16:00 submit.

### Gaps
- No rigorous dataset of what wins hardware hackathons; the advice sources are generic or opinion pieces.
- The event's common rubric is unpublished, so the weighting of "originality" against "working demo" against "metrics" for Track D is unknown.
