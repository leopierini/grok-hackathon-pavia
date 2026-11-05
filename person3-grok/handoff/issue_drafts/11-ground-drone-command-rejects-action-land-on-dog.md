<!-- title: [Ground] drone.command rejects action land_on_dog -->

# [Ground] drone.command rejects action land_on_dog

## What we tried

        We built the `drone.command` for `land_on_dog` (`primitive_id` `land-on-dog-v1`, `beacon_epoch` null, `camera_id` `downward`) and validated it with g11.

        ## Code path

        `command_message` drone branch.
`message.schema.json` `$defs/drone.command.properties.action` enum is `takeoff`, `search_step`, `track_step`, `hover`, `land`.

        ## Error

        Schema: `payload_shape: payload.action`.
`beacon_epoch: null` is a second fault on this payload. It is hidden until the action is a published value. That fault is filed separately.

        ## Why this blocks the demo

        The drone cannot be commanded to land on the dog. The published `land` action is a floor land (`verified-floor-land-v1`), not `land-on-dog-v1`.

        ## Suggested fix owner

        Ayush for the drone.command enum. Drone owner for the land-on-dog primitive and runtime.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
