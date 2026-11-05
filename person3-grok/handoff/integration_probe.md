# Integration probe — Person 3 against Ground

Ran from `person3-grok` with `PYTHONPATH=person3-grok` and `PATROL_TEAM_REPO` at the repo root.
Ground checkers were loaded by file path. Dog and drone sockets were not opened.
Environment values for host, port, auth, and `XAI_API_KEY` are recorded only as set or unset.

- Ground root: `/workspace/ground base`
- Dog root (not imported on this path): `/workspace/dog backend`
- Presence trace: `warn`, `follow-warn`, `gone`

Published action enums:

- `motion.proposal`: `hold`, `search`, `reposition`, `dispatch`, `step`, `turn`, `approach`, `stop`, `review`
- `dog.command`: `stand`, `move_local`, `turn`, `halt`
- `drone.command`: `takeoff`, `search_step`, `track_step`, `hover`, `land`


## vision.request

### dog_approach

```json
{
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null
}
```

### drone_track

```json
{
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null
}
```


## vision.decision

### decision play_warning

```json
{
  "assess_detail": "bad_suggested_action",
  "assess_error": "rejected",
  "assess_status": "failed",
  "motion_authorized": false,
  "outcome": "rejected",
  "proposal": null,
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.suggested_action",
  "trace": [
    "rejected",
    "bad_suggested_action",
    "track_unchanged:target-001",
    "devices:untouched"
  ]
}
```

### decision follow

```json
{
  "assess_detail": "bad_suggested_action",
  "assess_error": "rejected",
  "assess_status": "failed",
  "motion_authorized": false,
  "outcome": "rejected",
  "proposal": null,
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.suggested_action",
  "trace": [
    "rejected",
    "bad_suggested_action",
    "track_unchanged:target-001",
    "devices:untouched"
  ]
}
```

### decision return_home

```json
{
  "assess_detail": "bad_suggested_action",
  "assess_error": "rejected",
  "assess_status": "failed",
  "motion_authorized": false,
  "outcome": "rejected",
  "proposal": null,
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.suggested_action",
  "trace": [
    "rejected",
    "bad_suggested_action",
    "track_unchanged:target-001",
    "devices:untouched"
  ]
}
```

### decision land_on_dog

```json
{
  "assess_detail": "bad_suggested_action",
  "assess_error": "rejected",
  "assess_status": "failed",
  "motion_authorized": false,
  "outcome": "rejected",
  "proposal": null,
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.suggested_action",
  "trace": [
    "rejected",
    "bad_suggested_action",
    "track_unchanged:target-001",
    "devices:untouched"
  ]
}
```


## g16

### dog_approach person_visible suggested approach

```json
{
  "motion_authorized": false,
  "outcome": "track_updated",
  "proposal": null,
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null,
  "status": "ok",
  "trace": [
    "accepted",
    "track_updated:target-001",
    "no_proposal",
    "direction:center:image",
    "motion:empty",
    "devices:untouched"
  ]
}
```

### dog_approach person_visible suggested stop

```json
{
  "motion_authorized": false,
  "outcome": "track_updated",
  "proposal": null,
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null,
  "status": "ok",
  "trace": [
    "accepted",
    "track_updated:target-001",
    "no_proposal",
    "direction:center:image",
    "motion:empty",
    "devices:untouched"
  ]
}
```

### dog_approach not_visible suggested stop

```json
{
  "motion_authorized": false,
  "outcome": "hold",
  "proposal": null,
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null,
  "status": "ok",
  "trace": [
    "hold",
    "not_visible",
    "no_proposal",
    "track_unchanged:target-001",
    "motion:empty",
    "devices:untouched"
  ]
}
```

### dog_approach uncertain suggested review

```json
{
  "motion_authorized": false,
  "outcome": "review",
  "proposal": null,
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null,
  "status": "ok",
  "trace": [
    "review",
    "uncertain",
    "no_proposal",
    "track_unchanged:target-001",
    "motion:empty",
    "devices:untouched"
  ]
}
```

### drone_track person_visible suggested hold (proposal is emitted)

```json
{
  "motion_authorized": false,
  "outcome": "track_updated",
  "proposal": "hold",
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null,
  "status": "ok",
  "trace": [
    "accepted",
    "track_updated:target-001",
    "proposal:hold",
    "direction:center:image",
    "motion:empty",
    "devices:untouched"
  ]
}
```


## motion.proposal

### play_warning

```json
{
  "command_dropped_fields": [
    "warning_id",
    "text"
  ],
  "extras": [
    "warning_id",
    "text"
  ],
  "g17_code": "invalid_input",
  "g17_ok": false,
  "g17_reason": "unknown proposal field",
  "g17_status": "failed",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "text,warning_id"
}
```


## command

### dog.command play_warning

```json
{
  "action": "play_warning",
  "kind": "dog.command",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.action"
}
```


## motion.proposal

### follow

