<!-- title: [Ground] dog.command rejects action return_home -->

# [Ground] dog.command rejects action return_home

## What we tried

        We built the `dog.command` for `return_home` and validated it. No socket was opened.

        ## Code path

        `command_message` with `action` `return_home`, `kind` `dog.command`.
Dog command enum: `stand`, `move_local`, `turn`, `halt`.

        ## Error

        Schema: `payload_shape: payload.action`.

        ## Why this blocks the demo

        The dog cannot be commanded home after the person is gone. g23 will also rewrite a dog proposal whose action is not a step action into `move_local` (separate issue), which is not return-to-start.

        ## Suggested fix owner

        Ayush for the command enum. Leo if return home is `run_route` back to the start zone rather than a v2 command action.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
