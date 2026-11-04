# Ground Station and Integration

Ground validates observations and model proposals, selects bounded commands, tracks ACKs,
and keeps target completion separate from aircraft recovery. Tasks 01–32 are integrated here.

The active demo is the drone-first v2 specification in [ground.md](ground.md),
[ground task.md](<ground task.md>), and [contracts/README.md](contracts/README.md).
The original Python robot ABI in `patrol/contract.py` remains version 1.0.

Camera evidence accepts JPEG images named `.jpg` or `.jpeg`, including uppercase
extensions. They use the same JPEG encoding and `image/jpeg` media type. Validation
checks decoded bytes, hash and provenance; renaming a PNG to `.jpg` does not pass.

## Run the offline demo

Python 3.11 or later. From this checkout:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m patrol.ground --dog fake --drone fake --grok fake
```

The command loads all 22 v2 providers and composes the actual Ground base services.
Robot, Pi, link, geometry, and model inputs are synthetic. It requires no credentials,
robot SDKs, hardware, or network calls. Reports and the real disk journal are written
under `artifacts/demo-*/`. An existing run directory is never overwritten.

```powershell
python -m patrol.ground --dog fake --drone fake --grok fake --scenario unknown_landing
python -m patrol.ground --dog fake --drone fake --grok fake --dog-transport wifi --seed 29
```

Failure scenarios return exit 1 while preserving an unresolved report. Unknown landing
preserves a reached goal and requires recovery. `--help` lists all scenarios.

Real mode returns exit 2. The teammates' v2 transports/factories, authentication,
physical acceptance, model choice, and clock negotiation have not been supplied.
The v1 `run_route`/`inspect` APIs cannot be used as v2 RSSI or scouting transports.
This repository's simulated success does not establish robot or flight readiness.

## Verify

```powershell
python -m coverage run -m pytest -q
python -m coverage html -d artifacts/coverage-html
python -m ruff check patrol tests tools
python -m mypy patrol/ground
python tools/verify_ground.py
python tools/verify_composed.py
```

The simulation gate runs all 32 task providers with seeds 0, 7, and 29 and checks
assertions, teardown, skipped cases, and zero live calls. The composed gate checks
10 scenarios × 2 transports × 3 seeds and saves each actual result.

See [the scope audit](docs/ground/scope-audit.md) for task-by-task evidence,
integration fixes, measurements, and remaining external acceptance items.
See [the operator brief](demo/script.md) for the teammate handoff files.

Development uses an editable checkout because simulation assets and specifications
are repository files. CI checks Python 3.11 on Linux and Python 3.12 on Windows.
Historical handoffs describe the isolated task branches; the scope audit records
the integrated state.

## Backend controls for the frontend

Use `patrol.ground.backend.start_demo` to obtain a running session handle, then
read `snapshot()` and call `await command(...)` for `wait_more`, `retry`,
`set_budgets`, or `halt`. Completed stages are retained within that process.
See [the complete API and JSON examples](docs/ground/step-controls.md), including
the separate soft/hard times and trusted reconciliation required for motion.
This is a Python backend API; an HTTP/WebSocket frontend adapter is still to be added.
