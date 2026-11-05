<!-- title: [Ground] g08 public factory resolve fails closed -->

# [Ground] g08 public factory resolve fails closed

## What we tried

        With `PYTHONPATH` set to `ground base` only, we called `patrol.ground.extensions.g08.resolve.resolve_factories({"source": "public"})`. That is the boot path `gateway.py` uses before it constructs dog, drone, and reasoner.

        ## Code path

        `g08/resolve.py` `_public` imports `patrol.dog:create_dog`, `patrol.drone:create_drone`, and `patrol.grok:create_reasoner`.
Any miss raises `fault("unavailable", MISSING_PUBLIC)` and there is no private fallback on the public source.
`ground base` has none of those three packages. `person3-grok` has `patrol.grok` only. `dog backend` has `patrol.dog` only. Nothing in the repo defines `patrol.drone`.

        ## Error

        `GroundFault: unavailable: public factory missing: patrol.dog:create_dog, patrol.drone:create_drone, patrol.grok:create_reasoner; no private fallback`.
Direct imports from that same process: `ModuleNotFoundError` for `patrol.dog`, `patrol.drone`, and `patrol.grok`.

        ## Why this blocks the demo

        Ground cannot construct the adapters that would carry a presence command or a Grok answer. The demo boot stops at factory resolution.

        ## Suggested fix owner

        Ayush for the resolver (it could load the other trees by path the way the bridge loads g11/g16/g17). Leo owns `create_dog`. Vik owns `create_reasoner`. Drone owner owns the missing `create_drone`. The missing drone package and the `patrol` name collision are filed separately.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
