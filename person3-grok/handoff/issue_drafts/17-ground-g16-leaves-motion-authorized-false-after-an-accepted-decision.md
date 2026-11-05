<!-- title: [Ground] g16 leaves motion_authorized false after an accepted decision -->

# [Ground] g16 leaves motion_authorized false after an accepted decision

## What we tried

        Every `assess` call in this run was checked for `motion_authorized`, including the `drone_track` decision that does emit a `hold` proposal.

        ## Code path

        `Assessment` is documented "motion_authorized stays false". The ok return in `_assess` passes `motion_authorized=False`. `_withheld` does the same. Trace always ends with `motion:empty`, `devices:untouched`.
The emitted hold proposal can still be approved later: g17 `armed_context` with action `hold` returned `draft_action` `hover`, primitive `verified-hold-v1`. A caller that honors `motion_authorized` will not make that call.

        ## Error

        `motion_authorized` was false on all five g16 rows in `integration_probe.md`, including `proposal` `hold`.

        ## Why this blocks the demo

        The presence loop never gets a flag that motion may proceed. Dog actions are dropped before this, and the one drone proposal that exists is marked unauthorized.

        ## Suggested fix owner

        Ayush. If a later task is supposed to authorize, the demo path needs that task to consume the hold proposal. It does not run from `assess` today.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
