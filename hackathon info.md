# Grok Hackathon at the Museum: Info

> Scraped on 2026-11-04 from https://pavia.grokbot.it/ (mirror: grok-hackathon-pavia.vercel.app): `/`, `/tracks`, `/rules`, plus the Luma event page https://luma.com/spacexai-z1ys.
> `/register` and the dashboard are behind login (Luma email + OTP), so they were not scraped.
> Raw text dumps are in `scraped/`.
> Kickoff slides (16 pages) are merged in: see the "Kickoff slides" section at the bottom. Original at `scraped/kickoff-slides.pdf`.

---

## TL;DR

- **What:** a 2-day hackathon. Pick a piece of hardware or an API, **connect it to Grok** (API, Grok Voice, or Grok Bot), and **by Thursday afternoon show something that didn't work when you started.**
- **When:** Wed 4 Nov 09:00 to Thu 5 Nov 21:00 (Rome time, CET). It runs overnight and the space stays open the whole time.
- **Where:** Ctrl+Alt Museum, a retro computing museum run by the nonprofit comPVter. Address: Via Gragnani 18, 27100 Pavia. It is 200 m from Pavia station, about 25 min by train from Milano Rogoredo.
- **Host:** SpaceXAI for Milan, Italy (Luma calendar "SpaceXSI for Milan"). Lead organiser: Luca Bianchi.
- **Teams:** 4 to 6 people (the site says 4–6; the Luma text says "1 to 4", but the site is the source of truth). Capacity is 100 people; 149 registered on Luma.
- **Provided:** API credits. Bring a laptop. **Wi-Fi: network `hackathon` / password `hackathon`.**
- **Field (from the slides, as of 3 Nov):** 16 teams, 65 participants, 10 tracks.
- **🚨 HARD DEADLINE, Thursday 16:00:**
  - **Every team submits a ~2-minute VIDEO DEMO** (all tracks; from the slides).
  - The minimum demo must be shown on a new case chosen by the jury (from the site).
  - Then pitches and evaluation run 16:00–19:00. Awards at 21:00.
- **Deliverable:** a repo with a README, the data used, **at least one result measured against a baseline**, and known limitations.
- **Evaluation criteria:** the common rubric is "To be announced". Each track adds its own specific criteria (below).

---

## Schedule (site version)

### Wednesday 4 November
| Time | What |
|---|---|
| 09:00 | Kick-off: hardware tour, find a team, start building |
| 10:00 | Intro to cobots, dogs, drones and rovers |
| 11:00 | Factory Academia |
| 18:30 | Riso Scotti meets the Hackathon |
| Overnight | Hacking continues through the night. Spaces open until Thu 21:00, free entry/exit |

### Thursday 5 November
| Time | What |
|---|---|
| 09:00–16:00 | **Build.** Ralph joins the tables after his 10:00 talk |
| 10:00 | Talk by **Ralph Johnson (SpaceXAI)**: Grok models, API, Grok Voice, Grok Bots |
| 11:00 | Meet the MESetAs: "Using Grok Bots for everything" (Luca Bianchi, CTIO at MESA Group) |
| **16:00** | **🎬 Video demo deadline, ~2 min (all tracks)** |
| **16:00–19:00** | **Project evaluation and pitches** |
| 21:00 | Awards ceremony |

> The Luma version differs slightly: Wed 18:00 "Ctrl+Alt Ecosystem presentation"; Thu 9:00 Ralph's talk; 21:00 "closing". Trust the site and the slides.
> FYI: **Startup Weekend Milano–Pavia** runs Nov 6–8, the morning after closing. You can do both.

---

## The tools (what "connect to Grok" means)

| Tool | What it is | Docs |
|---|---|---|
| **Grok API** | Grok 4.7 for chat, reasoning and code, with function calling and structured outputs | https://docs.x.ai/overview |
| **Search and code tools** | Built into the API: web search, X search, code execution, search over your own docs | https://docs.x.ai/developers/tools/overview |
| **Grok Voice** | Real-time speech-to-speech agents, TTS, STT | https://docs.x.ai/developers/model-capabilities/audio/voice |
| **Grok Imagine** | Generate and edit images and videos from text | https://docs.x.ai/developers/model-capabilities/imagine |
| **Grok Build** | A coding agent for the terminal, also usable in scripts and from editors | https://docs.x.ai/build/overview |
| **Grok Bot** | AI teammates with their own computer that work across your apps | https://x.ai/news/introducing-grok-bot |
| **Cursor** | A desktop and terminal coding agent with parallel cloud agents; Grok 4.7 is among its models | https://cursor.com/docs |