```json
{
  "command_dropped_fields": [
    "standoff_m"
  ],
  "extras": [
    "standoff_m"
  ],
  "g17_code": "invalid_input",
  "g17_ok": false,
  "g17_reason": "unknown proposal field",
  "g17_status": "failed",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "standoff_m"
}
```


## command

### dog.command follow

```json
{
  "action": "follow",
  "kind": "dog.command",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.action"
}
```


## motion.proposal

### stop

```json
{
  "command_dropped_fields": [],
  "extras": [],
  "g17_code": "rejected",
  "g17_ok": false,
  "g17_reason": "wrong_component",
  "g17_status": "blocked",
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null
}
```


## command

### dog.command stop

```json
{
  "action": "stop",
  "kind": "dog.command",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.action"
}
```


## motion.proposal

### return_home

```json
{
  "command_dropped_fields": [],
  "extras": [],
  "g17_code": "rejected",
  "g17_ok": false,
  "g17_reason": "wrong_component",
  "g17_status": "blocked",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.action"
}
```


## command

### dog.command return_home

```json
{
  "action": "return_home",
  "kind": "dog.command",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.action"
}
```


## motion.proposal

### land_on_dog

```json
{
  "command_dropped_fields": [],
  "extras": [],
  "g17_code": "rejected",
  "g17_ok": false,
  "g17_reason": "unsupported_action",
  "g17_status": "blocked",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.action"
}
```


## command

### drone.command land_on_dog

```json
{
  "action": "land_on_dog",
  "kind": "drone.command",
  "schema_code": "payload_shape",
  "schema_ok": false,
  "schema_reason": "payload.action"
}
```

### dog.command halt

```json
{
  "action": "halt",
  "kind": "dog.command",
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null
}
```


## motion.proposal

### published approach

```json
{
  "g17_code": "rejected",
  "g17_ok": false,
  "g17_reason": "wrong_component",
  "g17_status": "blocked",
  "schema_code": null,
  "schema_ok": true,
  "schema_reason": null
}
```


## ground-native

### g17-and-g23

```json
{
  "g08_public": {
    "error": "GroundFault: unavailable: public factory missing: patrol.dog:create_dog, patrol.drone:create_drone, patrol.grok:create_reasoner; no private fallback",
    "ok": false
  },
  "g17_armed": {
    "approach_on_dog": {
      "beacon_epoch": null,
      "code": "rejected",
      "draft_action": null,
      "ok": false,
      "primitive_id": null,
      "reason": "wrong_component",
      "status": "blocked"
    },
    "hold": {
      "beacon_epoch": 4,
      "code": "",
      "draft_action": "hover",
      "ok": true,
      "primitive_id": "verified-hold-v1",
      "reason": "approved",
      "status": "ok"
    },
    "land_on_dog": {
      "beacon_epoch": null,
      "code": "rejected",
      "draft_action": null,
      "ok": false,
      "primitive_id": null,
      "reason": "unsupported_action",
      "status": "blocked"
    },
    "play_warning_on_drone": {
      "beacon_epoch": null,
      "code": "rejected",
      "draft_action": null,
      "ok": false,
      "primitive_id": null,
      "reason": "unsupported_action",
      "status": "blocked"
    },
    "stop": {
      "beacon_epoch": 4,
      "code": "",
      "draft_action": "land",
      "ok": true,
      "primitive_id": "verified-floor-land-v1",
      "reason": "approved",
      "status": "ok"
    }
  },
  "g23": {
    "approach": {
      "merged_action": "move_local",
      "order_action": "move_local",
      "order_type": "_StepOrder"
    },
    "approach bridge-shaped": {
      "merged_action": "move_local",
      "parse_error": "_Invalid: candidate_id is required"
    },
    "follow": {
      "merged_action": "move_local",
      "order_action": "move_local",
      "order_type": "_StepOrder"
    },
    "follow bridge-shaped": {
      "merged_action": "move_local",
      "parse_error": "_Invalid: candidate_id is required"
    },
    "land_on_dog": {
      "merged_action": "move_local",
      "parse_error": "_Reject: proposal target_component is not dog"
    },
    "play_warning": {
      "merged_action": "move_local",
      "order_action": "move_local",
      "order_type": "_StepOrder"
    },
    "play_warning bridge-shaped": {
      "merged_action": "move_local",
      "parse_error": "_Invalid: candidate_id is required"
    },
    "return_home": {
      "merged_action": "move_local",
      "order_action": "move_local",
      "order_type": "_StepOrder"
    },
    "return_home bridge-shaped": {
      "merged_action": "move_local",
      "parse_error": "_Invalid: candidate_id is required"
    },
    "stop": {
      "merged_action": "move_local",
      "order_action": "move_local",
      "order_type": "_StepOrder"
    },
    "stop bridge-shaped": {
      "merged_action": "move_local",
      "parse_error": "_Invalid: candidate_id is required"
    }
  },
  "patrol.dog": {
    "error": "ModuleNotFoundError: No module named 'patrol.dog'",
    "ok": false
  },
  "patrol.drone": {
    "error": "ModuleNotFoundError: No module named 'patrol.drone'",
    "ok": false
  },
  "patrol.grok": {
    "error": "ModuleNotFoundError: No module named 'patrol.grok'",
    "ok": false
  }
}
```


