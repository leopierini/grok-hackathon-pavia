# Master prompt: Ground Mission Control UI

You are the product designer and full-stack implementation engineer for this repository. Build **Ground Mission Control**: a complete local operator UI for the Ground Station and Integration project defined by Tasks 01–32. Deliver a working application connected to the available Ground runtime, with an offline simulation experience and truthful visibility into missing integrations.

I prefer **Next.js**. Use Next.js App Router, React, strict TypeScript, Tailwind CSS, and accessible components such as shadcn/ui. Keep the existing Python Ground runtime as the authority for mission state, policy decisions, command approval, device ownership, cancellation, leases, and recovery. The UI must let an operator configure the run, understand what is happening, issue supported commands, investigate failures, and inspect results from one place.

## 1. Read the repository before designing

Find and read the actual files, including when their locations differ from these examples:

- `ground task.md` — all 32 task cards, especially the active drone-first revision of Tasks 11–32.
- `ground.md` — especially the active demo, phases, commands, interlocks, networking, and acceptance scenarios.
- `docs/ground/foundation.md`, `plan.md`, and `tasks.md` for foundation and legacy contract context.
- `contracts/README.md`, `contracts/message.schema.json`, `contracts/examples-index.json`, and the direction-specific contract documents.
- `patrol/ground/kernel/**`, `patrol/ground/base.py`, the entry point, and `patrol/ground/extensions/g01` through `g32`.
- Relevant tests, fixtures, handoffs, and demo scripts.
- Applicable `AGENTS.md` instructions and existing frontend conventions, if present.

The current reference checkout has `ground task.md` at the repository root. Search rather than assuming `docs/task.md` exists. Verify repository identity and preserve existing uncommitted work.

This request explicitly adds a web UI despite the older foundation document excluding a web frontend. It does not replace the robot contracts or authorize changes to teammate-owned device internals. The active drone-first Tasks 11–32 supersede the older phone-photo mission for this UI. Preserve useful foundation services from Tasks 01–10. Do not build the obsolete incident workflow as the primary product.

Before implementation, write `docs/ground/ui-coverage.md` with exactly one row for each task 01–32. Include its actual title, UI surface, observable data, allowed operator actions, Python provider/contract, evidence source, integration status, and verification method. Distinguish specification, installed provider, independently tested provider, composed runtime, and hardware acceptance. File presence and a checked checkbox do not prove completion. Handoffs can be stale; check current code and measured evidence.

## 2. Architecture

Use this basic arrangement:

```text
Next.js operator interface
        |
        | typed HTTP actions and a reconnectable event stream
        v
Local Python API / integration bridge
        |
        v
Existing Ground services, policies, journal, and workflow
        |
        v
Dog application / drone adapter / Pi / vision provider
```

Use a small persistent Python API, preferably FastAPI when no suitable API already exists. Keep new dependencies isolated where practical. Use HTTP for commands and SSE or WebSocket for observations; choose one streaming approach and implement it end to end. Next.js can provide a thin proxy where useful, but must not own robot workers. Run locally on the operator laptop, with Windows/PowerShell instructions. The core UI and simulated workflow must work without cloud hosting, credentials, hardware, or internet at runtime.

Reuse real public interfaces. Do not create a second Tello client, import vendor SDKs in the browser, shell out to arbitrary user-provided commands, or copy Python safety logic into React. Device connections have a single owner. UI mount, reload, navigation, development hot reload, and multiple tabs must not construct duplicate device workers or restart a mission.

First inspect whether a composed v2 runtime exists. The reference entry point may still refuse live operation even when all extension files exist. Do not bypass that refusal or declare live control working because a button calls a stub. Add the smallest additive bridge needed to use existing services. If essential orchestration is absent, implement the UI integration in simulation and expose the exact live blocker. Keep any required coordinated runtime change small, documented, and covered by integration tests. Avoid rewrites of Tasks 01–32.

Use a typed transport interface with separate runtime and simulation implementations. Both must expose the same UI data contract. Simulation must run ordered scenarios and emit correlated events; a simulation report viewer alone does not satisfy the interactive mission workflow. Keep replay, simulation, and live sessions visibly separate. Never silently substitute fake devices for failed real devices.

