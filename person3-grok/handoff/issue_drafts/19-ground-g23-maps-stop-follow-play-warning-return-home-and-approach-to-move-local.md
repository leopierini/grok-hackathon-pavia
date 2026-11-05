<!-- title: [Ground] g23 maps stop, follow, play_warning, return_home, and approach to move_local -->

# [Ground] g23 maps stop, follow, play_warning, return_home, and approach to move_local

## What we tried

        With `PYTHONPATH` set to `ground base` only, we loaded g23 and parsed Ground's own dog proposal fixture (`fixtures/ground/g23/proposal.json`, which has a `candidate_id`) after setting the payload action to `approach`, `stop`, `play_warning`, `follow`, and `return_home`. Target stayed `dog`. We called `_merged_action` and `_parse`.

        ## Code path

        `ground base/patrol/ground/extensions/g23/implementation.py` `_merged_action`.
If the proposal action is not in `_STEP_ACTIONS` (`stand`, `move_local`, `turn`) and is not `halt`, the function returns `move_local`.
`approach` is a legal proposal action and is still rewritten. `stop` is a legal proposal action and is rewritten. The presence actions are rewritten the same way.

        ## Error

        For each of those five actions, `_parse` returned `_StepOrder` with `order_action` `move_local`. `merged_action` was `move_local`.
See `integration_probe.md` section `g23`.
A bridge-shaped copy with `candidate_id` null does not get that far: `_Invalid: candidate_id is required` (separate issue). The rewrite still happens inside `_merged_action` before that error.

        ## Why this blocks the demo

        If a presence stop or warning is handed to the dog-command factory with a navigation candidate filled in, Ground issues a local move. Stop becomes motion. Play-warning becomes motion. The dog does not stop and does not speak.

        ## Suggested fix owner

        Ayush. `_merged_action` should reject unknown semantics instead of substituting `move_local`. Leo should not treat that command as follow or stop.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