## dog-native

### create_dog

```json
{
  "has_execute": false,
  "has_play_audio_file": true,
  "has_play_warning": false,
  "methods": [
    "capture_frame",
    "close",
    "connect",
    "get_status",
    "get_volume",
    "halt",
    "play_audio_file",
    "play_chime",
    "play_pcm",
    "prepare",
    "record_audio",
    "run_route",
    "say",
    "scenario",
    "set_volume",
    "spoken",
    "stop_audio",
    "trace"
  ],
  "patrol_file": null,
  "port_methods": [
    "capture_frame",
    "close",
    "connect",
    "get_status",
    "halt",
    "prepare",
    "run_route"
  ],
  "signature": "(*, mode: 'Mode', config: 'Mapping[str, Any]', output_dir: 'Path') -> 'DogPort'"
}
```


## import

### patrol package collision

```json
{
  "paths": {
    "dog_then_person3": {
      "patrol.bridge": "/workspace/person3-grok/patrol/bridge/__init__.py",
      "patrol.dog": "ModuleNotFoundError: No module named 'patrol.dog'",
      "patrol.drone": "ModuleNotFoundError: No module named 'patrol.drone'",
      "patrol.grok": "/workspace/person3-grok/patrol/grok/__init__.py",
      "patrol.ground": "ModuleNotFoundError: No module named 'patrol.ground'",
      "patrol_file": "/workspace/person3-grok/patrol/__init__.py"
    },
    "ground_then_person3": {
      "patrol.bridge": "ModuleNotFoundError: No module named 'patrol.bridge'",
      "patrol.dog": "ModuleNotFoundError: No module named 'patrol.dog'",
      "patrol.drone": "ModuleNotFoundError: No module named 'patrol.drone'",
      "patrol.grok": "ModuleNotFoundError: No module named 'patrol.grok'",
      "patrol.ground": "/workspace/ground base/patrol/ground/__init__.py",
      "patrol_file": "/workspace/ground base/patrol/__init__.py"
    },
    "person3_then_dog": {
      "patrol.bridge": "/workspace/person3-grok/patrol/bridge/__init__.py",
      "patrol.dog": "ModuleNotFoundError: No module named 'patrol.dog'",
      "patrol.drone": "ModuleNotFoundError: No module named 'patrol.drone'",
      "patrol.grok": "/workspace/person3-grok/patrol/grok/__init__.py",
      "patrol.ground": "ModuleNotFoundError: No module named 'patrol.ground'",
      "patrol_file": "/workspace/person3-grok/patrol/__init__.py"
    },
    "person3_then_ground": {
      "patrol.bridge": "/workspace/person3-grok/patrol/bridge/__init__.py",
      "patrol.dog": "ModuleNotFoundError: No module named 'patrol.dog'",
      "patrol.drone": "ModuleNotFoundError: No module named 'patrol.drone'",
      "patrol.grok": "/workspace/person3-grok/patrol/grok/__init__.py",
      "patrol.ground": "ModuleNotFoundError: No module named 'patrol.ground'",
      "patrol_file": "/workspace/person3-grok/patrol/__init__.py"
    }
  }
}
```


## reasoner

### create_reasoner real

```json
{
  "error": "AdapterError: unsupported: real Grok transport is unset (no host, port, or auth in this tree)",
  "ok": false
}
```

### create_reasoner fake keywords

```json
{
  "ok": true,
  "type": "FakeReasoner"
}
```

### signature

```json
{
  "methods": [
    "assess_ground_view",
    "assess_incident",
    "close",
    "compose_alert",
    "metadata",
    "read_presence",
    "resolve_incident"
  ],
  "signature": "(mode: 'str', config: 'Mapping[str, object]', output_dir: 'str | Path') -> 'FakeReasoner'"
}
```


## transport

### python -m patrol.vision_v2

```json
{
  "returncode": 2,
  "stderr": "patrol.vision_v2: real mode exits 2; /ws/robot/v2 host, port, and auth are unset",
  "stdout": ""
}
```

### env

```json
{
  "names": {
    "GROUND_HOST": false,
    "GROUND_PORT": false,
    "GROUND_WS_HOST": false,
    "GROUND_WS_PORT": false,
    "GROUND_WS_URL": false,
    "ROBOT_AUTH": false,
    "ROBOT_HOST": false,
    "ROBOT_PORT": false,
    "ROBOT_WS_URL": false,
    "UNITREE_ROBOT_IP": false,
    "WS_ROBOT_AUTH": false,
    "WS_ROBOT_HOST": false,
    "WS_ROBOT_PORT": false,
    "XAI_API_KEY": false
  }
}
```

### ws/robot/v2

```json
{
  "attempted": false,
  "reason": "host, port, and auth are unset; no connection was opened"
}
```

Schema rejections for the five presence proposals are also in `handoff/ground_rejection_log.md`.
