# Robot Patrol — four independent assignments

Read this page first. Your job is to finish **one numbered assignment**. Read only your assignment, the shared rules below, and the referenced contract sections in [plan.md](plan.md). You do not need to study the other three implementations.

**What we are making:** a phone image triggers a museum investigation. A Go2 dog walks to a marked area and stops. Grok reads its camera and can request a higher view. A Tello performs a short approved inspection flight, lands on the floor, and Grok writes the result. The intended physical version carries the drone on the dog; floor flight is an explicitly labeled fallback.

## Rules shared by all four people

### Start without waiting

1. Use Python 3.11 and your own branch, named `codex/patrol-dog`, `codex/patrol-drone`, `codex/patrol-grok`, or `codex/patrol-ground`.
2. Work in a clean Robot Patrol project root. The parent workspace's Resume Changer code is unrelated.
3. Copy the **exact Python code block in plan.md section 6** into `patrol/contract.py` in your private branch. It uses only Python's standard library. Everyone may make that identical copy immediately. Do not redesign it or wait for Person 4.
4. Read plan.md sections **6, 7, and 11**: types/signatures, configuration, and fake scenarios. Those are the shared agreement. The exact contract code block can be syntax-checked independently; it does not require any other package.
5. Build your fake implementation and module selftest first. A hardware/API booking is not required to start.
6. Use only your owned files. Never edit another person's module, fixture folder, tests, or config.
7. Keep uncertain integration details inside your adapter. Never rename a public function or return a different field because a vendor SDK uses another name.
8. Put dependencies in your own `requirements/<module>.txt`. Pin tested versions. Do not modify a shared dependency list; Person 4 aggregates it.
9. Keep credentials out of commits and logs. Document required environment variables in your handoff.
10. If a real capability is blocked, return a truthful unavailable/error result, finish the fake and failure behavior, and explain the exact blocker. Do not implement another person's work to work around it.

The frozen contract is the source of truth. If a change appears necessary, write the proposal in your handoff. Only the senior can publish a revised contract. Ordinary SDK research and internal code choices do not need group discussion.

The senior handles equipment booking, staff access, and shared physical integration. Independence means you can complete your software and offline checks without another junior's code; it does not mean four people can use the same robot at once. Publish physical constraints/results in your handoff instead of creating new cross-module requirements in chat.

### Decisions already made

| Item | Fixed choice |
| --- | --- |
| Shared language / execution | Python 3.11, one `asyncio` ground-station process. |
| Dog integration research | `unitree_webrtc_connect` first, subject to actual Go2 verification. |
| Drone integration | DJITelloPy; approved relative flight profiles; elevated forward camera. |
| Reasoning | Official asynchronous `xai-sdk`, Pydantic validation internally, configured image-capable model. |
| User interface | Terminal commands owned by Person 4. No separate frontend assignment. |
| Evidence | Absolute JPEG paths and contract metadata. |
| Storage | JSON config, local evidence, JSON Lines event logs. |
| Tests | `pytest` behavior checks; hardware checks only in the staff-approved slot. |
| Zone names | Exactly `entrance`, `room_2`, `display`. |
| Starting position | Every route starts at the same calibrated `start` mark and orientation. |
| Drone decision | Grok requests a view; Ground authorizes it; Drone executes the fixed profile. |
| Excluded work | RSSI homing, drone-led patrol, mapping, voice, web UI, external alerts, landing back on the dog. |

### Ownership map

| Person | Owns | Receives | Delivers |
| --- | --- | --- | --- |
| 1 — Dog | Go2 control, route execution, stop, state, dog camera. | Named zone and bounded run context. | Stopped route result, status, fresh JPEG. |
| 2 — Drone | Tello control, carrier/mount work, flight profiles, landing, aerial camera. | Approved profile, zone, launch origin, bounded context. | Inspection result, final flight state, fresh JPEG. |
| 3 — Grok | Image decisions, verdicts, alert wording, evaluation. | Incident, saved frames, bounded context. | Valid contract decisions and text. |
| 4 — Ground | Input, terminal, state machine, interlocks, logs, metrics, integration. | The three public adapter factories. | A runnable end-to-end workflow and recorded demo. |

