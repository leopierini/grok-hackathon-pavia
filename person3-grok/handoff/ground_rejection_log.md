# Ground rejection log

Person 3 presence bridge, run against Ayush's Ground in this checkout.
No dog socket, no drone socket, and no xAI call.

- Ground root: `/workspace/ground base`
- Dog root (not imported): `/workspace/dog backend`
- Checkers: `patrol/ground/extensions/g11/schema_check.py` (`validate_message`), `g16/decide.py` (`assess`), `g17/policy.py` (`decide`).
- Presence session trace for still-there, still-there, gone: `warn`, `follow-warn`, `gone`

Published action enums loaded from Ground's schema:

- `motion.proposal`: `hold`, `search`, `reposition`, `dispatch`, `step`, `turn`, `approach`, `stop`, `review`
- `dog.command`: `stand`, `move_local`, `turn`, `halt`
- `drone.command`: `takeoff`, `search_step`, `track_step`, `hover`, `land`

Origin `hritvik-arora/robot-patrol` at `1f5b6c6` was not readable from this run (no Origin session). The messages below are the shapes this bridge sends, matching HAC-62 / HAC-58: `play_warning` (`warning_id` `go-away`, text `go away`), `follow` (standoff 2.0), `stop`, `return_home`, and `land_on_dog` (`primitive_id` `land-on-dog-v1`, `beacon_epoch` null).

## Proposals and commands

### play_warning

#### Exact proposal (extra fields: warning_id, text)

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "ground",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "motion.proposal",
  "message_id": "msg-proposal-play_warning-1",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "play_warning",
    "beacon_epoch": null,
    "candidate_id": null,
    "direction_hint": "center",
    "evidence_frame_id": "dog-front-presence-001",
    "proposal_id": "proposal-play_warning-1",
    "reason": "Say the go-away warning.",
    "target_component": "dog",
    "text": "go away",
    "track_id": "target-001",
    "warning_id": "go-away"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 1,
  "simulated": true,
  "source": "vision"
}
```

- Schema: rejected `payload_shape: text,warning_id`.
- Factory `g17.policy.decide`: rejected status `failed`, code `invalid_input`, reason `unknown proposal field`.

#### Schema-shaped proposal (extras removed so the action enum is reached)

Same action and routing as the exact proposal. Extra keys are omitted only for this check.

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "ground",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "motion.proposal",
  "message_id": "msg-proposal-play_warning-1",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "play_warning",
    "beacon_epoch": null,
    "candidate_id": null,
    "direction_hint": "center",
    "evidence_frame_id": "dog-front-presence-001",
    "proposal_id": "proposal-play_warning-1",
    "reason": "Say the go-away warning.",
    "target_component": "dog",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 1,
  "simulated": true,
  "source": "vision"
}
```

- Schema: rejected `payload_shape: payload.action`.
- Factory `g17.policy.decide`: rejected status `blocked`, code `rejected`, reason `wrong_component`.

#### Command shape asked of Ground (not sent to a robot)

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "dog",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "dog.command",
  "message_id": "msg-cmd-play_warning-1",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "play_warning",
    "beacon_epoch": null,
    "command_id": "cmd-play_warning-1",
    "lease_ms": 500,
    "motion": null,
    "proposal_id": "proposal-play_warning-1",
    "reason": "Say the go-away warning.",
    "safety_snapshot_id": "safety-presence-001",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 1,
  "simulated": true,
  "source": "ground"
}
```

- Schema: rejected `payload_shape: payload.action`.

### follow

#### Exact proposal (extra fields: standoff_m)

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "ground",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "motion.proposal",
  "message_id": "msg-proposal-follow-2",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "follow",
    "beacon_epoch": null,
    "candidate_id": null,
    "direction_hint": "center",
    "evidence_frame_id": "dog-front-presence-001",
    "proposal_id": "proposal-follow-2",
    "reason": "Follow the tracked person at the published standoff.",
    "standoff_m": 2.0,
    "target_component": "dog",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 2,
  "simulated": true,
  "source": "vision"
}
```

- Schema: rejected `payload_shape: standoff_m`.
- Factory `g17.policy.decide`: rejected status `failed`, code `invalid_input`, reason `unknown proposal field`.

#### Schema-shaped proposal (extras removed so the action enum is reached)

