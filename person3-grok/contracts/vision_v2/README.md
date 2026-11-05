# Vision v2 contract (Person 3 view)

Ayush's schema in this shared repo is the source of truth:

`ground base/contracts/message.schema.json` (`urn:robot-patrol:message:2.0-draft`)

This folder does not vendor a second copy. The bridge loads that file through Ground's
`g11` checker (`PATROL_TEAM_REPO`), so a schema edit on Ground is what the rejection log sees.

Our presence map (not a schema):

| Read | Stage | Camera | `suggested_action` |
| --- | --- | --- | --- |
| still there | `dog_approach` | `front` | `approach` |
| still there | `drone_track` | `downward` | `hold` |
| gone | either | stage camera | `stop` |
| unsure / timeout | either | stage camera | `review` (timeout sends no decision) |

Prompt version on those requests: `patrol-presence-v1`.

Decision `expires_at` is null. `correlation_id` is the request `message_id`.
Track id is copied from `active_track_id`. This package does not mint one.

The five bridge actions (`play_warning`, `follow`, `stop` as a dog command,
`return_home`, `land_on_dog`) are not in that schema. See
`handoff/grok_ground_integration.md` and `handoff/ground_rejection_log.md`.
