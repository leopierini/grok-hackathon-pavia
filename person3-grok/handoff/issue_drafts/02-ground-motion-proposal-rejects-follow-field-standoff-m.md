<!-- title: [Ground] motion.proposal rejects follow field standoff_m -->

# [Ground] motion.proposal rejects follow field standoff_m

## What we tried

        The second still-there read emits `follow` with `standoff_m` 2.0. We validated that exact `motion.proposal` and called g17 `decide`.

        ## Code path

        `proposal_message` sets `standoff_m` from `STANDOFF_M`.
`motion.proposal` in `message.schema.json` does not list `standoff_m` and sets `additionalProperties: false`.
g17 `_PROPOSAL_FIELDS` also omits it, so `_known_fields` fails before the action check.

        ## Error

        Schema: `payload_shape: standoff_m`.
g17: status `failed`, code `invalid_input`, reason `unknown proposal field`.

        ## Why this blocks the demo

        Follow never reaches an action check. The dog cannot be told to keep a 2.0 m standoff.

        ## Suggested fix owner

        Ayush (allow `standoff_m` on the proposal, or define where the standoff lives). Vik if the field must move to a different message.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
