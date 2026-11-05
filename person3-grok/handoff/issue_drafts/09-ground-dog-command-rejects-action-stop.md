<!-- title: [Ground] dog.command rejects action stop -->

# [Ground] dog.command rejects action stop

## What we tried

        `stop` is a legal `motion.proposal` action, so the proposal validates. We then built the `dog.command` with `action` `stop` and validated that. We also called g17 on the proposal.

        ## Code path

        Proposal enum includes `stop`. Dog command enum does not. It has `halt`, which the bridge uses only for operator halt, not for presence stop.
`command_message` still writes `action` `stop` onto `dog.command`.

        ## Error

        Proposal schema: accepted.
g17 on the dog-targeted proposal: status `blocked`, code `rejected`, reason `wrong_component`.
Dog command schema: `payload_shape: payload.action`.
Operator `halt` on `dog.command` does validate. Presence stop is not halt.

        ## Why this blocks the demo

        When the person leaves, the dog is supposed to stop in place. The proposal looks legal and the command is rejected, so nothing tells the dog to stop. Mapping this to `halt` would latch an operator halt, which is a different behavior.

        ## Suggested fix owner

        Ayush (either a `stop` dog command that is not `halt`, or an explicit documented mapping). Leo for the posture-preserving stop.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