## 3. Product structure and visual direction

Create a coherent operator workstation with these surfaces:

1. **Mission Control** — the main operational screen.
2. **Devices & Readiness** — capabilities, connection profiles, and preflight gates.
3. **Vision & Evidence** — drone/dog frames, requests, decisions, and provenance.
4. **Navigation & RSSI** — safe candidates, beacon hold, Pi windows, and visual handoff.
5. **Commands & Safety** — proposals, approvals, ACKs, leases, faults, and recovery.
6. **Runs & Logs** — chronological investigation, artifacts, and measured timings.
7. **Rehearsal & Tasks** — scenario controls and evidence-backed coverage of Tasks 01–32.
8. **Settings** — validated profiles and configuration.

Group tasks into these operator workflows. Do not turn the 32 implementation tasks into 32 unrelated pages. Keep software implementation progress separate from runtime mission progress.

Use a desktop-first layout suited to a laptop in a demo space: clear typography, compact useful tables, restrained dark neutral surfaces, and consistent status colors with text labels. Include a usable light theme and responsive tablet layout. Use motion sparingly. Put mission state, blockers, evidence, and controls ahead of decoration. Avoid marketing sections, placeholder charts, and ornamental telemetry.

The global header must show mission ID, epoch, runtime connection, simulation/live/replay mode, individual device modes, phase, arming state, current fault/recovery state, and **Halt**. Halt must remain accessible while requests, images, dialogs, and model calls are pending. It should submit immediately without a confirmation dialog; show backend acceptance and device delivery/verification separately.

Mission Control should combine a mission phase rail, camera/evidence workspace, device health summary, active command, chronological activity feed, and context-sensitive next action. Explain why an action is disabled and what evidence or confirmation is needed. Support loading, empty, stale, disconnected, blocked, rejected, partial-failure, and unknown states throughout.

## 4. Coverage of all 32 tasks

Implement the following capabilities, refining names and fields from the actual source contracts:

| Task | Required UI coverage |
| --- | --- |
| 01 | Kernel/provider inventory, contract versions, feature availability, and missing-provider diagnostics. |
| 02 | Validated configuration, profiles, independent adapter modes, redacted settings, and dog transport. |
| 03 | Authoritative session phase, mission/epoch/stage identity, arming, locks, and fenced stale actions. |
| 04 | Ordered journal, run history, evidence artifacts, summary publication, and writer health. |
| 05 | Pending operations, stage deadlines, cancellation, timeout, and outstanding worker status. |
| 06 | JPEG validation, capture provenance, source, freshness, integrity, and rejection reasons. |
| 07 | Responsive typed operator actions and scoped confirmations with expiry/invalidation. |
| 08 | Adapter connection lifecycle, ownership, availability, and guarded calls. |
| 09 | Composed workflow visibility, authoritative phase transitions, and one-mission enforcement. |
| 10 | Halt latch, cleanup, shutdown, recovery verification, and disarmed reset. |
| 11 | v2 envelope validation, protocol version, deduplication/correlation, and typed rejections. |
| 12 | Dog/drone/Pi capability reports and the specific features actually admitted for arming. |
| 13 | Drone flight state, altitude with its reference, observation age, beacon, and available cameras. |
| 14 | Frame IDs, camera epoch, calibration, hash, byte validation, and exact evidence provenance. |
| 15 | Vision sampling, latest-frame scheduling, in-flight request, dropped frames, and timeout. |
| 16 | Grok decisions, uncertainty, track updates, review state, and proposals without motor authority. |
| 17 | One bounded drone primitive, approval/rejection reasons, profile limits, and current authorization. |
| 18 | Drone command accepted/running/final ACKs, execution uncertainty, and unknown landing. |
| 19 | Stable beacon hold, beacon epoch changes after drone motion, and dog-stop gating. |
| 20 | Dog pose/navigation health, map identity, obstacle clearance, and safe planner candidates. |
| 21 | Pi heartbeat, telemetry path, RSSI windows in dBm, quality, age, clock error, and comparability. |
| 22 | Selected safe candidate, RSSI trend, decision explanation, no-progress budget, and stop reason. |
| 23 | Approved leased dog commands, command IDs, expiry, and priority halt. |
| 24 | Dog accepted/running/final ACKs, rejected steps, and verified stationary state. |
| 25 | Same-target dog-camera acquisition and RSSI-to-vision handoff, including ambiguous/wrong tracks. |
| 26 | Separate current dog-target range and drone horizontal offset, thresholds, sources, and goal decision. |
| 27 | Goal result and landing/recovery result displayed independently; unknown landing retains the fault. |
| 28 | Halt, link loss, stale evidence, expired leases, and safety actions independent of Grok. |
| 29 | v2 event/message explorer with correlation IDs and provisional/versioned log schema status. |
| 30 | Ethernet/Wi-Fi readiness, tether acceptance, simultaneous connectivity, and the Pi delivery path. |
| 31 | Measured demo timings and quality metrics, with missing values shown as unknown plus reasons. |
| 32 | Ordered offline rehearsal, scenario results, fault injection, report artifacts, and operator runbook. |