### What every handoff must contain

Use `handoff/<module>.md` with: working command; tested OS/Python; pinned dependency versions; public factory import; example configuration; fake scenario coverage; tests and results; real hardware/API evidence; known blockers; exact setup/recovery instructions. Distinguish measured behavior from assumptions. The senior should not need a chat to run your module.

## 1. Person 1 — make the robot dog controllable

### Your job in plain words

Make a small Python package that connects to the Go2, stands it safely, walks one short preapproved route to a named floor mark, stops, and saves a picture from the dog's camera. Also make a fake version that works on a normal laptop.

You are **not** deciding whether an incident is suspicious or whether to launch the drone. You are making the dog usable through a small, predictable interface.

### Files you own

```text
patrol/dog/**
fixtures/dog/**
tests/dog/**
requirements/dog.txt
config/dog.example.json
handoff/dog.md
```

You may copy the frozen contract unchanged. Do not edit `patrol/drone`, `patrol/grok`, `patrol/ground`, root packaging, or the other people's files.

### The exact thing the others will call

Export `create_dog` from `patrol/dog/__init__.py`. It accepts keyword arguments `mode`, `config`, and `output_dir` exactly as defined in plan.md section 6.1 and returns an object implementing `DogPort`.

| Method | Required result |
| --- | --- |
| `await connect()` | `DogStatus`; no standing or walking side effect. |
| `await prepare(ctx)` | Stable stand and avoidance setup; return actual status. |
| `await get_status()` | Connected / standing / stationary / avoidance, preserving unknowns. |
| `await run_route(zone, ctx)` | `RouteResult`; stop before returning; no arrival claim from timing alone. |
| `await capture_frame(zone, ctx)` | A fresh `Frame` with source `dog`. |
| `await halt()` | Stop walking promptly while preserving the tested stable stance. |
| `await close()` | Idempotent stop and connection cleanup. |

Keep `RealDog` and `FakeDog` behind that factory. Do not expose vendor object types to Ground.

### Do these tasks in order

**D1. Make FakeDog run without the robot.**

- Implement every public method using the frozen dataclasses.
- Keep a state object and call trace so tests can inspect preparation, routes, capture, halt, and close.
- Copy a small bundled JPEG into `output_dir` when capture is requested; mark it simulated.
- Simulate the default route completing and stopping. No busy waits or hardware imports.
- Implement the scenarios assigned to Dog in the table below. Other known shared scenarios use ordinary successful dog behavior; unknown scenario strings are invalid input.

**D2. Learn what this exact Go2 supports.**

