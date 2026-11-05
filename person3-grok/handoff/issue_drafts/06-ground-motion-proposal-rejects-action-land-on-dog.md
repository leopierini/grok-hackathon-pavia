<!-- title: [Ground] motion.proposal rejects action land_on_dog -->

# [Ground] motion.proposal rejects action land_on_dog

## What we tried

        The gone-branch also emits `land_on_dog` with `target_component` `drone`. We validated that proposal and called g17 `decide` with only the proposal in the context.

        ## Code path

        `proposal_message` for `land_on_dog`. Action enum has `stop` and no `land_on_dog`.
g17 `_PROPOSAL_ACTIONS` is `hold→hover`, `search→search_step`, `reposition→track_step`, `stop→land`.

        ## Error

        Schema: `payload_shape: payload.action`.
g17: status `blocked`, code `rejected`, reason `unsupported_action`.
The same `unsupported_action` is returned when the action is swapped onto Ground's armed drone context (`integration_probe.md` `g17_armed.land_on_dog`).

        ## Why this blocks the demo

        The drone never receives a proposal it can approve for landing on the dog. `stop` is the only proposal that becomes a land, and that is a different bug.

        ## Suggested fix owner

        Ayush for the proposal enum and g17 map. Drone owner for the `land_on_dog` primitive (`land-on-dog-v1` is not in `fixtures/ground/g17/allowlist.json`; the land row is `verified-floor-land-v1`).

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
