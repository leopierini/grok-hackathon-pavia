# Ground station — 32 implementation assignments

Status: implementation specification, not implemented software or completed tests. All checkboxes are intentionally open. The deliverable is this single task file; executing the assignments will create the application.

Read with [ground.md](ground.md), [plan.md](plan.md), and [tasks.md](tasks.md). This roadmap covers **only Person 4: Ground Station and Integration**. Dog, drone, and Grok internals remain other teammates' work.

## 1. Scope, precedence, and known setup

- Build one local Python 3.11 application with a responsive operator console, one incident at a time, fixed adapter calls, evidence checks, logs, metrics, and recovery controls.
- The dog is the photographed **Unitree Go2 PRO**; older plan text saying edition unknown is superseded by this confirmed identification.
- Dog connection must support both **Ethernet and Wi-Fi profiles** behind the same DogPort. Ethernet is the current default; its cable stays connected throughout an Ethernet run.
- The back enclosure is a router whose networking currently does not work. A Wi-Fi profile in code does not prove repaired or operational hardware.
- The robot uses onboard power; no additional external power cable is required for the described setup. Do not invent a PoE dependency or battery specification.
- Drone is **Tello EDU**, controlled by the team's confirmed **DJITelloPy**, `from djitellopy import Tello`, inside the drone adapter. Ground never creates a second Tello client.
- Baseline drone networking is its Wi-Fi AP. Later firmware-specific alternatives require their own acceptance; avoid the older blanket claim that every EDU station-mode video path is impossible.
- Laptop must maintain dog control, Tello Wi-Fi, and Grok internet simultaneously. No automatic transport handover or mid-run radio switching.
- Default real flight tier is floor; stationary-pad and carried-pad tiers need separately recorded physical acceptance, including existing router/antenna/cable clearance.
- Workflow: input photo → dispatch assessment → prepared dog route → stopped arrival confirmation → dog frame/view assessment → optional preflight/readiness/inspection → grounded evidence → resolution/report.
- The drone lands before the remote final reasoning call. Dog motion remains locked through flight and physical recovery.
- RSSI homing, maps/SLAM, raw motion from Grok, autonomous return landing, voice, web frontend, external alert delivery, and drone-first patrol are excluded.

Precedence: latest explicit user constraints above, unchanged external contract v1.0 in plan.md §6, then ground.md's detailed implementation decisions. Preserve external signatures; a newer hardware fact does not authorize silently editing shared robot types.

The Resume Changer backend references were used for **assignment structure only**: especially `github_integration_plan/task.md`, with `docs/project-plan.md` and UI task plans as secondary examples. Their product logic, Node/Next.js dependencies, secrets, CI requirements and sequential workflow do not transfer here.

## 2. The dependency graph and dispatch gates

```text
Task 01 — reviewed, merged, tested
              |
    refs/tags/ground-foundation-v1
              |
     Tasks 02–10, in parallel
       (no peer dependencies)
              |
     senior merges and runs Gate B
              |
       refs/tags/ground-base-v1
              |
     Tasks 11–32, in parallel
       (no peer dependencies)
              |
     senior merges and runs Gate C
```

**Task 01:** depends only on the senior-approved robot repository baseline. It establishes the common contracts, executable harness, root tooling and extension seams.

**Tasks 02–10:** depend **only on Task 01**. Each must import the kernel/frozen types and inject Task 01 doubles for all peer services. Do not import another Task 02–10 implementation, cherry-pick its branch, or wait for it.

**Tasks 11–32:** depend **only on the reviewed merged Tasks 01–10 baseline**. They use BaseServices Protocols and seeded inputs/doubles, never another Task 11–32 provider. A task that accepts a prior-stage result tests with a frozen fixture; it does not need that prior stage's implementation.

Development independence does not mean a partially merged application may fly. Missing mandatory stage policies fail closed. Final complete-product simulation is the **senior's post-merge Gate C**, outside the independent assignments; Task 32 is not a hidden dependency on all previous tasks.

The senior creates the immutable local tags only after gates pass. Juniors never create, move, or force-update those tags. Record their resolved commit SHAs; do not substitute a moving main tip or unfinished peer branch.

This is a fine-grained parallel backlog, not a promise that 32 reviewed deliverables and hardware acceptance fit into one person's 30-hour sprint. Dispatch multiple agents after each gate and preserve the minimum safe vertical demo if the event deadline requires narrower physical scope.

## 3. Repository and new-worktree rule

The current `re_changer` checkout stores these documents as reference. **Implement in the robot Git repository that the user connects to Cursor or explicitly identifies. Do not assume `AyushGahtori/resume-changer` is the robotics implementation repository.**

Before any task, set these values to actual approved absolute paths/ref; placeholders are not runnable defaults:

```powershell
$RobotRepo = '<absolute path to the user-connected robot repository>'
$WorktreeRoot = '<absolute directory reserved for robot task worktrees>'
$ApprovedBase = '<senior-approved starting commit/ref for Task 01>'
git -C "$RobotRepo" rev-parse --show-toplevel
git -C "$RobotRepo" remote -v
git -C "$RobotRepo" worktree list
```

Verify repository identity against the user's selected GitHub repository before editing. Check the intended branch/path for existing work; never overwrite it. Each card has its own exact branch and worktree command. All worktrees share that verified Git repository, even when their folders are outside the primary checkout.

In Cursor use the card's `git worktree add` command. In Codex, prefer managed `create_worktree` when available, using the same repository, branch, and resolved base commit. Verify the result rather than assuming a tool used the correct base.

Do not reset/clean another checkout, force-replace a branch, delete a peer worktree, globally reformat source, or pull unrelated commits to resolve a missing interface. No task pushes directly to main. Prepare a focused commit/PR through the project's authorized workflow after checks pass; review and merge remain separate.

The research files are currently local/uncommitted in the reference checkout. Before dispatching Task 01, the senior makes this task file and the three source documents available in the robot repository or an explicitly mapped reference location. Before later dispatch, those documents and the kernel must be reachable from the frozen baseline; agents must not rely on untracked files from another worktree.

## 4. Linear coordination in every task

User's intended location: **Hackathon → Projects → Ground Station and Integration**. These are display labels; actual workspace/team/project IDs and status names were not verified in this planning session. No Linear issues have been created or synchronized by this document.

Use Cursor's connected Linear tools to inspect the actual workspace and select the correct project before mutating it. Each card uses stable local key `GROUND-NN`; it is not a claim that a Linear issue with that exact identifier already exists.

Search for the card key and title within the verified project; prefer the matching existing issue. If none exists, create one only within the user-authorized project workflow and verified project. Do not guess an issue ID, create duplicates in another team, or overwrite another task's issue.

At start set the actual equivalent of In Progress and record branch, baseline SHA, scope and dependency gate. At handoff attach actual test/simulation results and PR/commit when available; use a review status while review is pending. Mark Done only after that project's real completion requirements are satisfied. Add task prerequisites as actual issue relations when verified, rather than inventing IDs.

If the connector is unavailable, continue code when the Git prerequisites are satisfied. Record **Linear sync pending** with the intended project, local task key, branch, SHA, state and evidence in the owned handoff. Do not claim a remote update succeeded. Do not commit tokens or secret-bearing URLs. Reconcile the pending record when authorized access becomes available.

## 5. Ownership and additive extension mechanism

Task 01 alone owns root packaging, shared entry points, kernel contracts, extension discovery, quality tooling and shared fixture builders. It seeds every required seam now; later tasks must not modify these shared files in parallel.

Each task NN owns only:

```text
patrol/ground/extensions/gNN/manifest.json
patrol/ground/extensions/gNN/implementation.py   (and private helpers under gNN/)
tests/ground/gNN/**
fixtures/ground/gNN/**
handoff/ground/gNN.md
```

Task 01 additionally owns the shared foundation paths. Task 32 additionally owns `demo/script.md` because its assignment owns the reproducible rehearsal/runbook. No later card edits shared `__init__.py`, a global registry, pyproject, requirements, source docs, another task's tests/fixtures, or another person's robot/Grok package.

Use namespace packages or existing empty package initializers so new owned directories do not require shared import edits. No root requirements change is allowed after Task 01 inside a parallel batch; dependency changes go to the senior's coordinated baseline update. Ground's pinned offline dependency set includes pytest, Ruff, mypy, prompt_toolkit and Pillow; pytest-asyncio is optional if the foundation chooses asyncio.run-based tests instead.

Fixed manifest example:

```json
{
  "schema_version": "ground-task-v1",
  "task_id": "GROUND-11",
  "slot": "feature.incident_input",
  "factory": "patrol.ground.extensions.g11.implementation:create",
  "scenario_factory": "patrol.ground.extensions.g11.scenarios:cases"
}
```

The scenario module is another private file under the owning gNN directory. Task 01's loader discovers manifests automatically in stable task-ID order. It rejects duplicate ownership, unknown slots, mismatched versions, path escapes and arbitrary executable command strings. This is a small static application composition mechanism, not a general plugin platform.

The loader never grants safety permission based on ordering or arbitrary plugin priority. The workflow calls fixed named slots in the sequence below. Same-batch code imports only shared contracts, never a neighboring gNN implementation.

## 6. Frozen internal interfaces to materialize in Task 01

External robot types/factories remain exactly as plan.md §6. Ground-internal names below live in `patrol/ground/kernel/contracts.py`; they are distinct from the robot contract and must not leak vendor types.

| Type | Frozen minimum fields/meaning |
| --- | --- |
| `Ticket` | `mission_id: str`, `epoch: int`, `stage_id: str`; immutable identity for every action/result/confirmation. |
| `GroundError` | `code: str`, `detail: str`, `recovery_required: bool`; code from a declared allowlist, never a silent success. |
| `FeatureRequest` | `kind: stage|command|guard|projection|diagnostic`, `name: str`, `ticket: Ticket|None`, `payload: Mapping[str, object]`. |
| `FeatureResult` | `status: ok|blocked|failed`, `data: Mapping[str, object]`, `events: tuple[GroundEvent,...]`, `error: GroundError|None`. |
| `GroundEvent` | `kind: str`, `ticket: Ticket|None`, `payload: Mapping[str, object]`; exact event allowlist frozen by Task 01. |
| `SessionSnapshot` | phase, trusted incident, epoch/stage, modes, transport, arming, arrival/readiness, evidence, decisions, outcome, flight/recovery locks; immutable. |
| `GroundSettings` | normalized plan configuration plus separate `dog_transport: ethernet|wifi`, profile identity, runtime caps and private adapter mappings. |
| `IncidentInput` / `AdmissionResult` | Raw image path, trusted zone/target, optional capture time and simulation flag; admission returns an accepted Incident or typed rejection, never motion permission. |
| `OperationResult` | operation/ticket, status `completed|failed|timeout|cancelled`, value/error, pending flag, start/end UTC and monotonic times. |
| `EventRecord` | sequence, UTC/elapsed time, mission/ticket/state, event name, trusted zone/target, modes, safe structured data. |
| `SimulationCase` | task/case IDs, seed, setup, scripted stimuli/barriers/faults, expected outcomes/forbidden calls, teardown assertions. |
| `SimulationReport` | actual case results, failures, assertion counts, modes, trace, artifact paths and no-live-call evidence; examples are never measured hardware results. |

All factories are synchronous, side-effect-free construction. Async operations must not start until explicitly invoked. Protocol method signatures below are frozen; Task 01 supplies concrete typed argument/return definitions, fixtures and rejection rules before publishing the foundation tag.

| Slot / owner | Interface and required public operations |
| --- | --- |
| kernel / 01 | `Clock.monotonic()`, `utc_now()`, `async sleep(seconds)`; real/manual variants; authority `require_current(ticket)`, `latch_cancel(reason)`; retained-task registry. |
| `base.config` / 02 | `ConfigPort.load(path, *, modes, scenario) -> GroundSettings`; `redacted(settings) -> Mapping`. |
| `base.state` / 03 | `StatePort.open(incident, settings) -> SessionSnapshot`; `apply(event, *, expected_ticket) -> SessionSnapshot`; `snapshot() -> SessionSnapshot`. |
| `base.journal` / 04 | `async open(run_id, output_root)`; nonblocking `emit(record)`; `async flush()`; `async publish(summary)`; `async scan(output_root)`; `async close()`. |
| `base.executor` / 05 | `async run(name, ticket, factory, *, limit_s) -> OperationResult`; `pending() -> tuple`; `async collect(*, deadline)`. Operation factory receives frozen `RunContext`. |
| `base.evidence` / 06 | `async validate(frame, *, expected_source, zone, mode, output_root, interval) -> EvidenceResult`; phone input and live rules explicit. |
| `base.console` / 07 | `parse(text) -> Command`; `async commands() -> AsyncIterator[Command]`; `async confirm(wait_spec) -> ConfirmationResult`; `write(message)`; `async close()`. |
| `base.adapters` / 08 | `async build(settings, output_root, *, resolver)`; `async connect(component)`; `async status(component)`; `async invoke(component, method, args, *, ticket, context)`; `async close()`; exactly one owner. |
| `base.workflow` / 09 | `async load(raw: IncidentInput) -> AdmissionResult`; `start(incident) -> MissionHandle` schedules at most one mission; `snapshot()`; `async join(handle)`; static feature-slot/command routing. |
| `base.safety` / 10 | synchronous `request(reason, ticket) -> SafetyHandle`; `async observe(handle, *, deadline) -> SafetySnapshot`; `async reset(recovery)`; `async shutdown(reason)`. |
| every feature / 11–32 | `create(services: BaseServices) -> FeaturePort`; `async FeaturePort.execute(request: FeatureRequest) -> FeatureResult`. |

Base provider factory shape is `create(kernel: KernelContext, peers: ServicePorts) -> <its Port>`. BaseServices/ServicePorts expose the above Protocols, not concrete gNN classes. Task 01 supplies explicit test doubles for every port and a fixed wiring graph. Constructors do not call peers; the workflow may request safety, but safety uses kernel cancellation/task primitives and device ports directly, never the workflow implementation.

BaseServices exposes named config/state/journal/executor/evidence/console/adapters/workflow/safety ports plus `kernel`. Shared test and utility capabilities are reached through `kernel.clock`, `kernel.io`, `kernel.authority`, `kernel.tasks`, `kernel.features`, `kernel.result_validation`, and `kernel.simulator`; do not invent task-private peer-service access paths. Task 01 freezes the helper Protocols, including bounded IO fault injection, result validation, `features.get(slot)` and `async simulator.run(case, *, providers, clock_mode) -> SimulationReport`. The simulation command always has test peer builders available without importing another contribution.

Feature providers return proposed events in FeatureResult. Workflow applies them through StatePort after checking ticket/cancel authority; wording in cards such as “StatePort-applied” means this guarded commit path, not permission to mutate private global state. Safety may always latch cancellation immediately through kernel authority. Observer projections cannot clear faults or grant motion.

Task 01 freezes enum values, payload key validation and typed aliases below. Dataclass annotations are not automatic validation. Unknown keys/types at a boundary are rejected deliberately; no truthiness coercion of strings into booleans.

## 7. Feature slot and payload table

Common payload keys: `incident: Incident`, `settings: GroundSettings`, `snapshot: SessionSnapshot`, `operation: OperationResult`, `frame/ground/aerial: Frame|None`, `command: Command`, and `interval: CaptureInterval`. Request tickets and authoritative cancellation state are checked independently of payload copies.

| Task | Slot | Exact additional input keys → output data |
| --- | --- | --- |
| 11 | `feature.incident_input` | `image_path`, `zone`, `target`, `captured_at`, `simulated` → `incident`, `provenance`. |
| 12 | `feature.dispatch` | `incident`, `operation` containing DispatchDecision/error → `decision`, `continuation` (investigate/ignored/unresolved). |
| 13 | `feature.prepare` | `incident`, `settings`, `snapshot` → bounded preparation, `dog_status`, `may_route`. |
| 14 | `feature.route_result` | `incident`, `operation` containing RouteResult, `dog_status` → `route`, `may_wait_arrival`; never confirmed arrival. |
| 15 | `feature.arrival` | `incident`, `route`, `wait_spec` → `arrival_confirmed`, `arrival_monotonic`, `arrival_method`; null timing if unconfirmed. |
| 16 | `feature.dog_frame` | `incident`, `arrival`, `snapshot` → bounded capture, `ground`, `interval`, `validation`. |
| 17 | `feature.ground_view` | `incident`, `ground`, `operation` containing GroundDecision → `decision`, `continuation` (resolve/preflight/unresolved). |
| 18 | `feature.preflight` | `check: initial|final`, `incident`, `snapshot`, `readiness` (null before confirmation) → `inspection_request`, `checks`, `may_confirm`, `may_inspect`. |
| 19 | `feature.flight_ready` | `incident`, `initial_preflight`, `wait_spec` → `readiness`, `confirmation_method`; never takeoff itself. |
| 20 | `feature.inspection_result` | `incident`, `inspection_request`, `operation` containing InspectionResult → `aerial`, `flight_state`, `continuation`, `recovery_required`. |
| 21 | `feature.resolution` | `incident`, `ground`, `aerial`, `operation` containing Resolution → `resolution`, `outcome`. |
| 22 | `feature.report` | `incident`, `resolution` (optional on failure), `outcome`, `snapshot`, `metrics` → `report`, `summary`, `wording_source`, `publication_status`; this provider owns the single wording call and single base-journal publication. |
| 23 | `feature.status` | `snapshot`, `pending_operations`, `writer_health` → `display`, safe status fields. |
| 24 | `feature.transport` | `settings`, `snapshot`, `acceptance`, `tether` → `ready`, `checks`, selected-profile metadata. |
| 25 | `feature.metrics` | `events`, `snapshot`, `evaluation` (optional saved manifest) → `metrics`, denominators and unavailable reasons. |
| 26 | `feature.restart` | `prior_runs`, `current_device_status`, `ownership` → `may_arm`, `recovery_required`, incomplete-run evidence. |
| 27 | `feature.redaction` | `record`, `sensitive_values` (private injected list) → `safe_record`, rejected-field diagnostics. |
| 28 | `feature.persistence_fault` | `writer_health`, `fault_event`, `snapshot` → `block_actions`, `request_safety`, reportable persistence status. |
| 29 | `feature.console_shutdown` | `command`/`input_event`, `snapshot` → shutdown intent and observed cleanup result, never motor cut. |
| 30 | `feature.adapter_probe` | `resolver`, `settings`, `acceptance_evidence`, `probe_mode` → per-component contract report; actual public-factory fake probes require explicit opt-in, and physical evidence is supplied by adapter owners. |
| 31 | `feature.network_diagnostics` | `settings`, injected `probe`, `diagnostic_mode` → read-only route/link/uplink findings, never network repair. |
| 32 | `feature.rehearsal` | `scenario`, `seed`, `simulation_mode`, `output_root` → rehearsal report, honest simulation labels and runbook artifacts. |

The kernel seeds every listed input/output shape, including completion and fault envelopes. Providers may add private internal helpers, but cannot rename these keys or make another same-batch output implementation a compile-time dependency. Task 01 centralizes the final exact slot strings for any agent-drafted synonyms in cards.

## 8. Fixed orchestration order and policy precedence

Task 09's workflow performs adapter/Grok operations through base ports and invokes feature policies at their frozen slots. No action occurs twice because both the workflow and a feature attempt it.

1. Startup: scan incomplete runs and ownership; invoke restart policy; remain disarmed if incomplete/unknown.
2. `workflow.load(IncidentInput)` invokes 11 in a pre-admission context with `ticket=None` and no motion capability. Recheck the idle/no-active-mission condition and kernel generation after validation; only then commit its accepted Incident with `StatePort.open`. Rejected input creates no active mission. The console may now arm this loaded incident. `start(incident)` consumes its one-use permission, records the original monotonic start, and creates a current mission ticket. Concurrent load/start attempts cannot replace an active incident. Pre-admission events are committed by the input controller, not by a feature mutating state.
3. Run `assess_incident` once through executor/gateway; classify via 12. Dismiss means no preparation/route/flight.
4. Check transport policy 24; invoke 13 for bounded `prepare` and readiness; only then run one bounded `dog.run_route` through the workflow.
5. Classify route result via 14; invoke 15 for exact current-zone arrival confirmation.
6. Invoke 16 for bounded dog capture/validation; run `assess_ground_view` once; classify via 17.
7. If inspection needed: transport guard 24; acquire and retain the dog motion/flight lock; initial preflight 18; readiness wait 19; final preflight 18 with fresh statuses; kernel final cancellation check before invoking one `drone.inspect` through the workflow. Successful initial check returns `may_confirm=True`, `may_inspect=False`; only a successful final check with the current readiness token can return `may_inspect=True`. Failure never releases the lock automatically; verified recovery/reset does.
8. Classify inspection through 20; grounded/valid evidence is mandatory before final reasoning. Unknown landing takes fault precedence over a usable frame.
9. Run `resolve_incident` once; classify via 21. Project metrics through 25, then invoke 22 for its single bounded wording call from a valid verdict and one safe report/summary publication. For non-verdict terminal paths, 22 emits a factual status report without calling wording.
10. Project status through 23; journal through base04 and sanitizer27. Metrics are computed before final summary publication. Missing optional projections never create success facts.
11. Any storage fault goes immediately to a kernel no-new-action latch, then policy28/safety10. Halt from console never waits for a normal policy or filesystem operation.
12. Ctrl+C/EOF/quit integration29 requests base10 lifecycle; reset uses base10 after verified physical recovery and worker quiescence.

Normal operation timeouts do not authorize automatic retries. Recovery commands use separate bounded budgets. Never run a partial production pipeline with permissive seeded policies; seeded doubles exist only behind explicit simulation/selftest paths.

## 9. Automated simulation contract for every task

Task 01 provides **behavioral simulation**, not physics: scripted statuses, readable images, operator events, results, fault injection, logical time, named barriers and observable call traces. It does not simulate rotor dynamics, certify obstacle avoidance or prove real radio behavior.

Every task adds its own `scenarios.py:cases` and fixture files. The fixed harness runs the actual owned provider with frozen peer doubles. Assert both expected outputs and forbidden side effects. A scenario that only prints expected answers is not a test.

```powershell
python -m pytest tests/ground/gNN -q
python -m patrol.ground.sim --task NN --case all --seed 0 --report artifacts/task-NN/simulation.json
python -m patrol.ground.quality --task NN
git diff --check
```

Task 01 implements these commands before publishing its gate. The quality command discovers task-owned files and runs pinned Ruff/type/import-boundary checks without editing source. Requirements and gate scripts must exist; until Task 01 lands, their presence is a deliverable, not an assertion.

Simulation reports include task/case/seed, actual observed outcomes, assertions, forbidden-call checks, clock mode, trace, failures and teardown status. Failure exits nonzero. No credentials, paid APIs, real robot SDK imports, sockets or real Linear requests in ordinary simulations.

