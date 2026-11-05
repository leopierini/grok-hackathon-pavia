<!-- title: [Ground] motion.proposal rejects action follow -->

# [Ground] motion.proposal rejects action follow

## What we tried

        We removed `standoff_m` from the `follow` proposal and validated the copy, then called g17.

        ## Code path

        Same `motion.proposal` action enum as above. `follow` is not a member. Rejection log section "follow" / "Schema-shaped proposal".

        ## Error

        Schema: `payload_shape: payload.action`.
g17: status `blocked`, code `rejected`, reason `wrong_component` (dog target is rejected before the action is read).

        ## Why this blocks the demo

        The second still-there beat cannot propose follow. The dog stays on the warning/approach vocabulary Ground already had.

        ## Suggested fix owner

        Ayush for the enum and g17. Leo for a dog follow command that is not the RSSI follower.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
