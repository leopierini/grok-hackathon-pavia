<!-- title: [Ground] g16 drops every dog_approach proposal -->

# [Ground] g16 drops every dog_approach proposal

## What we tried

        We built the `vision.request` Ground would send for `dog_approach` (g11 accepted it) and the `vision.decision` for still-there (`suggested_action` `approach`) and for a visible stop (`suggested_action` `stop`). Both decisions validate. We called `g16.decide.assess` with `current_track_id` `target-001`.

        ## Code path

        `ground base/patrol/ground/extensions/g16/decide.py` `_proposal`: `if halt_latched or request.stage in _DOG_STAGES: return None`.
`_DOG_STAGES` is `dog_acquire` and `dog_approach`.
`_PROPOSAL_ACTION` does contain `approach` and `stop`, so the drop is the stage guard, not a missing label. `motion_authorized` is set false on the assessment that is returned.

        ## Error

        Both assessments: status `ok`, outcome `track_updated`, proposal none, `motion_authorized` false.
Trace includes `accepted`, `track_updated:target-001`, `no_proposal`, `motion:empty`, `devices:untouched`.
A `drone_track` + `person_visible` + `hold` decision in the same run did emit `proposal:hold`, so the checker can emit a proposal on a drone stage.

        ## Why this blocks the demo

        The post-dispatch dog camera is `dog_approach`. g16 accepts the decision and then throws away the proposal. Ground never produces approach, stop, play_warning, or follow from the dog frame.

        ## Suggested fix owner

        Ayush. Dog stages have to be allowed to emit the presence proposal, or a later stage has to consume `suggested_action` instead of dropping it.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
