<!-- title: [Ground] g17 maps proposal action stop to drone command land -->

# [Ground] g17 maps proposal action stop to drone command land

## What we tried

        We loaded g17 with `PYTHONPATH` set to `ground base` only, took `armed_context()` (capabilities, observation, allowlist, armed, beacon epoch 4), and changed the proposal action from `reposition` to `stop`. `target_component` stayed `drone`. `decide` was called.

        ## Code path

        `g17/policy.py` `_PROPOSAL_ACTIONS` contains `"stop": "land"`.
`_from_proposal` then issues that mapped action. The allowlist land row is `verified-floor-land-v1`.
Presence "stop" means stop in place and is not an operator land. The bridge aims `stop` at the dog, but `stop` is a legal proposal action and this map runs for any drone-targeted stop.

        ## Error

        `decide` returned ok `true`, status `ok`, reason `approved`, `draft_action` `land`, `primitive_id` `verified-floor-land-v1`, `beacon_epoch` 4.
Quoted in `integration_probe.md` under `g17_armed.stop`.
A drone-targeted `hold` in the same context was approved as `hover` / `verified-hold-v1`, which matches the map. `land_on_dog` in that context was `unsupported_action`.

        ## Why this blocks the demo

        A proposal whose action is the published word `stop` becomes an approved floor-land. If a drone-stage "person gone" stop is ever routed at the drone, the aircraft is told to land. That is not the presence stop, and it is not land-on-dog.

        ## Suggested fix owner

        Ayush (change the stop map; do not treat presence stop as `land`). Drone owner before any land primitive is flown from this path.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
