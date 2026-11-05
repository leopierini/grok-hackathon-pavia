<!-- title: [Drone] patrol.drone package is missing -->

# [Drone] patrol.drone package is missing

## What we tried

        We tried `import patrol.drone` with `PYTHONPATH` set to each of `ground base`, `person3-grok`, and `dog backend`, and with those trees combined. We also searched the repo for `patrol/drone`.

        ## Code path

        g08 `PUBLIC_FACTORIES` expects `patrol.drone:create_drone`.
g08 gateway `_ASYNC_METHODS["drone"]` expects `connect`, `get_status`, `inspect`, `land`, `close` on a v1 `DronePort`.
No `patrol/drone` directory exists under `ground base`, `dog backend`, or `person3-grok`. `land_on_dog` therefore has no adapter to call.

        ## Error

        `ModuleNotFoundError: No module named 'patrol.drone'` from every path combination in `integration_probe.md`.

        ## Why this blocks the demo

        There is no process that can construct a drone, so `land_on_dog` cannot be delivered even after the schema allows the action.

        ## Suggested fix owner

        Drone owner. Ayush's g08 will keep failing the public resolve until `create_drone` exists.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