Use manual clock plus matching manual waits for deterministic policies; do not compare virtual absolute RunContext deadlines to real hardware clocks. Use real time.monotonic for public adapter smoke tests. The fake 0.5-second halt recognition target gets a separate bounded wall-clock check; virtual time alone cannot prove responsiveness.

Release deliberately stuck tasks/barriers in teardown and await them. Test that no worker remains able to issue commands before reset/replacement. Include result/halt/deadline races in both orders and same-turn release. Record physical checks separately as documented, simulated or physically demonstrated.

Neither tests nor simulations can establish correctness in every possible real-world situation. Each card lists a minimum risk matrix and explicitly requires the implementer to identify more applicable edge cases, add tests, and explain any remaining untested limitations.

## 10. Senior integration gates and completion evidence

**Gate A — after 01:** all shared types/imports, ownership manifest, real/manual clocks, fake fixtures, per-task harness, CLI/test commands and fail-closed defaults work without any peer implementation. Publish `refs/tags/ground-foundation-v1` at the reviewed merged SHA.

**Gate B — after merged 01–10:** instantiate the real base services together; no peer mock accidentally replaces a production base provider. Run seeded stage policies through complete base workflows for all shared plan scenarios, halt/link/storage failures and reset races. Confirm offline imports, exact v1 signatures, console responsiveness and safe missing-feature rejection. Publish `refs/tags/ground-base-v1` only after this passes.

**Gate C — after merged 11–32:** load all real Ground providers and use fake robot/Grok boundaries. Run the exact all-fake production command, each shared scenario, both dog transports with acceptance metadata, result/halt races, unknown landing, persistence failure, interrupted startup, Ctrl+C/EOF and reset. Require all intended feature contributions, no stage-policy doubles, actual discovered test counts, and complete artifacts. This is senior integration work, not a dependency assigned to Task 32.

Then substitute actual teammate factories/fakes, followed by one deliberately selected real adapter at a time. The drone owner's pinned-SDK acceptance must prove any no-retry wire claim; a Ground fake marker is insufficient. Adapter owners must supply freshness and worker-quiescence evidence absent from the frozen status fields. Ethernet routes/tether, dog Wi-Fi, simultaneous links, stops, floor flight and optional pad/carriage remain distinct physical acceptance items.

The real command starts disarmed. No routine CI test takes off, walks a robot, calls a paid model or changes Linear. Network diagnostics are read-only and explicit; they do not repair the router or change firewall/routes.

Every task's handoff contains baseline SHA, branch/worktree, owned files, frozen interfaces used, implemented behavior, tests/simulations actually run, new edge cases found, observed limitations, Linear mapping/status or sync-pending record, and review/PR link when available. Do not mark a task or issue Done on an unexecuted test or simulated hardware claim.

## 11. Task index

| ID | Deliverable | Prerequisite |
| --- | --- | --- |
| 01 | Kernel, frozen interfaces, loader and simulation foundation | Approved starting baseline |
| 02 | Configuration and normalized profiles | 01 only |
| 03 | Session reducer and admission fencing | 01 only |
| 04 | Ordered event journal and artifacts | 01 only |
| 05 | Bounded operation execution | 01 only |
| 06 | Evidence and provenance validation | 01 only |
| 07 | Async command/confirmation transport | 01 only |
| 08 | Adapter gateway and lifecycle | 01 only |
| 09 | Fixed workflow/composition | 01 only |
| 10 | Independent halt/reset/shutdown primitives | 01 only |
| 11 | v2 message envelope and compatibility facade | Merged 01–10 only |
| 12 | Capability reports and honest feature arming | Merged 01–10 only |
| 13 | Drone observation intake and height reference | Merged 01–10 only |
| 14 | Camera epoch, frame provenance, and image bytes | Merged 01–10 only |
| 15 | Vision sampling schedule and stale-frame drop | Merged 01–10 only |
| 16 | xAI Grok decision validation without motor authority | Merged 01–10 only |
| 17 | Approved drone primitives and bounded search | Merged 01–10 only |
| 18 | Drone acknowledgements, dedup, and unknown landing | Merged 01–10 only |
| 19 | Stable beacon hold and beacon epoch | Merged 01–10 only |
| 20 | Dog navigation health and safe local candidates | Merged 01–10 only |
| 21 | Raspberry Pi RSSI windows measured on the dog | Merged 01–10 only |
| 22 | RSSI homing across safe dog candidates only | Merged 01–10 only |
| 23 | Approved dog commands, leases, and halt | Merged 01–10 only |
| 24 | Dog acknowledgements and rejected commands | Merged 01–10 only |
| 25 | Dog-camera acquisition and RSSI handoff | Merged 01–10 only |
| 26 | Dog range and drone horizontal proximity | Merged 01–10 only |
| 27 | Demo goal separated from landing recovery | Merged 01–10 only |
| 28 | Halt, link loss, stale evidence, and lease expiry | Merged 01–10 only |
| 29 | Correlated v2 journal and proposed team logs | Merged 01–10 only |
| 30 | Ethernet, Wi-Fi, and Pi data-path readiness | Merged 01–10 only |
| 31 | Demo timing metrics with explicit gaps | Merged 01–10 only |
| 32 | Offline drone-first rehearsal and runbook | Merged 01–10 only |

The numbered cards below are individually assignable. Each contains its worktree command, Linear rule, at least ten implementation scope items, named tests, specific edge cases, automated simulation and completion evidence.

Tasks 01–10 below stay the foundation and keep their original cards. Tasks 11–32 are the 4 November 2026 drone-first demo. Their sequence, v2 slots, and JSON logs are specified after Task 10. Section 7 still names the retired phone-incident slots; those rows are not the active demo.

---

## Task 01: Freeze the Ground kernel, interfaces, extension loader, and simulation foundation

