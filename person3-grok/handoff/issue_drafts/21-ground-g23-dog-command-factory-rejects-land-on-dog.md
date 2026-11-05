<!-- title: [Ground] g23 dog-command factory rejects land_on_dog -->

# [Ground] g23 dog-command factory rejects land_on_dog

## What we tried

        We passed a proposal with `action` `land_on_dog` and `target_component` `drone` into g23 `_merged_action` and `_parse`, using the g23 fixtures for readiness and candidates.

        ## Code path

        `_check_proposal` in `g23/implementation.py` raises `_Reject` when `target_component` is not `dog`.
g23 only builds `dog.command`. There is no drone command factory call on this path. g17 is the drone factory, and it returns `unsupported_action` for `land_on_dog`.

        ## Error

        `_parse` raised `_Reject: proposal target_component is not dog`.
`_merged_action` by itself returned `move_local` for that proposal, because it does not look at the target. `_parse` rejects before it uses that value.

        ## Why this blocks the demo

        Landing on the dog is a drone action. The dog-command factory refuses the target, and the drone factory refuses the action. Nothing drafts `land_on_dog`.

        ## Suggested fix owner

        Ayush to route a drone target to g17. Drone owner for the primitive. Do not let `_merged_action` rewrite a drone action into `move_local` if the target check is ever reordered.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
