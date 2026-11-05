<!-- title: [Person3] create_reasoner is a v1 port and real mode raises unsupported -->

# [Person3] create_reasoner is a v1 port and real mode raises unsupported

## What we tried

        We called `create_reasoner(mode="fake", config={}, output_dir=...)` and `create_reasoner(mode="real", config={}, output_dir=...)` with the keywords g08 uses (`mode`, `config`, `output_dir`). We listed public methods. No xAI call was made.

        ## Code path

        `person3-grok/patrol/grok/__init__.py` `create_reasoner(mode, config, output_dir) -> FakeReasoner`.
Fake methods: `metadata`, `assess_incident`, `assess_ground_view`, `resolve_incident`, `compose_alert`, `close`, `read_presence`.
That matches Ground's v1 `ReasonerPort` and g08 `_ASYNC_METHODS["reasoner"]`. It does not match v2 vision: there is no `assess_frame` and nothing returns a `vision.decision`.
`read_presence` is not on the port g08 invokes.
`mode="real"` raises before any socket or HTTP client is built.

        ## Error

        Fake keywords: ok, type `FakeReasoner`.
Real: `AdapterError: unsupported: real Grok transport is unset (no host, port, or auth in this tree)`.
Signature: `(mode: str, config: Mapping[str, object], output_dir: str | Path) -> FakeReasoner`. Keyword calls work. The mismatch is the protocol, not the keyword form.

        ## Why this blocks the demo

        Ground's post-dispatch path asks for a `vision.decision`. Booting `create_reasoner` in fake mode answers `assess_incident` / `assess_ground_view` instead, and `read_presence` is never called by g08. Real mode refuses, so we got no model answer.

        ## Suggested fix owner

        Vik for a v2 entry that turns a `vision.request` into a `vision.decision`. Ayush if g08 should call that entry instead of the v1 methods during dog_approach.

        Evidence: [integration_probe.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/integration_probe.md) and [ground_rejection_log.md](https://github.com/leopierini/grok-hackathon-pavia/blob/cursor/ground-integration-probe-2c8b/person3-grok/handoff/ground_rejection_log.md).