A control must execute a supported backend operation or be explicitly disabled with a concrete reason. A label, decorative card, or fake success toast does not count as implementation.

## 5. Ground-specific behavior

Use the active demo phases from `ground.md`:

`IDLE → CONNECT → SCOUT → TRACK → HOLD → HOME → DOG_VISION → PROXIMITY → LAND → DONE`, with `ABORTED` and `FAULT` as applicable.

Reflect authoritative backend transitions rather than advancing this rail with frontend timers. Keep mission phase, observed physical state, and demo outcome separate.

Implement the documented operator command semantics: status, arm, start, supervised mode, halt, reset, and quit/shutdown where applicable. Scope confirmations and actions to the current mission, epoch, stage, and authoritative state. Expose additional device actions only where a validated Ground API and current policy permit them. Do not add a joystick, raw motor editor, arbitrary coordinates, or bypass/force-enable controls.

Respect these project facts and policies:

- Hardware is Go2 PRO, Tello EDU, and a Pi mounted on the dog. Vision is xAI Grok; the verified model ID is configurable.
- Ethernet is the current dog transport. Wi-Fi requires its own acceptance; there is no automatic handover during a run. Display tether constraints and independent dog, Tello, internet, and Pi-data-path readiness.
- Directional drone control is an unresolved real capability unless new evidence proves it. Downward camera, venue height, calibration, and proximity thresholds are also verified capabilities, not assumptions. A proposed 4 m profile is not an enabled default. Do not invent a rear camera.
- The dog remains stopped while the drone moves. New drone motion invalidates the previous beacon hold and RSSI comparison context. Dog motion requires a new valid hold and backend checks.
- RSSI is a signal trend in dBm, never meters or proof of arrival. Display noisy, absent, stale, and incomparable windows honestly. Select only dog-planner-approved candidates; Ground does not implement new SLAM or obstacle avoidance.
- Handoff to dog vision requires the same current target track. Ambiguous or mismatched people require review, without biometric identity claims.
- Goal completion requires two separately valid measurements: dog-target range and drone horizontal offset. Altitude and obstacle clearance are different quantities. Unconfigured thresholds and missing evidence remain unresolved.
- Goal reached does not mean landed. Unknown landing retains recovery-required status and blocks another ordinary run.
- Arming is explicit and scoped. Reset is backend-verified and returns disarmed; browser reload, reconnect, a modal dismissal, or a late model reply cannot clear a fault.
- Accepted commands are not completed commands. Show submitted, accepted, running, completed, rejected, timed out, and unknown only where supported by evidence. Do not automatically repeat takeoff or motion after an ambiguous timeout.
- Protocol `2.0-draft` is distinct from the legacy Python v1 contract. Keep a versioned bridge; do not silently alter shared signatures.
- The log requirements are provisional pending the team's final list. `contracts/example-events.jsonl` is a catalog of independent synthetic examples, not a valid mission replay.

## 6. Streaming, actions, evidence, and configuration

Create a documented UI API contract based on real runtime capabilities. Include session snapshots, capabilities/readiness, typed operator actions, command status, events, evidence, runs, settings validation, and simulation controls as needed. Clearly label endpoints that you introduce; proposed teammate endpoints are not existing integrations.

