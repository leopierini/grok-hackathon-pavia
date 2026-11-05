<!-- title: [Ground] g23 rejects presence proposals because candidate_id is required -->

# [Ground] g23 rejects presence proposals because candidate_id is required

## What we tried

        We parsed the same g23 fixture after clearing `candidate_id` and `beacon_epoch` to null, which is what `proposal_message` sends for play_warning, follow, stop, and return_home.

        ## Code path

        `g23/implementation.py` `_parse_step` calls `_agree_text("candidate_id", ...)` and `_agree_text` raises `_Invalid` when every value is null.
The bridge sets `candidate_id` to null because presence does not pick a planner candidate.

        ## Error

        `_merged_action` still returned `move_local`, then `_parse` raised `_Invalid: candidate_id is required`.
Same error for approach, stop, play_warning, follow, and return_home bridge-shaped copies in `integration_probe.md`.

        ## Why this blocks the demo

        The dog-command factory cannot accept the proposal the presence bridge sends. The demo stops at candidate selection even if the action enum is later extended. Filling a candidate in to get past this check currently turns the action into `move_local`.

        ## Suggested fix owner

        Ayush (allow a vision-guided dog command without a navigation candidate, or document the candidate the demo must attach). Leo supplies candidates today; presence does not have one.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
