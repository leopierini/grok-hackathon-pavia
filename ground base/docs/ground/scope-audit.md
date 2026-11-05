# Integrated Ground scope audit

The active software requirements are Tasks 11–32 in the drone-first v2 section
of [`ground task.md`](../../ground%20task.md), together with `ground.md` and
`contracts/`. The retired phone-incident slot table and the v1 four-person plan
are historical context. The Python robot ABI in `patrol/contract.py` remains
unchanged at version 1.0. The wire contract remains `2.0-draft`.

All 22 task branch tips are ancestors of the integrated branch. Their source,
fixtures, tests and original handoffs are preserved. Tasks 04 and 06 were missing
from the committed base, although their implementation was present locally;
commit `4452893` preserved them with the revised specifications before merging
the remaining branches. Merge commit `363331b` combines Tasks 11–32. Subsequent
integration commits fix cross-task behavior and add operator step controls.

The user's explicit instruction to merge and publish replaces the old task-card
instructions to stop at an isolated PR. No task worktree was deleted or reset.
Historical handoffs still say “loader pending”, “not merged”, or “no remote”;
this audit and the verification reports describe the integrated result.

## Task scope evidence

The [task-by-task table](verification/task-table.md) records each task's reviewed
behavior, discovered test count, and cases across three simulation seeds. The
[machine-readable scope report](verification/task-scope.json) adds its source
branch SHA, specification heading line, test filenames and merge ancestry check.
The [requirements index](verification/task-requirements.json) preserves every
checkbox with its section and source line so a reviewer can compare the original
card with its owned code/tests. Indexing a checkbox is not a claim of physical
acceptance or of completed external project administration.

Software scope for all 22 providers is implemented and tested against the task
cards. Each provider loads under its exact owned v2 slot and runs its own direct
tests and harness without importing peer feature policies. The separate composed
runner then exercises the actual merged policies together. This distinguishes
isolated task acceptance from integration acceptance.

## Integration defects repaired

- Gate C now admits the exact v2 slot/owner pairs. It rejects invented v2 names
  and foreign owners. G16, G30 and G32 no longer advertise retired v1 aliases.
- Pytest imports isolated task test files without duplicate-module collisions.
  Packaged extension manifests are included. Static types and formatting issues
  in the previously uncommitted base services were corrected.
- G11 no longer rejects a legitimate command's ACKs for sharing its command ID.
  Cached replay cannot bypass mission/epoch checks, publisher sequence order, or
  a concurrent duplicate barrier.
- G15 preserves submillisecond capture timestamps and adds clock uncertainty to
  frame age. G16's real stage entry validates request, frame, camera, model,
  prompt, track, expiry and authoritative cancellation before returning a result.
  Its proposal uses the required `vision -> ground` direction and non-null expiry.
- G17 checks current authorization before cached approval replay; request identity
  is scoped by mission/epoch and immutable copies protect cached command data.
  A different payload under one approval ID is rejected.
- G19/G23 obey the authoritative halt/current ticket. Dog movement also requires
  stationary, standing and avoidance readiness. G23 rejects changed motion under
  a reused selection identity. G24 blocks further selection while any command is
  accepted, active, unverified, timed out, or faulted.
- G22 and G30 expose their real decisions to composition. G26/G27 compare their
  own side effects rather than rejecting every run with earlier legitimate events.
- G29 can bind a unique real journal directory. The G04 bridge propagates write,
  flush and publish failures and records actual modes, clock and ticket metadata.
  G31 consumes the real journal shape rather than only isolated fixture records.
- The composed offline CLI, explicit `selftest --stubs --scenario drone_first`,
  negative scenarios and frontend-ready session handles now run the merged code.
  Requested live modes and unsupported custom incidents remain visibly refused.
- `.jpg` and `.jpeg` both pass the JPEG decoder and artifact pipeline, including
  uppercase extensions. Added regression tests cover both robot sources and
  renamed non-JPEG bytes. No image conversion or weakened content check is needed.

## Verification and results

