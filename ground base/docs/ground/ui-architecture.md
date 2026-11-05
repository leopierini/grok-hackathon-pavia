# Ground Mission Control architecture

The browser is an operator console. Ground, in Python, remains the authority for
mission state, device ownership, policy, leases, halt, recovery, and evidence.

```text
Browser / Next.js UI
        |
        | same-origin /api/ground/*  (Next.js adds the local operator token)
        v
FastAPI on 127.0.0.1:8765
        |
        +-- simulation: one StepSession + patrol.ground.demo providers
        +-- live: refused, with the missing-bridge reasons, never a fake device
        +-- replay: read-only report from artifacts/operator-runs
```

## What this process owns

- One asyncio session and at most one mission worker.
- Operator actions: status, arm, start, supervised, halt, reset, quit.
- Step-controller commands already implemented in `patrol.ground.steps`:
  snapshot, set budgets, wait more, retry, and halt. Retry never repeats a
  motor command unless that controller's own rule allows it.
- SSE observation. The first event is a snapshot. A cursor gap asks the
  browser to resynchronize. Reloading the page does not repeat an action.
- JPEG evidence by allowlisted artifact id only.

## What it does not own

- A second Tello client, dog SDK, or vision client.
- Safety rules copied into React. Buttons follow `snapshot.actions`.
- Phase advances. The v2 phase changes only when the rehearsal checkpoints.
- Physical completion. Halt acceptance and device delivery are separate fields.
  `halt_delivered` stays false or null until a real transport exists.

## HTTP surface

Implemented here:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/session` | Authoritative snapshot |
| GET | `/api/v1/events` | SSE snapshot, event, resync, keepalive |
| POST | `/api/v1/actions/{status,arm,start,supervised,halt,reset,quit}` | Operator actions |
| POST | `/api/v1/steps/command` | Existing step controller |
| GET/POST | `/api/v1/config` | Validated settings, secrets rejected |
| POST | `/api/v1/mode` | `simulation` or `live` |
| POST | `/api/v1/replay/{run_id}` | Read-only replay |
| GET | `/api/v1/journal` | Filtered, paged journal |
| GET | `/api/v1/runs` and `/api/v1/runs/{id}` | History and detail |
| GET | `/api/v1/runs/{id}/export` | Summary export |
| GET | `/api/v1/evidence?artifact_id=` | Allowlisted JPEG |
| GET | `/api/v1/coverage` | Tasks 01–32 |
| GET | `/api/v1/docs/{name}` | Operator documents |

Proposed and not implemented: teammate WebSocket `/ws/robot/v2` from
`contracts/README.md`. This bridge does not pretend that socket exists.

## Fencing

Mutations other than halt, status, and quit require `session_epoch`. Halt bumps
the epoch immediately. Idempotency-Key returns the first result for that key.
Two different keys cannot start two workers.

## Clocks and missing values

Mission deadlines use the rehearsal's manual clock. The snapshot also carries
the API wall time as `updated_at`. Null measurements stay null. RSSI points
omit samples that are not numbers. They are not plotted as 0 dBm.

## Security

The API binds to loopback. Every request needs `X-Ground-Operator-Token`.
The Next.js server reads that token from the environment and does not put it
in the browser bundle. Browser calls stay on the Next origin. A foreign
`Origin` is rejected. Evidence paths cannot escape the fixture store or the
operator run root.
