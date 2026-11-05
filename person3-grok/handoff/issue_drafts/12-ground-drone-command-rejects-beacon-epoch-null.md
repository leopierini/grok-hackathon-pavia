<!-- title: [Ground] drone.command rejects beacon_epoch null -->

# [Ground] drone.command rejects beacon_epoch null

## What we tried

        `land_on_dog` sets `beacon_epoch` to null. The action error hides that. We copied the drone command, set `action` to the published value `land`, and validated again. This copy is not a message the bridge sends on its own.

        ## Code path

        `command_message` sets `beacon_epoch` to `None` for every drone command.
`$defs/drone.command.properties.beacon_epoch` is `{ "type": "integer", "minimum": 0 }` with no null branch.
`dog.command` and `motion.proposal` do allow null. The drone command does not.
g17 `CommandDraft.beacon_epoch` is typed `int`, and `_beacon` reads an integer from context.

        ## Error

        Schema on the action-`land` copy: `payload_shape: payload.beacon_epoch`.
See the "Beacon check" section of the rejection log.

        ## Why this blocks the demo

        A presence land cannot name a beacon epoch because the vision path has none. Any drone command we can form fails schema even after the action is corrected to `land`.

        ## Suggested fix owner

        Ayush (null beacon on drone.command, or a documented epoch the demo must copy). Drone owner if a land-on-dog primitive must not require RSSI epoch.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
