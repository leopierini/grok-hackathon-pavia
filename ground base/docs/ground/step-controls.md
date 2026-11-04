# Backend step timing and recovery

The backend can pause on a slow or failed runtime step, preserve completed work,
extend the observation wait, or manually retry that step. This is an in-process
Python API with a strict JSON command facade. There is no HTTP server in this
repository yet. A frontend server can hold the session handle and call these
functions on its asyncio loop.

Implementation assignment numbers (GROUND-11–32) identify provider groups. Runtime
steps have their own IDs, such as `g16.003`, because a demo can use the same provider
many times. A generic workflow can instead declare IDs such as `takeoff`,
`photo-50`, and `landing` using `StepSpec`.

## Functions

| Function | Purpose |
| --- | --- |
| `backend.step_catalog()` | List all 22 provider groups, default times, retry policy, and fixed safety groups. |
| `backend.start_demo(output, scenario, seed, transport, mission_limit_s, budgets)` | Validate group budgets atomically, start the offline composed demo in the current event loop, return `DemoHandle` immediately. |
| `DemoHandle.snapshot()` | Return controls, completion state, goal, landing, and outcome. |
| `await DemoHandle.command(request)` | Apply a JSON command below. |
| `await DemoHandle.close()` | Latch an unfinished session's halt and allow bounded cleanup. |
| `StepSession(specs, session_id, mission_limit_s, clock, is_halted, on_halt)` | Reusable controller for a custom workflow, including takeoff. |
| `await StepSession.run_step(step_id, operation, reconcile=None, validate_result=None)` | Run one operation and park on a recoverable failure/soft timeout. Return its accepted result. Earlier steps are not executed again. |
| `StepSession.add_step(spec)` | Trusted workflow adds an iteration when its count is unknown beforehand. |
| `StepSession.get_snapshot()` / `events()` | Inspect progress, attempts, allowed actions and an ordered audit copy. |
| `StepSession.notify_halt(reason)` / `bind_safety(is_halted, on_halt)` | Connect the existing authority and physical safety controller. |
| `await StepSession.close(grace_s=0.2)` | Bound shutdown; resistant workers remain visible as pending. |
| `StepAttempt.run_context()` | Produce the unchanged v1 `RunContext` with a fixed hard deadline and cancellation event. |

Import from `patrol.ground.backend` and `patrol.ground.steps`. Operations and status
reconcilers are trusted Python callbacks. JSON never supplies executable code,
`safe_to_retry` flags, device addresses, or raw motor commands.

## Exact default times

| Budget | Default | Meaning |
| --- | --- | --- |
| Operator wait per normal v2 provider call | 3 seconds | Soft deadline; an unfinished stage becomes `awaiting_operator`. |
| Hard observation limit per attempt | 30 seconds | Fixed when the attempt starts; clamped to mission time remaining. |
| Whole controlled demo | 180 seconds | Includes operator pauses and retries. Never extended by `wait_more`. |
| Maximum attempts per step | 3 total | First attempt plus at most two manual retries. |
| Device-status reconciliation wait | 3 seconds | A slow query stays tracked and blocks further retries. |
| Shutdown collection grace | 0.2 seconds | Remaining workers are reported pending, never declared stopped. |

