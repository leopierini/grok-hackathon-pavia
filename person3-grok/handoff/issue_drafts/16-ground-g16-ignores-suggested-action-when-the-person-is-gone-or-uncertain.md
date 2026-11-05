<!-- title: [Ground] g16 ignores suggested_action when the person is gone or uncertain -->

# [Ground] g16 ignores suggested_action when the person is gone or uncertain

## What we tried

        We sent a `dog_approach` decision with `target_state` `not_visible` and `suggested_action` `stop`, and one with `target_state` `uncertain` and `suggested_action` `review`. Both validate. `assess` was called with the matching request.

        ## Code path

        `g16/decide.py` `_assess`: if `decision.target_state != "person_visible"` it returns `_withheld` immediately. `suggested_action` is not read. `_withheld` always appends `no_proposal` and sets `motion_authorized` false.
`not_visible` uses head `hold`. `uncertain` uses head `review`.

        ## Error

        `not_visible`: status `ok`, outcome `hold`, proposal none. Trace starts `hold`, `not_visible`, `no_proposal`.
`uncertain`: status `ok`, outcome `review`, proposal none. Trace starts `review`, `uncertain`, `no_proposal`.
The bridge's gone sequence (stop, land_on_dog, return_home) is never started by this assessment.

        ## Why this blocks the demo

        Gone is the cue to stop, land the drone, and send the dog home. g16 turns it into a hold with no proposal. Uncertain becomes a review with no proposal. The suggested action on the decision has no effect.

        ## Suggested fix owner

        Ayush.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