Same action and routing as the exact proposal. Extra keys are omitted only for this check.

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "ground",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "motion.proposal",
  "message_id": "msg-proposal-follow-2",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "follow",
    "beacon_epoch": null,
    "candidate_id": null,
    "direction_hint": "center",
    "evidence_frame_id": "dog-front-presence-001",
    "proposal_id": "proposal-follow-2",
    "reason": "Follow the tracked person at the published standoff.",
    "target_component": "dog",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 2,
  "simulated": true,
  "source": "vision"
}
```

- Schema: rejected `payload_shape: payload.action`.
- Factory `g17.policy.decide`: rejected status `blocked`, code `rejected`, reason `wrong_component`.

#### Command shape asked of Ground (not sent to a robot)

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "dog",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "dog.command",
  "message_id": "msg-cmd-follow-2",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "follow",
    "beacon_epoch": null,
    "command_id": "cmd-follow-2",
    "lease_ms": 500,
    "motion": null,
    "proposal_id": "proposal-follow-2",
    "reason": "Follow the tracked person at the published standoff.",
    "safety_snapshot_id": "safety-presence-001",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 2,
  "simulated": true,
  "source": "ground"
}
```

- Schema: rejected `payload_shape: payload.action`.

### stop

#### Exact proposal

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "ground",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "motion.proposal",
  "message_id": "msg-proposal-stop-3",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "stop",
    "beacon_epoch": null,
    "candidate_id": null,
    "direction_hint": "unknown",
    "evidence_frame_id": "dog-front-presence-001",
    "proposal_id": "proposal-stop-3",
    "reason": "Stop in place. This is not an operator halt.",
    "target_component": "dog",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 3,
  "simulated": true,
  "source": "vision"
}
```

- Schema: accepted (`validate_message` returned without error).
- Factory `g17.policy.decide`: rejected status `blocked`, code `rejected`, reason `wrong_component`.

#### Command shape asked of Ground (not sent to a robot)

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "dog",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "dog.command",
  "message_id": "msg-cmd-stop-3",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "stop",
    "beacon_epoch": null,
    "command_id": "cmd-stop-3",
    "lease_ms": 500,
    "motion": null,
    "proposal_id": "proposal-stop-3",
    "reason": "Stop in place. This is not an operator halt.",
    "safety_snapshot_id": "safety-presence-001",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 3,
  "simulated": true,
  "source": "ground"
}
```

- Schema: rejected `payload_shape: payload.action`.

### return_home

#### Exact proposal

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "ground",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "motion.proposal",
  "message_id": "msg-proposal-return_home-4",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "return_home",
    "beacon_epoch": null,
    "candidate_id": null,
    "direction_hint": "unknown",
    "evidence_frame_id": "dog-front-presence-001",
    "proposal_id": "proposal-return_home-4",
    "reason": "Return to the start mark.",
    "target_component": "dog",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 4,
  "simulated": true,
  "source": "vision"
}
```

- Schema: rejected `payload_shape: payload.action`.
- Factory `g17.policy.decide`: rejected status `blocked`, code `rejected`, reason `wrong_component`.

#### Command shape asked of Ground (not sent to a robot)

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "dog",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "dog.command",
  "message_id": "msg-cmd-return_home-4",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "return_home",
    "beacon_epoch": null,
    "command_id": "cmd-return_home-4",
    "lease_ms": 500,
    "motion": null,
    "proposal_id": "proposal-return_home-4",
    "reason": "Return to the start mark.",
    "safety_snapshot_id": "safety-presence-001",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 4,
  "simulated": true,
  "source": "ground"
}
```

- Schema: rejected `payload_shape: payload.action`.

### land_on_dog

#### Exact proposal

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "ground",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "motion.proposal",
  "message_id": "msg-proposal-land_on_dog-5",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "land_on_dog",
    "beacon_epoch": null,
    "candidate_id": null,
    "direction_hint": "unknown",
    "evidence_frame_id": "dog-front-presence-001",
    "proposal_id": "proposal-land_on_dog-5",
    "reason": "Land on the dog.",
    "target_component": "drone",
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 5,
  "simulated": true,
  "source": "vision"
}
```

- Schema: rejected `payload_shape: payload.action`.
- Factory `g17.policy.decide`: rejected status `blocked`, code `rejected`, reason `unsupported_action`.

#### Command shape asked of Ground (not sent to a robot)

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "drone",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "drone.command",
  "message_id": "msg-cmd-land_on_dog-5",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "land_on_dog",
    "beacon_epoch": null,
    "camera_id": "downward",
    "command_id": "cmd-land_on_dog-5",
    "evidence_frame_id": "dog-front-presence-001",
    "height_reference": "unknown",
    "lease_ms": 500,
    "primitive_id": "land-on-dog-v1",
    "proposal_id": "proposal-land_on_dog-5",
    "reason": "Land on the dog.",
    "requested_height_m": null,
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 5,
  "simulated": true,
  "source": "ground"
}
```

