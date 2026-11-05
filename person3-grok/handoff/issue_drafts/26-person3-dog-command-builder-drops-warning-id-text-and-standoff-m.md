<!-- title: [Person3] dog.command builder drops warning_id, text, and standoff_m -->

# [Person3] dog.command builder drops warning_id, text, and standoff_m

## What we tried

        We compared each presence `Intent` to the command `command_message` builds. The proposal for `play_warning` carries `warning_id` and `text`. The proposal for `follow` carries `standoff_m` 2.0.

        ## Code path

        `person3-grok/patrol/bridge/messages.py` `command_message`. The dog payload keys are `command_id`, `proposal_id`, `action`, `lease_ms`, `motion`, `track_id`, `beacon_epoch`, `safety_snapshot_id`, `reason`. The extras are not copied.
The probe records `command_dropped_fields` `warning_id` and `text` for play_warning, and `standoff_m` for follow.

        ## Error

        No exception. The fields are absent. Ground would also reject them today (`additionalProperties: false` on `dog.command`), so this only shows up by reading the builder. After the schema grows the fields, this command would still omit them.

        ## Why this blocks the demo

        A forwarded play_warning command would not contain the words "go away" or the warning id. A forwarded follow command would not contain the 2.0 m standoff.

        ## Suggested fix owner

        Vik. Copy the intent fields onto the command once Ayush's schema allows them.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
