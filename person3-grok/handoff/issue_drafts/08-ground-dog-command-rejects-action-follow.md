<!-- title: [Ground] dog.command rejects action follow -->

# [Ground] dog.command rejects action follow

## What we tried

        We built the `dog.command` for `follow` (standoff was not copied onto the command) and validated it with g11.

        ## Code path

        `command_message` sets `kind` `dog.command` and `action` `follow`.
Published dog actions are only `stand`, `move_local`, `turn`, `halt`.

        ## Error

        Schema: `payload_shape: payload.action`.

        ## Why this blocks the demo

        Ground cannot hand the dog a follow command after the second still-there read.

        ## Suggested fix owner

        Ayush for the command schema. Leo for executing follow. The dog package's RSSI `Follower` is a different mechanism and is not this command.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
