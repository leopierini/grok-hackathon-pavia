<!-- title: [Ground] dog.command rejects action play_warning -->

# [Ground] dog.command rejects action play_warning

## What we tried

        We built the `dog.command` the bridge asks Ground to forward for `play_warning` (`source` `ground`, `destination` `dog`) and ran g11 `validate_message`. It was not sent to a robot.

        ## Code path

        `person3-grok/patrol/bridge/messages.py` `command_message`.
`message.schema.json` `$defs/dog.command.properties.action` enum is `stand`, `move_local`, `turn`, `halt`.

        ## Error

        Schema: `payload_shape: payload.action`.
The command payload also has no `warning_id` or `text`. Those stay on the proposal only. That drop is filed separately.

        ## Why this blocks the demo

        There is no legal dog command for the go-away warning, so Ground cannot forward it to Leo's dog.

        ## Suggested fix owner

        Ayush (dog.command enum and factory). Leo (runtime that would speak `go away`; `FakeDog.say` / `play_audio_file` exist but are not `play_warning`).

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
