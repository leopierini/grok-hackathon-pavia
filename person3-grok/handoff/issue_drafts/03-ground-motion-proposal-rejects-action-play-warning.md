<!-- title: [Ground] motion.proposal rejects action play_warning -->

# [Ground] motion.proposal rejects action play_warning

## What we tried

        We sent the same `play_warning` proposal again with `warning_id` and `text` removed, so the checker could see the action. g11 `validate_message` and g17 `decide` both ran.

        ## Code path

        `ground base/contracts/message.schema.json` `$defs/motion.proposal.properties.action` enum is `hold`, `search`, `reposition`, `dispatch`, `step`, `turn`, `approach`, `stop`, `review`.
`play_warning` is not in that list. Recorded under "Schema-shaped proposal" in the rejection log.

        ## Error

        Schema: `payload_shape: payload.action`.
g17 on that shaped message does not report the action. It returns status `blocked`, code `rejected`, reason `wrong_component`, because `target_component` is `dog` and that check runs first (`policy.py` `_from_proposal`).

        ## Why this blocks the demo

        Even a schema-shaped warning proposal is illegal. Ground has no proposal action that means "say go away".

        ## Suggested fix owner

        Ayush (add `play_warning` to the proposal enum and to g17). Leo if the dog runtime must grow a matching command.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