Backend action handlers must revalidate mission/epoch/stage, permissions, current state, capability, evidence age, and command lease at execution time. Use idempotency to prevent double-clicks, retries, or multiple tabs creating duplicate operations. Serialize ordinary control through the existing owner while giving halt its priority path. A generic busy flag, model wait, or full ordinary queue must not block halt.

Use a backend snapshot plus a monotonic journal cursor for streaming. Detect gaps/duplicates, reconnect with bounded backoff, and resynchronize from an authoritative snapshot when necessary. Respect per-publisher sequence semantics on device envelopes. Show last update and stale state. Never replay a mutating command automatically after reconnect.

Expose the correlation needed to inspect an action: message/mission/epoch, command/request/frame/track, beacon/map/camera epochs, timestamps, validation results, and reason codes. Provide a human-readable event view and a structured inspector. Bound event buffers, paginate history, and throttle high-rate rendering without dropping journal records.

Display real images or clearly marked simulation fixtures. Show front/downward/dog feeds only when supported. Each frame needs capture time, age, camera, epoch, and validation status. Associate overlays with their exact frame. When streaming video is unavailable, display timestamped snapshots; do not imply they are live video. Maps require real planner/map data; otherwise explain what is missing and show the available candidate list.

Serve artifacts through constrained backend identifiers, with path containment, type/size checks, and source validation. Do not expose arbitrary filesystem reads. Redact keys/tokens from UI, errors, configuration exports, and logs. Bind locally by default and enforce origin/session protections for commands and streams. Keep secrets server-side. Do not expose a public unauthenticated robot-control endpoint.

Configuration should cover only documented settings: profiles, transport, device modes, model/prompt identity, cameras, budgets, leases, evidence age, calibrated limits, and proximity thresholds. Validate on the backend, explain null/unset fields, and gate edits that cannot apply during a mission. Include effective configuration and provenance in each run.

## 7. Implementation and verification

Proceed from repository inspection to implementation; do not stop after producing a plan or static mockup. Use this order:

1. Inspect sources and current integration gaps; write the 32-row coverage matrix and a concise architecture note.
2. Build the application shell, typed data boundary, Python bridge, and first complete simulated mission.
3. Connect remaining operational surfaces and existing providers. Show missing real capabilities as blocked.
4. Add runs, evidence inspection, metrics, rehearsals, and task coverage.
5. Verify the complete browser → API → Ground service → event → browser loop, then refine usability.

Simulation must support an ordered happy path and meaningful fault scenarios: stale frame, slow/late Grok, unavailable controlled motion, moving beacon, old beacon epoch, noisy/empty RSSI, blocked planner, wrong target, missing proximity evidence, rejected/expired dog command, link loss, and goal reached with unknown landing. Provide start, inspect, and reset controls; replay remains read-only.

Write meaningful tests for the new integration: start/arm flow, duplicate start, halt during pending vision/device work, stale confirmation/epoch rejection, stream reconnect/resync, stale evidence rendering, command ACK distinctions, missing thresholds, unknown landing, and path containment. Confirm no hardware calls occur in simulation and that UI reload/reconnect cannot duplicate workers or commands. Test keyboard access and narrow layouts. Inspect the running UI in a browser at desktop and tablet sizes, including failure states.

Run frontend type checking, linting, production build, relevant Python checks, and affected existing tests. Use repository simulation/quality commands where applicable. Record actual results and distinguish pre-existing failures from regressions. Do not claim hardware validation from fixtures or offline tests. Do not operate real hardware as part of implementation verification.

Deliver source code, dependency lockfiles, example configuration without secrets, the coverage matrix, API/architecture notes, exact PowerShell startup commands, and a short operator guide. Prefer one documented development command that starts both local services and cleans them up correctly. Ensure offline runtime assets such as fonts are bundled.

Finish with a concise report of what works, which tasks are covered, how to launch and run the rehearsal, checks actually performed, and exact remaining live integration blockers. Build a usable Ground operator application whose visible behavior is backed by runtime evidence.
