<!-- title: [Ground] g17 rejects every dog-targeted proposal as wrong_component -->

# [Ground] g17 rejects every dog-targeted proposal as wrong_component

## What we tried

        We called `g17.policy.decide` on dog-targeted proposals: schema-shaped `play_warning` and `follow`, exact `stop` and `return_home`, and Ground's own g23 fixture proposal whose action is the legal value `approach`. We also ran `approach` through `armed_context()`.

        ## Code path

        `ground base/patrol/ground/extensions/g17/policy.py` `_from_proposal`: if `target_component == "dog"` it calls `_block("wrong_component")` before reading `action`.
`_PROPOSAL_ACTIONS` has no dog actions. The factory only drafts drone commands.

        ## Error

        Every dog-targeted call returned status `blocked`, code `rejected`, reason `wrong_component`, including the published `approach` proposal that g11 accepts.
`armed_context` with `approach` forced onto `target_component` `dog` returns the same reason (`integration_probe.md` `g17_armed.approach_on_dog`).

        ## Why this blocks the demo

        g17 cannot approve play_warning, follow, stop, return_home, or even a legal dog `approach`. Dog motion from a vision proposal has no factory here. g23 is a different factory and maps those actions to `move_local`.

        ## Suggested fix owner

        Ayush. Dog proposals need a dog policy, or g17 must stop claiming them and return them to g23 without rewriting the action.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
