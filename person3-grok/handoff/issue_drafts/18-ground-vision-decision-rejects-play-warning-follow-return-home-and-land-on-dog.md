<!-- title: [Ground] vision.decision rejects play_warning, follow, return_home, and land_on_dog -->

# [Ground] vision.decision rejects play_warning, follow, return_home, and land_on_dog

## What we tried

        The decisions we actually emit use `approach`, `stop`, `hold`, and `review`, which are in the enum. To see what happens if the five presence actions are put on the decision itself, we built a valid decision and replaced `suggested_action` with each of `play_warning`, `follow`, `return_home`, and `land_on_dog`, then called g11 and g16.

        ## Code path

        `$defs/vision.decision.properties.suggested_action` enum is `continue_search`, `hold`, `reposition`, `dispatch_dog`, `continue_homing`, `switch_to_dog_vision`, `approach`, `stop`, `review`.
g16 `_ACTIONS` is that same set. `_choice` fails with `bad_suggested_action` when the value is outside it.

        ## Error

        Schema for each of the four: `payload_shape: payload.suggested_action`.
g16 for each: status `failed`, error `rejected`, detail `bad_suggested_action`, proposal none, `motion_authorized` false.
Trace: `rejected`, `bad_suggested_action`, `track_unchanged:target-001`, `devices:untouched`.

        ## Why this blocks the demo

        The decision channel cannot carry the demo actions. They have to ride on a separate `motion.proposal`, and that proposal is rejected too. There is no accepted message whose action is play_warning, follow, return_home, or land_on_dog.

        ## Suggested fix owner

        Ayush for the decision enum if those actions belong there. Vik if they must stay off the decision and only appear on the proposal.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
