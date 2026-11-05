<!-- title: [Person3] XAI_API_KEY is unset and no model request was sent -->

# [Person3] XAI_API_KEY is unset and no model request was sent

## What we tried

        We checked the process environment for `XAI_API_KEY` and did not read or print any secret. `config/grok.example.json` names `grok-4.20-non-reasoning` and does not contain a key. We called `create_reasoner` in real mode and did not open a connection to api.x.ai.

        ## Code path

        `create_reasoner` raises `AdapterError` for `mode="real"` before it looks at the environment. Nothing in `person3-grok` reads `XAI_API_KEY`.
Ground's g02 notes say empty fake input does not read `XAI_API_KEY`. This run used that unset state.

        ## Error

        `XAI_API_KEY` is unset (`integration_probe.md` transport env: false).
Real reasoner: `AdapterError: unsupported: real Grok transport is unset (no host, port, or auth in this tree)`.
No HTTP status was returned because no request was sent.

        ## Why this blocks the demo

        We cannot get a live still-there / gone / unsure answer from Grok. The fake reasoner can script a state, and that state still dies in g16, but it is not a model answer.

        ## Suggested fix owner

        Vik to read `XAI_API_KEY` from the environment once real mode exists. Do not commit a key. Whoever runs the demo has to provide the variable; it is not in this checkout.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
