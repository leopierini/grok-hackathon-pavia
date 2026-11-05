# Grok signal connector — mixed rehearsal

Ayush runs Ground. Dog, drone, Pi, and pictures stay scripted. Only the three
vision replies come from Vik's connector.

From `ground base`:

```bash
export XAI_API_KEY="the key, not stored in the repo"
python -m patrol.ground --dog fake --drone fake --grok real
```

`--vision real` is the same flag. `--grok fake` is unchanged and does not read
the key or open a socket.

What the real flag does:

1. Ground still builds each `vision.request` (one `drone_search`, then two
   `dog_acquire` frames).
2. `patrol.ground.signal.assess_frame` resolves `artifact://…` under
   `fixtures/ground/g14/store`, checks SHA-256, and sends the JPEG to xAI.
3. The connector returns a `vision.decision`. Task 16 still validates it.
   Ground still writes any motion proposal. The model text is not a motor command.
4. Replies stay `simulated: true` because the JPEGs are rehearsal fixtures.
   `simulated: false` is refused.

Stage rules on a visible person:

- Drone search: `track_id` null (Ground binds `target-001`), `suggested_action`
  `reposition`, `image_direction` `left` (the rehearsal allowlist's track step).
- Both dog frames: `track_id` `target-001`, `suggested_action`
  `switch_to_dog_vision`.

The key is read only inside the connector, from `XAI_API_KEY`. If it is unset,
or the artifact is missing, or the hash does not match, the process exits 2
with `grok signal connector refused`. It does not fall back to the JSON files.

`--dog real`, `--drone real`, and `--pi real` still exit 2. Do not point this
path at a Tello, a Go2, or a Pi radio.

`stale_frame`, `missing_pi_path`, and `uncontrolled_motion` stop before a vision
request, so the connector is not called. `happy_path` and `unknown_landing`
call it three times. Scenarios that stop during homing or the halt latch call
it once, for the drone frame.

The call uses `grok-4.20-non-reasoning`. On `--grok real` the rehearsal request
names that model too, because Task 16 requires the decision `model_id` to
match the request. `--grok fake` still sends the placeholder
`CONFIGURE_VERIFIED_IMAGE_MODEL` and the scripted JSON reply.

Person 3's v1 `create_reasoner("real")` still does not perform this call. It
checks `XAI_API_KEY` and returns an error that names this connector. The image
call lives here so Ground and `person3-grok` do not share a `patrol` import.
