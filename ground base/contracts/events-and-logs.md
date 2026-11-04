# Proposed logs, command ACKs, and failure records

Status: **provisional log proposal awaiting the team's exact requirements**. Do not claim that the promised final log list was received. Preserve the stable correlation fields; add later fields through a schema revision and migration, not ad hoc incompatible payloads.

Messages are operational inputs/outputs; logs are immutable records **of** receiving, validating, deciding, approving, executing and observing those messages. An AI response is not a device ACK, and an ACK is not necessarily physical completion.

## Required record categories

| Category | Exact information to retain |
| --- | --- |
| Session/capabilities | Protocol, mission/epoch, selected device/transport identities, verified capabilities and acceptance references, configured model/prompt/profile. |
| Observation | Frame ID/camera/time, drone flight/hold/beacon epoch, dog pose/navigation/obstacle health, Pi RSSI sample/window identity and validity. |
| Vision request/decision | Request ID, exact input frame, capture/receive/inference times, model/prompt, labels/boxes/uncertainty, proposed action, failure/refusal. |
| Approval/rejection | Proposal ID, current safety snapshot, candidate/profile/calibration IDs, guard results and reason. |
| Command | Command/message IDs, target, epoch, expiry, lease, primitive or local motion, relevant evidence/track/beacon/map identity. |
| ACK/execution | Accepted/running/final state, same command ID, observed physical state, verification method, unknown/failure reason. |
| Safety | Halt, link loss, stale evidence, lease expiry, obstacle block, lost SLAM/track, noisy RSSI, unknown landing and recovery status. |
| Completion | Dog range evidence, drone horizontal offset evidence, same track, source/timestamps/thresholds, goal reached versus aircraft landed. |
| Persistence | Enqueued/flushed/published state and writer errors; do not claim durability from an enqueue. |

## Command lifecycle

Example file: [examples/dog-ack-running.json](examples/dog-ack-running.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-dog-ack-running",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 5,
  "sent_at": "2026-11-04T13:00:10.250Z",
  "source": "dog",
  "destination": "ground",
  "kind": "command.ack",
  "correlation_id": "msg-ground-to-dog-command",
  "expires_at": null,
  "simulated": true,
  "payload": {
    "command_id": "cmd-dog-001",
    "state": "running",
    "reason_code": "ok",
    "observed_at": "2026-11-04T13:00:10.250Z",
    "verified": false,
    "observed_motion": "moving",
    "detail": "Synthetic lifecycle example."
  }
}
```
Example file: [examples/dog-ack-completed.json](examples/dog-ack-completed.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-dog-ack-completed",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 6,
  "sent_at": "2026-11-04T13:00:10.450Z",
  "source": "dog",
  "destination": "ground",
  "kind": "command.ack",
  "correlation_id": "msg-ground-to-dog-command",
  "expires_at": null,
  "simulated": true,
  "payload": {
    "command_id": "cmd-dog-001",
    "state": "completed",
    "reason_code": "ok",
    "observed_at": "2026-11-04T13:00:10.450Z",
    "verified": true,
    "observed_motion": "stationary",
    "detail": "Synthetic lifecycle example."
  }
}
```
Example file: [examples/drone-landing-unknown.json](examples/drone-landing-unknown.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-drone-landing-unknown",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 6,
  "sent_at": "2026-11-04T13:00:12.000Z",
  "source": "drone",
  "destination": "ground",
  "kind": "command.ack",
  "correlation_id": "msg-ground-to-drone-land",
  "expires_at": null,
  "simulated": true,
  "payload": {
    "command_id": "cmd-drone-land-001",
    "state": "unknown",
    "reason_code": "landing_not_verified",
    "observed_at": "2026-11-04T13:00:12.000Z",
    "verified": false,
    "observed_motion": "unknown",
    "detail": "Retain recovery fault; do not infer grounded from a local flag."
  }
}
```

Receiver deduplicates command IDs; accepted is not completed. On response timeout Ground queries the command/status and preserves uncertainty, rather than silently issuing another movement or takeoff. Priority safety requests remain possible, coordinated by the device's single command owner.

## Mission event example

Example file: [examples/event-demo_goal_reached.json](examples/event-demo_goal_reached.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-event-demo_goal_reached",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 11,
  "sent_at": "2026-11-04T13:00:12.000Z",
  "source": "ground",
  "destination": "all",
  "kind": "mission.event",
  "correlation_id": null,
  "expires_at": null,
  "simulated": true,
  "payload": {
    "event": "demo_goal_reached",
    "phase": "proximity_verify",
    "outcome": "completed",
    "device_recovery_required": false,
    "reason": "Both separately defined proximity checks passed; aircraft recovery remains separate.",
    "details": {
      "logs_requirements_status": "proposed_pending_team",
      "track_id": "target-001"
    }
  }
}
```

`demo_goal_reached` and verified final landing are separate events. A successful target approach cannot erase a later aircraft recovery fault. Record both goal time and full mission/recovery outcome.

The canonical JSON examples are in [examples-index.json](examples-index.json). [example-events.jsonl](example-events.jsonl) is a catalog of independent synthetic event templates, **not** a complete causally valid mission replay. It includes mutually exclusive success and failure examples. Runtime replay tests must construct their own valid ordered scenario.

## Timing and metrics proposal

- Mission start → first valid drone target observation.
- Detection → stable beacon hold → dog activation.
- Dog activation → same-target dog-camera acquisition.
- Activation/mission start → jointly verified proximity.
- Goal reached → verified landing/recovery.
- Vision latency, evidence age on use, discarded stale frames, command accept/run/complete latency.
- RSSI quality/window age, beacon resets, no-progress stops, blocked candidates, navigation/transport failures.
- False positives/misses/reviews measured on labeled images, separately from fake orchestration success.

Use local monotonic clocks for durations and negotiated UTC/clock-error bounds for cross-device evidence. Never subtract unrelated device monotonic clocks. Unknown measurements are null with reasons. Do not log API/AES keys, account tokens, raw authentication headers or unnecessary personal identifiers; image retention follows the venue's agreed handling.
