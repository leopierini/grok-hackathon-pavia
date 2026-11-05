# Ground Mission Control verification

Recorded from this checkout on 4 November 2026. These are simulation and
local-process results. None of them is hardware acceptance.

## Python

```text
python -m pytest -q tests/ground/operator
34 passed

python -m mypy patrol/ground/operator
Success: no issues found in 11 source files

python -m ruff check patrol/ground/operator patrol/ground/demo.py tests/ground/operator
All checks passed

python -m pytest -q tests/ground/integration/test_composed_demo.py::test_public_cli_runs_all_fake_and_keeps_real_mode_disarmed
1 passed
```

The operator suite includes the composed happy path, unknown landing, halt
during the simulated Grok wait, duplicate start, stale epoch, live-mode
refusal, and all 18 rehearsal scenarios. `live_call_count` stayed 0.
Real CLI mode still exits without starting a fake mission.

Ruff line length is ignored only under `patrol/ground/operator` and
`tests/ground/operator`. The rest of the repository keeps the 100-character
rule.

The full 60-case composed matrix and the repository-wide pytest run were not
repeated in this pass. The CLI smoke test above is the regression check for
`patrol.ground.demo` after the operator hooks were added.

## Frontend

```text
npm test
23 passed (14 files)

npm run typecheck
tsc --noEmit passed

npm run build
Next.js 15.5.29 compiled and generated 12 routes

npm run lint
next lint passed
```

## Browser

With the API on `127.0.0.1:8765` and Next.js on `127.0.0.1:3000`:

- The mission page loaded IDLE, session epoch 1, and the readiness checks.
  Directional control, venue thresholds, and the 4 m profile were shown as
  unknown or not enabled.
- Arm, then Start on `happy_path`, was accepted by the API (`202`).
  The header moved through the rehearsal and reached `DONE` with goal reached
  and landing verified as separate statements.
- The vision page loaded the downward drone JPEG (320×240) and dog-front JPEGs
  (1280×720) from allowlisted artifact ids.
- At a 768×1024 viewport the section navigation stayed on one row and Halt
  remained in the header.

## Not claimed

- No robot, Tello, Pi, or xAI call was made.
- Directional motion, downward-camera hardware, venue thresholds, and the
  proposed 4 m profile are not accepted.
- The team log list is still `proposed-1` / `proposed_pending_team`.