Read plan.md section 4.1 and follow its linked official/upstream sources. Start with the [community driver's README](https://github.com/legion1581/unitree_webrtc_connect/blob/master/README.md) and the [avoidance example](https://github.com/legion1581/unitree_webrtc_connect/blob/master/examples/go2/data_channel/obstacles_avoid/obstacles_avoid.py).

In your handoff record: AIR/PRO/EDU edition; firmware; connection mode; library version/commit; video support; status support; tested movement API; avoidance behavior; account/AES setup requirement. Ask staff only for facts that require their hardware/access. Do not collect or commit their credentials.

The real dog may not support everything in the notes. Your interface remains the same. Unsupported functionality must report `unsupported`, not be replaced with invented telemetry.

**D3. Prove connection, camera, and halt before a route.**

- Connect without motion, read fresh status, and save one live frame.
- Demonstrate halt on the supported control path. Keep staff's independent controller available.
- Stand, enable avoidance, and read it back. Test one short supervised move using that same motion/control path.
- Record how command expiry behaves if control traffic stops. A Python watchdog does not guarantee stopping after a disconnected network.
- A missing/unknown standing, stationary, or avoidance state blocks real walking/launch readiness; do not default it to true.

**D4. Implement one calibrated route, then more if time permits.**

- Start with `room_2`. Record a known starting pose, endpoint mark, segment sequence, duration bounds, and stop behavior.
- Store route segments in your own route file, referenced by `routes_path`. Include units and turn conventions. Ground treats it as an opaque file.
- Send bounded movement segments. Check cancellation/deadline before every segment and during waits; choose conservative values tested with staff.
- Return incomplete/stopped for an obstacle or failed sequence. Return stopped false if stop cannot be verified.
- Do not assume a timed route works from arbitrary positions. Every incident resets physically to `start`; Ground obtains arrival confirmation.
- Reject uncalibrated `entrance`/`display` routes as unsupported. A truthful one-zone demo is better than three unverified routes.
- There is no RSSI scanner, home-to-beacon loop, SLAM, or general map in your assignment.

**D5. Make cancellation and camera behavior dependable.**

- Halt can run while `run_route()` is awaiting SDK work. It must not wait for the entire route lock.
- Vendor calls have bounded I/O. A cancelled worker must stop issuing later commands.
- Never retry a timed-out move automatically; it may already have executed.
- Capture after the request starts and reject an old stream buffer. Write a unique complete JPEG, return its absolute path, actual capture timestamp, trusted zone, and simulation flag. Follow plan.md section 6.3 for freshness.
- Block new route commands after cancellation until Ground deliberately resets/recreates the run.

**D6. Package your selftest and handoff.**

Required command: `python -m patrol.dog.selftest --mode fake`.

Optional real invocation uses `--mode real --config config/dog.local.json --arm`; it must begin with a clear operator preflight and never move on import or connection. Your selftest owns its own input handling; it does not import Ground.

### Fake behavior you own

| Scenario | Dog behavior |
| --- | --- |
| `route_blocked` | Route returns `completed=False`, `stopped=True`, descriptive detail. |
| `stale_frame` | Capture intentionally returns stale metadata for Ground's rejection test. |
| All other shared scenarios | Successful prepared route and fresh simulated frame; honor cancel/deadline. |

Add your own isolated failure tests for disconnection, unknown avoidance, halt during a route, and a timed-out command. Those test names need not become shared scenario names.

### You are finished when

- Your fake selftest and tests run with no Go2, Grok key, Tello, or another junior's code.
- Ground can instantiate your factory and call every frozen method.
- Tests prove cancellation prevents later route steps and halt is not blocked by a long route.
- Real evidence shows connection, fresh camera, stand, avoidance, short movement, halt, and at least one calibrated route **or** your handoff clearly records the exact blocked capabilities.
- Every real frame/status is truthful; a route completion is not mislabeled as confirmed arrival.

## 2. Person 2 — make the drone provide an extra view

### Your job in plain words

Make a package that connects to a Tello EDU, checks it, performs one short predefined inspection flight, saves a picture from above the dog's viewpoint, and lands on a safe floor patch. Also make the fake version. You own the physical drone carrier and launch experiments.

You are **not** searching the whole museum or telling the dog where to walk. Your drone only flies when Ground requests an approved inspection.

### Files you own

```text
patrol/drone/**
fixtures/drone/**
tests/drone/**
requirements/drone.txt
config/drone.example.json
handoff/drone.md
```

Store flight profiles and carrier measurements/photos inside your owned tree. Do not edit the dog package to attach flight logic.

### The exact thing the others will call

Export `create_drone` from `patrol/drone/__init__.py`, with the common factory keywords. Return `DronePort`.

| Method | Required result |
| --- | --- |
| `await connect()` | `DroneStatus`; no takeoff side effect. |
| `await get_status()` | Connection, grounded/airborne/unknown, battery percent or unknown. |
| `await inspect(request, ctx)` | Run the approved profile, capture, attempt landing, then return `InspectionResult`. |
| `await land()` | Controlled abort/landing for the approved profile; idempotent when grounded. |
| `await close()` | Landing/cleanup attempt, then release resources; preserve errors. |

`InspectionRequest` contains `zone`, `profile_id`, and `launch_origin`. The origin is exactly `dog_pad` or `floor`. Ground maps carried/stationary pad tiers to `dog_pad` and records the detailed tier in its logs.

Keep `RealDrone` and `FakeDrone` behind the factory. No Tello object, NumPy image, SDK response string, or raw UDP detail crosses the public contract.

### Do these tasks in order

**T1. Make FakeDrone first.**

- Implement connected/grounded state, battery, call trace, inspection, landing, and close.
- The default inspection saves a bundled simulated image and returns captured/grounded.
- Implement unavailable, ambiguous takeoff, and unknown landing scenarios below.
- Fake mode imports no flight SDK and opens no network sockets.

**T2. Verify one floor flight and camera.**

Read plan.md sections 4.2–4.4, the [manufacturer SDK guide](https://dl-cdn.ryzerobotics.com/downloads/Tello/Tello%20SDK%202.0%20User%20Guide.pdf), and [DJITelloPy API documentation](https://djitellopy.readthedocs.io/en/latest/tello/).

- Record the drone model, firmware if available, SDK/library versions, video decoder dependencies, and dedicated network interface.
- Connect to its AP, read battery/status, and receive video without the dog.
- During the staff flight slot, prove takeoff, a short view-producing path, and floor landing.
- Use the forward camera. Downward video is optional device-specific research; it must not hold up your deliverable.
- Check command units and SDK limits before coding a profile. A relative `up` command is not an absolute height above the room floor.

**T3. Implement a complete bounded inspection profile.**

- Start with profile ID `room_2_view_v1` for the `room_2` zone. Keep the actual trajectory in your own configuration.
- A profile records compatible launch origin, starting orientation, permitted area, route segments, viewpoint, landing patch, battery reserve, maximum flight time, and phase-specific abort behavior.
- Use an allowlist. Reject unknown IDs, wrong zones, or unsupported origins before takeoff.
- Capture a fresh JPEG while the aircraft is stable at the tested viewpoint. Preserve its real capture time; later transit/landing can make it older by the time `inspect()` returns. Follow plan.md section 6.3 rather than changing the timestamp after landing.
- Reach the cleared floor landing position before descending. Do not issue a raw land command while above the dog.
- Attempt landing in cleanup even if capture fails. Report actual post-attempt flight state; do not treat the command acknowledgement alone as proof of grounded state.
- Keep flight command supervision/watchdog running independently from Grok and the main sequence.
- Never take off twice because the first response timed out. State may already be airborne.

**T4. Test the carrier in increasing steps.**

1. Measure the actual dog/drone, guards, attachment points, sensor positions, and clearances. Coordinate the physical attachment constraints through the dog handoff/staff, without depending on dog code changes.
2. Prove a floor profile first.
3. Test a flat stationary pad with staff approval; dog must remain in the tested stable posture. Prove normal and abort floor landing paths.
4. Design retention that secures the drone during walking and can be released after stopping. A human release is acceptable; do not build a complex automatic release for the deadline.
5. Test stationary retention/release, then a short supervised carried walk, then pad takeoff.
6. Record the highest passed tier: `floor`, `stationary_pad`, or `carried_pad`.

The profile may support only floor launch at handoff. State that clearly. Pad takeoff is not proven by a successful floor takeoff. A plate alone does not solve retention or release.

**T5. Prove networking and abort behavior.**

- Use the dedicated Tello Wi-Fi interface and document its route setup. Ground must keep a separate dog link and internet available.
- Do not solve this by switching one Wi-Fi radio during the run.
- `land()`/cancellation must preempt the normal sequence. Do not wait for the full inspection operation to finish before noticing halt.
- Stop normal pending steps before sending an abort; serialize SDK responses so the abort does not corrupt command handling.
- Unknown position/link state may require operator takeover. Document that limitation and keep `flight_state="unknown"` until verified.
- Normal halt is controlled landing, not immediate motor cut. Keep any vendor emergency motor-off mechanism local to trained operator procedures; it is not a Grok tool.

**T6. Package your selftest and handoff.**

Required command: `python -m patrol.drone.selftest --mode fake`.

Real selftest accepts `--mode real --config config/drone.local.json --launch-origin floor --arm`. It must check operator readiness before takeoff. Keep its control loop separate from Ground code.

### Fake behavior you own

| Scenario | Drone behavior |
| --- | --- |
| `drone_unavailable` | Return unavailable with no takeoff; remain grounded. |
| `takeoff_timeout` | Record one takeoff attempt and abort attempt; return failed/unknown; never retry. |
| `landing_unknown` | Return a captured frame with final flight state unknown. |
| All others | Successful simulated captured/grounded result if called; honor cancel/deadline. |

### You are finished when

- Your fake selftest and tests need no dog, model key, or Ground implementation.
- An allowlisted request produces a fresh JPEG and a truthful landing result.
- Tests cover no-retry takeoff timeout, cancellation, capture failure cleanup, unknown landing, and repeated landing/close.
- Real flight evidence and the highest passed carrier tier are documented, or the specific blocker is recorded.
- The next person can run your profile using only your config and handoff, without asking where it will land.

## 3. Person 3 — make Grok return dependable decisions

### Your job in plain words

Make a package that reads saved images and returns four things: whether to send the dog, whether the dog's view needs help, what the final evidence shows, and a short report. Make a fake version and measure the real prompt on labeled images.

You do **not** control either robot, build a state machine, infer a room name from an image, or generate flight coordinates.

### Files you own

```text
patrol/grok/**
fixtures/grok/**
tests/grok/**
requirements/grok.txt
config/grok.example.json
handoff/grok.md
eval/results.md
```

You may keep labeled manifests and matched ground/aerial examples under `fixtures/grok/`. Do not depend on pictures captured by the other juniors; begin with your own consented/staged images.

### The exact thing the others will call

Export `create_reasoner` from `patrol/grok/__init__.py`, using the common factory keywords. Return `ReasonerPort`.

| Method | Returns | Meaning |
| --- | --- | --- |
| `metadata()` | String mapping | At least `model`, `prompt_version`, `sdk_version`; no API call. |
| `await assess_incident(incident, ctx)` | `DispatchDecision` | `dispatch`, `dismiss`, or `review`. |
| `await assess_ground_view(incident, frame, ctx)` | `GroundDecision` | `sufficient`, `inspect`, or `review`, with observation/reason. |
| `await resolve_incident(incident, ground, aerial, ctx)` | `Resolution` | `confirmed`, `cleared`, or `inconclusive`. Aerial may be `None`. |
| `await compose_alert(incident, result, ctx)` | Nonempty string | Short report preserving the verdict and uncertainty. |
| `await close()` | None | Idempotent client cleanup. |

Keep `GrokReasoner` and `FakeReasoner` behind the factory. Return contract dataclasses, not Pydantic/vendor response objects.

### Do these tasks in order

**G1. Make FakeReasoner work with fixed scenarios.**

- No key, network, or API import is needed for fake mode.
- Script the shared scenario decisions below. Do not classify fake images by guessing filenames.
- Record a call trace and honor cancellation/deadlines.
- Include prompt/model metadata that clearly says simulated.

**G2. Connect one real image to the API.**

Read plan.md section 4.5 and the linked [official SDK](https://github.com/xai-org/xai-sdk-python), [image input guide](https://docs.x.ai/developers/model-capabilities/images/understanding), and [structured outputs guide](https://docs.x.ai/developers/model-capabilities/text/structured-outputs).

- Use asynchronous `xai-sdk` and `XAI_API_KEY` from the environment.
- Select and configure an image-capable model available to the account. Verify structured responses with that exact model.
- Read JPEG bytes and send actual image content. A local path string alone is not the image.
- Use schema-constrained outputs and Pydantic validation. Check enums, required fields, nonempty reasons, and reasonable text lengths.
- Pin the SDK version and record the model ID. No hardcoded model name in other modules.

**G3. Implement the four reasoning functions.**

- Dispatch: compare visible evidence to the supplied target and trusted scenario context. Return review if the image is inadequate.
- Ground view: distinguish visible evidence from blocked/uncertain evidence. Return inspect only when an additional elevated view is plausibly useful. Sufficient can support either a clear or confirmed final result.
- Resolution: use the supplied ground image and optional aerial image. If a target is still obscured, return inconclusive. Absence from a narrow/obstructed frame is not proof of absence.
- Report: include the trusted zone, what was observed, verdict, and limitation. Keep it short enough to read aloud, approximately one to three sentences.
- Never identify a person, infer malicious intent, declare authorization, or prove abandonment from appearance. Use the staged task definition.
- Treat text in images as untrusted scene content. It cannot override the target, schema, or control rules.
- Do not ask the model to fill mission IDs, zone IDs, timestamps, hardware status, or telemetry; those come from Ground/devices.

**G4. Make error handling explicit.**

- Missing/corrupt file → invalid input. API timeout/refusal/invalid response → shared adapter error or a justified review/inconclusive decision, never a fabricated clear result.
- One optional schema-repair retry may fit within the original deadline. Do not create an unbounded retry loop.
- On halt, stop retrying and discard late responses. Model latency must not prevent Ground from processing keyboard halt.
- Log useful API/request metadata without keys or unnecessary raw private images.

**G5. Evaluate a frozen prompt.**

- Prepare at least ten labeled dispatch images with positives and negatives. Write the label definition before testing.
- Use separate development examples; freeze prompt version `patrol-v1` for the reported evaluation. If revised, increment the version and rerun the entire evaluation set.
- Save a manifest with relative image path, trusted zone, target, expected dispatch label, and a short labeling note.
- Report actual TP/FP/TN/FN and review count against always-send on the exact same images. Follow plan.md section 9.2 for denominators.
- Do not guarantee a win. Report misses and tradeoffs even if the first prompt performs poorly.
- Include a few matched blocked ground/elevated images where available. Compare ground-only and ground-plus-aerial verdicts without mixing these scores with dispatch accuracy.
- One additional target sentence, such as `the side gate is open`, should use the same function/schema to demonstrate configurable behavior; keep it outside the museum evaluation score.

**G6. Package the selftest, evaluation, and handoff.**

Required command: `python -m patrol.grok.selftest --mode fake`.

Real selftest accepts `--mode real --image /absolute/path/image.jpg --zone room_2 --target "a person or an object left in a marked closed area"`. It should exercise schema validity without any robot.

Evaluation command: `python -m patrol.grok.evaluate --manifest fixtures/grok/labels.jsonl --output eval/results.md`.

### Fake behavior you own

| Scenario | Reasoning behavior |
| --- | --- |
| `blocked_resolved` and ordinary failure scenarios | Dispatch; ground view inspect; final aerial result confirmed if called. |
| `dismiss` | Dispatch decision dismiss. |
| `ground_clear` | Dispatch; sufficient ground view; cleared resolution. |
| `ground_confirmed` | Dispatch; sufficient ground view; confirmed resolution. |
| `invalid_model` | Raise an API/invalid-output error during dispatch. |
| `slow_model` | Keep dispatch pending while polling cancel/deadline; no late usable decision after halt. |

Ground must not call a scripted confirmed resolution if required evidence failed. Fake decisions test orchestration; they are not reported as model accuracy.

### You are finished when

- Fake functions run independently and return the exact contract types.
- Real image calls produce validated decisions, or a specific account/API blocker is documented.
- Tests cover every decision enum, corrupt image, malformed/refused/timed-out output, and cancellation.
- `eval/results.md` contains measured counts, dataset size, model ID, prompt version, methodology, and limitations, or explicitly says evaluation is blocked. No invented scores.
- Nothing in your package imports a robot SDK or issues movement commands.

## 4. Person 4 — connect the pieces and run the demo

### Your job in plain words

Make the terminal application that receives an image, asks Grok what to do, calls the dog and drone at the correct times, handles halt and failure, and saves the result. You own the sequence, not the vendor SDKs or prompt wording.

You can start immediately using your own private scripted adapters. The other three people do not need to finish first.

### Files you own

```text
patrol/ground/**
fixtures/ground/**
tests/ground/**
requirements/ground.txt
config/ground.example.json
handoff/ground.md
demo/script.md
root packaging / dependency aggregation / combined setup instructions
```

Keep private early stubs at `patrol/ground/testing/stubs.py`; do not create or edit another person's adapter package. Root packaging must not import all real vendor SDKs on startup.

### Your exact dependencies

Use only these public factories from plan.md section 6.1:

```python
from patrol.dog import create_dog
from patrol.drone import create_drone
from patrol.grok import create_reasoner
```

Until they exist, inject your private objects implementing the same Protocols. Do not change production signatures to match a temporary stub. Once merged, run the workflow through the real module factories in fake mode.

### Do these tasks in order

**C1. Build the input, model, and private-stub runner.**

- Materialize the exact contract. Create a pure coordinator accepting `DogPort`, `DronePort`, and `ReasonerPort` objects.
- Create private scripted stubs and run the happy path without importing any other junior's module.
- Deliver `python -m patrol.ground.selftest --stubs --scenario blocked_resolved` as your independent starter check. The final production runner must use public factories and must not silently substitute these stubs.
- Accept a supplied JPEG, trusted zone, target, adapter modes, and config. Generate a unique mission ID.
- Keep capture provenance/time for supplied images. Copying a photo is not a new capture.
- Validate the zone, target, file, config, mode choices, and scenario before motion.
- Save one chronological event stream and one final summary per mission.

**C2. Implement the exact state machine.**

Follow plan.md sections 3 and 8. Use its state names and deterministic terminal report outcomes. The main successful inspection sequence is:

```text
assess_incident
→ prepare dog / check status
→ run_route
→ verify stopped / wait for operator arrival confirmation
→ capture dog frame
→ assess_ground_view
→ if inspect: interlocks / wait for flight-ready / inspect / verify grounded and valid aerial image
→ resolve_incident
→ compose_alert
→ print and save
```

- Dismiss means no motion. Review means unresolved with no automatic escalation.
- A sufficient dog view skips flight and still goes through final resolution.
- A failed route, missing arrival, stale frame, unavailable drone, or invalid decision does not become a successful investigation.
- Only call resolve with evidence that actually exists and passed freshness checks.
- Keep trusted zone/target/mission state outside the model outputs.

**C3. Add operator input and independent halt handling.**

- Implement `status`, `arm`, `start`, `arrived <zone>`, `flight-ready`, `halt`, `reset`, `quit`, and Ctrl+C as specified in plan.md section 7.2.
- Read commands while an API/device operation is pending. Do not block terminal handling with synchronous SDK work.
- Halt immediately latches the shared cancellation event and starts both dog stop and drone abort requests; one slow device cannot delay requesting the other.
- Ignore late model results after halt and prevent new motion until recovery and explicit rearming.
- Implement reset by verifying recovery, waiting for old workers to stop, closing/recreating adapters, reconnecting disarmed, and creating a fresh cancellation event. If a worker cannot be stopped, remain in fault; do not start a second control worker.
- `arm` is scoped to one incident. The real operator confirms start pose, route, secured carrier where applicable, and independent controls. A start command cannot silently arm a real motion adapter.
- Only accept `arrived` in the correct state for the exact current zone and after a completed/stopped route.
- A fake dog can simulate arrival. A real dog always needs actual operator confirmation.
- `flight-ready` is a separate confirmation after arrival and the inspection decision. Only accept it in `PREFLIGHT`; confirm completed carrier release and the clear launch/landing area. Do not use pre-walk arming as proof the drone has been released.

**C4. Add launch and recovery interlocks.**

- Re-read dog/drone status immediately before flight. Unknown status blocks launch.
- Select an allowlisted profile from `profile_by_zone`; the model cannot choose coordinates.
- Check launch tier, profile compatibility, calibrated battery reserve, cancellation, and deadlines.
- A real drone may not launch from `dog_pad` based on fake dog status. Require both real devices and physical standing/stationary verification. A real-drone/fake-dog test is floor-only and still requires an operator.
- Lock walking/turning for the complete flight and until verified landing/recovery. Never implement dog motion inside flight processing.
- `InspectionResult.flight_state != "grounded"` enters latched fault even if an image was captured.
- No automatic takeoff or walk retry after timeout. No new incident from a fault without recovery.
- During shutdown attempt both adapters' cleanup and preserve diagnostic errors. Do not overwrite the original exception with a cleanup exception.
- A disconnected process cannot guarantee physical safety; document independent staff controls and the tested device timeout behavior.

**C5. Implement configuration, logs, and measurements.**

- Deliver the exact final commands in plan.md section 7.3 and the configuration envelope in section 7.1. The all-fake command runs automatically on a bundled input; commands with real motion adapters start disarmed.
- Select fake/real modes independently and display them prominently.
- Pass each adapter only its own config and its own absolute output directory.
- Enforce per-stage and whole-incident deadlines, including the separate flight-readiness wait. Safety/cleanup must still run after an incident deadline.
- Write JSON Lines state events and `summary.json` fields from plan.md section 9, including prompt/model, simulation flags, launch tier, error, recovery status, and alert.
- Measure event acceptance to operator arrival using a monotonic clock. Leave arrival time null for no/failed/unconfirmed arrival.
- Display Junior 3's saved classification results; do not invent an always-send score from one live run.
- If report wording fails after a valid verdict, use a deterministic local report template. Preserve uncertainty.

**C6. Integrate and write the two-minute script.**

- First run private stubs, then the three actual module factories in all-fake mode. These are distinct checks.
- Substitute one real module at a time; keep remaining modes labeled fake.
- Aggregate pinned dependencies into a combined install path. Record real OS/library compatibility and any decoder/network prerequisites.
- Verify all three network needs simultaneously: Go2, Tello video/control, Grok internet.
- Write `demo/script.md` with operator setup, staged target, terminal commands, arrival and post-release flight-readiness confirmations, highest verified launch tier, alert reading, halt demonstration, and manual reset.
- Record the full carried version only if its physical gates passed. Otherwise record and label the strongest passed fallback.

### Required acceptance checks

Run every shared scenario from plan.md section 11. Tests should verify meaningful calls and outcomes:

| Check | Evidence needed |
| --- | --- |
| Dismiss | No prepare, route, or inspection calls. |
| Ground clear / confirmed | Correct final verdict; no flight. |
| Blocked resolved | One inspection; resolution only after grounded result. |
| Blocked route / no arrival | No flight; arrival metric null where unconfirmed. |
| No flight-ready / fake dog with real pad flight | No takeoff; explicit unresolved or rejected setup. |
| Invalid model / stale image | No unsafe continuation; unresolved/error recorded. |
| Drone unavailable | No fabricated aerial evidence or clear verdict. |
| Slow model + halt | Coordinator responds within fake target; late response cannot start a route. |
| Halt during route / inspection | Cancel latched; both safety requests issued; no later ordinary movement. |
| Takeoff timeout | Exactly one attempt; no automatic retry. |
| Landing unknown | Fault/recovery lock; dog cannot move or reset automatically. |
| Cleanup failure | Original failure remains visible; both cleanup attempts made. |
| Actual factory integration | Full all-fake run uses merged module factories, not only private stubs. |

Use tests for these cross-component behaviors, rather than tests that merely repeat the implementation's state assignments.

### You are finished when

- The final all-fake command works without hardware, credentials, or a live internet connection.
- The same runner supports real adapters by flags/config, without editing the state machine.
- Halt remains usable during model/device waits, and failures produce truthful outcomes and recovery state.
- Logs show the measured arrival value or null, model metadata, evidence, final report, and adapter modes.
- The combined setup guide and demo script let the senior reproduce the pass without asking you what to click or run.

## Merge rule for the senior

Merge only the owned paths, retain one identical contract, run each module's independent fake selftest, then run Ground through the actual factories in all-fake mode. Resolve dependency conflicts centrally. Do not ask juniors to patch one another's modules to make the demo work.

Then integrate one real capability at a time. Report separately: software integration passed, dog hardware passed, flight passed, stationary pad passed, carriage/release passed. A blocked real capability must remain visible in the final demo description.
