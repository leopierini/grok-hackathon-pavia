<!-- title: [Ground] motion.proposal rejects play_warning fields warning_id and text -->

# [Ground] motion.proposal rejects play_warning fields warning_id and text

## What we tried

        After a still-there read on `dog_approach`, the presence session emits `play_warning` (`warning_id` `go-away`, `text` `go away`). We validated that exact `motion.proposal` with g11 `validate_message` and passed it to g17 `decide`.

        ## Code path

        `person3-grok/patrol/bridge/messages.py` `proposal_message` adds `warning_id` and `text`.
`ground base/contracts/message.schema.json` `$defs/motion.proposal` has `additionalProperties: false` and no those keys.
g11 `schema_check.validate_message` reports the unknown keys. g17 `policy._known_fields` uses `_PROPOSAL_FIELDS`, which is the same nine keys.

        ## Error

        Schema: `SchemaFault` code `payload_shape`, reason `text,warning_id`.
g17 `decide`: status `failed`, code `invalid_input`, reason `unknown proposal field`.
The action enum is not consulted on this message. The action failure is a separate issue, visible only after the extra keys are removed.

        ## Why this blocks the demo

        The first warning never becomes a proposal Ground will accept, so the dog never says "go away".

        ## Suggested fix owner

        Ayush (schema and g17 proposal fields). Vik owns the emitter; it is sending the fields HAC-58 names.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