- Schema: rejected `payload_shape: payload.action`.

#### Beacon check: same drone command with action set to land

Not a message the bridge sends. Action is replaced so Ground's schema can report `beacon_epoch: null` on its own. The published drone.command beacon_epoch is an integer, not null.

Message:

```json
{
  "correlation_id": "msg-presence-decision",
  "destination": "drone",
  "epoch": 1,
  "expires_at": "2026-11-04T13:00:15.100Z",
  "kind": "drone.command",
  "message_id": "msg-cmd-land_on_dog-5",
  "mission_id": "demo-20261104-001",
  "payload": {
    "action": "land",
    "beacon_epoch": null,
    "camera_id": "downward",
    "command_id": "cmd-land_on_dog-5",
    "evidence_frame_id": "dog-front-presence-001",
    "height_reference": "unknown",
    "lease_ms": 500,
    "primitive_id": "land-on-dog-v1",
    "proposal_id": "proposal-land_on_dog-5",
    "reason": "Land on the dog.",
    "requested_height_m": null,
    "track_id": "target-001"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.400Z",
  "seq": 5,
  "simulated": true,
  "source": "ground"
}
```

- Schema: rejected `payload_shape: payload.beacon_epoch`.

## g16 vision.decision on dog_approach

g16 keeps `motion_authorized` false. Dog stages (`dog_acquire`, `dog_approach`) drop the proposal even when the decision is accepted. `not_visible` and `uncertain` never consult `suggested_action`.

### dog_approach person_visible suggested approach

Decision sent:

```json
{
  "correlation_id": "msg-req-dog-visible",
  "destination": "ground",
  "epoch": 1,
  "expires_at": null,
  "kind": "vision.decision",
  "message_id": "msg-dec-10",
  "mission_id": "demo-20261104-001",
  "payload": {
    "detections": [
      {
        "box_xyxy_norm": [
          0.3,
          0.2,
          0.55,
          0.8
        ],
        "confidence": 0.91,
        "label": "person",
        "track_id": "target-001"
      }
    ],
    "frame_captured_at": "2026-11-04T13:00:10.000Z",
    "frame_id": "dog-front-presence-001",
    "image_direction": "center",
    "model_id": "grok-4.20-non-reasoning",
    "prompt_version": "patrol-presence-v1",
    "provider": "xai",
    "reason": "Person still in frame.",
    "request_id": "vision-dog-visible",
    "suggested_action": "approach",
    "target_state": "person_visible"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.200Z",
  "seq": 11,
  "simulated": true,
  "source": "vision"
}
```

- Schema: accepted.
- g16 `assess`: status `ok`, outcome `track_updated`, error `None`, detail `None`, proposal `none`, motion_authorized `false`.
- Trace: `accepted`, `track_updated:target-001`, `no_proposal`, `direction:center:image`, `motion:empty`, `devices:untouched`

### dog_approach person_visible suggested stop

Decision sent:

```json
{
  "correlation_id": "msg-req-dog-stop",
  "destination": "ground",
  "epoch": 1,
  "expires_at": null,
  "kind": "vision.decision",
  "message_id": "msg-dec-11",
  "mission_id": "demo-20261104-001",
  "payload": {
    "detections": [
      {
        "box_xyxy_norm": [
          0.3,
          0.2,
          0.55,
          0.8
        ],
        "confidence": 0.91,
        "label": "person",
        "track_id": "target-001"
      }
    ],
    "frame_captured_at": "2026-11-04T13:00:10.000Z",
    "frame_id": "dog-front-presence-002",
    "image_direction": "center",
    "model_id": "grok-4.20-non-reasoning",
    "prompt_version": "patrol-presence-v1",
    "provider": "xai",
    "reason": "Stop in place. This is not an operator halt.",
    "request_id": "vision-dog-stop",
    "suggested_action": "stop",
    "target_state": "person_visible"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.200Z",
  "seq": 12,
  "simulated": true,
  "source": "vision"
}
```

