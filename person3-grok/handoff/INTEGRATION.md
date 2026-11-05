# Integration note — real Grok, fake dog and drone

The run instructions Ayush uses are in `ground base/INTEGRATION.md`.

Short form, from `ground base`, with dog and drone left scripted:

```bash
export XAI_API_KEY="the key, not stored in the repo"
python -m patrol.ground --dog fake --drone fake --grok real
```

`--grok fake` still loads `contracts/examples/drone-vision-decision.json` once
and `dog-vision-decision.json` twice. `--grok real` replaces only those three
loads with `patrol.ground.signal.assess_frame`.

Issues this path closes:

- #32 — the connector reads `XAI_API_KEY` and fails closed when it is unset.
  `create_reasoner("real")` now checks the same variable and still does not
  send a request; the v1 factory is not the image call.
- #31 — `artifact://` rehearsal frames resolve to `fixtures/ground/g14/store`
  JPEGs and the SHA-256 is checked before any model call.
- #30 — the demo does not boot `create_reasoner` for vision. The v2 entry is
  `assess_frame` (`vision.request` in, `vision.decision` out).
- #29 — the Person 3 `dog.command` builder copies `warning_id`, `text`, and
  `standoff_m` from the intent. Ground's schema still rejects those extra keys.

`--dog real` and `--drone real` stay refused. Landing safety is not asked of
Grok on this path. No Tello, Go2, or Pi socket is opened.
