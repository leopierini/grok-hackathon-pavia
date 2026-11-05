<!-- title: [Ground] motion.proposal rejects action return_home -->

# [Ground] motion.proposal rejects action return_home

## What we tried

        On `not_visible` the session emits `return_home` aimed at the dog. We validated that exact proposal (no extra keys) and called g17.

        ## Code path

        `patrol/trigger/presence.py` gone-branch returns `stop`, `land_on_dog`, `return_home`.
`proposal_message` sets `action` `return_home`. The proposal enum has `dispatch` and `approach`, not `return_home`.

        ## Error

        Schema: `payload_shape: payload.action`.
g17: status `blocked`, code `rejected`, reason `wrong_component`.

        ## Why this blocks the demo

        After the person leaves, Ground will not accept a proposal to send the dog back to the start mark.

        ## Suggested fix owner

        Ayush (schema and g17). Leo if return-to-start is a dog route rather than a new action.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