Referenced in the tracks: the official **`xai-sdk-python`** SDK, plus the xAI examples **`voice-agent-web`** (browser voice agent) and **`voice-agent-phone`** (phone calls, needs Twilio).

---

## Hardware available

- **Robot dogs** (exact models below)
- A **flight simulator** (three screens on a motion platform)
- **Cobots / robotic arms** (exact models below; the tracks refer to "Arm 1/2/3")
- A **driving simulator** (seat and steering wheel)
- Also: **a few drones**
- Cameras ("camera 1", "camera 2"), and smartphones used as cameras

"Real access, not a demo behind a rope." Museum staff handle the hardware and support builders.

### Exact models (confirmed by the organisers, received separately from the site)
"Documentation and APIs can be downloaded from the respective manufacturers' websites."

**Cobots (5):**
| Model | Maker | SDK / API to start from (my pointers, repos checked to exist) |
|---|---|---|
| xArm 5 | UFactory | Python: [xArm-Python-SDK](https://github.com/xArm-Developer/xArm-Python-SDK) · ROS2: [xarm_ros2](https://github.com/xArm-Developer/xarm_ros2) |
| UR3e | Universal Robots | Python/C++ RTDE: [ur_rtde](https://gitlab.com/sdurobotics/ur_rtde) · ROS2: [Universal_Robots_ROS2_Driver](https://github.com/UniversalRobots/Universal_Robots_ROS2_Driver) · URSim for simulation |
| UR5e | Universal Robots | Same as UR3e |
| CS63 | Elite Robots | [Elite_Robots_CS_SDK](https://github.com/Elite-Robots/Elite_Robots_CS_SDK) · [Elite_Robots_CS_ROS2_Driver](https://github.com/Elite-Robots/Elite_Robots_CS_ROS2_Driver) |
| CS66 | Elite Robots | Same as CS63 |

**Robot dogs (2), both Unitree:**
| Model | SDK to start from |
|---|---|
| Unitree **Go1** | [unitree_legged_sdk](https://github.com/unitreerobotics/unitree_legged_sdk) (Go1 uses v3.8.x). Note: `unitree_sdk2` does **not** support Go1 |
| Unitree **Go2** | [unitree_sdk2_python](https://github.com/unitreerobotics/unitree_sdk2_python) (needs the EDU variant for full low-level access) · ROS2: [go2_ros2_sdk](https://github.com/abizovnuralem/go2_ros2_sdk) · WebRTC (also works on AIR/PRO): [go2_webrtc_connect](https://github.com/legion1581/go2_webrtc_connect) |

> We don't know yet which arm is "Arm 1/2/3" in the tracks. Ask staff at kickoff, and ask whether the Go2 is the EDU variant.

### ⚠️ Hardware constraints (apply to all tracks)
- Arms and the dog are used in **30-minute slots**, **always with staff alongside**. Outside your slots you work in **simulation or on video**.
- **The arms have NO gripper.** They carry a 3D-printed tool with a **fork, a pusher and a tip**, and can **only lift objects placed on slotted trays**.

---

## Rules for all tracks

1. **Grok** (API, Voice or Bot) **must be essential** to how the solution works, not decorative.
2. **The minimum demo must be shown Thursday by 16:00, on a new case chosen by the jury.**
3. **Deliver a repo** with a README, the data used, **at least one result measured against a baseline**, and the known limitations.
3b. **Submit a ~2-minute video demo by Thursday 16:00** (from the slides).
4. Arms and dog: 30-minute slots with staff (see above).
5. **Only public data, synthetic data, or data the companies provided** for the event.

---

## Tracks overview (10 tracks)

Tracks A–D are proposed by companies; 01–06 are open tracks from the organisers. "These are proposed tracks. They may be refined before the event."

| # | Track | Proposer | Hardware | Team cap | One-liner |
|---|---|---|---|---|---|
| A | **CTRL+F: SEA** | SEA Vision | Arm 2, camera 2, dog (1–2 slots) | ~2–3 teams | Find an object in real space from a description/photo, or spot what's out of place |
| B | **B.R.C. Best Rice Company: Autonomous Company** | Riso Scotti | None | Unlimited | Agents take a retail order through to the invoice and settle disputes |
| C | **Labelling from the Model Pack** | Cristina Portinaro Cosmetics | Arm 1, camera 1 | 2 teams (alternating) | A robot learns label placement from one sample pack and rejects non-compliant ones |
| D | **Robot Dog Patrol** | Riello | Dog, smartphones as cameras | 1–2 teams | A camera sees an anomaly, the dog goes to check, an alert goes out |
| 01 | **Research Radar** | Organisers | None | Unlimited | A map of how a research field changes over time |
| 02 | **GitHub Benchmark Arena** | Organisers | None | Unlimited | A reproducible benchmark of new open-source tools |
| 03 | **Agent Failure Lab** | Organisers | None | Unlimited | Understand why an agent fails and verify the fix |
| 04 | **Voice Control** | Organisers | Arm 3 (no camera) | 2 teams (alternating) | Control a robotic arm by voice in Italian with Grok Voice |
| 05 | **Robot Skill Passport** | Organisers | 15 min on arm 3 for the final test | Unlimited | Tutorials generated from manuals and videos, with a hands-on check |
| 06 | **LabOS** | Organisers | None | Unlimited | A chat custodian for a lab's inventory and bookings |

---

## Track details

### Track A: CTRL+F: SEA ("See, Explore, Assist"), by SEA Vision
**In one sentence:** How do you play "Where's Waldo?" when Waldo changes every time and hides in a real room?
**Hardware:** Arm, camera, dog

**Context:** The object to find changes and hides in real space. The system must work with people to map and identify objects: from a photo, from a description, or because something is "out of place".

**What to build:** A vision system, possibly with an arm or the robot dog, that is given an object to look for, finds it in the scene and shows it to a person.

**Inputs provided:** A station with a table and 20–30 everyday objects; camera 2; arm 2 with the printed tool (the tip is used); 1–2 slots on the robot dog to search the museum rooms *(to be confirmed)*. Public starting resource: **YOLO-World**, a detector that finds objects from a text description (GPL-3.0).

**Use of Grok:** Understand the request (text, voice, photo) and compare it with what the camera sees; explain why an object is out of place; ask for clarification when the request is ambiguous.

**Minimum demo** (two modes, tested by the jury on new requests):
- **Find this:** given a description or a photo, the system highlights the object in the image and the arm points to it.
- **What changed:** given a reference scene, the system flags the object that was added, removed or moved.

**Stretch goals:** the arm lifts an object on a tray with the fork; the dog explores a room and comes back with the location; voice dialogue; a map of the room with the objects found.

**Out of scope:** training a detector from scratch; autonomous dog navigation in unprepared spaces.

**How it's judged:** SEA Vision's criteria are originality, how well the team makes the theme its own, and a working demo. "Amaze us!" Measures: **objects found out of 10 new jury requests; average time to find them; false alarms in "What changed" mode.**

**Seats and mentors:** Arm 2 with camera 2 for 2 teams in alternating slots; 1–2 slots on the dog. When no hardware is free, teams work on recorded videos of the station. About 2–3 teams. Mentors: **Claudio Peroni** (Wed and Thu, also on the jury) and **Michele Antolini** (Thu).

---

### Track B: B.R.C. Best Rice Company: Autonomous Company, by Riso Scotti
**In one sentence:** How can a traditional food company handle orders, invoices and disputes without repetitive manual work?
**Hardware:** None

**Context:** Riso Scotti wants to rethink its business processes like a tech company: less manual paperwork, faster response to the market, higher product quality. The critical issue is the dialogue with large retail chains: complex orders, delivery notes, invoices, disputes. Production enters the simulation as events, not robots.

**What to build:** A **"zero-touch" back office on synthetic data**, plus an **architectural concept** of how data flows from the factory to the administration.

**Inputs provided:** No documents from Riso Scotti. You start from public resources and **generate the dispute emails with Grok**. Public resources:
- Sample **EDI ORDERS, DESADV, INVOIC** messages in **EdiFabric/EDIFACT-Examples**
- Italian e-invoices (FatturaPA) with **python-a38**
- Annotated commercial contract clauses in **CUAD**
- A reconciliation baseline with sample files of the typical dispute cases: **threeway**

**Use of Grok:** Agents that read orders and documents, check quantities against stock, prepare the invoice, compare order, delivery and invoice, and propose how to settle a dispute, **citing the documents they rely on**.

**Minimum demo:**
- An end-to-end process on a new order: receipt → availability check → simulated production and shipping events → invoice → reconciliation.
- On at least one dispute (partial delivery, different price, contested goods), the system proposes a resolution with the evidence.
- **Every decision above a threshold goes through a person** (human-in-the-loop).

**Stretch goals:** visual quality control of rice grains on images (e.g. GrainSet; licence to be checked); predictive production planning; an exceptions dashboard.

**Out of scope:** connecting to a real ERP; real customer data; robots and production lines.

**How it's judged:** orders reconciled correctly on a test set, **better than the deterministic baseline**; disputes resolved with the right evidence; cases handed to a person when needed; **every action traceable to its source document**.

**Seats and mentors:** No hardware, unlimited teams. Mentor: someone from Riso Scotti *(to be confirmed)*. Note the Wed 18:30 "Riso Scotti meets the Hackathon" session.

---

### Track C: Labelling from the Model Pack, by Cristina Portinaro Cosmetics
**In one sentence:** Can a robot learn to label a new product by looking at a single sample pack?
**Hardware:** Arm, camera

**Context:** For small batches of luxury cosmetics, labels are printed on die-cut sheets and applied by hand, usually two per pack: front (logo and name) and back (INCI and legal wording). Positions change from product to product (front, back, cap, bottom), and the model pack on the table shows the right combination. **A wrong INCI is a compliance problem**, not just a cosmetic one.

**What to build:** A system that reads the model pack, repeats the work cycle with an arm, and rejects non-compliant packs, **with no retraining for each product**.

**Inputs provided:** Packs and labels from Cristina Portinaro Cosmetics, or empty bottles and boxes with dummy labels on pre-cut adhesive sheets: one model pack per format plus defective examples (crooked, creased or wrong label); camera 1; arm 1 with the printed tool; packs on slotted trays. Public resources: **Bottle_defect** images (crooked, creased, bubbled labels; CC BY 4.0); official INCI names in the **EU CosIng** database; arm demos and policies in **LeRobot**.

**Use of Grok:** Read photos of the model pack and turn them into a **structured specification** (which label, on which face, where, with what tolerance); check that the sheet matches the product; judge compliance with an explanation.

**Minimum demo** (three steps):
1. **Read the model:** from photos of the model pack, Grok produces the spec in a structured format.
2. **Cycle:** the arm moves a pack from the left area to the work area (lifting it on the tray with the fork, or pushing it), has the camera frame it, then moves it right if compliant or pushes it into the reject box at the table edge if not. *The team applies the labels by hand.*
3. **New product:** the jury brings a model pack the system has never seen; the system produces the spec and checks without new training.

**Stretch goals:** a check after each label (so the back label isn't wasted if the front is defective); detecting when a sheet runs out; learning the cycle from a video of a team member labelling.

**Out of scope:** peeling and applying labels with the arm; picking up packs without a tray; production speed.

**How it's judged:** spec correct against the model; non-compliant packs rejected and compliant ones accepted (**the worst error is accepting a wrong pack**); cycle completed without intervention; result on the jury's new pack.

**Seats and mentors:** Arm 1 with camera 1, 2 teams in alternating slots; outside slots, work on photos and videos of the station. Mentor: someone from Cristina Portinaro Cosmetics who decides what is compliant *(to be confirmed)*.

---

### Track D: Robot Dog Patrol, by Riello
**In one sentence:** Can a robot dog become the patrol that goes to check when a camera sees something strange?
**Hardware:** Dog, smartphones as cameras

**Context:** A company with a site of about 55,000 m² wants to pair a robot dog with its video surveillance: programmable patrols, targeted checks when a camera flags an anomaly, control from the guardhouse, a PC or a smartphone, and automatic alerts to security or the caretaker. The museum rooms stand in for the site.

**What to build:** The **event → mission → check → alert** flow, with a control console and a log of everything that happens.

**Inputs provided:** The museum's robot dog (in slots); 2–3 smartphones or laptops used as surveillance cameras, plus the dog's camera if it has one; a floor plan of the available rooms; a simulator of the dog if the model allows it *(to be confirmed)*. Public resources: the **unitree_sdk2_python** and **go2_ros2_sdk** SDKs if the dog is a Unitree; camera events with **Frigate**; alert calls with the xAI **voice-agent-phone** example (needs Twilio).

**Use of Grok:** A natural-language console, typed or with Grok Voice ("patrol room 2"); assess the camera event and decide whether to send the dog; describe what the dog frames; compose the alert, also as a voice call.

**Minimum demo** (three steps):
1. A scheduled patrol between 3 spots in a room.
2. A smartphone used as a camera detects a staged anomaly (a person in a restricted area, an abandoned object) and Grok sends the dog to the spot.
3. The dog frames the scene, Grok describes it, and an alert goes out to a test number. Every event is logged.

*Without a slot on the dog, the same flow runs with a simulated dog.*

**Stretch goals:** a console on the smartphone; prioritising several events at once; recognising false alarms; an end-of-shift report.

**Out of scope:** sirens, deterrents or other modules on the dog; footage of the real site; real calls to security or police; autonomous navigation over 55,000 m².

**How it's judged:** **time between the event and the dog's arrival**; staged anomalies verified correctly; false alarms forwarded; clarity of the alert; completeness of the log.

**Seats and mentors:** Robot dog for 1–2 teams, only with museum staff present; 1–2 dog slots are reserved for Track A. Mentor: someone from Riello *(to be confirmed)*.

---

### Track 01: Research Radar ("Mapping the Evolution of Scientific Knowledge"), by the organisers
**In one sentence:** How is a research field changing?
**Hardware:** None

**Context:** Research evolves too fast to follow by hand. Keyword searches return lists of papers but rarely show how subtopics emerge, which approaches converge, and which results changed the landscape. Users: researchers, R&D, deep-tech investors, innovation teams.

**What to build:** Given a topic and a time range, a system that collects publications from open sources, identifies the main strands, reconstructs the relationships between papers, and flags which directions are accelerating or slowing down. **Distinctive element: the "What changed?" mode**, which compares two time windows and also states which variations come from changes in source coverage.

**Inputs provided:** A topic, a main period (e.g. 24 months), a comparison window, optional filters. Open sources: **arXiv, OpenAlex, PubMed/Europe PMC**. Public resources: the **pyalex** Python client for OpenAlex (CC0 data, MIT library); **BERTopic** for topics over time.

**Use of Grok:** Give clusters readable names; write a report where **every claim has a linked source**; flag uncertainty. Cluster names are hypotheses derived from the data, not predefined labels.

**Minimum demo:**
- One domain and one source, 500–1,000 records with a reproducible query.
- 5–10 clusters with readable names, example papers and a timeline.
- A comparison between two windows with at least 3 sourced insights.
- A mini-dashboard filterable by period and cluster.
- *Example:* "reinforcement learning", the last 90 days against the previous 90, with clusters such as offline RL or RL for agents and the relative growth of each.

**Stretch goals:** cross-source deduplication; an interactive citation graph; a novelty score; recurring alerts; comparing authors and labs; conversational search with sources; suggested topics close to the companies (AI for food quality control, robots that learn from a demonstration).

**Out of scope:** full-text extraction without the rights; claiming that more papers mean more quality or impact.

**How it's judged:** retrieval quality on an annotated sample; cluster coherence (judged by hand); correctness of dates; share of report claims with a valid source; usefulness of trends against a simple baseline.

**Seats and mentors:** No hardware, unlimited teams. Mentors to be confirmed.

---

### Track 02: GitHub Benchmark Arena ("Continuous Evaluation of Emerging Open-Source Tools"), by the organisers
**In one sentence:** Which new tools actually work?
**Hardware:** None

**Context:** New frameworks and libraries come out every week with claims that are hard to compare. Stars and promo demos don't measure reliability or performance on real workloads. Users: developers, platform engineers, AI infra teams, CTOs, applied researchers.

**What to build:** Given a software topic, a system that finds relevant OSS repos, installs and runs them in a controlled environment, compares them on shared tasks with reproducible metrics, and keeps a leaderboard over time. **Distinctive element:** re-running the comparisons when a repo changes or a new one arrives, keeping the experiments comparable.

**Inputs provided:** A category (e.g. agent harnesses), a GitHub query, minimum requirements, a task suite, a time budget. Public resources: agent tasks with tools and a simulated user in **tau-bench** and **tau2-bench** (MIT). Isolated containers with **Docker** on the teams' laptops.

**Use of Grok:** **Grok is the fixed model used by every tool being compared**, so the leaderboard measures the tools and not the models. For open-ended answers, Grok acts as a **judge with a rubric calibrated on examples**, alongside deterministic checks.

**Minimum demo:**
- 3 compatible repos chosen by hand.
- 10 tasks with a common adapter and an explicit baseline.
- At least 2 runs per tool, saving the commit, config and logs.
- A leaderboard with a comparison by metric and at least one reproducible failure.
- *Example:* 3 agent harnesses on the same 10 tasks, measuring success, duration, calls, tokens and estimated cost.

**Stretch goals:** automatic discovery of new repos; confidence intervals; regressions between versions; scheduled runs with notifications.

**Out of scope:** running unknown code outside the containers; using an LLM judge as the only source of truth without annotated examples.

**How it's judged:** reproducibility of runs; correctness of adapters; coverage and quality of tasks; transparency of scoring; robustness to install errors; execution security.

**Seats and mentors:** No hardware, unlimited teams. Mentors to be confirmed.

---

### Track 03: Agent Failure Lab ("Understanding Why AI Agents Fail"), by the organisers
**In one sentence:** Why does an agent fail, and how can it be improved?
**Hardware:** None

**Context:** When an agent fails, the final result rarely says whether the cause is a wrong plan, an incomplete search, a misused tool or a loop. Analysing long traces by hand is slow and doesn't scale. Users: agent teams, QA, MLOps, AI product engineering.

**What to build:** A system that reads agent execution traces, classifies the failures, identifies the most plausible cause, and proposes fixes **verified with new runs**. **Distinctive element: a fix only counts if it improves a test without obvious regressions.**

**Inputs provided:** A task, an expected outcome or success test, a structured trace (messages, tool calls, outputs, timings, costs), the agent config. Public resources: traces annotated with 14 failure modes in **MAST-Data** (code in **MAST**); failures attributed to agent and step in **Who&When**. Traces produced by teams on tracks A–D also count as real cases, if those teams share them.

**Use of Grok:** Grok is the **diagnostician**: it reads the trace and proposes a category and a cause, **citing the steps**, with a confidence level. Deterministic rules alongside it handle timeouts, loops and failed tests.

**Minimum demo:**
- 15–20 traces (synthetic ones count), with at least 4 error categories and annotated ground truth.
- A parser, a timeline, and a classifier with per-step evidence.
- 2 concrete fixes (e.g. a controlled retry, or a mandatory check before the final answer).
- A replay on 5 tasks showing success, regressions, timings and costs before and after.

**Starting failure categories:**
- **Plan:** incomplete, dependencies overlooked.
- **Tool use:** wrong tool, wrong parameters.
- **Context:** insufficient sources, lost context.
- **Reasoning:** unsupported inferences, premature choices.
- **Execution:** timeouts, crashes, resource limits.
- **Verification:** output not checked, tests not run, success wrongly claimed.

**Stretch goals:** reading traces live; grouping recurring failures; generated regression tests; fixes proposed with human approval; comparing agents and versions.

**Out of scope:** presenting a Grok diagnosis as causal proof without an experiment that verifies it.

**How it's judged:** classification accuracy on annotated traces; precision in finding the relevant step; quality and verifiability of explanations; effective fixes; regressions introduced; added cost.

**Seats and mentors:** No hardware, unlimited teams. Mentors to be confirmed.

---

### Track 04: Voice Control, by the organisers
**In one sentence:** Can you control a robotic arm by speaking, with natural requests in **Italian**?
**Hardware:** Arm

**Context:** In a lab or on a production line, people who don't program robots should be able to call up ready-made operations without code or the teach pendant. Voice frees the hands but must be safe: **confirmation before movements and a stop that is always available**.

**What to build:** A voice assistant that understands the request, chooses among **3–5 predefined arm skills**, asks for confirmation, executes, and reports what it did.

**Inputs provided:** Arm 3 with the printed tool and slotted trays; basic skills (go to pose, point, lift the tray, put down, push) **written by the team with the arms' software**; the laptop microphone. Public resources: the official **xai-sdk-python** SDK and the **voice-agent-web** example of a browser voice agent.

**Use of Grok:** **Grok Voice in real time with function calls** to the arm's skills; voice confirmation before every movement; recognising "stop" at any moment.

**Minimum demo:**
- The jury dictates 5 new commands, including an ambiguous request (the system asks for clarification) and a "stop" that halts the arm immediately.
- Each command maps to a skill, with confirmation before the movement and a final report.

**Stretch goals:** sequences of several skills ("lift the tray and take it to the right"); recording a new skill by voice; more languages.

**Out of scope:** free trajectories dictated by voice; movements without confirmation.

**How it's judged:** commands executed correctly out of 10; **latency from end of sentence to start of movement**; handling of ambiguous or out-of-reach commands; a stop that is reliable at any moment.

**Seats and mentors:** Arm 3 dedicated (no camera), 2 teams in alternating slots. Outside slots, teams use a **simulated arm that receives the same commands**. Mentors to be confirmed.

---

### Track 05: Robot Skill Passport, by the organisers
**In one sentence:** Can someone who has never used a robot learn from an automatically generated tutorial, and prove it?
**Hardware:** A short test on an arm

**Context:** Robot training relies on long manuals and on people who already know the robots. What's missing is a short path, with a check that tells whether the person has really learned.

**What to build:** A tutorial generator that turns manuals and videos into short steps with key images and a verifiable checklist, plus a **"passport"** that records the skills each person has acquired.

**Inputs provided:** The arms' manuals (available online); videos of basic operations (switching on, manual movement, attaching the tray, emergency stop) **recorded by the team during slots**. Public resource for prototyping before the real videos: demo datasets with video in **LeRobot**.

**Use of Grok:** Read manuals and video frames; write the steps; generate check questions and assess the answers; **flag when a tutorial step has no match in the manual**.

**Minimum demo:**
- A tutorial for 2 real operations.
- A person who doesn't know the arms follows it in front of the jury.
- The checklist records what they did well and what they didn't; the passport shows the skills acquired.

**Stretch goals:** a practical check with a smartphone (e.g. did they press the emergency stop?); tutorials in more languages; automatic updates when the manual changes.

**Out of scope:** real safety certifications; using the robot without staff.

**How it's judged:** time and errors of the person with and without the tutorial; no step invented beyond the manual; clarity of the checklist.

**Seats and mentors:** Nothing to build on hardware; 15 minutes on arm 3 for the final test; unlimited teams. Mentors to be confirmed.

---

### Track 06: LabOS, by the organisers
**In one sentence:** Can a digital custodian keep a robotics lab in order: what is there, where it is, who uses it and when?
**Hardware:** None

**Context:** In shared labs, time is lost on inventory, machine bookings and usage rules. The information lives in scattered spreadsheets and in the head of whoever runs the lab.

**What to build:** A chat custodian that manages inventory, calendar and bookings, applies the lab rules, and keeps the history.

**Inputs provided:** The real hackathon inventory (arms, dog, cameras, grippers) and the station slots as a real case *(to be confirmed)*. Public resource: **eLabFTW**, open-source software (AGPL-3.0) with inventory, a booking calendar and an API, usable as a base.

**Use of Grok:** A **Grok bot** that takes bookings in natural language, checks conflicts and rules, answers questions like "where is the suction gripper?", sends reminders, and frees up slots.

**Minimum demo:**
- A searchable inventory; a calendar; booking and cancelling in chat.
- At least 3 rules enforced (no overlaps, 30-minute slots, staff present).
- A history of operations.
- The jury's test includes conflicting requests.

**Stretch goals:** **becoming the tool the teams use to book slots on Thursday morning**; automatic reminders; connection to the machines' logs.

**Out of scope:** physical access control; integration with company systems.

**How it's judged:** requests handled correctly on a test set, including conflicting ones; rules never broken; time to complete a booking.

**Seats and mentors:** No hardware, unlimited teams. Mentors to be confirmed.

---

## Jury
- **Luca Bianchi**: lead organiser/host; **CTIO at MESA Group**; Build ambassador, SpaceXSI Community, Pavia, Cursor and Grok Bot. Gives the Thu 11:00 talk on Grok Bots, so using Grok Bot will likely land well with him ([LinkedIn](https://linkedin.com/in/lucabianchipavia), [X @bianchiluca](https://x.com/bianchiluca), bianchiluca.com)
- **Lorenzo Cerri**
- **Alessandro Rano**
- **Alberto Giusti**
- **Claudio Peroni**: also the Track A (SEA Vision) mentor
- **Ralph Johnson**: **Field Engineer @ SpaceXAI**; gives the Thu 10:00 talk (Grok models, API, Voice, Bots), then helps at the tables
- **Federico Pellegrini**: also a host ([LinkedIn](https://linkedin.com/in/federico-pellegrini))

**Evaluation criteria (common rubric):** *To be announced* (on the site and Luma). Track-specific criteria are listed under each track above.

## Hosts and organisers
- Site hosts: **Luca Bianchi, Federico Pellegrini, Marco D'Angelo** (founder of Radixia, cloud ecosystem/open source, ex-Microsoft; radixia.ai)
- Other Luma hosts: Beppe Leone, Marco Pagani, Federico Leone, Yuri
- Speaker: **Ralph Johnson** (SpaceXAI)
- Mentors named so far: Claudio Peroni, Michele Antolini (Track A)

## Sponsors / organised by (from the logos)
SpaceXAI · Ctrl+Alt Museum · comPVter · SEA Vision · Riso Scotti · Radixia · Coherency · SICAM · Spazio Robot · Pavia – Open your mind
(Track C proposer **Cristina Portinaro Cosmetics** and Track D proposer **Riello** are not among the logos.)

## Team and registration rules (/rules)
1. Sign in with your **Luma email** (6-digit OTP, no password). Only approved guests can sign in.
2. Register a team (you get a secret code), join with a code, or mark yourself "looking for a team".
3. **Teams of 4–6.** A team needs 4 to count as formed and auto-closes at 6.
4. One team at a time. If the creator leaves, the earliest-joined member takes over.
5. **Teams locked on 2 Nov 2026 at 23:59 (Rome).** This has already passed; teams are frozen.
6. Teams of 4+ got guaranteed seats; the rest of the 100 seats went first-come by Luma registration time.
- Codes: 8 characters, never 0/1/I/O. The team lead can regenerate the code.

## Links
- Site: https://pavia.grokbot.it/ · Tracks: https://pavia.grokbot.it/tracks · Rules: https://pavia.grokbot.it/rules
- Luma: https://luma.com/spacexai-z1ys
- Museum: https://ctrlalt.museum
- Maps: https://www.google.com/maps/search/?api=1&query=Ctrl%2BAlt%20Museum%2C%20Via%20Gragnani%2C%2018%2C%2027100%20Pavia%20PV%2C%20Italy
- xAI docs: https://docs.x.ai/overview

## Public resources mentioned (quick index)
| Resource | Used in | What |
|---|---|---|
| YOLO-World | A | Open-vocabulary object detector (text → boxes), GPL-3.0 |
| EdiFabric/EDIFACT-Examples | B | Sample EDI ORDERS / DESADV / INVOIC |
| python-a38 | B | Italian e-invoices (FatturaPA) |
| CUAD | B | Annotated contract clauses |
| threeway | B | Three-way-match reconciliation baseline plus dispute samples |
| GrainSet | B (stretch) | Rice grain images (licence to be checked) |
| Bottle_defect | C | Label defect images, CC BY 4.0 |
| EU CosIng | C | Official INCI names |
| LeRobot | C, 05 | Arm demos, policies, video datasets |
| unitree_sdk2_python, go2_ros2_sdk | D | Unitree dog SDKs |
| Frigate | D | Camera event / NVR detection |
| xAI voice-agent-phone | D | Voice alert calls (Twilio) |
| xai-sdk-python, voice-agent-web | 04 | Official SDK and browser voice agent |
| arXiv, OpenAlex (pyalex), PubMed/Europe PMC, BERTopic | 01 | Paper sources and topic modelling |
| tau-bench, tau2-bench | 02 | Agent task benchmarks, MIT |
| MAST / MAST-Data, Who&When | 03 | Annotated agent failure traces |
| eLabFTW | 06 | Open-source lab inventory and booking, AGPL-3.0 |

---

## 📑 Kickoff slides (Wed 4 Nov, "Opening", 16 pages)

Source: `scraped/kickoff-slides.pdf` (text in `scraped/kickoff-slides.txt`). What's new or different compared with the website:

**Practical info**
- **Wi-Fi: network `hackathon`, password `hackathon`**
- Open all night, free entry and exit, nonstop until Thu 21:00. Bring a laptop; API credits provided.
- Hardware slots: robot dog and arms in 30-minute slots, always with museum staff.
- Awards ceremony Thu 21:00, right after pitches and evaluation.

**Venue:** Ctrl+Alt Museum covers 1,800 m² across three pavilions, in 3 sections (Computing, Gaming, Objects).

**Agenda:** the same as the site's, plus **Thu 16:00 "Video demo deadline (all tracks)"**. Pitches and evaluation run 16:00–19:00.

**Talks:**
- Wed 10:00, *Intro to cobots, dogs, drones and rovers*: the hardware on site (robotic dog, robotic arm, drones, driving and flight simulators).
- Wed 11:00, *Factory Academia*.
- Wed 18:30, *Riso Scotti meets the Hackathon*: Riso Scotti is an event sponsor and proposes Track B.
- Thu 10:00, **Ralph Johnson**, Field Engineer @ SpaceXAI: Grok models, API, Grok Voice, Grok Bots. **Also on the jury.**
- Thu 11:00, *Meet the MESetAs, using Grok Bots for everything*: **Luca Bianchi, CTIO at MESA Group**.

**Tracks slide** (hardware tags): A = Arm, Camera, Dog · B = Software only · C = Arm, Camera · D = Dog, Phone cameras · 04 = ARM · 05 = ARM TEST · 01, 02, 03, 06 = no hardware. Full briefs: pavia.grokbot.it/tracks.

**Rules for all tracks (slide version):**
- **Deliver a repo:** README, the data used, one result measured against a baseline, known limitations.
- **Teams of 4–6.**
- **Grok is essential:** the API, Voice or Bot must be essential to how the solution works, not decorative.
- **Hardware slots:** arms and dog for 30 minutes, always with staff. Printed tool, no gripper.
- **Data:** only public, synthetic or company-provided data.
- **🎬 Video demo, about 2 minutes: every team submits one by Thu 16:00.**

**Code of Conduct:** respect everyone; take care of the museum (the exhibits are historic); safety first with hardware (robots, arms and drones only in your slot and with staff); play fair (only public, synthetic or company data, **credit your sources**); speak up.

**Filming:** video will be recorded during the event. Tell the organisers if you prefer not to be filmed.

**Teams in numbers (from the portal, 3 Nov):** 16 teams, 65 participants, 10 tracks, 4–6 per team. Numbers may change at check-in. With 16 teams across 10 tracks, the hardware tracks (A, C, D, 04) have only 2–3 team seats each, so competition for hardware slots is real.

**No team yet?** Mingle and form a team of 4–6.

**Closing slide:** "Let's build. Video demo Thu 16:00 · Awards Thu 21:00. Show something on Thursday that didn't work when you started."
