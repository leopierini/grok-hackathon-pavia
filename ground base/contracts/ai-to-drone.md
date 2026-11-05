# AI proposal → Ground approval → drone command

The AI never receives an unrestricted Tello motor-control tool. The vision teammate returns scene decisions and proposals. Ground checks capability, current frame/track/camera identity, area/profile, altitude/reference, deadlines, aircraft state and operator readiness, then creates a command for the drone teammate.

## What AI supplies

- The exact vision request/frame IDs, visible person boxes, uncertainty and a semantic direction/action.
- A direction is in the **image**, not automatically the aircraft/body/world frame.
- No invented global coordinates, range, flight height, or “move five meters” from a bounding box.
- A proposal can be rejected. It is not an execution acknowledgement.

Example file: [examples/ai-to-drone-proposal.json](examples/ai-to-drone-proposal.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-ai-to-drone-proposal",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 3,
  "sent_at": "2026-11-04T13:00:10.200Z",
  "source": "vision",
  "destination": "ground",
  "kind": "motion.proposal",
  "correlation_id": "msg-drone-vision-decision",
  "expires_at": "2026-11-04T13:00:10.700Z",
  "simulated": true,
  "payload": {
    "proposal_id": "proposal-drone-001",
    "target_component": "drone",
    "action": "reposition",
    "direction_hint": "left",
    "track_id": "target-001",
    "evidence_frame_id": "drone-downward-001",
    "candidate_id": null,
    "beacon_epoch": 3,
    "reason": "Semantic image-space proposal; requires calibrated approved primitive."
  }
}
```

## What the drone application receives

The Ground-approved command selects an allowlisted, previously tested primitive. It does not pass a model-produced raw SDK string. The drone adapter translates that primitive into its verified DJITelloPy calls and owns the bounded flight/local failsafe.

Example file: [examples/ground-to-drone-command.json](examples/ground-to-drone-command.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-ground-to-drone-command",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 5,
  "sent_at": "2026-11-04T13:00:10.210Z",
  "source": "ground",
  "destination": "drone",
  "kind": "drone.command",
  "correlation_id": "msg-ai-to-drone-proposal",
  "expires_at": "2026-11-04T13:00:10.510Z",
  "simulated": true,
  "payload": {
    "command_id": "cmd-drone-001",
    "proposal_id": "proposal-drone-001",
    "action": "track_step",
    "primitive_id": "verified-left-step-v1",
    "lease_ms": 300,
    "requested_height_m": null,
    "height_reference": "unknown",
    "evidence_frame_id": "drone-downward-001",
    "track_id": "target-001",
    "camera_id": "downward",
    "beacon_epoch": 4,
    "reason": "Synthetic approved primitive; invalidates epoch-3 RSSI comparisons."
  }
}
```

`primitive_id` must exist locally and be compatible with the actual control mode/camera. A reposition moves the beacon epoch forward; Ground halts the dog and collects new hold/RSSI evidence before resuming homing. A missing calibration or unverified primitive blocks autonomous repositioning.

Ordinary command expiry limits when a command may **start**. For continuous control it also bounds the local motion lease. A discrete takeoff/landing has its own bounded local operation deadline; do not cut motors after a 500 ms envelope lease. On lost Ground control, use the drone owner's tested hover/landing procedure independently of vision.

## ACK and final result

Example file: [examples/drone-ack-accepted.json](examples/drone-ack-accepted.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-drone-ack-accepted",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 3,
  "sent_at": "2026-11-04T13:00:10.220Z",
  "source": "drone",
  "destination": "ground",
  "kind": "command.ack",
  "correlation_id": "msg-ground-to-drone-command",
  "expires_at": null,
  "simulated": true,
  "payload": {
    "command_id": "cmd-drone-001",
    "state": "accepted",
    "reason_code": "ok",
    "observed_at": "2026-11-04T13:00:10.220Z",
    "verified": false,
    "observed_motion": "unknown",
    "detail": "Synthetic lifecycle example."
  }
}
```

Accepted means accepted, not completed. Continue with running and final ACKs for the same command. A completed tracking primitive may still leave the aircraft airborne; only a separately verified landing establishes grounded state. Unknown execution must be queried/recovered rather than retried as a fresh takeoff.

Other exact command examples: [hover](examples/ground-to-drone-hover.json), [land](examples/ground-to-drone-land.json), [unknown landing](examples/drone-landing-unknown.json). A requested 4 m height is a proposal requiring venue/clearance/profile acceptance; it is not a universally safe/default takeoff parameter.

Randomized search, if used, chooses from a bounded allowlist with a seed and search budget. Current uncontrolled drift is a capability failure; supervised/manual scouting is a distinct disclosed mode.