Exact counts and coverage are in [summary.json](verification/summary.json).
Portable per-run results are in [simulations.json](verification/simulations.json),
[composed.json](verification/composed.json) and [quality.json](verification/quality.json).
Full raw reports, JUnit, logs and the HTML coverage report are local under
`artifacts/`; generated run artifacts are not committed as source.

The gates include the complete pytest suite, Ruff, strict mypy, all 32 task quality
commands, 96 independent task simulation runs (seeds 0, 7, 29), and 60 composed
runs (10 scenarios × Ethernet/Wi-Fi × three seeds). The task simulation gate checks
every case result, assertions, no skips, teardown and zero live calls. The composed
gate independently checks goal/landing separation, expected unresolved outcomes,
unique command IDs, no takeoff replay and actual disk journal/summary creation.

The composed cases are happy path, unknown landing after goal, blocked planner,
noisy RSSI, stale frame, uncontrolled drone motion, missing Pi path, operator halt,
link loss and lease expiry. Expected failure cases pass verification only when
they refuse progress correctly. They are not counted as successful missions.

Additional tests validate every provided contract example against the official
JSON Schema and the custom parser, remove each required envelope/payload field,
reject unknown fields, and fuzz malformed schemas. Tests inject disk failures,
stale/foreign work, wrong correlations, cache mutation, deadline races, cancelled
workers and concurrent operator actions. The new controller is tested after 50
completed stages, with lost replies and trusted motion reconciliation callbacks.

A test originally gave the retry's successful planner call only 10 milliseconds;
coverage overhead could correctly push that second attempt into operator review.
The test now uses the normal three-second wait for the retry case and bounds its
own wait. The explicit slow-call cases retain injected short waits.

[function-coverage.json](verification/function-coverage.json) inventories all
nontrivial functions and their executed statements. Coverage is measured, not
assumed to be 100%. Defensive fixture methods, malformed-contract stubs and some
rare failure helpers can remain unentered; task quality/CLI processes also run
outside the main coverage process. Tests and simulations do not prove every
possible device behavior, hardware timing or classification accuracy.

Local interpreter: CPython 3.12.10 on Windows. CI additionally runs Python 3.11 on
Linux and Python 3.12 on Windows. See GitHub Actions for the actual remote status;
local type checking targeted at 3.11 is not a substitute for executing 3.11.

## Operator recovery and frontend handoff

See [step-controls.md](step-controls.md) for every backend function, exact default
times, request/response JSON, status fields, retry policy and example wiring.
`backend.start_demo()` returns a live handle. It can wait for a particular step,
manually retry an eligible step, configure declared future step budgets, report
progress and halt. Completed checkpoints remain in memory until this process
ends. The controller never automatically repeats a physical command, extends a
device motion lease, clears a halt, or resumes a mission after process restart.

The normal controlled-demo wait is 3 seconds, hard observation limit 30 seconds,
mission limit 180 seconds and maximum attempts 3. These are separately configurable
within backend bounds before execution. Existing device leases and evidence age
rules remain independent. A custom motion step must install trusted fresh status
reconciliation and result validation before enabling manual retry.

## Remaining external acceptance

These are not completed by offline Ground task code:

- Teammate v2 dog/drone/Pi/vision factories, persistent authenticated transport,
  image transfer, clock-offset/error negotiation and device command-status queries.
  `/ws/robot/v2` is served by the local operator on 127.0.0.1:8765 with the operator token.
- Physical Go2 control/stop, Tello controlled translation and camera modes,
  Pi RSSI data path, simultaneous networking, tether reach and independent
  on-device lease/link-loss behavior. No current fixture proves those measurements.
- A verified xAI image model/configuration, venue-approved flight profile, agreed
  proximity thresholds, final team log fields and staffed landing/recovery tests.
- Live external issue synchronization. Historical handoffs record **Linear sync
  pending**; no issue IDs, API activity or external completion states are invented.
- The HTTP/WebSocket frontend adapter and UI. Backend functions are provided for
  that work. Concurrent operator/UI files from another active chat are preserved
  locally and excluded from this integration release until verified separately.

The offline run is ready for software review and frontend integration. Physical
operation stays disarmed until the missing bridges and acceptance evidence exist.