Before execution, `wait_s` and `hard_limit_s` may be set to positive finite values
up to 300 seconds, with `wait_s <= hard_limit_s`. Mission time may be set up to
3600 seconds when creating the session. These are observation budgets, not motor
settings. Existing device leases (for example the dog command's 500 ms cap), frame
freshness, command expiry, venue limits, and the frozen G05 executor remain
independent. The legacy settings defaults are connect/prepare/capture 10 s,
model 20 s, route/flight 30 s, arrival 15 s, readiness 30 s, incident 180 s.

G28 safety and G29/G31/G32 cleanup/reporting are outside operator timing controls;
halt must bypass a stalled normal stage or journal. The offline demo permits
replay only for G20 read-only navigation planning and G30 link checks. Other
providers mutate ledgers or approve commands and use `retry_mode="never"`.
They still expose their times and support waiting while the original attempt
is active. A policy rejection ends the demo unresolved; adding time cannot make
an invalid frame or blocked candidate valid.

## Frontend integration

Create one handle per demonstration in a persistent server process. Use a unique,
server-owned output directory. Run these calls on the same event loop. Keep a
session registry in the future HTTP/WebSocket layer; a lost browser connection
must not create another demo automatically.

```python
from pathlib import Path
from patrol.ground.backend import start_demo, step_catalog

catalog = step_catalog()
handle = start_demo(
    Path("artifacts/operator-demo-001"),
    mission_limit_s=240,
    budgets=[{"task": 16, "wait_s": 5, "hard_limit_s": 20}],
)
snapshot = handle.snapshot()
# Do not await handle.task inside the request that starts the demo.
# Poll snapshot() or publish snapshots to your frontend while it runs.
```

The `controls` object contains `session_id`, monotonic `revision`, `active_step_id`,
`mission_remaining_s`, `completed_steps`, `halted`, `closed`, and `steps`. Each row
has configured times, status/reason, attempt history and `allowed_actions`.
Attempt rows contain `attempt_id`, `command_id`, elapsed and remaining seconds,
`max_extension_s`, pending/error and hard-expiry state. Render buttons from
`allowed_actions`; do not infer success from a timer or an HTTP response.

For a mutation, use the latest `revision` and current `attempt_id`. Generate one
unique `request_id` per user action. Resending exactly the same successful request
returns its original response with `replayed: true`; fetch a new snapshot afterward.
A reused ID with different content is rejected. A stale revision or attempt is
rejected with a current snapshot. Concurrent status queries cannot issue two moves.

Commands passed to `await handle.command(...)`:

```json
{"action":"snapshot"}
```

```json
{"action":"wait_more","request_id":"ui-wait-001","expected_revision":42,
 "step_id":"g16.003","attempt_id":"COPY_CURRENT_ATTEMPT_ID","seconds":5}
```

`wait_more` extends from the later of now or the existing soft deadline. It keeps
the original worker, command ID and hard deadline. Requests beyond
`max_extension_s` fail with `hard_limit`. A timely hard-deadline result that arrived
after the soft deadline waits for explicit acceptance. A hard-expired result is
discarded. A result validator runs again on acceptance where installed.

```json
{"action":"retry","request_id":"ui-retry-001","expected_revision":42,
 "step_id":"g20.001","attempt_id":"COPY_CURRENT_ATTEMPT_ID"}
```

Retry is manual, requires the previous worker to have stopped, and allocates a new
attempt/command ID. The runner resumes from this step's checkpoint. It never
replays earlier stages. No retry occurs while the original call is pending.

```json
{"action":"set_budgets","request_id":"ui-budget-001","expected_revision":7,
 "budgets":[{"step_id":"photo-50","wait_s":10,"hard_limit_s":30}]}
```

This atomically changes declared, unstarted steps in a generic `StepSession`.
Running attempts use `wait_more`; their hard deadlines stay fixed. For the composed
demo's future dynamic iterations, pass group budgets to `start_demo` as above.

```json
{"action":"halt","request_id":"ui-halt-001","expected_revision":42,
 "reason":"Operator stopped the demonstration"}
```

Halt accepts a stale integer revision to remain immediately available. It cancels
ordinary work, invokes the bound safety callback, and cannot be undone by wait or
retry. Reset/rearm after a physical fault remains the separate existing recovery
procedure. Process restart does not resume checkpoints or replay commands.

Responses are `{"ok":true,"snapshot":...}` or
`{"ok":false,"error":{"code":"...","detail":"..."},"snapshot":...}`.
Common codes: `stale_revision`, `stale_attempt`, `request_conflict`, `request_pending`,
`hard_limit`, `wait_unavailable`, `retry_unavailable`, `effect_unknown`,
`reconciliation_pending`, `reconciliation_failed`, `session_stopped`, `budget_locked`,
and `invalid_input`. Unknown/missing JSON fields are rejected.

## Takeoff and other physical effects

A missing takeoff reply does not establish that takeoff failed. For a custom
physical step, use `retry_mode="reconcile"` and a backend reconciler that queries
the **original command ID** and validates current device evidence:

```python
from patrol.ground.steps import StepSession, StepSpec, Reconciliation

session = StepSession([
    StepSpec("takeoff", "Take off", 3, 30, "reconcile"),
    StepSpec("photo-1", "First photograph", 5, 10, "idempotent"),
], is_halted=lambda: authority.cancelled, on_halt=physical_safety_request)

async def check_original(attempt):
    proof = await bridge.query_command(attempt.command_id)
    # Backend validates mission/epoch, freshness, command identity, flight state,
    # quiescence and safety before choosing one of these outcomes.
    if proof.verified_complete:
        return Reconciliation("completed", proof.result)
    if proof.verified_not_executed_and_safe:
        return Reconciliation("not_executed")
    return Reconciliation("unknown")

result = await session.run_step(
    "takeoff", send_takeoff_once, reconcile=check_original,
    validate_result=validate_current_flight_evidence,
)
```

`completed` uses the verified original result without another takeoff.
`not_executed` permits a fresh attempt; the operation must rerun all current
authorization checks before sending. `unknown` blocks replay. A generic boolean
from a browser is never sufficient. This callback example describes the bridge
interface to implement when teammate transports arrive; no real takeoff bridge
exists in this repository. Generic motion reconciliation is verified with synthetic
callbacks. The composed demo remains explicitly all-fake.

The demo writes `step-events.json` alongside `report.json` and the existing disk
journal. Checkpoints are held in memory for this process, with an audit on cleanup;
they are not a crash-resumable flight journal. Tests cover extension, late result
acceptance, hard expiry, cancellation-resistant workers, retry after 50 completed
steps, duplicate clicks, concurrent halt/reconciliation and actual composed-demo
recovery. See `tests/ground/integration/test_step_control.py` and
`test_backend_sessions.py`.