**Local task key:** GROUND-01. **Nature:** Project foundation and executable collaboration contract.
**Outcome:** Every later task can import stable ports, create its own worktree, and run its own automated simulation without peer implementations.
**Dependency boundary:** No numbered-task dependency; use only the senior-approved starting robot-repository baseline.
**Owned contribution slot:** `kernel.foundation`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = $ApprovedBase
$TaskTree = Join-Path $WorktreeRoot 'ground-01'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-01 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-01 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g01.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] plan.md §§5–7 and 11: package boundaries, frozen robot contract, factories, scenarios.
- [ ] tasks.md shared rules and Person 4: Ground ownership and private stubs.
- [ ] ground.md §§5–10 and 15: runtime architecture, state names, cancellation, test seams.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g01/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g01/**`, `fixtures/ground/g01/**`, and `handoff/ground/g01.md`.
- [ ] Additional ownership: root packaging/quality/CLI, patrol/contract.py, patrol/ground/kernel/**, shared testing builders and the fixed loader. Publish no tag yourself.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] The three robotics documents and the senior-approved robot-repository baseline.
- [ ] User-confirmed Go2 PRO, dog Ethernet default/alternate Wi-Fi, Tello EDU Wi-Fi via DJITelloPy.
- [ ] The complete frozen service/feature tables and batch graph in this task file.

Outputs:
- [ ] Unchanged patrol/contract.py v1.0 plus Ground-internal contracts and kernel utilities.
- [ ] A fixed extension loader and minimal executable per-task simulation/test entry points.
- [ ] A reviewed foundation baseline with seed doubles, fixture builders, and fail-closed missing-provider behavior.

### Exact integration requirement

Materialize the kernel contracts, seed interfaces and exact shared entry points in sections 5–9; preserve plan.md external contract v1.0 unchanged.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Initialize Python 3.11 packaging, test discovery, Ruff, type checking, and the explicit offline simulation entry point.
- [ ] Copy the exact external robot contract; freeze Ground tickets, events, errors, FeatureRequest/Result, BaseServices and service Protocols.
- [ ] Declare every base slot, feature slot, operation, command, payload key, lifecycle guard, and extension schema listed in this document.
- [ ] Implement only the small fixed manifest loader, duplicate/version validation, ownership checks, and lazy factory loading.
- [ ] Provide kernel authority for epoch/cancel latches, a retained task registry, and final pre-action identity checks.
- [ ] Provide real and manual Clock implementations; pair manual deadlines with manual waits rather than real-loop absolute timers.
- [ ] Create test-only DogPort, DronePort, and ReasonerPort doubles with truthful simulated flags, trace entries, and tiny readable JPEG builders.
- [ ] Expose named barriers, scheduled completions, fake status changes, filesystem fault seams, and operation-after-halt assertions.
- [ ] Make python -m patrol.ground.sim --task NN --case all load only the selected contribution and kernel test peers.
- [ ] Seed service doubles and feature inputs so any owner can test with every same-batch peer absent.
- [ ] Create shared CLI and fixed stage/command slot declarations; missing mandatory providers refuse live operations instead of pretending success.
- [ ] Publish read-only ownership/config/manifest conventions and a foundation checklist; leave the full coordinator to Task 09.

### Outside this task

- [ ] Do not implement vendor robot adapters, Grok API requests, trajectories, or real network discovery.
- [ ] Do not build all feature policies inside the kernel; test doubles remain explicitly test-only.
- [ ] Do not create or move integration tags before senior review and the documented gate.

### Required edge cases

- [ ] Duplicate extension slot or incompatible contract version must reject the composition before motion.
- [ ] A missing feature cannot become a permissive default; absent optional diagnostics must not enable hardware.
- [ ] A cancelled ticket, old epoch, or expired deadline must fail the final action check.
- [ ] A manifest path escaping its owned directory, duplicate task ID, or arbitrary executable command must be rejected.
- [ ] A manual clock must not generate absolute deadlines for real vendor adapters expecting time.monotonic().
- [ ] Importing the kernel or simulation must not load hardware packages, open sockets, or require credentials.
- [ ] A simulated stuck task must be released and collected in teardown so the test process can exit.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Build a clean temporary project with one synthetic contribution manifest and no other contribution directories.
- [ ] Load its provider and prove the expected slot and schema match the frozen declaration.
- [ ] Run a tiny happy case through seeded device and service doubles; save structured results and zero live-call count.
- [ ] Inject duplicate/missing/version-mismatched manifest cases and verify explicit failures before any device call.
- [ ] Hold a fake operation at a barrier, latch cancellation, release its result, and assert the ticket cannot authorize another action.
- [ ] Advance the manual clock through a deadline and compare trace ordering; separately run a bounded real-clock responsiveness smoke.
- [ ] Force fixture read/write failure and verify the harness reports it as a failure rather than a passing skipped scenario.
- [ ] Release all barriers, collect retained tasks, remove only owned temporary outputs, and assert no worker or socket leaked.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g01/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g01/test_contract.py covering dataclass shape and exact external signatures.
- [ ] Create loader tests for slot uniqueness, schema compatibility, absent providers, and path ownership.
- [ ] Create kernel tests for epoch fencing, cancellation monotonicity, and retained-task collection.
- [ ] Create clock tests proving manual-wait and real-clock paths are deliberately separate.
- [ ] Create simulator tests for meaningful trace assertions, readable JPEG fixtures, and deterministic seed replay.
- [ ] Add import-isolation tests that fail if a real SDK/network call is attempted in ordinary checks.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g01 -q
python -m patrol.ground.sim --task 01 --case all --seed 0 --report artifacts/task-01/simulation.json
python -m patrol.ground.quality --task 01
git diff --check
```

### Completion and handoff

- [ ] The foundation sim command and pytest run from a clean robot-repository checkout without robots, keys, or internet.
- [ ] All service/feature signatures and payload fields in this document have concrete importable definitions.
- [ ] A sample absent provider blocks its operation, while a selected synthetic provider can be tested independently.
- [ ] Root packaging and common CLI files have one owner; future tasks can add manifests without editing registries.
- [ ] The senior has a reproducible gate report before publishing refs/tags/ground-foundation-v1.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 02: Implement configuration loading and normalized connection settings

**Local task key:** GROUND-02. **Nature:** Base service: configuration and path validation.
**Outcome:** Ground receives one immutable validated configuration without guessing paths, transport, model settings, or real capabilities.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.config`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-02'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-02 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-02 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g02.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] plan.md §7: configuration envelope, per-file relative paths, stage deadlines.
- [ ] ground.md §§2–3 and 12: confirmed equipment and dual dog transports.
- [ ] This file's ConfigPort and GroundSettings contract.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g02/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g02/**`, `fixtures/ground/g02/**`, and `handoff/ground/g02.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A ground JSON path plus explicit adapter modes and optional scenario override.
- [ ] Per-module JSON files and references to opaque dog routes/drone profiles.
- [ ] Kernel filesystem/clock seams and synthetic configuration fixtures.

Outputs:
- [ ] ConfigPort.load(...) producing GroundSettings and resolved adapter config mappings.
- [ ] Actionable configuration errors with the offending key/path but no secret value.
- [ ] Redacted configuration input ready for journaling without mutating source files.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Load UTF-8 JSON with bounded file sizes and reject malformed or duplicate conflicting keys.
- [ ] Validate zones, adapter modes, launch tiers, scenario names, positive finite timeout values, and output root.
- [ ] Resolve each relative path against the JSON file that declares it, including nested adapter file references.
- [ ] Preserve opaque route/profile file ownership; resolve their paths without interpreting device trajectories.
- [ ] Keep dog physical transport ethernet|wifi separate from vendor connection_mode LocalSTA|LocalAP.
- [ ] Default current dog transport to Ethernet; represent alternate Wi-Fi as configured but not physically accepted.
- [ ] Require Tello's Wi-Fi transport and record the team's confirmed DJITelloPy choice without importing it.
- [ ] Validate battery threshold presence/range for real flight and retain disabled capability when absent.
- [ ] Produce immutable settings or defensive copies so later callers cannot change another stage's policy.
- [ ] Allow explicit per-adapter fake/real selection and reject any silent replacement of requested real mode.
- [ ] Support the plan's empty fake config/default scenario and resolve example/local config locations predictably.
- [ ] Return full private settings only to intended services and expose a separate redacted view for artifacts.

### Outside this task

- [ ] Do not repair the router, alter operating-system routes, or instantiate adapters.
- [ ] Do not validate flight trajectories or dog motion segments owned by device teammates.
- [ ] Do not import other Tasks 02–10 providers; use kernel doubles for peers.

### Required edge cases

- [ ] NaN, infinity, zero, negative, booleans masquerading as numeric limits, and wrong JSON types are rejected.
- [ ] A dog Ethernet profile must not be inferred merely from the vendor mode name.
- [ ] A valid Wi-Fi profile does not imply physical readiness or bypass arming.
- [ ] Missing optional drone configuration must permit a ground-only fake test without declaring real flight available.
- [ ] Nested relative paths must resolve from their own declaring file rather than the process working directory.
- [ ] Secrets in exception payloads and redacted snapshots must not appear in output.
- [ ] An unknown launch tier, wrong profile map zone, or real-pad/fake-dog combination is rejected before action.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Create a temporary config tree with nested dog/drone/Grok files and a different process working directory.
- [ ] Load it through the real Task 02 provider and compare normalized absolute paths and explicit modes.
- [ ] Switch between Ethernet and Wi-Fi profiles without changing the public factory signature or enabling hardware.
- [ ] Inject malformed JSON, missing keys, nonfinite limits, path resolution failures, and unavailable optional flight configuration.
- [ ] Feed the resulting settings into kernel readiness doubles and verify no implicit real-to-fake or transport fallback occurs.
- [ ] Pass secret-bearing values through the redacted view and assert the report contains only safe metadata.
- [ ] Repeat the scenario with identical seed and shuffled source-key ordering to verify stable normalized output.
- [ ] Close temporary files and assert source configuration was not rewritten.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g02/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g02/test_loading.py for valid nested configurations and output-root resolution.
- [ ] Create parametrized validation tests for enum/type/range boundaries and per-mode required fields.
- [ ] Test empty fake defaults and explicit override precedence without relying on environment residue.
- [ ] Test physical transport versus driver mode as independent fields.
- [ ] Test redacted output and exception messages with synthetic credentials.
- [ ] Test no network/device import occurs while loading settings.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g02 -q
python -m patrol.ground.sim --task 02 --case all --seed 0 --report artifacts/task-02/simulation.json
python -m patrol.ground.quality --task 02
git diff --check
```

### Completion and handoff

- [ ] Configuration behavior is complete using only Task 01 and this provider.
- [ ] Both dog transport profiles can be represented without changing DogPort.
- [ ] No real capability is enabled solely by a missing/default setting.
- [ ] All listed invalid cases fail with stable typed errors and no motion side effects.
- [ ] The normalized result can be injected into the merged base without path or signature changes.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 03: Implement session state, event reduction, and admission fencing

**Local task key:** GROUND-03. **Nature:** Base service: authoritative session lifecycle.
**Outcome:** Exactly one current mission exists, every phase change is legal, and late results cannot advance an aborted or replacement session.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.state`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-03'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-03 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-03 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g03.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] plan.md §§3,6,8: workflow, trusted metadata, state/outcome separation.
- [ ] ground.md §§7–8 and 10: session fields, phase table, stage-scoped commands.
- [ ] This file's StatePort, Ticket, GroundEvent and SessionSnapshot definitions.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g03/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g03/**`, `fixtures/ground/g03/**`, and `handoff/ground/g03.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Kernel session authority and immutable incident/settings data.
- [ ] Typed events with mission, epoch and stage identities.
- [ ] Seeded device/result/confirmation events, independent of real adapters.

Outputs:
- [ ] StatePort.open/apply/snapshot methods with defensive immutable snapshots.
- [ ] Legal transitions, distinct incident outcome and physical recovery state.
- [ ] Admission/confirmation decisions that reject stale or invalid events without side effects.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Implement the exact phase names and permitted transition graph declared in the frozen contract.
- [ ] Keep mission phase, physical snapshots, report outcome, and recovery lock separate.
- [ ] Admit one mission atomically and reject a concurrent or duplicated start request.
- [ ] Use kernel epoch/cancel authority rather than maintaining a competing cancellation generation.
- [ ] Apply only events matching the active mission and stage; retain rejection diagnostics for late responses.
- [ ] Store trusted zone, target and evidence identity independently from model-generated text.
- [ ] Implement one-incident arming permission and invalidate it on halt, reset or session replacement.
- [ ] Track arrival/readiness wait identities without buffering early commands for future stages.
- [ ] Make fault/abort locks monotonic during a session so ordinary success cannot clear them.
- [ ] Expose snapshots sufficient for console/status/metrics without mutable private dictionaries leaking.
- [ ] Maintain explicit event sequence/version checks to prevent duplicate application from changing counts.
- [ ] Provide deterministic event-reduction helpers testable without workflow, safety, journal or console implementations.

### Outside this task

- [ ] Do not call hardware or Grok from a reducer.
- [ ] Do not implement transport input, report wording or filesystem journaling.
- [ ] Do not add reset/status fields to the external robot contract.

### Required edge cases

- [ ] Two starts arriving in the same event-loop turn must produce one admitted mission.
- [ ] A successful old route or model result cannot update a replacement mission.
- [ ] A late grounded result after halt cannot erase a latched physical fault.
- [ ] Wrong-zone, early, duplicate and expired confirmations must remain rejected.
- [ ] A finished timed route alone cannot set arrival_confirmed or a non-null arrival metric.
- [ ] Unknown physical state cannot be normalized to safe booleans.
- [ ] Repeated identical events must not consume permission twice or publish duplicate completion.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Seed an idle session and apply the normal phase events with synthetic incident and statuses.
- [ ] Attempt two starts, duplicate decisions and repeated completion events; assert one mission and one terminal publication.
- [ ] Hold a result ticket, halt the session, then deliver that result and verify no normal phase advances.
- [ ] Reset through a kernel-approved recovery event, create a fresh epoch and deliver old confirmations.
- [ ] Inject captured-image plus unknown-flight state and verify outcome/fault remain distinct and locked.
- [ ] Attempt illegal phase jumps and wrong-zone confirmation while observing the event rejection trace.
- [ ] Replay the exact event stream twice into fresh state stores and compare immutable snapshots.
- [ ] Ensure no live service calls or retained tasks were created by pure reductions.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g03/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g03/test_transitions.py for every allowed phase transition and representative forbidden edges.
- [ ] Test double-start admission and idempotent terminal events.
- [ ] Test stale mission/epoch/stage result fencing.
- [ ] Test arming consumption, wrong/early confirmation and recovery-lock monotonicity.
- [ ] Test route completion versus independently confirmed arrival.
- [ ] Test immutable snapshot behavior and truthful unknown physical state.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g03 -q
python -m patrol.ground.sim --task 03 --case all --seed 0 --report artifacts/task-03/simulation.json
python -m patrol.ground.quality --task 03
git diff --check
```

### Completion and handoff

- [ ] The state provider runs against Task 01 only with no peer provider imports.
- [ ] Normal and failure traces produce the exact documented phase/outcome mappings.
- [ ] Every admitted session has unique current identity and one-use permission.
- [ ] Fault/abort cannot be overwritten by late ordinary success.
- [ ] Consumers can read snapshots without owning or mutating authoritative state.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 04: Implement asynchronous artifacts and the ordered event journal

**Local task key:** GROUND-04. **Nature:** Base service: local persistence.
**Outcome:** Every run has ordered inspectable artifacts, persistence failures remain visible, and disk I/O cannot block halt recognition.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.journal`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-04'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-04 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-04 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g04.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] ground.md §13: directories, JSON Lines schema, writer behavior and summary publication.
- [ ] ground.md §§9,14–15: cancellation, disk failures and restart evidence.
- [ ] plan.md §9: mandatory log fields and honest measurements.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g04/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g04/**`, `fixtures/ground/g04/**`, and `handoff/ground/g04.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Typed EventRecords and summary mappings from kernel callers.
- [ ] A task-owned run output root and injectable filesystem writer.
- [ ] Synthetic slow/full/permission-denied filesystem controls.

Outputs:
- [ ] JournalPort.open/emit/flush/publish/read methods with explicit writer health.
- [ ] Per-mission events.jsonl, summary.json and safe artifact locations.
- [ ] Nonblocking kernel persistence-failure events without invoking workflow or safety implementations.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Create a unique per-mission directory without reusing another run's output.
- [ ] Enqueue small structured events and assign/retain deterministic sequence ordering.
- [ ] Write one complete JSON object per JSONL line through a single bounded writer path.
- [ ] Expose writer failure and queue health rather than losing thread exceptions.
- [ ] Separate enqueue, flush and durable-sync claims in return metadata.
- [ ] Publish summaries through a same-directory temporary file and replacement with honest failure reporting.
- [ ] Preserve original mission errors alongside cleanup/writer failures.
- [ ] Bound event size, queue growth and flush waits while allowing halt to bypass logging backpressure.
- [ ] Implement read-only scanning needed to detect incomplete runs without replaying their actions.
- [ ] Handle partial last JSONL records as incomplete evidence and retain parse diagnostics.
- [ ] Accept an injected event sanitizer; do not implement Task 27's full redaction policy here.
- [ ] Ensure shutdown collects the writer or reports it pending instead of claiming all artifacts were saved.

### Outside this task

- [ ] Do not call dog halt or drone landing from the writer thread.
- [ ] Do not implement complete event redaction or persistence escalation policies owned by Tasks 27–28.
- [ ] Do not add a database, cloud log delivery or external notification.

### Required edge cases

- [ ] Disk full or permission denial before motion must be surfaced through a kernel fault event.
- [ ] A stalled flush cannot prevent the cancellation latch from being set.
- [ ] Queue saturation must follow a documented bounded policy rather than consume unlimited memory.
- [ ] Summary replacement failure must preserve the prior complete file and report failure.
- [ ] A partial JSONL tail cannot be mistaken for a completed mission.
- [ ] Two run IDs or processes cannot overwrite the same run directory silently.
- [ ] Secrets passed to an injected sanitizer must not leak through fallback exception logging.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Open a unique temporary run and enqueue events while a manual writer barrier controls progress.
- [ ] Release writes and verify parseable lines, ordering and expected summary contents.
- [ ] Inject disk-full, permission, closed-stream and rename failures at specific operation boundaries.
- [ ] Fill a bounded queue and request halt through the kernel; observe latch independently from stalled storage.
- [ ] Read an interrupted run with a truncated final line and missing summary without executing any device call.
- [ ] Run a normal shutdown and a stalled-writer shutdown, checking reported completion versus pending status.
- [ ] Repeat the same seeded event script and compare normalized artifact records.
- [ ] Release writer barriers and join owned workers in teardown; retain error evidence in the simulation report.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g04/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g04/test_journal.py for ordered JSONL and event-size/queue limits.
- [ ] Test unique run creation and no silent overwrite.
- [ ] Test flush/replacement failure with injected filesystem adapters.
- [ ] Test partial-tail scanning and missing/corrupt summary metadata.
- [ ] Test halt latency remains independent of blocked writes.
- [ ] Test writer exception propagation and teardown without leaked workers.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g04 -q
python -m patrol.ground.sim --task 04 --case all --seed 0 --report artifacts/task-04/simulation.json
python -m patrol.ground.quality --task 04
git diff --check
```

### Completion and handoff

- [ ] The provider records events without depending on another base implementation.
- [ ] Simulation output distinguishes queued/flushed/published and failed states truthfully.
- [ ] All synthetic persistence failures are observable to the kernel.
- [ ] Ordinary I/O does not run directly on the event-loop path that latches halt.
- [ ] Artifacts remain local, per-run, bounded and parseable under the documented recovery rules.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 05: Implement bounded asynchronous operation execution

**Local task key:** GROUND-05. **Nature:** Base service: stage deadlines and task ownership.
**Outcome:** Every operation has a tracked identity, bounded wait, final cancellation fence, and explicit late/pending-work handling.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.executor`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-05'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-05 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-05 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g05.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] ground.md §9: stage runner, deadlines, halt and thread cancellation limitations.
- [ ] plan.md §6.2: shared cancellation semantics and no motion retries.
- [ ] This file's OperationPort, OperationResult and Clock contracts.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g05/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g05/**`, `fixtures/ground/g05/**`, and `handoff/ground/g05.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A Ticket, operation name, lazy RunContext-to-awaitable factory and stage limit.
- [ ] Kernel real/manual clock, cancellation authority and task registry.
- [ ] Injected operation doubles that complete, fail, hang or ignore cancellation.

Outputs:
- [ ] OperationResult identifying completed, failed, timed-out or cancelled work.
- [ ] Retained operation/task metadata including pending work after the observation deadline.
- [ ] Completion events carrying original ticket identity and timing.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Check current epoch, cancellation and deadlines before constructing a potentially active operation.
- [ ] Create stage RunContext with the original mission Event and min of remaining mission/stage budgets.
- [ ] Use the injected clock for both deadline calculations and waiting in deterministic simulations.
- [ ] Register strong references before scheduling operation work and name tasks for diagnostics.
- [ ] Observe completion, cancellation and deadline without blocking operator input.
- [ ] Recheck the ticket after completion before accepting the value or scheduling any subsequent action.
- [ ] Keep timed-out/cancellation-resistant work tracked instead of assuming cancelling its Future stopped hardware.
- [ ] Expose a quiescence observation over kernel-owned tasks without inventing a robot workers_idle API.
- [ ] Preserve the first failure while collecting cleanup exceptions as separate diagnostics.
- [ ] Provide explicit helper paths for recovery deadlines that do not reuse cancelled normal contexts.
- [ ] Never automatically retry walking, turning, takeoff or inspection.
- [ ] Remove only genuinely completed owned tasks and consume their exceptions to avoid hidden background failures.

### Outside this task

- [ ] Do not encode mission decisions or phase-specific result policies.
- [ ] Do not implement hardware SDK thread control or kill threads.
- [ ] Do not import the safety/workflow provider to handle an operation timeout.

### Required edge cases

- [ ] A zero/expired remaining budget must reject before the operation factory runs.
- [ ] Completion and halt in one loop turn must not authorize the next action.
- [ ] Completion exactly at deadline follows one explicit conservative precedence rule.
- [ ] Cancellation-resistant operations remain pending and block replacement/reset.
- [ ] An awaitable raising CancelledError differs from a normal successful result.
- [ ] A manual deadline must not be compared to an unrelated real loop clock.
- [ ] A cleanup failure must not replace the primary timeout/device error.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Run a completed operation with a current ticket and verify returned value and timing.
- [ ] Hold model/route/inspection doubles behind named barriers while keeping a console pulse task active.
- [ ] Advance the simulated deadline before start and during execution and inspect whether any factory/action ran.
- [ ] Release completion just before halt, just after halt and in the same scheduler turn.
- [ ] Use an operation that ignores cancellation; verify pending registry state and blocked replacement.
- [ ] Run a recovery operation with a separate budget after the normal cancellation event is set.
- [ ] Check exactly one invocation and no implicit retries after a synthetic timeout.
- [ ] Release all delayed operations and assert every retained task is awaited/collected in teardown.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g05/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g05/test_execution.py for success, errors, expired budget and lazy factory behavior.
- [ ] Test same-turn result/halt/deadline races through deterministic barriers.
- [ ] Test original total mission deadline is not extended by retries or later stages.
- [ ] Test strong task ownership and cancellation-resistant pending work.
- [ ] Test cleanup error preservation and recovery-budget separation.
- [ ] Add a bounded real-clock responsiveness test separate from virtual-time assertions.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g05 -q
python -m patrol.ground.sim --task 05 --case all --seed 0 --report artifacts/task-05/simulation.json
python -m patrol.ground.quality --task 05
git diff --check
```

### Completion and handoff

- [ ] Tests import only the kernel and this base provider.
- [ ] No expired/stale/cancelled ticket invokes an ordinary action factory.
- [ ] Late results remain inspectable but cannot advance the mission.
- [ ] The executor reports uncertainty without claiming that coroutine cancellation stopped a device.
- [ ] The full task's tests and simulation finish with no abandoned tasks.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 06: Implement JPEG evidence and provenance validation

**Local task key:** GROUND-06. **Nature:** Base service: evidence boundary validation.
**Outcome:** Only readable, correctly scoped and truthfully labeled evidence can reach reasoning stages.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.evidence`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-06'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-06 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-06 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g06.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] plan.md §6.3: Frame metadata and freshness semantics.
- [ ] ground.md §§2.2,11.3–11.4: forward imagery, timestamps and simulation truth.
- [ ] ground.md §15: evidence edge-case matrix.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g06/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g06/**`, `fixtures/ground/g06/**`, and `handoff/ground/g06.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Frame, expected source/zone/mode, assigned output root and operation capture interval.
- [ ] Initial phone input metadata with known or unknown capture time.
- [ ] Injected bounded file/decoder access and kernel clock readings.

Outputs:
- [ ] EvidencePort validation results with accepted Frame references or typed rejection.
- [ ] Recorded capture age/provenance/file identity without invented timestamps.
- [ ] Diagnostic reasons that distinguish corruption, stale metadata and simulated/live mismatch.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Validate the frozen Frame type and expected source, zone and simulation flag.
- [ ] Require absolute regular-file paths and live-output containment in the adapter-assigned directory.
- [ ] Reject symlink/path traversal escapes using resolved paths while preserving the correct diagnostic.
- [ ] Apply file-size and decoding bounds; verify JPEG content rather than filename extension.
- [ ] Parse UTC-aware capture timestamps and allow unknown time only for an initial supplied phone image.
- [ ] Compare live capture to its operation start/end interval and reject future/pre-request/naive metadata.
- [ ] Allow a valid aerial capture followed by longer landing transit without applying return-time five-second rejection.
- [ ] Keep adapter stream-selection freshness as external acceptance evidence, not a claim Ground can prove from metadata.
- [ ] Preserve original phone-image provenance and avoid rewriting time when copying into artifacts.
- [ ] Return immutable validated references suitable for logs and model calls.
- [ ] Make deterministic fake fixtures exercise the same validation code, with explicit intentionally invalid cases.
- [ ] Keep decoding/file I/O bounded and off responsiveness-critical event-loop sections where appropriate.

### Outside this task

- [ ] Do not decode live Tello/WebRTC streams or capture device frames.
- [ ] Do not classify image content or infer abandonment/permission.
- [ ] Do not alter the external Frame dataclass or forge capture times.

### Required edge cases

- [ ] Zero-byte, truncated, non-JPEG and oversized payloads are rejected.
- [ ] Wrong source/zone and simulated evidence returned by a real adapter are rejected.
- [ ] Relative paths and resolved symlink escapes cannot bypass output containment.
- [ ] Null, naive, malformed, future and pre-request timestamps are handled explicitly.
- [ ] Aerial capture returned twelve seconds after capture due to landing remains valid when interval-consistent.
- [ ] Copied phone files retain unknown/original capture time rather than file-copy time.
- [ ] A file disappearing or changing during validation produces an explicit failure.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Create readable small JPEGs and corresponding phone/dog/drone Frame objects in temporary roots.
- [ ] Validate the normal live and explicitly simulated cases through the actual provider.
- [ ] Inject corrupt bytes, oversize limits, wrong metadata, relative paths and symlink/containment escapes.
- [ ] Capture an aerial frame inside inspect's interval, advance twelve seconds for landing and assert acceptance.
- [ ] Contrast it with a pre-request stream buffer and assert rejection without changing its timestamp.
- [ ] Inject file disappearance and decoder failure while a separate halt pulse remains responsive.
- [ ] Verify rejected evidence never reaches a seeded reasoner or inspection operation.
- [ ] Close images/files and inspect output identity/provenance in the deterministic report.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g06/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g06/test_files.py for JPEG integrity, size and path containment.
- [ ] Create metadata tests for every source/mode/zone combination.
- [ ] Test timestamp boundaries and unknown phone provenance.
- [ ] Test delayed-landing aerial acceptance versus genuinely pre-request capture rejection.
- [ ] Test disappearing/changed files and bounded decoder errors.
- [ ] Test validation has no model, network or device side effects.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g06 -q
python -m patrol.ground.sim --task 06 --case all --seed 0 --report artifacts/task-06/simulation.json
python -m patrol.ground.quality --task 06
git diff --check
```

### Completion and handoff

- [ ] The provider is runnable from the Task 01 baseline alone.
- [ ] Every accepted live reference has valid file and scope metadata.
- [ ] Landing delay is not mistaken for stale selection, and stale buffers are not relabeled fresh.
- [ ] The handoff states which freshness claims still require adapter-owner evidence.
- [ ] All invalid fixtures produce deliberate failures rather than fallback evidence.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 07: Implement responsive command input and scoped confirmation primitives

**Local task key:** GROUND-07. **Nature:** Base service: terminal transport.
**Outcome:** Operators can issue commands during pending work, while every arrival/readiness token is tied to its current wait.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.console`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-07'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-07 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-07 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g07.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] ground.md §10: commands, Windows-compatible input, Ctrl+C and EOF.
- [ ] ground.md §§7,9: ticket identity, independent safety path and command races.
- [ ] plan.md §7.2: agreed terminal command meanings.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g07/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g07/**`, `fixtures/ground/g07/**`, and `handoff/ground/g07.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Text/key/EOF events from an injected input stream.
- [ ] Frozen command grammar, current ticket/state snapshot and cancellation callback.
- [ ] Kernel clock and confirmation wait descriptors.

Outputs:
- [ ] ConsolePort command parsing, prompt transport and current-wait confirmation primitives.
- [ ] Typed accepted/rejected command events without raw model text execution.
- [ ] Nonblocking halt notification and a terminal session with controlled teardown.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Parse exactly status, arm, start, arrived <zone>, flight-ready, halt, reset and quit.
- [ ] Separate parsing/transport from phase-specific policies delivered by later feature providers.
- [ ] Use prompt_toolkit asynchronous input and patchable stdout behind an injectable ConsolePort.
- [ ] Route halt to the kernel's immediate latch callback without awaiting the normal mission or journal.
- [ ] Create fresh confirmation waiters keyed by mission, epoch, stage, kind and zone.
- [ ] Reject early, wrong-zone, duplicate, expired and stale confirmations instead of queuing them for later.
- [ ] Support noninteractive scripted input for selftests without requiring a TTY.
- [ ] Keep command input responsive while adapter/model doubles remain pending.
- [ ] Publish clear command rejection reasons without changing mission state directly.
- [ ] Expose Ctrl+C/EOF as typed lifecycle events consumed by the later shutdown integration.
- [ ] Make input cancellation/close idempotent and collect its tasks.
- [ ] Keep Unix-specific termios/add_reader/signal assumptions out of the Windows path.

### Outside this task

- [ ] Do not decide whether a physical launch is safe.
- [ ] Do not implement the report/status presentation feature or device SDKs.
- [ ] Do not implement Task 29's whole-application shutdown policy inside the input parser.

### Required edge cases

- [ ] Whitespace, empty commands, unsupported commands and extra arguments have explicit outcomes.
- [ ] arrived for a different zone cannot resolve the current wait.
- [ ] A confirmation entered before the waiter exists cannot be reused.
- [ ] Halt and flight-ready arriving together must invalidate readiness conservatively.
- [ ] EOF during a pending command is delivered without hanging a background input thread.
- [ ] Very long input and control characters cannot become model/SDK commands.
- [ ] A prompt renderer failure must not prevent the kernel halt callback.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Feed a synthetic command stream through the actual parser/ConsolePort with dummy terminal output.
- [ ] Start a seeded arrival wait, submit wrong/early/correct/duplicate confirmations and inspect its single resolution.
- [ ] Hold a model operation pending and deliver status and halt while measuring command progress.
- [ ] Schedule flight-ready and halt in both orders and the same logical turn.
- [ ] Inject Ctrl+C, EOF and renderer/input errors into pending operation states.
- [ ] Repeat the same scripted input without a TTY and assert equivalent typed events.
- [ ] Check rejected commands cause zero device invocations and cannot mutate trusted target/zone.
- [ ] Cancel/close the input loop and collect all confirmation/input tasks.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g07/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g07/test_parser.py with a grammar table and invalid-input cases.
- [ ] Test epoch/stage/zone-specific confirmation primitives.
- [ ] Use prompt_toolkit pipe input and dummy output for async console integration tests.
- [ ] Test halt callback bypasses blocked ordinary handlers.
- [ ] Test EOF, Ctrl+C and input-close idempotency.
- [ ] Test no Unix-only keyboard APIs are required for the default Windows path.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g07 -q
python -m patrol.ground.sim --task 07 --case all --seed 0 --report artifacts/task-07/simulation.json
python -m patrol.ground.quality --task 07
git diff --check
```

### Completion and handoff

- [ ] A task can exercise the console against only Task 01 peer doubles.
- [ ] Input remains usable while a seeded long operation waits.
- [ ] No early or stale confirmation becomes future permission.
- [ ] The console emits typed lifecycle events and never directly controls hardware.
- [ ] All test input streams terminate cleanly without leaked threads.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 08: Implement adapter selection, guarded calls, and connection lifecycle gateway

**Local task key:** GROUND-08. **Nature:** Base service: robot/reasoner boundary.
**Outcome:** Ground resolves exactly one owner per adapter, invokes it through frozen signatures, and preserves truthful availability.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.adapters`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-08'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-08 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-08 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g08.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] plan.md §6: all public dataclasses, factory signatures and cancellation semantics.
- [ ] ground.md §§3,6,12.4: exact devices, contract limitations and connection lifecycle.
- [ ] tasks.md Person 4: use private stubs first, public factories after merge.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g08/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g08/**`, `fixtures/ground/g08/**`, and `handoff/ground/g08.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Validated adapter modes/config mappings and assigned output directories.
- [ ] Injected public factory resolver or explicit private-stub resolver.
- [ ] Kernel identity/cancellation/task registry and contract peer doubles.

Outputs:
- [ ] AdapterPort build/connect/status/invoke/close gateway using unchanged external Protocols.
- [ ] Availability snapshots distinguishing missing package, disconnected optional device and active link loss.
- [ ] One active dog connection/profile and no silent substitute factories.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Resolve create_dog/create_drone/create_reasoner lazily and pass exact mode/config/output_dir keywords.
- [ ] Permit the explicit private-stub selftest resolver without automatic production fallback.
- [ ] Keep fake mode usable without importing real SDK packages or credentials.
- [ ] Create each adapter once per connection lifecycle and prevent duplicate command owners.
- [ ] Apply the kernel's final ticket/cancellation fence immediately before ordinary device call construction.
- [ ] Pass RunContext and typed request objects without raw vendor commands leaking into Ground.
- [ ] Collect bounded connection/status results while permitting an unused optional drone to remain unavailable.
- [ ] Represent unknown telemetry truthfully and record response observation time without inventing device sample timestamps.
- [ ] Keep Ethernet and Wi-Fi dog profiles behind the same DogPort; one selected profile per lifecycle.
- [ ] Expose close/recreate only through approved recovery flow and require old work to quiesce.
- [ ] Collect cleanup failures independently so one adapter error does not skip another close attempt.
- [ ] Surface SDK capability/worker-quiescence/freshness evidence gaps for the contract-probe feature instead of guessing.

### Outside this task

- [ ] Do not implement a Go2/Tello/Grok vendor adapter or second client.
- [ ] Do not add public robot reset/workers_idle methods.
- [ ] Do not repair Wi-Fi, send raw keepalives or change OS routes.

### Required edge cases

- [ ] Missing public factory in production fails explicitly rather than using private stubs.
- [ ] A real-to-fake substitution or second dog connection is rejected.
- [ ] A disconnected optional drone at startup differs from active flight link loss.
- [ ] Wrong return object/type from a factory or adapter must be reported at the boundary.
- [ ] A late operation from the prior adapter generation cannot affect a recreated session.
- [ ] A pending old worker blocks recreation even if its outer coroutine was cancelled.
- [ ] Unknown status cannot be replaced with connected/grounded defaults.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Inject synthetic public modules with exact factory exports and capture their keyword arguments.
- [ ] Build/connect fake adapters and exercise each public signature without actual SDK imports.
- [ ] Remove a module/export and verify explicit unavailable results with no private fallback.
- [ ] Hold an adapter operation pending, invalidate its epoch and prove a guarded second operation never starts.
- [ ] Simulate optional drone unavailable while a seeded ground-only path remains possible.
- [ ] Switch connection profile only after a complete quiescent close and assert one dog owner.
- [ ] Inject close failures and cancellation-resistant old work; verify error aggregation and blocked recreation.
- [ ] Collect all gateway tasks and ensure fake tests created zero sockets.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g08/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g08/test_resolution.py for exact imports/factories/keyword compatibility.
- [ ] Test lazy fake imports and production missing-module failures.
- [ ] Test guarded invocation rejects stale/cancelled identities.
- [ ] Test optional availability versus active link-loss classification.
- [ ] Test lifecycle single ownership and pending-worker recreation block.
- [ ] Test cleanup attempts all adapters without hiding the primary fault.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g08 -q
python -m patrol.ground.sim --task 08 --case all --seed 0 --report artifacts/task-08/simulation.json
python -m patrol.ground.quality --task 08
git diff --check
```

### Completion and handoff

- [ ] The adapter gateway runs independently using kernel factory doubles.
- [ ] Every actual external call preserves contract v1 signatures.
- [ ] No fallback, duplicate ownership or vendor-side control is hidden in Ground.
- [ ] Unavailable/unknown states remain visible to callers.
- [ ] Recreation is impossible while the prior lifecycle may still issue commands.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 09: Implement the fixed mission workflow and extension composition

**Local task key:** GROUND-09. **Nature:** Base service: orchestration engine.
**Outcome:** A complete ordered mission pipeline can call independently registered stage policies while refusing missing safety-critical stages.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.workflow`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-09'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-09 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-09 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g09.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] plan.md §§3,8,11: agreed branches, phases, scenarios.
- [ ] ground.md §§5,7–9: sequential mission coroutine, interlocks and results.
- [ ] This file's stage order, feature slot table and observer/command bindings.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g09/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g09/**`, `fixtures/ground/g09/**`, and `handoff/ground/g09.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] BaseServices Protocol bundle and fixed manifest/feature resolver.
- [ ] A current admitted incident and validated settings.
- [ ] Seeded feature providers and service doubles supplied by Task 01.

Outputs:
- [ ] WorkflowPort load/start/snapshot/join interface plus a retained one-mission coroutine.
- [ ] Deterministic stage ordering, command routing and missing-provider diagnostics.
- [ ] A fail-closed integration path that composes later providers without editing this module.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Implement one sequential normal mission coroutine with independent input/safety task supervision.
- [ ] Invoke the exact frozen phase and feature slot order, including preflight checks both before and after flight-ready.
- [ ] Resolve feature providers through their declared slot and factory; never import individual later task modules.
- [ ] Keep stage input/output maps typed and validate every FeatureResult before applying state events.
- [ ] Reject double starts and ensure only one normal hardware sequence is active.
- [ ] Use injected executor/state/adapter/journal ports, with kernel doubles when peer base services are absent.
- [ ] Keep the final kernel/adapter action fence after policy acceptance and before ordinary calls.
- [ ] Route arm/arrived/flight-ready/reset and observational commands to their fixed policy bindings.
- [ ] Apply conservative built-in transport/cancel/mixed-mode guards even when an enhancement policy is absent.
- [ ] Treat missing mandatory stage policies as unavailable and prohibit real motion; do not default to approval.
- [ ] Support explicit synthetic complete stage packs in tests without silently loading them in production.
- [ ] Expose hooks for startup guard, health monitor, report projection and persistence fault events without same-batch imports.

### Outside this task

- [ ] Do not implement the business logic of Tasks 11–32 inside the workflow.
- [ ] Do not call vendor SDKs or own flight trajectories.
- [ ] Do not make a final integration test depend on unfinished late task branches.

### Required edge cases

- [ ] A missing preflight or dispatch policy must block its stage rather than skip it.
- [ ] A malformed feature result or wrong payload type cannot mutate phase state.
- [ ] Late completion after halt cannot trigger the next feature or device call.
- [ ] Dismiss and sufficient-ground branches must skip the correct actions.
- [ ] A report outcome must not clear a separate recovery lock.
- [ ] An optional missing diagnostic provider must not be treated as a failed mandatory flight guard.
- [ ] One failure event must not create repeated terminal publications or competing cleanup loops.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Compose the real workflow provider with kernel-seeded complete feature pack and service doubles.
- [ ] Run dispatch-dismiss, ground-clear, ground-confirmed and blocked-resolved branches with trace assertions.
- [ ] Remove one required feature at each safety boundary and verify fail-closed behavior.
- [ ] Hold stage completion, request halt, then release the result and assert no subsequent stage begins.
- [ ] Inject malformed/wrong-stage results and verify typed failure without accidental motion.
- [ ] Publish persistence/link-loss events while a normal stage is pending and observe independent safety requests.
- [ ] Demonstrate additive loading of one synthetic feature manifest without editing shared registry files.
- [ ] Collect workflow/input/background tasks and compare ordered traces across fixed-seed runs.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g09/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g09/test_pipeline.py for normal stage order and all branch skips.
- [ ] Test missing required versus optional providers.
- [ ] Test double start and terminal publication idempotency.
- [ ] Test stale result/halt races at every device boundary.
- [ ] Test typed payload and ticket validation for feature responses.
- [ ] Test import isolation from Tasks 02–10 and 11–32 implementations by using only seeded ports.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g09 -q
python -m patrol.ground.sim --task 09 --case all --seed 0 --report artifacts/task-09/simulation.json
python -m patrol.ground.quality --task 09
git diff --check
```

### Completion and handoff

- [ ] The workflow can be tested with Task 01 alone and no same-batch implementation imports.
- [ ] Later features can be added through manifests without changing this provider.
- [ ] Missing mandatory policies refuse motion rather than appearing as a completed fake demo.
- [ ] Normal stages never run after cancellation/fault admission is lost.
- [ ] The senior can use this engine for the post-base integration gate.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 10: Implement halt supervision, cleanup, shutdown, and safe reset primitives

**Local task key:** GROUND-10. **Nature:** Base service: independent safety lifecycle.
**Outcome:** Halt immediately blocks ordinary work, requests both devices' safety actions, and preserves faults until verified recovery.
**Dependency boundary:** Task 01 ONLY; start after Gate A. No import, cherry-pick, wait or dependency on any other Task 02–10.
**Owned contribution slot:** `base.safety`; freeze manifest schema as `ground-task-v1`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-foundation-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-10'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-10 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-10 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g10.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] ground.md §§9.4–9.6,10,14: latch, stop concurrency, reset and shutdown.
- [ ] plan.md §§6.2,8: cleanup semantics and physical uncertainty.
- [ ] This file's SafetyPort, kernel latch/task registry and recovery event contracts.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g10/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g10/**`, `fixtures/ground/g10/**`, and `handoff/ground/g10.md`.
- [ ] No shared kernel, root CLI, registry, configuration, dependency or peer-file edits. Request a senior baseline change if a frozen interface is insufficient.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Kernel session/cancellation/task authority and injected dog/drone/reasoner ports.
- [ ] Typed halt, timeout, link-loss and recovery requests.
- [ ] Independent safety deadlines, task barriers and observed physical statuses.

Outputs:
- [ ] Synchronous SafetyPort.request latch with one retained supervisor handle.
- [ ] Independent stop/landing attempt records and truthful settled/pending/unknown states.
- [ ] Reset/shutdown primitives that close/recreate only after old work and physical recovery are verified.

### Exact integration requirement

Export create(kernel: KernelContext, peers: ServicePorts) -> the Port assigned to this slot; implement its exact frozen methods. Inject kernel doubles for all peers.
Feature results propose typed events; the workflow applies them through StatePort after identity/cancellation checks. Never mutate another provider's private state.
Register this contribution through its OWN manifest only; the fixed loader discovers it without edits to a shared list.

### Implementation scope

- [ ] Latch cancellation and invalidate ordinary tickets synchronously before any device or disk await.
- [ ] Create one supervisor per incident and coalesce repeated halt requests.
- [ ] Start dog.halt and drone.land promptly as independent requests so one blocked device does not delay the other.
- [ ] Keep safety attempts alive and observable when normal mission tasks cancel or fail.
- [ ] Use bounded recovery observation and deadlines separate from cancelled normal RunContext values.
- [ ] Collect all errors without fail-fast cancellation of the other device's stop attempt.
- [ ] Re-read physical status where available and retain unknown/airborne/not-stopped recovery lock.
- [ ] Prevent ordinary success and late grounded results from silently clearing a prior fault.
- [ ] Implement verified quiescence/close/recreate primitives without inventing external workers_idle/reset methods.
- [ ] Create fresh epoch, Event and confirmation state only after operator/physical recovery and old-worker termination.
- [ ] Reconnect recreated adapters disarmed and never resume a timed route or retry takeoff.
- [ ] Expose lifecycle primitives for later Ctrl+C/EOF/startup features without importing workflow/console implementations.

### Outside this task

- [ ] Do not implement aircraft abort trajectories, motor-cut routines or robot posture internals.
- [ ] Do not claim remote stop delivery after the control link is lost.
- [ ] Do not build hardware fault-injection tests that create hazardous airborne outages.

### Required edge cases

- [ ] Dog halt failure or hang must not suppress the drone landing request.
- [ ] Repeated halt must not produce multiple simultaneous landing sequences.
- [ ] An ignored cancellation in an old worker must block reset/recreation.
- [ ] An image with unknown landing state cannot unlock walking.
- [ ] A cancelled normal deadline must not prohibit required clearance/landing recovery actions.
- [ ] Cleanup errors must remain separate from the original mission failure.
- [ ] Physical recovery confirmation without old-worker quiescence is insufficient to reset.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Hold a normal device operation behind a barrier and invoke the synchronous halt entry point.
- [ ] Assert the cancellation latch is visible immediately before releasing either safety device await.
- [ ] Block dog halt, permit drone abort and prove both requests were started independently.
- [ ] Repeat halt requests and inspect that the same supervisor/attempt identities are reused.
- [ ] Inject stop errors and unknown flight/stopped states; verify recovery remains latched.
- [ ] Attempt reset with a cancellation-resistant old worker and verify no new adapters are created.
- [ ] Release all work, provide verified recovery, close/recreate and prove fresh tokens with disarmed status.
- [ ] Run a bounded real-clock fake responsiveness check plus deterministic trace replay, then collect every pending task.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g10/; existing shared tests alone do not satisfy this assignment.
- [ ] Create tests/ground/g10/test_halt.py for immediate latch and independent stop request ordering.
- [ ] Test repeated halt coalescing and both-attempt error aggregation.
- [ ] Test separate recovery deadlines and cancellation-resistant task retention.
- [ ] Test no reset/recreation while old work or physical state remains uncertain.
- [ ] Test fresh epoch/Event/waiters and disarmed reconnect after verified recovery.
- [ ] Test original fault preservation under cleanup exceptions and late successful results.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g10 -q
python -m patrol.ground.sim --task 10 --case all --seed 0 --report artifacts/task-10/simulation.json
python -m patrol.ground.quality --task 10
git diff --check
```

### Completion and handoff

- [ ] Halt can be tested without any other base provider implementation.
- [ ] Both safety requests begin even when one subsequently fails or hangs.
- [ ] The fake recognition target is measured separately from physical stop time.
- [ ] Reset never creates a second command issuer or resumes old motion.
- [ ] Every simulation records actual attempt/unknown/pending states and leaves no test workers behind.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Drone-first demo — Tasks 11–32

Status: active demo revision, 4 November 2026. Tasks 01–10 and sections 1–10 stay as written. This block replaces the old phone-incident cards that used to occupy Tasks 11–32.

This section is the handout for the new demo. Distribute Tasks 11–32 below. Tasks 01–10 stay the foundation and are not the new mission. The wire contract is protocol **2.0-draft**. Every JSON example is synthetic `simulated=true`. Opening one does not command hardware. The folder for every example is `C:\Users\Ayush\Desktop\ground\contracts\examples\`.

### What the demo is

An operator runs the demo in a space tall enough for a proposed 4 m flight. The hackathon room ceiling is too low for that profile. The drone scouts, xAI Grok classifies a staged person, and Ground may approve a bounded move toward that person. The dog stays put while the drone is moving. A Raspberry Pi on the dog measures the Tello beacon. Ground uses those RSSI windows only to choose among collision-checked steps the dog teammate already marked safe, because obstacles can hide the person from the dog at the start. When the dog camera sees the same person, the dog finishes on its own vision. The demo goal is current dog-target range plus current drone horizontal offset. Landing is a separate recovery step.

### Confirmed inputs from the meeting

- Vision provider is **xAI Grok**. Groq is a different service and is not selected. Model ID stays configurable; examples use `CONFIGURE_VERIFIED_IMAGE_MODEL` on purpose.
- The dog is Go2 PRO. Ethernet is the connection available now and stays plugged in for an Ethernet run. Wi-Fi is a separate accepted profile.
- The broken router in the back enclosure is not the Raspberry Pi. The Pi is mounted on the dog and is the RSSI receiver.
- The drone is Tello EDU through `from djitellopy import Tello`, owned by the drone teammate. Directional motion is currently unreliable in their build. Treat that as an unresolved control fault. The manufacturer SDK documents bounded translations, so the demo does not depend on uncontrolled random drift.
- The dog teammate owns the control app, LiDAR, SLAM or reactive avoidance, and JSON parsing. "LAM" in the meeting means SLAM until that teammate names the real stack.
- The camera on the belly is **downward**. There is no rear camera. At about 4 m, a nearby front view can be a wall; a front view from farther away can still see a person. Both cameras are capability gates.
- The team will still send their final log list. Task 29 records the proposed fields below and must accept a later versioned addition. It must not pretend that list already arrived.

### Who receives which JSON file

Ground sits in the middle. Grok returns a `motion.proposal` or a scene decision. Ground writes the device command. The dog and drone apps enforce their own leases and stops. Model JSON never becomes a motor string.

`ai-to-drone-proposal.json` and `ai-to-dog-proposal.json` go to the vision teammate as the shape they return, and they stay with Ground. Do not give those two files to the drone or the dog as commands.

#### Drone teammate — Tasks 13, 14, 17, 18, 19

Also send `C:\Users\Ayush\Desktop\ground\contracts\drone-to-ai.md` and `C:\Users\Ayush\Desktop\ground\contracts\ai-to-drone.md`.

| They send Ground | File |
| --- | --- |
| What the aircraft can do | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-capabilities.json` |
| Flight state, height, beacon, and frame | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-observation.json` |
| Command accepted, not finished | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-ack-accepted.json` |
| Command running | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-ack-running.json` |
| Command finished | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-ack-completed.json` |
| Landing not verified | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-landing-unknown.json` |

| Ground sends them | File |
| --- | --- |
| One approved move | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-drone-command.json` |
| Hover | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-drone-hover.json` |
| Land | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-drone-land.json` |

#### Dog-app teammate — Tasks 20, 23, 24, 25

Also send `C:\Users\Ayush\Desktop\ground\contracts\dog-to-ai.md` and `C:\Users\Ayush\Desktop\ground\contracts\ai-to-dog.md`.

| They send Ground | File |
| --- | --- |
| What the dog can do | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-capabilities.json` |
| Pose, LiDAR, and navigation mode | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-observation.json` |
| Safe steps Ground may choose | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-navigation-candidates.json` |
| Command accepted | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-ack-accepted.json` |
| Command running | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-ack-running.json` |
| Command finished and the dog stopped | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-ack-completed.json` |
| Command rejected, dog did not move | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-command-rejected.json` |

| Ground sends them | File |
| --- | --- |
| One approved step | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-dog-command.json` |
| Halt | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-dog-halt.json` |

#### Vision teammate — Tasks 15, 16, 25

Also send `C:\Users\Ayush\Desktop\ground\contracts\vision.md`.

| Ground sends them | File |
| --- | --- |
| Drone frame to classify | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-vision-request.json` |
| Dog frame to classify | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-vision-request.json` |

| They send Ground | File |
| --- | --- |
| Decision on the drone frame | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-vision-decision.json` |
| Decision on the dog frame | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-vision-decision.json` |
| Proposal for the drone, not a motor command | `C:\Users\Ayush\Desktop\ground\contracts\examples\ai-to-drone-proposal.json` |
| Proposal for the dog, not a motor command | `C:\Users\Ayush\Desktop\ground\contracts\examples\ai-to-dog-proposal.json` |

#### Pi teammate — Tasks 21, 22, 30

The Pi is mounted on the dog. Also send `C:\Users\Ayush\Desktop\ground\contracts\rssi-and-navigation.md`.

| They send Ground | File |
| --- | --- |
| What the Pi can measure | `C:\Users\Ayush\Desktop\ground\contracts\examples\pi-capabilities.json` |
| One RSSI window at the dog | `C:\Users\Ayush\Desktop\ground\contracts\examples\pi-rssi-window.json` |
| Pi is alive and the clock error | `C:\Users\Ayush\Desktop\ground\contracts\examples\pi-heartbeat.json` |

Ground does not send the Pi a motion command.

#### Logs you keep — Tasks 26, 27, 29, 31, 32

Also send everyone `C:\Users\Ayush\Desktop\ground\contracts\events-and-logs.md`. These are Ground records, not packets for a robot.

| Record | File |
| --- | --- |
| Person first seen from the drone | `C:\Users\Ayush\Desktop\ground\contracts\examples\event-drone_target_acquired.json` |
| Dog allowed to start homing | `C:\Users\Ayush\Desktop\ground\contracts\examples\event-dog_dispatched.json` |
| Demo goal reached | `C:\Users\Ayush\Desktop\ground\contracts\examples\event-demo_goal_reached.json` |
| Landing not verified | `C:\Users\Ayush\Desktop\ground\contracts\examples\event-landing_unverified.json` |
| Dog range and drone horizontal offset | `C:\Users\Ayush\Desktop\ground\contracts\examples\proximity-evidence.json` |
| Index of every example | `C:\Users\Ayush\Desktop\ground\contracts\examples-index.json` |
| All examples as separate lines, not one mission | `C:\Users\Ayush\Desktop\ground\contracts\example-events.jsonl` |

### Runtime order for the senior's Gate C

Each card below is still independent and tests with frozen fixtures. The composed demo order is:

1. Task 30 reports link and tether readiness. Task 12 admits only capabilities the peers actually report.
2. Task 13 ingests drone observations. Task 14 checks the camera epoch and image bytes. Task 19 requires a stable beacon before the dog moves.
3. Task 15 samples the latest frame. Task 16 accepts a Grok decision and may open a target track. It does not move anything.
4. Task 17 approves one drone primitive. Task 18 tracks its acknowledgements. A reposition advances the beacon epoch and Task 19 stops homing until a new hold exists.
5. Task 21 validates a Pi window. Task 20 supplies safe dog candidates. Task 22 may select one candidate. Task 23 issues one leased dog command. Task 24 tracks the dog acknowledgements.
6. Task 25 switches the dog from RSSI to its own camera once the same person is visible there.
7. Task 26 records the demo goal only when dog range and drone horizontal offset are both current. Task 27 lands and keeps an unknown landing as a recovery fault.
8. Task 28 may halt at any step without waiting for Grok. Task 11 rejects malformed envelopes on every hop. Task 29 journals the accepted messages. Task 31 computes timings from that journal.
9. Task 32 rehearses this order offline and writes the operator script.

### v2 slots

Manifests for these cards use `schema_version` `ground-task-v2`. Do not register them by editing Task 01's v1 slot table. Tests call `create(services)` directly. The senior adds the slot names in one Gate C baseline update.

```json
{
  "schema_version": "ground-task-v2",
  "task_id": "GROUND-11",
  "slot": "feature.v2_envelope",
  "factory": "patrol.ground.extensions.g11.implementation:create",
  "scenario_factory": "patrol.ground.extensions.g11.scenarios:cases"
}
```

| Task | Slot | Frozen fixture in → result out |
| --- | --- | --- |
| 11 | `feature.v2_envelope` | raw JSON message → accepted envelope or typed rejection |
| 12 | `feature.v2_capabilities` | `capabilities.report` → armed feature set |
| 13 | `feature.v2_drone_observation` | `drone.observation` → normalized observation |
| 14 | `feature.v2_frame` | frame metadata plus bytes → camera epoch and hash result |
| 15 | `feature.v2_vision_schedule` | fresh frame and stage → `vision.request` or dropped |
| 16 | `feature.v2_vision_decision` | `vision.decision` → track update or review |
| 17 | `feature.v2_drone_command` | `motion.proposal` for the drone → `drone.command` or rejection |
| 18 | `feature.v2_drone_ack` | drone `command.ack` → lifecycle state |
| 19 | `feature.v2_beacon` | beacon snapshot → hold, epoch, dog-stop requirement |
| 20 | `feature.v2_dog_navigation` | `dog.observation` plus `navigation.candidates` → candidate set |
| 21 | `feature.v2_rssi` | `rssi.window` plus `heartbeat` → comparable or rejected window |
| 22 | `feature.v2_rssi_homing` | valid window plus candidates → one `candidate_id` or stop |
| 23 | `feature.v2_dog_command` | approved selection or dog proposal → `dog.command` |
| 24 | `feature.v2_dog_ack` | dog `command.ack` → lifecycle state |
| 25 | `feature.v2_dog_acquire` | dog `vision.decision` plus track → visual approach or remain on RSSI |
| 26 | `feature.v2_proximity` | `proximity.evidence` → goal reached or unresolved |
| 27 | `feature.v2_recovery` | land acknowledgement plus goal event → recovery outcome |
| 28 | `feature.v2_safety` | halt, link, stale, or lease fault → safety latch |
| 29 | `feature.v2_logs` | accepted message → journal record |
| 30 | `feature.v2_links` | settings plus injected probes → link readiness |
| 31 | `feature.v2_metrics` | journal → timings, with null where evidence is missing |
| 32 | `feature.v2_rehearsal` | seeded scenario → offline report and `demo/script.md` |

Common payload keys from section 6 still apply: `ticket`, `snapshot`, `settings`, and `command` where the card names them. v2 message bodies use the keys in [contracts/message.schema.json](contracts/message.schema.json). Initial simulation budgets, to be measured and then tuned: image sample 1000 ms, one vision request in flight, vision timeout 5000 ms, evidence age 3000 ms, ordinary command lease at most 500 ms. A 4 m height is a profile value, not an enabled default.

### Proposed logs, already written as examples

Task 29 owns the journal rules. Every other card must emit or consume the example that matches its message kind, and must copy these correlation fields into the journal fixture it proposes: `message_id`, `mission_id`, `epoch`, `command_id` or `request_id` when present, `frame_id`, `track_id`, `beacon_epoch`, `map_epoch`, and `camera_epoch`.

| Log | Example |
| --- | --- |
| Drone capability | [contracts/examples/drone-capabilities.json](contracts/examples/drone-capabilities.json) |
| Dog capability | [contracts/examples/dog-capabilities.json](contracts/examples/dog-capabilities.json) |
| Pi capability | [contracts/examples/pi-capabilities.json](contracts/examples/pi-capabilities.json) |
| Drone observation | [contracts/examples/drone-observation.json](contracts/examples/drone-observation.json) |
| Dog observation | [contracts/examples/dog-observation.json](contracts/examples/dog-observation.json) |
| Pi RSSI window | [contracts/examples/pi-rssi-window.json](contracts/examples/pi-rssi-window.json) |
| Pi heartbeat | [contracts/examples/pi-heartbeat.json](contracts/examples/pi-heartbeat.json) |
| Dog planner candidates | [contracts/examples/dog-navigation-candidates.json](contracts/examples/dog-navigation-candidates.json) |
| Drone to vision | [contracts/examples/drone-vision-request.json](contracts/examples/drone-vision-request.json) |
| Vision to Ground, drone stage | [contracts/examples/drone-vision-decision.json](contracts/examples/drone-vision-decision.json) |
| Dog to vision | [contracts/examples/dog-vision-request.json](contracts/examples/dog-vision-request.json) |
| Vision to Ground, dog stage | [contracts/examples/dog-vision-decision.json](contracts/examples/dog-vision-decision.json) |
| AI proposal for the drone | [contracts/examples/ai-to-drone-proposal.json](contracts/examples/ai-to-drone-proposal.json) |
| Ground command to the drone | [contracts/examples/ground-to-drone-command.json](contracts/examples/ground-to-drone-command.json) |
| Drone hover and land | [contracts/examples/ground-to-drone-hover.json](contracts/examples/ground-to-drone-hover.json), [contracts/examples/ground-to-drone-land.json](contracts/examples/ground-to-drone-land.json) |
| AI proposal for the dog | [contracts/examples/ai-to-dog-proposal.json](contracts/examples/ai-to-dog-proposal.json) |
| Ground command to the dog | [contracts/examples/ground-to-dog-command.json](contracts/examples/ground-to-dog-command.json) |
| Dog halt | [contracts/examples/ground-to-dog-halt.json](contracts/examples/ground-to-dog-halt.json) |
| Command acknowledgements | `dog-ack-*.json`, `drone-ack-*.json`, [contracts/examples/dog-command-rejected.json](contracts/examples/dog-command-rejected.json), [contracts/examples/drone-landing-unknown.json](contracts/examples/drone-landing-unknown.json) |
| Proximity and mission events | [contracts/examples/proximity-evidence.json](contracts/examples/proximity-evidence.json), `contracts/examples/event-*.json` |

[contracts/example-events.jsonl](contracts/example-events.jsonl) is a catalog of separate examples, including both success and failure. It is not one valid mission. Task 32 builds its own ordered scenario.

---

## Task 11: Validate v2 envelopes and keep the v1 robot contract unchanged

**Local task key:** GROUND-11. **Nature:** Protocol-boundary feature for every drone-first message.
**Outcome:** Every later card can trust a parsed 2.0-draft envelope, and a v1 robot call is never treated as a v2 command.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_envelope`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-11'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-11 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-11 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g11.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md and contracts/README.md: envelope, authority, and the compatibility facade.
- [ ] contracts/message.schema.json: required envelope keys and payload kinds.
- [ ] contracts/examples/drone-observation.json and contracts/examples/ground-to-dog-command.json: one observation and one command.
- [ ] plan.md §6: frozen v1 robot methods that this task must leave untouched.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g11/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g11/**`, `fixtures/ground/g11/**`, and `handoff/ground/g11.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] FeatureRequest carrying one UTF-8 JSON object, the expected source and destination, and the current mission epoch.
- [ ] BaseServices clock and StatePort from the merged Tasks 01–10 baseline.
- [ ] Task-owned copies of the synthetic examples, plus malformed fixtures.

Outputs:
- [ ] FeatureResult ok with the parsed envelope, kind, and correlation fields, or blocked with a stable diagnostic.
- [ ] A proposed journal event that records acceptance or rejection and never includes a credential.
- [ ] No DogPort, DronePort, or model call in either result.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_envelope` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/drone-observation.json — observation envelope the drone teammate sends Ground.
- [ ] contracts/examples/ground-to-dog-command.json — command envelope Ground sends the dog app.
- [ ] contracts/message.schema.json — the structural rules this task enforces.

### Implementation scope

- [ ] Create the provider in patrol/ground/extensions/g11/ and register only feature.v2_envelope in a ground-task-v2 manifest.
- [ ] Require protocol_version 2.0-draft, the twelve envelope fields, a known kind, and a payload object.
- [ ] Reject unknown fields, truncated JSON, a second JSON value, and a payload whose shape does not match its kind.
- [ ] Require simulated=true on the bundled examples and reject a fixture that claims simulated=false while using the synthetic artifact hashes.
- [ ] Require a non-null expires_at on command, proposal, and vision.request kinds. Observations may omit an expiry.
- [ ] Reject a source/destination pair that contradicts the kind, such as a drone.command whose source is vision.
- [ ] Treat message_id as immutable. A duplicate message_id returns the stored result and does not create a second action.
- [ ] Reject an epoch that does not match the current session, and do not let a reconnect refresh expires_at.
- [ ] Map correlation_id, frame_id, track_id, beacon_epoch, map_epoch, and camera_epoch into the result when the payload contains them.
- [ ] Leave patrol/contract.py, the v1 loader, and Tasks 01–10 files unmodified. Tests call create() directly.
- [ ] Write handoff/ground/g11.md with the accepted kinds and the rejection diagnostics.
- [ ] Load examples through task-owned fixtures so this card does not import another task package.

### Outside this task

- [ ] Do not approve motion, call xAI, or open a socket.
- [ ] Do not edit the section 7 v1 slot names or Task 09's phone-incident workflow.
- [ ] Do not implement dog, drone, or Pi behavior beyond parsing.

### Required edge cases

- [ ] A valid drone observation with pose null is accepted. Null means unknown, and this task must not fill in coordinates.
- [ ] The same command message submitted twice yields one stored result.
- [ ] The same command_id with a different payload is rejected as a conflict.
- [ ] A vision.request with expires_at null is rejected.
- [ ] An expired command is rejected and produces no motion trace.
- [ ] A halt command is still schema-valid when an ordinary command has expired. This task only parses it; Task 28 ranks it.
- [ ] UTF-8 BOM, comments, and trailing commas fail parsing.
- [ ] Add further malformed-envelope cases you find, and record any you leave untested.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Load the Task 01 harness with only G11 active and an isolated output directory.
- [ ] Parse drone-observation.json and ground-to-dog-command.json and observe accepted kinds with empty adapter traces.
- [ ] Submit the dog command twice and observe one stored acceptance.
- [ ] Submit a command with the wrong source and observe rejection.
- [ ] Submit expired and null-expiry commands and observe rejection before any gateway invoke.
- [ ] Change the session epoch with a barrier held across parse, then observe the late result marked stale.
- [ ] Confirm the journal projection has mission, epoch, kind, and message_id, and no key material.
- [ ] Release barriers and record the simulation report in the handoff.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g11/; existing shared tests alone do not satisfy this assignment.
- [ ] Known-good observation and command fixtures round-trip their correlation fields.
- [ ] Duplicate message_id is idempotent.
- [ ] Conflicting command_id, bad epoch, and expired command are rejected.
- [ ] Unknown kind and extra payload fields are rejected.
- [ ] Synthetic simulated=false is rejected.
- [ ] A result that finishes after epoch change cannot enter the new session.
- [ ] Adapter motion traces stay empty for every case.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g11 -q
python -m patrol.ground.sim --task 11 --case all --seed 0 --report artifacts/task-11/simulation.json
python -m patrol.ground.quality --task 11
git diff --check
```

### Completion and handoff

- [ ] Only G11-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g11.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 12: Admit device capabilities and arm only reported features

**Local task key:** GROUND-12. **Nature:** Session-admission feature for dog, drone, and Pi capability reports.
**Outcome:** The demo arms downward video, controlled motion, LiDAR, SLAM, and RSSI only when that peer reports them, with acceptance evidence.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_capabilities`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-12'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-12 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-12 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g12.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md sections on capability exchange and unresolved Tello control.
- [ ] contracts/drone-to-ai.md and contracts/dog-to-ai.md: what each capability flag means.
- [ ] contracts/examples/drone-capabilities.json, dog-capabilities.json, and pi-capabilities.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g12/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g12/**`, `fixtures/ground/g12/**`, and `handoff/ground/g12.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Three capabilities.report envelopes for drone-01, dog-01, and pi-01, already parsed by a frozen envelope fixture.
- [ ] GroundSettings profile for the proposed flight, dog transport, and RSSI receiver.
- [ ] A disarmed session snapshot.

Outputs:
- [ ] A feature set with each flag true only when the matching report says true and validated=true.
- [ ] A blocked result when a required peer is missing, stale, or contradicts the selected profile.
- [ ] Proposed capability events. No takeoff, stand, or RSSI guidance permission is included.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_capabilities` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/drone-capabilities.json — Tello EDU report, including controlled_motion and downward_video.
- [ ] contracts/examples/dog-capabilities.json — Go2 PRO report, including lidar and slam.
- [ ] contracts/examples/pi-capabilities.json — Pi report with rssi_receiver.

### Implementation scope

- [ ] Register feature.v2_capabilities from g12 only.
- [ ] Accept role values dog, drone, and pi, and require the device_id to match the connected profile.
- [ ] Store model, software_version, supported_commands, and acceptance_evidence_ref on the armed record.
- [ ] Arm controlled_motion, downward_video, rssi_receiver, lidar, slam, and target_range independently.
- [ ] Leave a feature disarmed when validated is false or the acceptance reference is null.
- [ ] Reject a report that claims a command the demo might send when that command is absent from supported_commands.
- [ ] Reject a second owner for the same role in one mission.
- [ ] Record the Pi and the broken back-router as different devices. A router failure does not change the Pi report.
- [ ] Return the armed set to later cards through the result data. Do not import those cards.
- [ ] Preserve an honest copy of the teammate's reported control fault: controlled_motion false stays false.
- [ ] Write the handoff so the drone and dog teammates can see which flags Ground will believe.
- [ ] Keep credentials and radio passwords out of the capability event.

### Outside this task

- [ ] Do not probe the network or connect to hardware to invent a capability.
- [ ] Do not turn controlled_motion on because the Tello SDK documentation lists move commands.
- [ ] Do not start search, homing, or vision.

### Required edge cases

- [ ] A drone report with controlled_motion false and downward_video false disarms both and remains ok as a report.
- [ ] A profile that requires autonomous search while controlled_motion is false returns blocked, not a random-motion plan.
- [ ] A dog report with lidar true and slam false arms reactive-avoidance eligibility only. Task 20 consumes that fact from a fixture.
- [ ] A Pi report with rssi_receiver false blocks RSSI homing and leaves vision-only dog approach available for a later card to refuse or accept.
- [ ] validated false with a confident feature map does not arm.
- [ ] Mismatched role and device_id is rejected.
- [ ] A replay of the same report id is idempotent.
- [ ] Add a case for a drone that reports downward video but not the downward camera id.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Seed the three example capability files and observe all three peers admitted.
- [ ] Flip drone controlled_motion to false and observe autonomous search blocked.
- [ ] Omit the Pi report and observe RSSI disarmed with a stable reason.
- [ ] Mark slam false while lidar stays true and observe the navigation mode left unresolved for Task 20's fixture.
- [ ] Submit a validated=false dog report and observe no armed motion.
- [ ] Replay one report and observe a single armed record.
- [ ] Confirm no adapter connect or invoke calls.
- [ ] Save the armed-set projection in the handoff.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g12/; existing shared tests alone do not satisfy this assignment.
- [ ] Example capability files produce the expected armed flags.
- [ ] Unvalidated and missing reports cannot arm.
- [ ] Command allowlists are enforced.
- [ ] Pi identity stays distinct from the failed router.
- [ ] Duplicate reports do not double-arm.
- [ ] Autonomous search is blocked when controlled motion is false.
- [ ] No gateway motion calls appear.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g12 -q
python -m patrol.ground.sim --task 12 --case all --seed 0 --report artifacts/task-12/simulation.json
python -m patrol.ground.quality --task 12
git diff --check
```

### Completion and handoff

- [ ] Only G12-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g12.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 13: Ingest drone observations and preserve height reference

**Local task key:** GROUND-13. **Nature:** Observation feature for airborne scout telemetry.
**Outcome:** Ground stores flight state, battery, beacon, active command, and a height estimate only together with its reference.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_drone_observation`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-13'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-13 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-13 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g13.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md drone sequence and the 4 m profile note.
- [ ] contracts/drone-to-ai.md: observation and height rules.
- [ ] contracts/examples/drone-observation.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g13/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g13/**`, `fixtures/ground/g13/**`, and `handoff/ground/g13.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A parsed drone.observation envelope.
- [ ] The armed drone capability fixture from a task-owned copy, not from g12.
- [ ] Current mission epoch and monotonic receive time.

Outputs:
- [ ] A normalized observation with flight_state, height_estimate_m, height_reference, beacon, and frame metadata or null.
- [ ] Rejection when the height is labeled floor_agl without a reported floor reference, or when required beacon fields are missing.
- [ ] A proposed observation event. No command is produced.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_drone_observation` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/drone-observation.json — the drone-to-Ground log, including a 4 m example and a downward frame.
- [ ] The beacon object inside that file is inputs to Task 19; this task only checks it is present and well formed.

### Implementation scope

- [ ] Register feature.v2_drone_observation from g13 only.
- [ ] Accept flight_state grounded, airborne, or unknown. Unknown stays unknown.
- [ ] Store battery_percent when present and reject values outside 0–100.
- [ ] Keep pose null when the drone has no map pose. Do not invent x, y, or yaw.
- [ ] Require height_reference floor_agl, takeoff_relative, or unknown whenever height_estimate_m is present.
- [ ] Reject a 4 m value labeled floor_agl unless the observation's reference is floor_agl. A takeoff-relative SDK number stays takeoff_relative.
- [ ] Require the beacon id, BSSID, SSID, beacon_epoch, hold_state, and hold window.
- [ ] Carry frame metadata through when present, and allow frame null when no picture was captured.
- [ ] Record active_command_id or null. Do not treat a matching id as completion; Task 18 owns acknowledgements.
- [ ] Stamp local receive time beside the sender timestamp and keep both.
- [ ] Reject an observation whose device_id is not the armed drone.
- [ ] Hand the normalized record to the journal proposal with mission and epoch.

### Outside this task

- [ ] Do not call takeoff, move, hover, or land.
- [ ] Do not decide that the beacon is stable enough for the dog. Task 19 owns that policy.
- [ ] Do not decode image bytes. Task 14 owns the artifact.

### Required edge cases

- [ ] The example observation is accepted with height 4 m and reference floor_agl.
- [ ] The same numbers with reference unknown are stored as unknown height, not as an approved 4 m profile.
- [ ] pose null remains null.
- [ ] flight_state unknown does not become airborne because a frame is attached.
- [ ] A BSSID that is not six octets is rejected.
- [ ] An observation for a different device_id is rejected.
- [ ] A late observation after epoch change is stale.
- [ ] Battery null is allowed and stays null.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Accept the example observation and record height, reference, and beacon epoch.
- [ ] Relabel the reference unknown and observe no floor-AGL claim.
- [ ] Drop the pose and observe a valid stored null.
- [ ] Corrupt the BSSID and observe rejection with no state write.
- [ ] Hold the apply barrier, advance the epoch, and observe a stale result.
- [ ] Confirm the trace contains no drone command method.
- [ ] Project sender time and local receive time separately.
- [ ] Write the simulation report.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g13/; existing shared tests alone do not satisfy this assignment.
- [ ] Example observation normalizes cleanly.
- [ ] Height reference is preserved and cannot be upgraded.
- [ ] Null pose and null battery survive.
- [ ] Bad BSSID and foreign device_id fail.
- [ ] Unknown flight state stays unknown.
- [ ] Epoch races do not commit.
- [ ] No command methods are invoked.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g13 -q
python -m patrol.ground.sim --task 13 --case all --seed 0 --report artifacts/task-13/simulation.json
python -m patrol.ground.quality --task 13
git diff --check
```

### Completion and handoff

- [ ] Only G13-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g13.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 14: Check camera epoch, frame provenance, and image bytes

**Local task key:** GROUND-14. **Nature:** Evidence feature for front and downward frames.
**Outcome:** A frame can be sent onward only after its camera, epoch, hash, and resolved bytes agree.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_frame`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-14'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-14 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-14 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g14.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md downward-camera section.
- [ ] contracts/drone-to-ai.md and contracts/vision.md: artifact resolution.
- [ ] contracts/examples/drone-observation.json and contracts/examples/dog-observation.json for their frame objects.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g14/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g14/**`, `fixtures/ground/g14/**`, and `handoff/ground/g14.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A frame object from a drone or dog observation fixture.
- [ ] Task-owned image bytes and the declared sha256.
- [ ] Base evidence service for JPEG checks, and the previous camera epoch stored in the fixture snapshot.

Outputs:
- [ ] An accepted frame handle with camera_id, camera_epoch, captured_at, and a resolved artifact reference.
- [ ] Rejection when the hash mismatches, the camera id is unknown, or downward is labeled as a rear camera.
- [ ] A proposed evidence event. No vision request is sent by this task.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_frame` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] Frame inside contracts/examples/drone-observation.json — downward 320×240 example.
- [ ] Frame inside contracts/examples/dog-observation.json — dog front-camera example.
- [ ] contracts/examples/drone-vision-request.json — shows the frame a later card may forward after this check.

### Implementation scope

- [ ] Register feature.v2_frame from g14 only.
- [ ] Allow camera_id front or downward. Reject rear, back, and empty.
- [ ] Require width and height above zero. The downward example is 320×240 and the front example is 1280×720; accept other positive sizes when the camera epoch changes with them.
- [ ] Require a 64-character sha256 and compare it to the resolved bytes.
- [ ] Resolve artifact:// through the task fixture store. A bare Windows path is not an artifact on another machine.
- [ ] Reject simulated=false when the bytes are the bundled synthetic placeholder.
- [ ] Increment expectations: a camera switch, resolution change, or calibration change must arrive with a new camera_epoch.
- [ ] Reject a frame that reuses the previous epoch after a switch.
- [ ] Keep camera_to_body_calibration_id null when the teammate has no calibration, and surface that null to the result.
- [ ] Use the baseline JPEG validator for real JPEG fixtures and reject text renamed to .jpg.
- [ ] Record captured_at from the frame. Do not replace it with file modification time.
- [ ] Leave the bytes in the artifact store and pass only the handle onward.

### Outside this task

- [ ] Do not call xAI.
- [ ] Do not switch the Tello camera yourself.
- [ ] Do not approve motion from a good picture.

### Required edge cases

- [ ] The downward example hash matches its synthetic bytes and is accepted.
- [ ] A single flipped hash bit is rejected.
- [ ] camera_id rear is rejected.
- [ ] A front frame that keeps the old camera_epoch after a declared switch is rejected.
- [ ] Calibration null is accepted and flagged uncalibrated.
- [ ] A path that exists only on the sender laptop is rejected.
- [ ] A disappearing file during validation fails closed.
- [ ] An epoch change mid-validation makes the result stale.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Accept a matching downward JPEG fixture.
- [ ] Accept a matching dog front JPEG fixture.
- [ ] Mismatch the hash and observe rejection.
- [ ] Replay a switched camera at the old epoch and observe rejection.
- [ ] Supply a rear camera id and observe rejection.
- [ ] Remove the file while validation is paused and observe failure.
- [ ] Confirm no vision or motion calls.
- [ ] Record artifact paths in the handoff.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g14/; existing shared tests alone do not satisfy this assignment.
- [ ] Hash match and mismatch.
- [ ] Front and downward identities, and rejection of rear.
- [ ] Camera epoch must change across a switch.
- [ ] Null calibration is preserved.
- [ ] Non-JPEG payload is rejected.
- [ ] Capture time is not replaced by file mtime.
- [ ] No model or motion calls.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g14 -q
python -m patrol.ground.sim --task 14 --case all --seed 0 --report artifacts/task-14/simulation.json
python -m patrol.ground.quality --task 14
git diff --check
```

### Completion and handoff

- [ ] Only G14-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g14.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 15: Schedule vision requests and drop stale frames

**Local task key:** GROUND-15. **Nature:** Timing feature for the xAI request path.
**Outcome:** Ground emits at most one vision.request at a time, from the latest frame only, and drops anything older than the evidence budget.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_vision_schedule`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-15'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-15 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-15 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g15.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md provider timing paragraph.
- [ ] contracts/vision.md: stages, deadlines, and one-in-flight rule.
- [ ] contracts/examples/drone-vision-request.json and dog-vision-request.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g15/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g15/**`, `fixtures/ground/g15/**`, and `handoff/ground/g15.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] An accepted frame handle fixture, a stage name, and the target description.
- [ ] Scheduler settings: sample 1000 ms, timeout 5000 ms, evidence age 3000 ms, max in flight 1.
- [ ] A manual clock and a fixture showing whether a request is already in flight.

Outputs:
- [ ] A vision.request envelope addressed ground → vision, correlated to the frame, with expires_at set.
- [ ] A dropped result when the frame is older than the evidence budget or another request is in flight.
- [ ] No vision.decision and no device command.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_vision_schedule` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/drone-vision-request.json — drone_search request the vision teammate receives.
- [ ] contracts/examples/dog-vision-request.json — dog_acquire request.
- [ ] Both are proposals of the exact JSON shape this task must emit.

### Implementation scope

- [ ] Register feature.v2_vision_schedule from g15 only.
- [ ] Accept stages drone_search, drone_track, dog_acquire, and dog_approach.
- [ ] Copy frame_id, captured_at, camera_id, camera_epoch, and the artifact reference into the request.
- [ ] Set provider xai, the configured model id, and prompt_version from settings. Refuse to invent a live model name when the setting is still the placeholder.
- [ ] Set max_evidence_age_ms from settings and expires_at from the manual clock plus the request timeout.
- [ ] Sample no faster than the configured interval. A burst of frames yields one request for the newest fresh frame.
- [ ] While one request is in flight, drop older queued frames and keep only the newest for the next slot.
- [ ] Reject a request whose frame age already exceeds the evidence budget.
- [ ] Include active_track_id when the fixture has one, and null during the first drone search.
- [ ] Include the staged-demo scene context from settings. The model must not be asked to infer criminal intent.
- [ ] Use a new request_id per emitted request. Retrying the same frame after a timeout uses a new id and still cites the same frame_id.
- [ ] Record dropped-frame counts on the result for Task 31's later metric fixture.

### Outside this task

- [ ] Do not perform the HTTP call to xAI.
- [ ] Do not interpret the picture.
- [ ] Do not move the dog or drone while waiting.

### Required edge cases

- [ ] A fresh drone frame emits the drone_search shape.
- [ ] A second frame 200 ms later is held, not sent, while the first request is in flight.
- [ ] A frame older than 3000 ms is dropped even if no request is in flight.
- [ ] dog_acquire without a track id is rejected.
- [ ] drone_search with a null track id is accepted.
- [ ] Placeholder model id is copied through and marked unresolved; it does not become a real model.
- [ ] A timeout expiry does not silently resend the old request_id.
- [ ] Clock uncertainty larger than the age budget blocks emission.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Emit one drone request from a fresh frame at t=0.
- [ ] Deliver three frames during the in-flight window and observe one follow-up request for the newest.
- [ ] Age a frame past 3000 ms and observe a drop.
- [ ] Request dog_acquire with and without a track id.
- [ ] Advance the clock past the timeout and observe the old request unusable.
- [ ] Count dropped frames in the result.
- [ ] Confirm the model port and both device ports have no calls.
- [ ] Save the emitted JSON beside the example and compare required keys.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g15/; existing shared tests alone do not satisfy this assignment.
- [ ] Stage allowlist and track-id rule.
- [ ] One in flight, newest frame wins.
- [ ] Evidence-age drop.
- [ ] Timeout does not reuse request_id.
- [ ] Emitted JSON contains the example's required keys.
- [ ] Placeholder model id is not rewritten.
- [ ] No network and no motion.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g15 -q
python -m patrol.ground.sim --task 15 --case all --seed 0 --report artifacts/task-15/simulation.json
python -m patrol.ground.quality --task 15
git diff --check
```

### Completion and handoff

- [ ] Only G15-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g15.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 16: Validate xAI decisions and withhold motor authority

**Local task key:** GROUND-16. **Nature:** Decision feature for vision.decision messages.
**Outcome:** A person detection can open or update a track and a semantic proposal, and it cannot move a robot by itself.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_vision_decision`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-16'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-16 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-16 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g16.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] contracts/vision.md and contracts/ai-to-drone.md.
- [ ] contracts/examples/drone-vision-decision.json and dog-vision-decision.json.
- [ ] contracts/examples/ai-to-drone-proposal.json: a proposal is not a command.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g16/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g16/**`, `fixtures/ground/g16/**`, and `handoff/ground/g16.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A parsed vision.decision correlated to a known vision.request fixture.
- [ ] The request's frame_id, camera_epoch, and expiry.
- [ ] Optional current track fixture.

Outputs:
- [ ] An updated track when target_state is person_visible and the frame matches, plus an optional motion.proposal.
- [ ] A review/hold outcome for not_visible, uncertain, bad geometry, or a late frame.
- [ ] Zero device commands.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_vision_decision` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/drone-vision-decision.json — vision teammate to Ground after a drone frame.
- [ ] contracts/examples/dog-vision-decision.json — vision teammate to Ground after a dog frame.
- [ ] contracts/examples/ai-to-drone-proposal.json — semantic proposal Ground may store, not send to motors.

### Implementation scope

- [ ] Register feature.v2_vision_decision from g16 only.
- [ ] Require the decision's request_id and frame_id to match the outstanding request.
- [ ] Accept target_state person_visible, not_visible, or uncertain.
- [ ] Accept label person only. Reject identity, name, weapon, or intent labels.
- [ ] Require box_xyxy_norm length 4, each value in 0–1, with xmin < xmax and ymin < ymax.
- [ ] Store confidence as a model score. Do not treat it as a probability or a permission.
- [ ] Map image_direction left, center, right, or unknown. Record that this direction is image space.
- [ ] Open a track on the first accepted drone_search person. Reuse the fixture track id when the decision already carries one.
- [ ] Emit a motion.proposal only as data on the result. Leave command creation to Tasks 17 and 23.
- [ ] Force suggested_action review or hold when the frame is uncalibrated and the action would require a body-frame move.
- [ ] Reject SDK strings, RC values, or distances invented inside the decision payload.
- [ ] Drop a decision that arrives after the request expiry or for an older camera epoch, and do not clear an existing halt.

### Outside this task

- [ ] Do not send drone.command or dog.command.
- [ ] Do not convert a bounding box into meters or global coordinates.
- [ ] Do not call the model again from this card.

### Required edge cases

- [ ] The drone example decision opens a track and a hold/reposition proposal with an empty motion trace.
- [ ] uncertain returns review and no proposal.
- [ ] A box of [0.8, 0.2, 0.3, 0.9] is rejected as unordered.
- [ ] A decision for a different frame_id is rejected.
- [ ] A late decision after expiry does not move the track.
- [ ] A payload field named sdk_command is an unknown-field rejection at the envelope fixture, and this task also rejects a reason string that is only a Tello command.
- [ ] Two people in one frame, with no staged association, returns review.
- [ ] person_visible on a dog frame with a mismatched track id does not steal the drone track.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Accept the drone example and observe a track and a proposal record.
- [ ] Accept uncertain and observe review with no proposal.
- [ ] Swap the frame id and observe rejection.
- [ ] Expire the request before the decision and observe no track update.
- [ ] Pass two detections and observe review.
- [ ] Assert the adapter trace has no execute, takeoff, or move.
- [ ] Record image_direction as image-space in the event payload.
- [ ] Save the report.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g16/; existing shared tests alone do not satisfy this assignment.
- [ ] Matching decision updates the track.
- [ ] Uncertain and not_visible do not authorize motion.
- [ ] Bad boxes and foreign frames fail.
- [ ] Late decisions are ignored.
- [ ] Multiple people require review.
- [ ] Proposal payload has no SDK command.
- [ ] Device ports are untouched.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g16 -q
python -m patrol.ground.sim --task 16 --case all --seed 0 --report artifacts/task-16/simulation.json
python -m patrol.ground.quality --task 16
git diff --check
```

### Completion and handoff

- [ ] Only G16-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g16.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 17: Approve one bounded drone primitive at a time

**Local task key:** GROUND-17. **Nature:** Command-approval feature for the aircraft.
**Outcome:** Ground sends a drone.command only for an allowlisted primitive that the capability report and current evidence still support.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_drone_command`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-17'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-17 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-17 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g17.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md controlled-movement section.
- [ ] contracts/ai-to-drone.md.
- [ ] contracts/examples/ai-to-drone-proposal.json, ground-to-drone-command.json, ground-to-drone-hover.json, and ground-to-drone-land.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g17/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g17/**`, `fixtures/ground/g17/**`, and `handoff/ground/g17.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A motion.proposal whose target_component is drone, or an operator search/hold/land request fixture.
- [ ] Armed capability fixture, current observation, frame calibration flag, and beacon epoch.
- [ ] An allowlist of primitive ids supplied in the task fixture.

Outputs:
- [ ] One drone.command with command_id, primitive_id, lease_ms, camera_id, and beacon_epoch.
- [ ] A rejection with a stable reason when control, calibration, freshness, or the primitive is missing.
- [ ] A proposed command event. The drone adapter is not called here; the workflow performs one later invoke.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_drone_command` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/ai-to-drone-proposal.json — AI to Ground. This is not the packet the drone executes.
- [ ] contracts/examples/ground-to-drone-command.json — Ground to the drone teammate for one track step.
- [ ] contracts/examples/ground-to-drone-hover.json and ground-to-drone-land.json — hold and land use their own primitives.

### Implementation scope

- [ ] Register feature.v2_drone_command from g17 only.
- [ ] Accept actions takeoff, search_step, track_step, hover, and land, each bound to a fixture primitive_id.
- [ ] Refuse a proposal that contains a raw SDK string or a requested displacement such as five meters.
- [ ] Set lease_ms at most 500 for search_step and track_step. That lease limits when motion may start and how long the local RC lease lasts.
- [ ] Give takeoff and land their own fixture deadlines. Do not reuse the 500 ms motion lease as a motor-cut timer.
- [ ] Require controlled_motion true for search_step and track_step. When it is false, accept only hover, land, or a labeled operator-supervised step.
- [ ] Require a calibrated camera before an autonomous track_step. Missing calibration blocks that step.
- [ ] Copy evidence frame id, track id, and the current beacon epoch onto the command.
- [ ] A search profile may pick the next primitive from a seeded allowlist with a step cap. It must not call an unbounded random move.
- [ ] Requested height is copied only when the profile and the observation reference agree. 4 m is absent unless the fixture profile allows it.
- [ ] One approval yields one command_id. Re-running the same proposal id returns the same command record.
- [ ] Leave execution acknowledgements to Task 18.

### Outside this task

- [ ] Do not import DJITelloPy or open UDP.
- [ ] Do not convert image left/right into a body yaw inside this card.
- [ ] Do not command the dog from a drone proposal.

### Required edge cases

- [ ] The example proposal becomes a track_step only when the fixture says the primitive and calibration exist.
- [ ] The same proposal with controlled_motion false is rejected.
- [ ] A five-meter move string is rejected.
- [ ] lease_ms 5000 on a track step is rejected.
- [ ] A land command is still issuable when ordinary tracking is blocked, and its deadline is the landing deadline.
- [ ] A second approval of the same proposal id does not allocate a new command.
- [ ] Height 4 with reference unknown is rejected.
- [ ] An expired proposal is rejected.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Approve the example track step against an armed, calibrated fixture and compare keys to ground-to-drone-command.json.
- [ ] Disarm controlled motion and observe rejection.
- [ ] Request land and observe the land primitive rather than a 500 ms cut.
- [ ] Submit a five-meter instruction and observe rejection.
- [ ] Replay the proposal and observe one command_id.
- [ ] Set calibration null and observe track_step blocked.
- [ ] Confirm this provider does not call the drone port; it only returns the command.
- [ ] Record the supervised-mode rejection path.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g17/; existing shared tests alone do not satisfy this assignment.
- [ ] Happy-path command matches the example keys.
- [ ] Uncontrolled motion cannot search or track.
- [ ] Lease and height reference limits hold.
- [ ] Land and hover remain available as their own primitives.
- [ ] Proposal replay is idempotent.
- [ ] Raw SDK text is rejected.
- [ ] The provider itself performs no UDP or SDK import.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g17 -q
python -m patrol.ground.sim --task 17 --case all --seed 0 --report artifacts/task-17/simulation.json
python -m patrol.ground.quality --task 17
git diff --check
```

### Completion and handoff

- [ ] Only G17-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g17.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 18: Track drone acknowledgements and preserve unknown landing

**Local task key:** GROUND-18. **Nature:** Lifecycle feature for drone command.ack messages.
**Outcome:** Accepted, running, and completed stay distinct, and a missing landing stays a recovery fault.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_drone_ack`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-18'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-18 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-18 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g18.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] contracts/ai-to-drone.md acknowledgement section.
- [ ] contracts/events-and-logs.md command lifecycle.
- [ ] contracts/examples/drone-ack-accepted.json, drone-ack-running.json, drone-ack-completed.json, and drone-landing-unknown.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g18/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g18/**`, `fixtures/ground/g18/**`, and `handoff/ground/g18.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A drone command.ack envelope and the matching drone.command fixture.
- [ ] Current aircraft observation fixture.
- [ ] Manual clock for the reply deadline.

Outputs:
- [ ] A lifecycle record for that command_id.
- [ ] A query-required outcome when the deadline passes with no terminal ack.
- [ ] A recovery-required outcome for landing state unknown. No replacement takeoff.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_drone_ack` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/drone-ack-accepted.json — accepted is not completed.
- [ ] contracts/examples/drone-ack-running.json and drone-ack-completed.json — later states of the same command.
- [ ] contracts/examples/drone-landing-unknown.json — unknown landing log.

### Implementation scope

- [ ] Register feature.v2_drone_ack from g18 only.
- [ ] Accept states accepted, running, completed, rejected, cancelled, failed, and unknown.
- [ ] Bind every ack to the command_id that was issued. An unknown command_id is rejected.
- [ ] Store observed_motion and verified exactly as reported.
- [ ] Treat accepted as non-terminal. Require a later running or final state for completion.
- [ ] Treat completed on a track step as motion finished, not as landed. flight_state may remain airborne.
- [ ] On reply timeout, emit query_command and keep the command unresolved. Do not mint a new takeoff or move.
- [ ] A second final ack with the same payload is idempotent. A conflicting final state is a fault.
- [ ] landing state unknown sets recovery_required and blocks the next mission.
- [ ] A local is_flying default in the payload detail does not count as grounded.
- [ ] Correlate the ack message_id to the command message_id.
- [ ] Leave the dog's lifecycle to Task 24.

### Outside this task

- [ ] Do not issue a new drone.command from this card.
- [ ] Do not clear a demo goal. Task 27 separates goal and landing.
- [ ] Do not power-cycle the aircraft in software.

### Required edge cases

- [ ] accepted then running then completed on one track command succeeds, and the aircraft can still be airborne.
- [ ] completed is rejected as a landing proof when the command action was track_step.
- [ ] Timeout produces query_command and no second command_id.
- [ ] The landing-unknown example sets recovery_required.
- [ ] Duplicate completed ack does not create a second completion event.
- [ ] completed followed by failed for the same id is a conflict fault.
- [ ] Ack for a foreign epoch is stale.
- [ ] verified false on completed does not count as verified completion.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Play the three track-step acks in order and observe one lifecycle.
- [ ] Stop after accepted and observe a non-terminal record.
- [ ] Expire the reply timer and observe query_command with the original command_id.
- [ ] Play drone-landing-unknown.json and observe recovery_required.
- [ ] Replay the final ack and observe one completion.
- [ ] Conflict the final state and observe a fault.
- [ ] Confirm no new takeoff command is proposed.
- [ ] Save the lifecycle projection.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g18/; existing shared tests alone do not satisfy this assignment.
- [ ] Ordered acks update one command.
- [ ] Accepted is not completed.
- [ ] Timeout queries and does not reissue.
- [ ] Unknown landing requires recovery.
- [ ] Duplicate final ack is idempotent.
- [ ] Conflicting final ack faults.
- [ ] Track completion does not imply grounded.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g18 -q
python -m patrol.ground.sim --task 18 --case all --seed 0 --report artifacts/task-18/simulation.json
python -m patrol.ground.quality --task 18
git diff --check
```

### Completion and handoff

- [ ] Only G18-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g18.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 19: Require a stable beacon hold and advance beacon epoch after motion

**Local task key:** GROUND-19. **Nature:** Safety feature for the Tello radio source.
**Outcome:** The dog may be homed only while the drone beacon is stable, and any drone reposition invalidates old RSSI.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_beacon`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-19'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-19 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-19 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g19.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md steps on beacon hold and dog stop.
- [ ] contracts/rssi-and-navigation.md beacon epoch rules.
- [ ] Beacon object in contracts/examples/drone-observation.json and the beacon_epoch on contracts/examples/ground-to-drone-command.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g19/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g19/**`, `fixtures/ground/g19/**`, and `handoff/ground/g19.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] The latest normalized beacon fixture and drone flight_state.
- [ ] The previous beacon epoch and whether a drone command is running.
- [ ] Manual clock compared with hold_valid_until.

Outputs:
- [ ] hold_state stable, moving, or unknown, plus dog_motion_allowed true only for a current stable hold.
- [ ] A new beacon epoch requirement when a drone reposition completes.
- [ ] A proposed beacon event. No dog command is created here.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_beacon` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] Beacon inside contracts/examples/drone-observation.json — stable hold example.
- [ ] contracts/examples/ground-to-drone-command.json — a reposition that moves beacon_epoch from 3 to 4 in the example story.
- [ ] contracts/examples/event-dog_dispatched.json — dispatch is legal only after this policy would allow it.

### Implementation scope

- [ ] Register feature.v2_beacon from g19 only.
- [ ] Accept hold_state stable, moving, or unknown.
- [ ] Allow dog motion only when hold_state is stable, flight_state is airborne, and now is inside hold_valid_until.
- [ ] Set dog_motion_allowed false for moving, unknown, grounded, or an expired hold window.
- [ ] When a drone search or track command is running, force the hold to moving and block the dog.
- [ ] After that command completes, require the next observation to use a higher beacon_epoch before any RSSI comparison.
- [ ] Mark windows from the previous epoch incomparable. Do not delete them; label them invalid.
- [ ] A hover that does not change position may keep the epoch when the fixture says the beacon did not move.
- [ ] Reject a hold that cites a different BSSID than the armed drone.
- [ ] Unknown aircraft state blocks the dog even if the last hold was stable.
- [ ] Publish the current epoch on the result for Task 21 fixtures.
- [ ] Keep this policy free of RSSI math.

### Outside this task

- [ ] Do not read Wi-Fi from the laptop as a substitute beacon.
- [ ] Do not issue the dog command that the hold would allow.
- [ ] Do not fly the drone to create a hold.

### Required edge cases

- [ ] A fresh stable hold allows dog motion.
- [ ] hold_state moving blocks the dog.
- [ ] A stable label whose hold_valid_until is in the past blocks the dog.
- [ ] Completing a track step requires a new epoch before the old window can be used.
- [ ] A window tagged with the old epoch is incomparable.
- [ ] BSSID mismatch is rejected.
- [ ] flight_state unknown blocks the dog.
- [ ] A duplicate observation of the same hold is idempotent.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Accept the example stable beacon and observe dog_motion_allowed true.
- [ ] Switch the hold to moving and observe false.
- [ ] Expire the window and observe false.
- [ ] Complete a reposition and observe the old epoch unusable.
- [ ] Supply the next epoch and observe comparisons allowed again once the hold is stable.
- [ ] Mismatch the BSSID and observe rejection.
- [ ] Confirm no dog execute call.
- [ ] Record both epochs in the report.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g19/; existing shared tests alone do not satisfy this assignment.
- [ ] Stable, moving, and expired holds.
- [ ] Running drone command blocks the dog.
- [ ] Epoch advances after reposition.
- [ ] Old windows are incomparable and retained.
- [ ] BSSID and unknown flight state fail closed.
- [ ] Hover without motion can keep the epoch when the fixture says so.
- [ ] No dog command is emitted.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g19 -q
python -m patrol.ground.sim --task 19 --case all --seed 0 --report artifacts/task-19/simulation.json
python -m patrol.ground.quality --task 19
git diff --check
```

### Completion and handoff

- [ ] Only G19-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g19.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 20: Accept dog navigation health and safe local candidates

**Local task key:** GROUND-20. **Nature:** Observation feature for the Go2 planner boundary.
**Outcome:** Ground can rank only the candidate ids the dog app marks safe, and it never invents a path around an obstacle.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_dog_navigation`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-20'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-20 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-20 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g20.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md LiDAR, SLAM, and planning section.
- [ ] contracts/dog-to-ai.md and contracts/rssi-and-navigation.md.
- [ ] contracts/examples/dog-observation.json and dog-navigation-candidates.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g20/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g20/**`, `fixtures/ground/g20/**`, and `handoff/ground/g20.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A dog.observation envelope and a navigation.candidates envelope for the same device.
- [ ] Armed dog capability fixture with lidar and slam flags.
- [ ] Current map epoch fixture.

Outputs:
- [ ] A readiness record: standing, stationary, avoidance, navigation_mode, slam_state, and minimum_clearance_m.
- [ ] The list of candidate ids that are safe and unexpired, or blocked true with an empty list.
- [ ] No motion command. Clearance is not target range.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_dog_navigation` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/dog-observation.json — dog-to-Ground pose, LiDAR freshness, and mode.
- [ ] contracts/examples/dog-navigation-candidates.json — the only steps Ground may later select.

### Implementation scope

- [ ] Register feature.v2_dog_navigation from g20 only.
- [ ] Preserve standing, stationary, and avoidance_enabled as true, false, or null. Null is not true.
- [ ] Accept navigation_mode slam_local_planner, reactive_avoidance, or unavailable.
- [ ] When slam is disarmed, reject a payload that claims slam_local_planner.
- [ ] Require lidar_observed_at and minimum_clearance_m for any candidate list that is non-empty.
- [ ] Store map_id and map_epoch with the pose. A candidate from another map epoch is unusable.
- [ ] Accept a candidate only when safe is true, its frame is dog/base_link, and valid_until is still in the future.
- [ ] An empty list with blocked true is a successful observation meaning stop and review.
- [ ] Reject a candidate that includes a target range. Obstacle clearance stays in minimum_clearance_m.
- [ ] Require the dog transport ethernet or wifi to match the selected profile before declaring readiness.
- [ ] Carry the front-camera frame handle through without interpreting it.
- [ ] Return candidate ids for Task 22 to consume from a fixture copy.

### Outside this task

- [ ] Do not run a SLAM implementation.
- [ ] Do not command a detour when blocked is true.
- [ ] Do not treat the closest obstacle as the person.

### Required edge cases

- [ ] The example observation and candidate are accepted together.
- [ ] blocked true and an empty list yield ready-to-wait, not a synthetic forward step.
- [ ] A safe candidate with an expired valid_until is dropped.
- [ ] slam_local_planner while the capability says slam false is rejected.
- [ ] minimum_clearance_m is stored and is not copied into a target range field.
- [ ] standing null blocks route readiness.
- [ ] A candidate in a different map epoch is dropped.
- [ ] Ethernet observation while the profile is wifi is not ready.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Load both example files and observe one safe candidate id.
- [ ] Empty the list, set blocked true, and observe no invented candidate.
- [ ] Expire the candidate and observe an empty usable set.
- [ ] Claim SLAM without the capability and observe rejection.
- [ ] Null out standing and observe not ready.
- [ ] Change map epoch and observe the candidate dropped.
- [ ] Confirm no move_local command is produced.
- [ ] Record clearance separately from any target field.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g20/; existing shared tests alone do not satisfy this assignment.
- [ ] Example files produce the documented candidate.
- [ ] Blocked empty lists stay empty.
- [ ] Expiry, map epoch, and mode mismatches fail.
- [ ] Null readiness booleans fail closed.
- [ ] Clearance is not target range.
- [ ] Transport profile is checked.
- [ ] No dog motion method is proposed.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g20 -q
python -m patrol.ground.sim --task 20 --case all --seed 0 --report artifacts/task-20/simulation.json
python -m patrol.ground.quality --task 20
git diff --check
```

### Completion and handoff

- [ ] Only G20-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g20.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 21: Validate Raspberry Pi RSSI windows sampled on the dog

**Local task key:** GROUND-21. **Nature:** Radio-evidence feature for the dog-mounted receiver.
**Outcome:** A window can guide the dog only when it names the drone BSSID, the current beacon epoch, and the dog pose at each sample.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_rssi`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-21'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-21 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-21 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g21.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md RSSI section.
- [ ] contracts/rssi-and-navigation.md.
- [ ] contracts/examples/pi-rssi-window.json and pi-heartbeat.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g21/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g21/**`, `fixtures/ground/g21/**`, and `handoff/ground/g21.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] An rssi.window envelope and a recent heartbeat fixture.
- [ ] The current beacon id, BSSID, and beacon epoch from a Task 19-shaped fixture.
- [ ] Dog pose and map epoch from a navigation fixture.

Outputs:
- [ ] A comparable window with median, spread, quality, and per-sample poses, or a rejected window.
- [ ] quality unavailable with null statistics when there is no signal. Never a fake 0 dBm.
- [ ] No heading and no distance in meters.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_rssi` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/pi-rssi-window.json — Pi to Ground. This is the RSSI log.
- [ ] contracts/examples/pi-heartbeat.json — liveness and clock_error_ms.
- [ ] Laptop RSSI is not a supported example and must not be accepted under another name.

### Implementation scope

- [ ] Register feature.v2_rssi from g21 only.
- [ ] Require receiver_mount dog and a receiver_id that matches the armed Pi.
- [ ] Require the BSSID pattern and an exact match to the armed drone beacon. SSID alone is insufficient.
- [ ] Require beacon_epoch equal to the current hold epoch.
- [ ] Require each sample's rssi_dbm in the closed range -150 to 0, plus a pose with the dog map epoch.
- [ ] Reject quality valid when samples are empty or the heartbeat is missing or unhealthy.
- [ ] Store clock_error_ms and reject the window when it exceeds the fixture limit.
- [ ] Preserve raw samples and the reported median and spread. Do not replace them with a meters estimate.
- [ ] Accept quality noisy, stale, or unavailable as observations that Task 22 must not follow.
- [ ] Map no-signal to quality unavailable, empty samples, and null median. Reject 0 dBm used as a sentinel.
- [ ] Record the interface name. Do not open that interface.
- [ ] A window measured while the beacon epoch was moving is rejected as incomparable.

### Outside this task

- [ ] Do not scan Wi-Fi or change routes.
- [ ] Do not compute a bearing from antenna rotation.
- [ ] Do not issue a dog step.

### Required edge cases

- [ ] The example window is comparable when the fixture epoch and BSSID match.
- [ ] The same window with beacon_epoch 2 while the hold is epoch 3 is rejected.
- [ ] SSID match with a different BSSID is rejected.
- [ ] An empty sample list with median 0 is rejected.
- [ ] An empty list with quality unavailable and null median is accepted as no-signal.
- [ ] clock_error_ms above the limit is rejected.
- [ ] A sample pose on another map epoch drops the window.
- [ ] A heartbeat older than the fixture limit drops the window.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Accept the example window and heartbeat together.
- [ ] Change the epoch and observe incomparable.
- [ ] Swap the BSSID and observe rejection.
- [ ] Send a no-signal window and observe null statistics.
- [ ] Send median 0 with no samples and observe rejection.
- [ ] Increase clock error and observe rejection.
- [ ] Confirm no socket and no dog command.
- [ ] Record quality and epoch on the result.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g21/; existing shared tests alone do not satisfy this assignment.
- [ ] Happy-path example window.
- [ ] Epoch and BSSID binding.
- [ ] No-signal encoding.
- [ ] 0 dBm sentinel rejection.
- [ ] Clock error and stale heartbeat.
- [ ] Pose map epoch binding.
- [ ] No range or bearing field is created.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g21 -q
python -m patrol.ground.sim --task 21 --case all --seed 0 --report artifacts/task-21/simulation.json
python -m patrol.ground.quality --task 21
git diff --check
```

### Completion and handoff

- [ ] Only G21-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g21.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 22: Choose an RSSI step only from safe dog candidates

**Local task key:** GROUND-22. **Nature:** Guidance feature that ranks existing candidates.
**Outcome:** Ground either names one current safe candidate_id or stops the search. It does not invent a heading from signal strength.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_rssi_homing`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-22'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-22 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-22 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g22.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] contracts/rssi-and-navigation.md guidance loop.
- [ ] contracts/examples/pi-rssi-window.json and dog-navigation-candidates.json.
- [ ] demo-v2.md step that keeps the dog stopped until the beacon hold is stable.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g22/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g22/**`, `fixtures/ground/g22/**`, and `handoff/ground/g22.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A comparable RSSI window fixture and at least two pose-tagged windows when the case compares them.
- [ ] The current safe candidate list fixture.
- [ ] dog_motion_allowed, search budget, and hysteresis settings.

Outputs:
- [ ] A selection containing one candidate_id, or a stop/review result with a reason.
- [ ] No dog.command. Task 23 turns a selection into a command.
- [ ] A proposed homing event that states the windows and epoch used.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_rssi_homing` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/pi-rssi-window.json — evidence this policy may rank.
- [ ] contracts/examples/dog-navigation-candidates.json — the only legal outputs are ids from this list.
- [ ] contracts/examples/event-dog_dispatched.json — mission log emitted only when a selection is allowed.

### Implementation scope

- [ ] Register feature.v2_rssi_homing from g22 only.
- [ ] Require dog_motion_allowed true, quality valid, and a non-empty safe candidate list before selecting.
- [ ] Compare medians only inside one beacon epoch and one map epoch.
- [ ] Select a candidate only if it is in the current safe list and its direction is consistent with the fixture's sampled improvement.
- [ ] Apply the fixture hysteresis so a tiny improvement does not flip direction every sample.
- [ ] Stop after the fixture exploration budget, on a flat trend, or on noisy or stale quality.
- [ ] When blocked is true, return stop. Do not create a waypoint.
- [ ] Return one candidate per decision. The next decision waits for a later card's stopped acknowledgement; this task refuses to select again while a command is active in the fixture.
- [ ] Never write a meters field derived from dBm.
- [ ] A single window with no earlier sample returns hold and sample again, not a direction.
- [ ] Record the sample ids used so Task 29 can correlate them.
- [ ] If the dog-vision fixture already says the same target is acquired, return handoff and do not start another RSSI step.

### Outside this task

- [ ] Do not send move_local.
- [ ] Do not override a blocked planner.
- [ ] Do not declare arrival from a strong signal.

### Required edge cases

- [ ] Two improving windows and one forward candidate select that candidate.
- [ ] Improving windows with an empty candidate list return stop.
- [ ] quality noisy returns stop.
- [ ] dog_motion_allowed false returns stop even when the signal improves.
- [ ] A one-window history returns hold.
- [ ] An active dog command in the fixture blocks a new selection.
- [ ] A strong median such as -40 with no candidate still does not produce a range.
- [ ] Crossing the exploration budget returns stop.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Select the example forward candidate from a scripted improving pair.
- [ ] Remove candidates and observe stop.
- [ ] Mark the beacon moving and observe stop.
- [ ] Mark quality noisy and observe stop.
- [ ] Leave only one window and observe hold.
- [ ] Set an active command and observe no second selection.
- [ ] Assert the result JSON has candidate_id and no range_m.
- [ ] Record the budget-exhausted case.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g22/; existing shared tests alone do not satisfy this assignment.
- [ ] Selection stays inside the supplied ids.
- [ ] Blocked, noisy, and moving-beacon cases stop.
- [ ] Single-window history holds.
- [ ] Active command prevents a new selection.
- [ ] Budget exhaustion stops.
- [ ] No meters field is emitted.
- [ ] No dog.command is emitted.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g22 -q
python -m patrol.ground.sim --task 22 --case all --seed 0 --report artifacts/task-22/simulation.json
python -m patrol.ground.quality --task 22
git diff --check
```

### Completion and handoff

- [ ] Only G22-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g22.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 23: Issue leased dog commands and a priority halt

**Local task key:** GROUND-23. **Nature:** Command-approval feature for the Go2 app.
**Outcome:** The dog app receives one Ground-approved dog.command in its JSON schema, with a short lease, or a halt that outranks ordinary motion.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_dog_command`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-23'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-23 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-23 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g23.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] contracts/ai-to-dog.md.
- [ ] contracts/examples/ai-to-dog-proposal.json, ground-to-dog-command.json, and ground-to-dog-halt.json.
- [ ] demo-v2.md Ethernet cable note.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g23/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g23/**`, `fixtures/ground/g23/**`, and `handoff/ground/g23.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Either a homing selection fixture or a motion.proposal whose target_component is dog.
- [ ] Current candidate, beacon epoch, track id, and safety snapshot id.
- [ ] Dog readiness fixture: standing, avoidance, transport, and tether limit.

Outputs:
- [ ] A dog.command for stand, move_local, turn, or halt.
- [ ] A rejection when the candidate, lease, tether, or readiness check fails.
- [ ] The command event. This provider does not call the dog SDK.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_dog_command` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/ai-to-dog-proposal.json — vision proposal. The dog app does not execute this file.
- [ ] contracts/examples/ground-to-dog-command.json — the JSON the dog teammate parses for one step.
- [ ] contracts/examples/ground-to-dog-halt.json — halt JSON, which wins over an ordinary step.

### Implementation scope

- [ ] Register feature.v2_dog_command from g23 only.
- [ ] Build move_local in frame dog/base_link with linear_x_m_s, linear_y_m_s, angular_z_rad_s, and duration_ms.
- [ ] Use +x forward, +y left, +z up, and positive yaw counterclockwise in the command frame. Document that the dog app must test its own Unitree mapping.
- [ ] Cap lease_ms and duration_ms at 500. Reject a longer ordinary step.
- [ ] Copy candidate_id, snapshot_id, and map_epoch from the current safe candidate. Reject a candidate that is not in the fixture list.
- [ ] Copy track_id and beacon_epoch. A missing beacon epoch rejects an RSSI step and still allows a pure visual step when Task 25's fixture says vision is active.
- [ ] Require standing true and avoidance_enabled true. Null fails closed.
- [ ] For Ethernet, reject a step that the fixture tether budget says would exceed cable reach.
- [ ] Treat operator up/down as a ground-frame request in the fixture, never as a vertical flight command. The dog command has no altitude field.
- [ ] Halt uses action halt, motion null, and the same command schema. It is a posture-preserving stop, not a lie-down command.
- [ ] One proposal or selection produces one command_id. Replay returns that id.
- [ ] Ordinary approval is refused while a halt is latched in the fixture.

### Outside this task

- [ ] Do not import the Unitree client.
- [ ] Do not skip the dog app's local revalidation. The command text says the app must recheck.
- [ ] Do not pass the raw Grok JSON as the command.

### Required edge cases

- [ ] The example proposal plus the example candidate yields the ground-to-dog-command keys.
- [ ] A candidate id that was not supplied is rejected.
- [ ] duration_ms 2000 is rejected.
- [ ] avoidance null is rejected.
- [ ] Ethernet tether overrun is rejected.
- [ ] Halt is emitted even when ordinary motion is blocked.
- [ ] A second request for the same selection does not create a second move.
- [ ] A vertical altitude field on the payload is rejected.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Emit the example move and compare required keys.
- [ ] Emit halt and compare it to ground-to-dog-halt.json.
- [ ] Use an unknown candidate and observe rejection.
- [ ] Overrun the tether and observe rejection.
- [ ] Latch halt, then request a move, and observe the move refused.
- [ ] Replay the selection and observe one command_id.
- [ ] Confirm the dog port is not called inside this provider.
- [ ] Record the frame convention in the handoff for the dog teammate.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g23/; existing shared tests alone do not satisfy this assignment.
- [ ] Move command matches the example schema.
- [ ] Halt matches the halt example and outranks motion.
- [ ] Lease, candidate, avoidance, and tether failures.
- [ ] No altitude field.
- [ ] Replay is idempotent.
- [ ] Raw proposal JSON is not the emitted command.
- [ ] No SDK import.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g23 -q
python -m patrol.ground.sim --task 23 --case all --seed 0 --report artifacts/task-23/simulation.json
python -m patrol.ground.quality --task 23
git diff --check
```

### Completion and handoff

- [ ] Only G23-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g23.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 24: Track dog acknowledgements and rejected steps

**Local task key:** GROUND-24. **Nature:** Lifecycle feature for dog command.ack messages.
**Outcome:** A dog step is complete only after a verified terminal acknowledgement, and an expired command produces no motion.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_dog_ack`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-24'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-24 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-24 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g24.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] contracts/ai-to-dog.md acknowledgement section.
- [ ] contracts/examples/dog-ack-accepted.json, dog-ack-running.json, dog-ack-completed.json, and dog-command-rejected.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g24/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g24/**`, `fixtures/ground/g24/**`, and `handoff/ground/g24.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A dog command.ack and the issued dog.command fixture.
- [ ] A readiness observation after the command window.
- [ ] Manual clock.

Outputs:
- [ ] Lifecycle state for that command_id.
- [ ] A stopped confirmation only when completed, verified, and observed_motion is stationary.
- [ ] No replacement step when the ack is rejected, expired, or missing.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_dog_ack` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/dog-ack-accepted.json — accepted, not done.
- [ ] contracts/examples/dog-ack-running.json and dog-ack-completed.json — later states.
- [ ] contracts/examples/dog-command-rejected.json — expired command, dog stayed still.

### Implementation scope

- [ ] Register feature.v2_dog_ack from g24 only.
- [ ] Bind acks to the issued command_id and reject foreign ids.
- [ ] Record accepted, running, and completed as separate states.
- [ ] completed counts as stopped only when verified is true and observed_motion is stationary.
- [ ] rejected with reason_code expired_command records no movement and releases the active-command flag.
- [ ] Timeout emits query_command and does not allocate a new move.
- [ ] Duplicate terminal acks are idempotent. Conflicting terminal states fault.
- [ ] A repeated command_id must not be interpreted as permission to move again.
- [ ] Correlate ack ids to the command message.
- [ ] While running, report that Task 22 must not select another step. Expose that as data, without importing Task 22.
- [ ] A halt ack is terminal for the halt command and does not mark the previous move completed.
- [ ] Keep LiDAR stop reasons distinct from target arrival.

### Outside this task

- [ ] Do not send a new dog.command.
- [ ] Do not mark the demo goal reached.
- [ ] Do not clear a halt.

### Required edge cases

- [ ] The three success acks end in verified stationary.
- [ ] accepted alone is not stopped.
- [ ] The rejected example records zero motion.
- [ ] Timeout does not create cmd-dog-002.
- [ ] completed with verified false is not stopped.
- [ ] A halt ack leaves the earlier move non-complete.
- [ ] Conflicting completed and failed acks fault.
- [ ] Foreign epoch acks are stale.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Play the success sequence and observe stopped.
- [ ] Stop after accepted and observe not stopped.
- [ ] Play the rejected example and observe no motion flag.
- [ ] Time out and observe query without a new id.
- [ ] Complete with verified false and observe not stopped.
- [ ] Ack a halt separately from the move.
- [ ] Replay the final ack and observe one event.
- [ ] Save the lifecycle report.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g24/; existing shared tests alone do not satisfy this assignment.
- [ ] Success sequence reaches verified stop.
- [ ] Accepted and unverified completed do not.
- [ ] Expired rejection moves nothing.
- [ ] Timeout does not reissue.
- [ ] Halt ack is separate.
- [ ] Conflicts fault.
- [ ] No new command is proposed.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g24 -q
python -m patrol.ground.sim --task 24 --case all --seed 0 --report artifacts/task-24/simulation.json
python -m patrol.ground.quality --task 24
git diff --check
```

### Completion and handoff

- [ ] Only G24-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g24.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 25: Hand the dog from RSSI to its own camera

**Local task key:** GROUND-25. **Nature:** Track-association feature for the dog view.
**Outcome:** Once the dog camera reliably sees the same staged person, further dog steps use visual approach and RSSI becomes supporting evidence.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_dog_acquire`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-25'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-25 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-25 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g25.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md handoff step.
- [ ] contracts/vision.md stages dog_acquire and dog_approach.
- [ ] contracts/examples/dog-vision-request.json and dog-vision-decision.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g25/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g25/**`, `fixtures/ground/g25/**`, and `handoff/ground/g25.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A dog vision.decision fixture correlated to a dog frame.
- [ ] The current track id opened from the drone.
- [ ] A short history fixture of recent dog decisions.

Outputs:
- [ ] Mode rssi, visual, or review.
- [ ] A handoff event when the same track is visible on enough fresh dog frames.
- [ ] No command. Arrival is not declared here.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_dog_acquire` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/dog-vision-request.json — Ground to vision for the dog frame.
- [ ] contracts/examples/dog-vision-decision.json — vision back to Ground.
- [ ] RSSI windows may remain in the journal and are not the handoff signal.

### Implementation scope

- [ ] Register feature.v2_dog_acquire from g25 only.
- [ ] Require the decision frame to be the dog front camera and the current camera epoch.
- [ ] Require track_id to match the active track. A new unlabeled person returns review.
- [ ] Count person_visible results that are inside the evidence budget.
- [ ] Switch to visual after the fixture's consecutive-hit threshold, default two fresh hits.
- [ ] A single hit stays in acquiring and does not disable RSSI yet.
- [ ] uncertain or not_visible resets the hit count and stays on RSSI if homing is still allowed.
- [ ] Multiple boxes without a matching track id return review and stop automatic handoff.
- [ ] After handoff, set rssi_role to supporting. Do not delete RSSI records.
- [ ] Reject a handoff built from a stale frame or from the drone camera.
- [ ] Leave approach commands to Task 23, which will see mode visual in a fixture.
- [ ] Record the frame ids used for the handoff.

### Outside this task

- [ ] Do not declare proximity.
- [ ] Do not keep issuing RSSI selections after a successful handoff inside this result.
- [ ] Do not identify a real person.

### Required edge cases

- [ ] Two fresh matching dog hits switch the mode to visual.
- [ ] One hit remains acquiring.
- [ ] A drone-camera decision does not count.
- [ ] A mismatched track id returns review.
- [ ] A stale frame resets progress.
- [ ] not_visible between two hits prevents the switch.
- [ ] After the switch, the result says RSSI is supporting evidence.
- [ ] An empty detection list is not a switch.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Feed two example-shaped dog decisions and observe visual mode.
- [ ] Feed one and observe acquiring.
- [ ] Insert not_visible and observe the count reset.
- [ ] Use a drone frame id and observe rejection.
- [ ] Use a second track id and observe review.
- [ ] Expire the frame and observe no switch.
- [ ] Confirm no proximity goal and no command.
- [ ] Record the frame ids.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g25/; existing shared tests alone do not satisfy this assignment.
- [ ] Threshold switches only on enough fresh matches.
- [ ] One hit is not enough.
- [ ] Wrong camera and wrong track fail.
- [ ] Stale frames reset.
- [ ] RSSI records remain labeled supporting after handoff.
- [ ] Multiple strangers force review.
- [ ] No goal and no command.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g25 -q
python -m patrol.ground.sim --task 25 --case all --seed 0 --report artifacts/task-25/simulation.json
python -m patrol.ground.quality --task 25
git diff --check
```

### Completion and handoff

- [ ] Only G25-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g25.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 26: Accept the demo goal only from separate proximity evidence

**Local task key:** GROUND-26. **Nature:** Completion feature for dog range and drone horizontal offset.
**Outcome:** The goal is reached only when both current checks pass for the same track. Missing geometry stays unresolved.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_proximity`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-26'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-26 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-26 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g26.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md proximity section, including the 4 m geometry note.
- [ ] contracts/rssi-and-navigation.md success data.
- [ ] contracts/examples/proximity-evidence.json and event-demo_goal_reached.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g26/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g26/**`, `fixtures/ground/g26/**`, and `handoff/ground/g26.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A proximity.evidence payload.
- [ ] Current track id, dog stopped flag, and drone hold_state.
- [ ] Configured dog_range_max_m and drone_horizontal_max_m from the profile fixture.

Outputs:
- [ ] goal_reached true only when both checks are current, associated, and inside their own thresholds.
- [ ] unresolved when range, offset, association, or timestamps are missing.
- [ ] A mission.event proposal. Landing state is untouched.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_proximity` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/proximity-evidence.json — dog range and drone horizontal offset are different fields.
- [ ] contracts/examples/event-demo_goal_reached.json — the goal log. It is not a landing log.

### Implementation scope

- [ ] Register feature.v2_proximity from g26 only.
- [ ] Read dog.range_m and drone.horizontal_offset_m separately.
- [ ] Reject a payload that supplies a single 3D distance and asks to satisfy both checks with it.
- [ ] At a fixture height of 4 m, reject a claim that the aircraft is also within 1 m of the person's center in full 3D.
- [ ] Require dog source lidar_associated, depth, or operator, and association_valid true for a non-operator range.
- [ ] Require the dog observation to say stationary when the goal is automatic.
- [ ] Require the drone hold_state stable and a fresh horizontal offset.
- [ ] Keep obstacle clearance out of dog.range_m. A clearance value in the wrong field fails.
- [ ] Allow operator_confirmed true to satisfy a missing sensor only when the profile enables operator evidence and both operator fields are current.
- [ ] Use the profile thresholds. The 1.5 m numbers in the example are fixture values, not a universal rule.
- [ ] Emit demo_goal_reached when both checks pass. Otherwise emit unresolved and no goal event.
- [ ] Do not set flight_state or recovery flags.

### Outside this task

- [ ] Do not land the drone.
- [ ] Do not convert RSSI to the dog range.
- [ ] Do not treat a person detection as proximity.

### Required edge cases

- [ ] The example evidence passes when the fixture thresholds are 1.5 m and both timestamps are fresh.
- [ ] dog range present and drone offset null is unresolved.
- [ ] A 4 m vertical separation labeled as a 1 m 3D proximity is rejected.
- [ ] Obstacle clearance written into range_m with association_valid false fails.
- [ ] A moving dog fails the automatic check.
- [ ] A moving beacon fails the drone check.
- [ ] Operator confirmation succeeds only when the profile allows it and both sides are confirmed.
- [ ] A stale timestamp fails even when the numbers are small.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Accept the example and observe one goal event.
- [ ] Null the drone offset and observe unresolved.
- [ ] Submit a 3D distance at 4 m height and observe rejection.
- [ ] Move the dog and observe failure.
- [ ] Use operator evidence in the enabled profile and observe success.
- [ ] Use operator evidence while the profile disables it and observe unresolved.
- [ ] Confirm no land command is proposed.
- [ ] Record thresholds actually used.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g26/; existing shared tests alone do not satisfy this assignment.
- [ ] Both fresh checks pass.
- [ ] Either side missing stays unresolved.
- [ ] 4 m geometry cannot satisfy a 1 m 3D claim.
- [ ] Clearance is not range.
- [ ] Motion on either platform blocks the goal.
- [ ] Operator mode is explicit.
- [ ] No landing side effect.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g26 -q
python -m patrol.ground.sim --task 26 --case all --seed 0 --report artifacts/task-26/simulation.json
python -m patrol.ground.quality --task 26
git diff --check
```

### Completion and handoff

- [ ] Only G26-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g26.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 27: Separate demo-goal completion from landing recovery

**Local task key:** GROUND-27. **Nature:** Recovery feature for the aircraft after the goal.
**Outcome:** A reached goal and a verified landing are two records. Unknown landing remains a fault even after the goal.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_recovery`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-27'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-27 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-27 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g27.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md final landing step.
- [ ] contracts/events-and-logs.md on goal versus landing.
- [ ] contracts/examples/event-demo_goal_reached.json, ground-to-drone-land.json, drone-landing-unknown.json, and event-landing_unverified.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g27/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g27/**`, `fixtures/ground/g27/**`, and `handoff/ground/g27.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] Optional goal-reached event fixture.
- [ ] A land command fixture and its command.ack.
- [ ] Latest drone observation.

Outputs:
- [ ] goal status and landing status as separate fields.
- [ ] recovery_required when landing is unknown, failed, or contradicted by the observation.
- [ ] No new search command.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_recovery` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/event-demo_goal_reached.json — goal log.
- [ ] contracts/examples/ground-to-drone-land.json — land request the drone teammate receives.
- [ ] contracts/examples/drone-landing-unknown.json and event-landing_unverified.json — recovery logs.

### Implementation scope

- [ ] Register feature.v2_recovery from g27 only.
- [ ] Record goal_reached from the fixture without re-checking geometry. Task 26 already did that.
- [ ] Accept a land acknowledgement only for the land command_id.
- [ ] verified completed with observed_motion grounded and flight_state grounded sets landing_verified.
- [ ] state unknown sets landing_unverified and device_recovery_required.
- [ ] A goal event cannot clear that recovery flag.
- [ ] A useful picture or a goal timestamp cannot clear it either.
- [ ] If no land command has been issued, landing status stays not_attempted rather than grounded.
- [ ] Block the next mission while recovery_required is true.
- [ ] Keep the dog in a hold/stop recommendation on the result. Do not emit a new move.
- [ ] Correlate goal event id and land command id in one recovery record.
- [ ] Leave physical retrieval of the aircraft as an operator step in the handoff, not a software success flag.

### Outside this task

- [ ] Do not call land() yourself.
- [ ] Do not erase the goal because landing failed.
- [ ] Do not resume search after an unknown landing.

### Required edge cases

- [ ] Goal true plus verified grounded yields both successes.
- [ ] Goal true plus landing unknown yields goal true and recovery required.
- [ ] Goal false plus verified landing does not invent a goal.
- [ ] Missing land command stays not_attempted.
- [ ] flight_state airborne after a completed land ack is a contradiction and a fault.
- [ ] A second recovery evaluation with the same ids is idempotent.
- [ ] Clearing recovery without a new grounded observation is rejected.
- [ ] A track-step completion is not a land ack.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Combine the goal example with a verified land ack and observe both closed.
- [ ] Combine the goal example with drone-landing-unknown.json and observe recovery_required.
- [ ] Omit the land command and observe not_attempted.
- [ ] Contradict flight_state and observe a fault.
- [ ] Replay and observe one recovery record.
- [ ] Attempt to clear recovery with no new observation and observe rejection.
- [ ] Confirm no search command appears.
- [ ] Save both statuses.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g27/; existing shared tests alone do not satisfy this assignment.
- [ ] Goal and landing are independent.
- [ ] Unknown landing survives a goal.
- [ ] No land command is not success.
- [ ] Contradictory telemetry faults.
- [ ] Idempotent replay.
- [ ] Track completion is not landing.
- [ ] No new search command.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g27 -q
python -m patrol.ground.sim --task 27 --case all --seed 0 --report artifacts/task-27/simulation.json
python -m patrol.ground.quality --task 27
git diff --check
```

### Completion and handoff

- [ ] Only G27-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g27.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 28: Halt, drop the link, and expire leases without waiting for Grok

**Local task key:** GROUND-28. **Nature:** Safety feature that outranks ordinary demo steps.
**Outcome:** Halt, link loss, stale evidence, and lease expiry stop new motion immediately and do not wait on a model call.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_safety`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-28'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-28 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-28 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g28.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md authority paragraph.
- [ ] contracts/README.md receiver rules.
- [ ] contracts/examples/ground-to-dog-halt.json and ground-to-drone-hover.json.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g28/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g28/**`, `fixtures/ground/g28/**`, and `handoff/ground/g28.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] A safety stimulus: operator halt, link loss, stale frame, expired lease, obstacle block, lost track, or noisy RSSI.
- [ ] Current command fixtures for dog and drone.
- [ ] Base safety port from Tasks 01–10.

Outputs:
- [ ] A latched safety handle and the commands a device must still accept: dog halt, drone hover or land as the fixture profile says.
- [ ] Rejection of ordinary proposals while the latch is set.
- [ ] A safety event that names the stimulus. No model request.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_safety` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/ground-to-dog-halt.json — dog stop.
- [ ] contracts/examples/ground-to-drone-hover.json — aircraft hold when the profile says hover.
- [ ] contracts/examples/ground-to-drone-land.json — used only when the stimulus is an explicit land or the profile's link-loss action is land.

### Implementation scope

- [ ] Register feature.v2_safety from g28 only.
- [ ] Call the base safety request path for every stimulus. Do not wait for vision, RSSI, or an in-flight model timeout.
- [ ] Emit dog halt immediately on operator halt, link loss, lease expiry, obstacle block, and lost local navigation.
- [ ] Emit drone hover or land from the armed profile. Do not invent a new emergency motor cut.
- [ ] Mark ordinary search, track, and homing proposals refused while the latch is set.
- [ ] A stale vision result cannot clear the latch.
- [ ] Lease expiry refuses a late start and asks Task 18 or 24's query path, via data on the result, to preserve unknown execution.
- [ ] Link loss records that local device failsafes still apply and Ground delivery is not guaranteed.
- [ ] Noisy RSSI and lost track stop homing and do not count as arrival.
- [ ] Reset is refused until the fixture shows workers quiescent and an operator recovery token.
- [ ] Duplicate halt is idempotent.
- [ ] Journal the stimulus, latch time, and which ordinary command ids were superseded.

### Outside this task

- [ ] Do not require a Grok response before halting.
- [ ] Do not power off the dog or spin the drone down except through the approved land primitive.
- [ ] Do not implement the teammates' onboard controllers.

### Required edge cases

- [ ] Halt during an in-flight vision timeout still emits dog halt and drone hover.
- [ ] A late person_visible decision does not clear the latch.
- [ ] Expired lease rejects a command that has not started.
- [ ] Link loss does not claim the dog physically stopped; it records command delivery as unknown and relies on the local lease.
- [ ] Obstacle blocked true emits halt and not a detour.
- [ ] Noisy RSSI emits stop and not goal_reached.
- [ ] A second halt returns the same handle.
- [ ] Reset without the recovery token is rejected.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Halt while a vision request is outstanding and observe safety commands with no model call.
- [ ] Deliver a late decision and observe the latch still set.
- [ ] Expire a lease and observe the unstarted command refused.
- [ ] Drop the link and observe unknown delivery plus local-failsafe instruction.
- [ ] Inject obstacle block and noisy RSSI as separate cases.
- [ ] Replay halt and observe one handle.
- [ ] Reset without a token and observe rejection.
- [ ] Save the superseded command ids.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g28/; existing shared tests alone do not satisfy this assignment.
- [ ] Halt does not wait on the model.
- [ ] Late vision cannot clear a latch.
- [ ] Lease and link behavior.
- [ ] Obstacle and noisy RSSI do not arrive.
- [ ] Idempotent halt.
- [ ] Reset requires the token.
- [ ] No motor-cut command is invented.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g28 -q
python -m patrol.ground.sim --task 28 --case all --seed 0 --report artifacts/task-28/simulation.json
python -m patrol.ground.quality --task 28
git diff --check
```

### Completion and handoff

- [ ] Only G28-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g28.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 29: Journal v2 messages and keep the proposed team log schema

**Local task key:** GROUND-29. **Nature:** Logging feature for the drone-first contract.
**Outcome:** Every accepted message becomes a correlated journal record, and the proposed log list stays open for the team's later requirements.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_logs`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-29'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-29 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-29 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g29.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] contracts/events-and-logs.md.
- [ ] contracts/examples-index.json.
- [ ] demo-v2.md note that the team's final log list has not arrived.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g29/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g29/**`, `fixtures/ground/g29/**`, and `handoff/ground/g29.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] One accepted envelope fixture at a time, covering each kind listed in the bridge.
- [ ] Base journal port from Task 04.
- [ ] A private denylist of secret field names supplied in the test, not hard-coded live secrets.

Outputs:
- [ ] An EventRecord with the category, correlation ids, and safe payload summary.
- [ ] A rejection when a required correlation field for that kind is missing.
- [ ] Published state only after a successful flush fixture. Enqueue alone is not durability.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_logs` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] Every file in contracts/examples-index.json is a legal input fixture for this task.
- [ ] contracts/example-events.jsonl is a catalog, not a mission replay, and this task stores each line as its own record.
- [ ] contracts/events-and-logs.md is the human description to give the team with these examples.

### Implementation scope

- [ ] Register feature.v2_logs from g29 only.
- [ ] Classify records as session, observation, vision, approval, command, acknowledgement, safety, completion, or persistence.
- [ ] Copy message_id, mission_id, epoch, source, destination, kind, and sent_at onto every record.
- [ ] Copy command_id, request_id, proposal_id, frame_id, track_id, beacon_epoch, map_epoch, and camera_epoch when present.
- [ ] Reject a command or ack record that has no command_id, and a vision record that has no request_id and frame_id.
- [ ] Store goal and landing events as different event names.
- [ ] Redact field names from the injected secret list, including any api key, token, or authorization header.
- [ ] Keep image bytes out of the journal line. Store the artifact reference and hash.
- [ ] Record writer state queued, flushed, or failed. A failed flush surfaces to the safety fixture as persistence_fault and does not claim the log was saved.
- [ ] Preserve unknown numeric measurements as null plus a reason. Do not write zero.
- [ ] Stamp a schema version so a future team field can be added by revision rather than by overloading a string.
- [ ] Document in the handoff that this list is proposed and waiting on the teammates.

### Outside this task

- [ ] Do not declare the team's final log list received.
- [ ] Do not drop core fields to make room for a new one.
- [ ] Do not log secrets or raw personal identifiers.

### Required edge cases

- [ ] Each example kind produces the expected category.
- [ ] A command without command_id is rejected.
- [ ] A vision decision without frame_id is rejected.
- [ ] demo_goal_reached and landing_unverified remain distinct.
- [ ] An api_key field is removed and the rejection of that field is recorded.
- [ ] A failed flush does not report published.
- [ ] Null RSSI median stays null.
- [ ] Replaying the same message_id does not append a second record.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Journal one example of each kind and check category and ids.
- [ ] Reject a command missing command_id.
- [ ] Store both goal and landing-unknown events.
- [ ] Inject a secret field and observe it absent from the output line.
- [ ] Fail the writer and observe persistence_fault without a published flag.
- [ ] Replay one message and observe one record.
- [ ] Confirm image bytes are absent and the hash is present.
- [ ] Write the category counts into the handoff.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g29/; existing shared tests alone do not satisfy this assignment.
- [ ] All example kinds classify.
- [ ] Required correlation fields are enforced.
- [ ] Goal and landing stay distinct.
- [ ] Secrets are redacted.
- [ ] Flush failure is honest.
- [ ] Null measurements stay null.
- [ ] Duplicate message_id is idempotent.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g29 -q
python -m patrol.ground.sim --task 29 --case all --seed 0 --report artifacts/task-29/simulation.json
python -m patrol.ground.quality --task 29
git diff --check
```

### Completion and handoff

- [ ] Only G29-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g29.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 30: Check Ethernet, Wi-Fi, and the Pi data path before arming

**Local task key:** GROUND-30. **Nature:** Readiness feature for links and the tether.
**Outcome:** A run starts only on the selected dog transport, with a separate documented path for Pi telemetry and no mid-run handover.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_links`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-30'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-30 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-30 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g30.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md network facts.
- [ ] contracts/dog-to-ai.md Pi relationship and Ethernet tether notes.
- [ ] plan.md §4.4 only as background for simultaneous links. The Pi is new relative to that section.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g30/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g30/**`, `fixtures/ground/g30/**`, and `handoff/ground/g30.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] GroundSettings dog_transport ethernet or wifi.
- [ ] An injected read-only probe fixture for dog, drone, Pi, and internet. This task does not open sockets.
- [ ] Tether acceptance fixture for Ethernet runs.

Outputs:
- [ ] ready true only when every required link in the selected profile is up and the Pi path is explicit.
- [ ] A blocked result that names the missing path.
- [ ] No route changes and no repair actions.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_links` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] contracts/examples/pi-heartbeat.json — evidence the Pi path can deliver telemetry.
- [ ] contracts/examples/dog-capabilities.json and drone-capabilities.json — peers that must be reachable at the same time.
- [ ] There is no log that says the broken router was fixed. Do not create one.

### Implementation scope

- [ ] Register feature.v2_links from g30 only.
- [ ] Require simultaneous dog, Tello, and internet probes for a real-mode profile. Simulation may mark them simulated.
- [ ] Ethernet profile requires the tether acceptance fixture and forbids a silent switch to Wi-Fi.
- [ ] Wi-Fi profile requires its own acceptance fixture and forbids a silent switch to Ethernet.
- [ ] Treat the Pi as an additional peer. A probe that only joins the Tello AP does not prove the Pi can reach the laptop.
- [ ] Require an explicit Pi path value: wired, usb, or second_radio. Missing path blocks RSSI even if the dog is connected.
- [ ] Record that the back router is a different failed device and is not part of this ready check.
- [ ] Reject any fixture action that would change routes, firewall rules, or installed services.
- [ ] A link that flaps after ready sets ready false and asks Task 28's latch through result data.
- [ ] Keep diagnostic output free of passwords and AES keys.
- [ ] Do not claim a probe is physical unless the fixture says physically demonstrated.
- [ ] Publish the selected profile name on the result.

### Outside this task

- [ ] Do not repair the router.
- [ ] Do not join or leave Wi-Fi networks.
- [ ] Do not move the dog to test the cable.

### Required edge cases

- [ ] Ethernet with tether acceptance and an explicit USB Pi path is ready in simulation.
- [ ] Ethernet without tether acceptance is blocked.
- [ ] A Tello association without a Pi path blocks RSSI and names the missing path.
- [ ] A mid-run request to switch transport is rejected.
- [ ] The router-failed flag does not by itself fail the Pi path when the Pi path is present.
- [ ] A probe result containing a route-change action is rejected.
- [ ] A dropped dog link clears ready.
- [ ] Secrets in a probe fixture are not copied to the result.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Ready the full Ethernet fixture.
- [ ] Remove tether acceptance and observe blocked.
- [ ] Remove the Pi path and observe RSSI blocked with dog and drone still identified.
- [ ] Request a transport switch and observe rejection.
- [ ] Drop the dog link and observe ready false.
- [ ] Include the router failure beside a good Pi path and observe the router named separately.
- [ ] Confirm no socket calls, only the injected probe.
- [ ] Save the profile record.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g30/; existing shared tests alone do not satisfy this assignment.
- [ ] Full profile passes.
- [ ] Missing tether or Pi path fails with a specific reason.
- [ ] Transport handover is rejected.
- [ ] Router failure is not confused with the Pi.
- [ ] Route-changing probes are rejected.
- [ ] Link drop clears ready.
- [ ] No live network calls.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g30 -q
python -m patrol.ground.sim --task 30 --case all --seed 0 --report artifacts/task-30/simulation.json
python -m patrol.ground.quality --task 30
git diff --check
```

### Completion and handoff

- [ ] Only G30-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g30.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 31: Compute demo timings and leave unknown values empty

**Local task key:** GROUND-31. **Nature:** Metrics feature over the v2 journal.
**Outcome:** The report shows each demo interval that the journal can support, and a null with a reason everywhere else.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_metrics`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-31'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-31 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-31 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g31.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] contracts/events-and-logs.md timing list.
- [ ] demo-v2.md initial budgets, as configuration to compare against, not as a pass mark.
- [ ] Task 29's record shape, copied into this task's fixtures.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g31/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g31/**`, `fixtures/ground/g31/**`, and `handoff/ground/g31.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

### Inputs and outputs

Inputs:
- [ ] An ordered list of journal fixtures for one synthetic mission.
- [ ] Mission start monotonic time and clock-quality notes.
- [ ] Optional empty or partial journals.

Outputs:
- [ ] A metrics object with the intervals below.
- [ ] Null and unavailable_reason when an endpoint event is missing.
- [ ] No rewritten success when a required event is absent.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_metrics` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] Uses copies of event-drone_target_acquired.json, event-dog_dispatched.json, event-demo_goal_reached.json, and event-landing_unverified.json.
- [ ] Vision latency comes from request and decision timestamps on the vision examples.
- [ ] RSSI quality and beacon resets come from the window and beacon fixtures.

### Implementation scope

- [ ] Register feature.v2_metrics from g31 only.
- [ ] Compute mission start to first valid drone target observation.
- [ ] Compute detection to stable beacon hold to dog activation.
- [ ] Compute dog activation to same-track dog-camera acquisition.
- [ ] Compute activation and mission start to jointly verified proximity.
- [ ] Compute goal reached to verified landing, and keep that null when landing is unverified.
- [ ] Compute vision latency, evidence age at use, and dropped stale-frame count from scheduler fixtures.
- [ ] Compute command accept, run, and complete latencies per command_id.
- [ ] Count RSSI windows by quality, beacon-epoch resets, no-progress stops, and blocked candidate events.
- [ ] Use one clock domain for durations. Do not subtract two devices' unrelated monotonic clocks.
- [ ] Leave model accuracy fields null unless a labeled-evaluation manifest is supplied. Orchestration success is not classification accuracy.
- [ ] Return denominators and the run id with every metric.

### Outside this task

- [ ] Do not call a model to fill a missing time.
- [ ] Do not mark landing latency zero when landing is unknown.
- [ ] Do not import another task's package.

### Required edge cases

- [ ] A complete scripted journal fills every interval.
- [ ] Missing landing leaves landing latency null and names landing_unverified.
- [ ] Missing dog acquisition leaves that interval null without failing the earlier detection metric.
- [ ] Dropped frames increment the drop count and do not look like fast vision.
- [ ] Two monotonic domains in one subtraction are rejected.
- [ ] An empty journal returns all nulls and a reason, not zeros.
- [ ] A beacon reset increments the reset count.
- [ ] Recomputing the same journal is deterministic.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Run the full scripted journal and compare expected durations.
- [ ] Remove the landing event and observe null landing latency.
- [ ] Remove the dog acquisition and observe only that interval null.
- [ ] Add dropped frames and observe the count.
- [ ] Feed an empty journal and observe nulls.
- [ ] Feed mismatched clocks and observe rejection.
- [ ] Recompute and observe identical output.
- [ ] Save the metric names in the handoff.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g31/; existing shared tests alone do not satisfy this assignment.
- [ ] Full journal metrics.
- [ ] Partial journals leave the right nulls.
- [ ] Unknown landing is not zero.
- [ ] Drop counts and beacon resets.
- [ ] Cross-clock subtraction fails.
- [ ] Empty input is honest.
- [ ] Deterministic recomputation.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g31 -q
python -m patrol.ground.sim --task 31 --case all --seed 0 --report artifacts/task-31/simulation.json
python -m patrol.ground.quality --task 31
git diff --check
```

### Completion and handoff

- [ ] Only G31-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g31.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.

---

## Task 32: Rehearse the drone-first demo offline and write the operator script

**Local task key:** GROUND-32. **Nature:** Independent rehearsal feature and the operator runbook.
**Outcome:** One offline command runs a seeded drone-first scenario and writes demo/script.md without the other v2 implementations.
**Dependency boundary:** Merged Tasks 01–10 ONLY; start after Gate B. No import, cherry-pick, wait, or dependency on any other Task 11–32.
**Owned contribution slot:** `feature.v2_rehearsal`; manifest schema `ground-task-v2`.

### Required repository and worktree

You must work in a NEW dedicated Git worktree for this task, in the user-connected robot Git repository; the Resume Changer reference checkout is not the implementation target.
Verify repository identity and existing branches/paths before running the command; do not overwrite another task's work.

```powershell
$BaseRef = 'refs/tags/ground-base-v1'
$TaskTree = Join-Path $WorktreeRoot 'ground-32'
git -C "$RobotRepo" rev-parse --verify "$BaseRef^{commit}"
git -C "$RobotRepo" worktree add -b codex/ground-32 "$TaskTree" "$BaseRef"
git -C "$TaskTree" status --short --branch
```

### Linear coordination

- [ ] In Cursor's Linear connector verify Hackathon → Projects → Ground Station and Integration, then match GROUND-32 and this title to the correct existing issue.
- [ ] Record that issue's actual ID, baseline SHA and branch; move it to the actual In Progress equivalent and preserve the dependency gate.
- [ ] Attach real checks/simulation evidence and PR/commit at handoff; use review status until completion criteria pass, never claim unperformed synchronization.
- [ ] If the connector is unavailable, continue from the valid code baseline and record **Linear sync pending** in handoff/ground/g32.md; do not guess IDs or create cross-project duplicates.

### Read first

- [ ] demo-v2.md full sequence.
- [ ] contracts/README.md communication graph.
- [ ] This file's Gate C order in the Tasks 11–32 introduction.

### Exclusive files and boundaries

- [ ] Implement only `patrol/ground/extensions/g32/**`, including its manifest, implementation, private helpers and scenarios.
- [ ] Own `tests/ground/g32/**`, `fixtures/ground/g32/**`, and `handoff/ground/g32.md`.
- [ ] No peer feature imports or shared-file edits. Copy any contract JSON this task needs into its own fixtures.
- [ ] Development acceptance is independent of the senior's Gate C slot registration.
- [ ] Keep actual dog/drone/Grok adapters, credentials, private photos, generated artifacts and unrelated product source out of this change.

- [ ] Additional owned output: demo/script.md; no other task edits it.

### Inputs and outputs

Inputs:
- [ ] A named scenario, seed, simulation mode, and output root.
- [ ] Task-owned JSON fixtures copied from the contract examples, not imports of g11–g31.
- [ ] Seeded base services from Tasks 01–10.

Outputs:
- [ ] A rehearsal report labeled software simulation, with the ordered assertions and artifact paths.
- [ ] demo/script.md, owned only by this task.
- [ ] A nonzero result when a required assertion fails.

### Exact integration requirement

Export `create(services: BaseServices) -> FeaturePort` and `async execute(request: FeatureRequest) -> FeatureResult`.
Use slot `feature.v2_rehearsal` and schema `ground-task-v2`. Do not edit the v1 loader or section 7's retired slot names.
Tests call this factory directly with Task 01 doubles. Feature results propose typed events; the workflow applies them through StatePort after identity and cancellation checks.
The senior admits v2 slots in one Gate C baseline update. This task does not wait for the other v2 cards.

### Contract messages

- [ ] The rehearsal consumes task-owned copies of the example messages listed in the bridge.
- [ ] It must not treat contracts/example-events.jsonl as one successful flight.
- [ ] The script tells teammates where the live logs will be written.

### Implementation scope

- [ ] Register feature.v2_rehearsal from g32 only, and own demo/script.md.
- [ ] Ship one ordered happy-path scenario: capabilities, stable hold, drone detection, one approved drone step, new beacon epoch, Pi window, one safe dog step, dog-camera handoff, proximity goal, then a separate landing result.
- [ ] Ship failure scenarios for uncontrolled drone motion, stale frame, blocked dog planner, noisy RSSI, and unknown landing after a goal.
- [ ] Force simulated=true for every rehearsal device and reject a real-mode flag.
- [ ] Use the contract JSON as fixtures and check the same correlation ids the live cards require.
- [ ] Assert forbidden calls: no raw model JSON forwarded to a device, no RSSI-to-meters field, no second takeoff after timeout.
- [ ] Keep the dog stopped in the trace while the drone step is running.
- [ ] Write demo/script.md for a two-minute operator brief: site check, 4 m profile only if the venue allows it, arm, what the drone teammate must have verified, what the dog app will receive, halt, and how goal differs from landing.
- [ ] Name the contract files the operator should send to each teammate.
- [ ] Make a failed assertion a failed command with the report still saved.
- [ ] Refuse to overwrite an existing run directory.
- [ ] State in the script that this rehearsal is not physical acceptance.

### Outside this task

- [ ] Do not import Tasks 11–31 to make the rehearsal pass.
- [ ] Do not fly, walk, or call xAI.
- [ ] Do not describe random uncontrolled flight as the success path.

### Required edge cases

- [ ] The happy path passes on seed 0.
- [ ] Unknown landing after a goal fails the landing assertion and keeps the goal assertion distinct.
- [ ] A real-mode flag is rejected before any scenario step.
- [ ] example-events.jsonl played as a mission fails the causal-order check.
- [ ] A blocked planner produces stop and no invented candidate.
- [ ] controlled_motion false selects the supervised or stopped outcome, not a random search.
- [ ] A second run into the same directory is rejected.
- [ ] An unreleased barrier fails teardown rather than passing.
- [ ] Identify additional task-relevant edge cases yourself; add regression tests and document both handling and any untested limitations.

### Automated simulation — required, not optional

Use the actual owned provider with Task 01's harness and frozen peer doubles; a printed expected sequence or live hardware run is not a substitute.
- [ ] Run the happy path and check the order from capability to separate landing.
- [ ] Run unknown landing after goal and check both statuses.
- [ ] Run blocked planner, noisy RSSI, and stale frame.
- [ ] Run uncontrolled-motion and check that random flight is not chosen.
- [ ] Reject a real adapter flag.
- [ ] Attempt to replay the catalog jsonl as one mission and observe failure.
- [ ] Run twice with different run ids and observe two directories.
- [ ] Confirm teardown closes barriers and files.

### Required test files and behavior

- [ ] Create task-specific test files under tests/ground/g32/; existing shared tests alone do not satisfy this assignment.
- [ ] Happy path order and labels.
- [ ] Goal versus landing failure case.
- [ ] Blocked, noisy, stale, and uncontrolled cases.
- [ ] Real mode and catalog-as-mission rejection.
- [ ] No overwrite of a previous run.
- [ ] Script names teammate files, halt, height profile, and simulation limits.
- [ ] Nonzero exit when an assertion is broken.
- [ ] Run the new test files after implementation, fix failures, and rerun; record actual commands, discovered test counts and results, including environment failures.

### Commands to run from your new worktree

```powershell
python -m pytest tests/ground/g32 -q
python -m patrol.ground.sim --task 32 --case all --seed 0 --report artifacts/task-32/simulation.json
python -m patrol.ground.quality --task 32
git diff --check
```

### Completion and handoff

- [ ] Only G32-owned paths and its additive manifest are changed.
- [ ] The provider passes its direct tests using merged Tasks 01–10 and task-owned fixtures, with no peer feature imports.
- [ ] The contract examples named above are accepted or deliberately rejected for a documented reason.
- [ ] Simulation evidence and handoff/ground/g32.md name the message kinds, edge cases, and anything left untested.
- [ ] Review the scoped diff; preserve other owners' source and tests. Commit/prepare a focused PR through the authorized repository workflow; do not merge directly to main.
- [ ] Record baseline SHA, branch/worktree, interfaces, exact files, tests/simulations actually run, extra edge cases found, limitations and Linear state in the owned handoff.
- [ ] Label evidence as documented, simulated or physically demonstrated; ordinary tests use no robot motion, paid model calls or live Linear writes.
