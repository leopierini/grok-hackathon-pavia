# Grok ↔ Ground presence integration

The drone-first rehearsal (`--dog fake --drone fake --grok real`) does not use
this presence session. That path is `patrol.ground.signal.assess_frame` in
Ground. Run notes: [INTEGRATION.md](INTEGRATION.md).

After YOLO has dispatched the dog, Grok only answers still-there / gone / unsure. Ground is the only component that may move a robot. This package never opens a dog or drone socket.

Authoritative schema: `ground base/contracts/message.schema.json` (`2.0-draft`). If this note and that file disagree, the file wins.

## What Vik sends on the vision path

Only `vision.decision` (`source: vision`, `destination: ground`).

| Stage | Camera | Prompt | Still there | Gone | Unsure |
| --- | --- | --- | --- | --- | --- |
| `dog_approach` | `front` | `patrol-presence-v1` | `approach` | `stop` | `review` |
| `drone_track` | `downward` | `patrol-presence-v1` | `hold` | `stop` | `review` |

- `expires_at` on the decision is `null`.
- `correlation_id` is the request `message_id`.
- `track_id` is a copy of `active_track_id` (`target-001` after dispatch). Vik does not mint ids.
- `not_visible` has `detections: []` and `image_direction: unknown`.
- Timeout does not produce a decision and does not move anything.
- `CONFIGURE_VERIFIED_IMAGE_MODEL` is refused before a decision is built.

Ground `g16` accepts those decisions and sets `motion_authorized: false`. On `dog_approach` it drops the proposal (`no_proposal`), including when `suggested_action` is `approach` or `stop`. `not_visible` becomes outcome `hold` and `uncertain` becomes `review`; `suggested_action` is not consulted. A `drone_track` + `person_visible` + `hold` decision does produce a proposal, action `hold`, aimed at the drone. See `handoff/ground_rejection_log.md`.

## What the bridge asks Ground to authorize

The presence session emits this sequence, through Ground only:

1. First dog `person_visible`: `play_warning` (`warning_id: go-away`, `text: go away`).
2. Later dog `person_visible`: `follow` (standoff 2.0) and another `play_warning`.
3. `not_visible`: `stop`, then `land_on_dog`, then `return_home`.
4. `uncertain` or timeout: nothing.
5. Operator halt: one `dog.command` action `halt`, then nothing else. Halt is already in the published enum.

Drone `person_visible` does not emit a dog command. The drone decision is `hold`.

Each step is a `motion.proposal` (`source: vision`, `destination: ground`) plus the command shape Ground would forward (`source: ground`). The command is not transmitted to a robot by this code.

### Proposal fields beyond the nine scene labels

`play_warning` adds `warning_id` and `text`. `follow` adds `standoff_m` (`2.0`). Those keys are not in the proposal schema (`additionalProperties: false`), so Ground's checker fails them before it looks at the action. A copy with only the published keys still fails the action enum, except `stop`.

`stop` is a legal `motion.proposal` action. It is not a legal `dog.command` action (`stand`, `move_local`, `turn`, `halt` only). `g17` refuses every dog-targeted proposal as `wrong_component` before the action is considered. `g16` never emits the dog-stage proposal in the first place.

`land_on_dog` is a drone proposal and a `drone.command` with `primitive_id: land-on-dog-v1` and `beacon_epoch: null`. The proposal action is not in g17's map (`unsupported_action`). The command action is not in the drone enum (`takeoff`, `search_step`, `track_step`, `hover`, `land`). `beacon_epoch` on `drone.command` is an integer, so `null` is also rejected. The log shows that beacon failure on a copy whose action is the published value `land`, so the two errors are not hidden behind each other.

### Exact rejection record

`handoff/ground_rejection_log.md` is produced by `python -m patrol.bridge.probe`. It quotes each message, the `g11` `SchemaFault`, and the `g17` decision when a proposal is involved.

## Config

`config/grok.example.json` selects `grok-4.20-non-reasoning`, prompt `patrol-v1`, presence prompt `patrol-presence-v1`, and the 5 second request budget. The key stays in `XAI_API_KEY` outside the repo. `create_reasoner("real")` checks that variable and does not call xAI; the rehearsal image call is the Ground signal connector.
