# AI proposal → Ground approval → dog application

This file is the contract to share with the teammate implementing the dog-control app. AI/Grok produces a perception decision or proposal; the **approved command is produced by Ground**, then independently checked by the dog app.

## Proposal from vision

Example file: [examples/ai-to-dog-proposal.json](examples/ai-to-dog-proposal.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-ai-to-dog-proposal",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 4,
  "sent_at": "2026-11-04T13:00:10.200Z",
  "source": "vision",
  "destination": "ground",
  "kind": "motion.proposal",
  "correlation_id": "msg-dog-vision-decision",
  "expires_at": "2026-11-04T13:00:10.700Z",
  "simulated": true,
  "payload": {
    "proposal_id": "proposal-dog-001",
    "target_component": "dog",
    "action": "approach",
    "direction_hint": "center",
    "track_id": "target-001",
    "evidence_frame_id": "dog-front-001",
    "candidate_id": "candidate-forward-01",
    "beacon_epoch": 3,
    "reason": "Proposal only; Ground and local planner must authorize."
  }
}
```

The `candidate_id`, if supplied, must refer to a current safe candidate already exposed to Ground/vision. A semantic direction such as left must not bypass camera-to-body calibration or obstacle planning. Before dog-camera acquisition, RSSI guidance proposes a candidate through the same approval path.

## Approved dog command

Example file: [examples/ground-to-dog-command.json](examples/ground-to-dog-command.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-ground-to-dog-command",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 3,
  "sent_at": "2026-11-04T13:00:10.210Z",
  "source": "ground",
  "destination": "dog",
  "kind": "dog.command",
  "correlation_id": "msg-ai-to-dog-proposal",
  "expires_at": "2026-11-04T13:00:10.510Z",
  "simulated": true,
  "payload": {
    "command_id": "cmd-dog-001",
    "proposal_id": "proposal-dog-001",
    "action": "move_local",
    "lease_ms": 300,
    "motion": {
      "frame_id": "dog/base_link",
      "linear_x_m_s": 0.1,
      "linear_y_m_s": 0.0,
      "angular_z_rad_s": 0.0,
      "duration_ms": 300,
      "candidate_id": "candidate-forward-01",
      "snapshot_id": "nav-001",
      "map_epoch": 1
    },
    "track_id": "target-001",
    "beacon_epoch": 3,
    "safety_snapshot_id": "safety-001",
    "reason": "Synthetic approved bounded step; not a real hardware setting."
  }
}
```

Units are explicit: meters/second, radians/second, milliseconds. Frame `dog/base_link` uses +x forward, +y left, +z up and positive yaw counterclockwise; the adapter must test its conversion to the app/Unitree convention. The dog has no vertical flight command: “up/down” UI arrows mean defined ground motion, not changing altitude.

Ground checks authenticated ownership, mission/epoch, evidence age, beacon hold where applicable, track, map/candidate validity, standing/avoidance, transport/tether and the remaining lease. Your app repeats its local safety checks immediately before and during execution, enforces the deadman, and stops at lease expiry. Values shown are synthetic, not approved physical speed/duration settings.

## ACKs and halt

Example file: [examples/dog-ack-accepted.json](examples/dog-ack-accepted.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-dog-ack-accepted",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 4,
  "sent_at": "2026-11-04T13:00:10.220Z",
  "source": "dog",
  "destination": "ground",
  "kind": "command.ack",
  "correlation_id": "msg-ground-to-dog-command",
  "expires_at": null,
  "simulated": true,
  "payload": {
    "command_id": "cmd-dog-001",
    "state": "accepted",
    "reason_code": "ok",
    "observed_at": "2026-11-04T13:00:10.220Z",
    "verified": false,
    "observed_motion": "unknown",
    "detail": "Synthetic lifecycle example."
  }
}
```

Use the same command ID through accepted → running → final result. Provide [completed](examples/dog-ack-completed.json) only when its stop/completion condition is observed. [Rejected expired command](examples/dog-command-rejected.json) causes no movement. A repeated command ID cannot repeat its movement; conflicting reuse is rejected.

Example file: [examples/ground-to-dog-halt.json](examples/ground-to-dog-halt.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-ground-to-dog-halt",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 4,
  "sent_at": "2026-11-04T13:00:11.000Z",
  "source": "ground",
  "destination": "dog",
  "kind": "dog.command",
  "correlation_id": null,
  "expires_at": "2026-11-04T13:00:11.500Z",
  "simulated": true,
  "payload": {
    "command_id": "cmd-dog-halt-001",
    "proposal_id": null,
    "action": "halt",
    "lease_ms": 500,
    "motion": null,
    "track_id": "target-001",
    "beacon_epoch": 3,
    "safety_snapshot_id": "safety-stop-001",
    "reason": "Operator halt; recipient safety priority applies."
  }
}
```

Halt has local safety priority and preserves the tested stable posture; it is not motor power-off or lying down. Ground cannot guarantee delivery over a disconnected cable, so the app's local expiry/stop behavior and independent operator control remain necessary.

Proximity completion needs current target-associated range or explicit operator verification. Seeing a person or reaching a strong RSSI value alone is insufficient. Once both demo proximity conditions pass, stop the dog and retain a hold/recovery state while the drone lands.