- Schema: accepted.
- g16 `assess`: status `ok`, outcome `track_updated`, error `None`, detail `None`, proposal `none`, motion_authorized `false`.
- Trace: `accepted`, `track_updated:target-001`, `no_proposal`, `direction:center:image`, `motion:empty`, `devices:untouched`

### dog_approach not_visible suggested stop

Decision sent:

```json
{
  "correlation_id": "msg-req-dog-gone",
  "destination": "ground",
  "epoch": 1,
  "expires_at": null,
  "kind": "vision.decision",
  "message_id": "msg-dec-12",
  "mission_id": "demo-20261104-001",
  "payload": {
    "detections": [],
    "frame_captured_at": "2026-11-04T13:00:10.000Z",
    "frame_id": "dog-front-presence-003",
    "image_direction": "unknown",
    "model_id": "grok-4.20-non-reasoning",
    "prompt_version": "patrol-presence-v1",
    "provider": "xai",
    "reason": "No person in frame.",
    "request_id": "vision-dog-gone",
    "suggested_action": "stop",
    "target_state": "not_visible"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.200Z",
  "seq": 13,
  "simulated": true,
  "source": "vision"
}
```

- Schema: accepted.
- g16 `assess`: status `ok`, outcome `hold`, error `None`, detail `None`, proposal `none`, motion_authorized `false`.
- Trace: `hold`, `not_visible`, `no_proposal`, `track_unchanged:target-001`, `motion:empty`, `devices:untouched`

### dog_approach uncertain suggested review

Decision sent:

```json
{
  "correlation_id": "msg-req-dog-unsure",
  "destination": "ground",
  "epoch": 1,
  "expires_at": null,
  "kind": "vision.decision",
  "message_id": "msg-dec-13",
  "mission_id": "demo-20261104-001",
  "payload": {
    "detections": [],
    "frame_captured_at": "2026-11-04T13:00:10.000Z",
    "frame_id": "dog-front-presence-004",
    "image_direction": "unknown",
    "model_id": "grok-4.20-non-reasoning",
    "prompt_version": "patrol-presence-v1",
    "provider": "xai",
    "reason": "Presence is uncertain.",
    "request_id": "vision-dog-unsure",
    "suggested_action": "review",
    "target_state": "uncertain"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.200Z",
  "seq": 14,
  "simulated": true,
  "source": "vision"
}
```

- Schema: accepted.
- g16 `assess`: status `ok`, outcome `review`, error `None`, detail `None`, proposal `none`, motion_authorized `false`.
- Trace: `review`, `uncertain`, `no_proposal`, `track_unchanged:target-001`, `motion:empty`, `devices:untouched`

### drone_track person_visible suggested hold (proposal is emitted)

Decision sent:

```json
{
  "correlation_id": "msg-req-drone-hold",
  "destination": "ground",
  "epoch": 1,
  "expires_at": null,
  "kind": "vision.decision",
  "message_id": "msg-dec-14",
  "mission_id": "demo-20261104-001",
  "payload": {
    "detections": [
      {
        "box_xyxy_norm": [
          0.3,
          0.2,
          0.55,
          0.8
        ],
        "confidence": 0.91,
        "label": "person",
        "track_id": "target-001"
      }
    ],
    "frame_captured_at": "2026-11-04T13:00:10.000Z",
    "frame_id": "drone-down-presence-001",
    "image_direction": "center",
    "model_id": "grok-4.20-non-reasoning",
    "prompt_version": "patrol-presence-v1",
    "provider": "xai",
    "reason": "Person still in frame.",
    "request_id": "vision-drone-hold",
    "suggested_action": "hold",
    "target_state": "person_visible"
  },
  "protocol_version": "2.0-draft",
  "sent_at": "2026-11-04T13:00:10.200Z",
  "seq": 15,
  "simulated": true,
  "source": "vision"
}
```

- Schema: accepted.
- g16 `assess`: status `ok`, outcome `track_updated`, error `None`, detail `None`, proposal `hold`, motion_authorized `false`.
- Trace: `accepted`, `track_updated:target-001`, `proposal:hold`, `direction:center:image`, `motion:empty`, `devices:untouched`

A `drone_track` row is included so the log shows a stage where g16 does emit a proposal. That proposal is `hold` for the drone, not one of the five presence actions.
