# Ground foundation checklist

Task 01 freezes the collaboration contract. It does not fly the dog or the drone, and it does not publish `refs/tags/ground-foundation-v1`. The senior publishes that tag after Gate A.

## Ownership

Task 01 owns root packaging, `patrol/contract.py`, `patrol/ground/kernel/**`, `patrol/ground/testing/**`, the simulation and quality commands, and `patrol/ground/extensions/g01/**`.

Later tasks add only:

```text
patrol/ground/extensions/gNN/manifest.json
patrol/ground/extensions/gNN/implementation.py
tests/ground/gNN/**
fixtures/ground/gNN/**
handoff/ground/gNN.md
```

They import `patrol.ground.kernel` and construct peers with `patrol.ground.testing.builders.build_test_services`. They do not edit this package to register themselves.

## Manifest

Schema `ground-task-v1`. A manifest has exactly `schema_version`, `task_id`, `slot`, `factory`, and `scenario_factory`. The factory form is `patrol.ground.extensions.gNN.implementation:create`. Shell text, `..`, and paths outside the task directory are rejected. The loader discovers manifests in task-id order.

`kernel.*` and `feature.*` factories are `create(services)`. `base.*` factories are `create(kernel, peers)`.

## Fail closed

Missing mandatory providers refuse a live command. A missing optional diagnostic does not enable hardware and is not itself a successful check. Test doubles run only when a simulation or test builds them.

Manual clocks must not create `RunContext` deadlines for real adapters. Those deadlines use `time.monotonic()`.

## Gate A before the tag

- `python -m pytest tests/ground/g01 -q`
- `python -m patrol.ground.sim --task 01 --case all --seed 0 --report artifacts/task-01/simulation.json`
- `python -m patrol.ground.quality --task 01`
- `git diff --check`
- Confirm `python -m patrol.ground --dog fake --drone fake --grok fake` exits 2 and names the missing providers.
- Confirm the simulation report says `evidence: simulated` and `live_call_count: 0`.
