# Drone teammate → Ground → xAI Grok

Read [README.md](README.md) for envelope, transport, IDs, clock rules and authority. You own DJITelloPy, its command/video workers, physical flight control and local failsafes. Ground owns when to request a permitted action. Vision owns image interpretation.

## What you must send

| Data | Required meaning |
| --- | --- |
| Capability report | Actual firmware/SDK, verified movement mode, supported camera modes, and acceptance evidence. Report unsupported features honestly. |
| Drone observation | Flight state, battery, height estimate **with reference**, known pose or null, active command, beacon hold state and current image metadata. |
| Frame | Unique ID, actual camera and camera epoch, capture UTC, resolution, artifact reference/hash, calibration identity or null, and simulation flag. |
| Beacon | Exact BSSID/SSID, beacon epoch, stable/moving/unknown hold state and validity window. Increment epoch after repositioning and invalidate old RSSI comparisons. |
| ACK/result | Accepted/running/final state for the same command ID, with observed motion/landing truth. |

Images must be captured after selecting the reported camera; flush older buffers. `downward` is not `rear`. If switching cameras changes orientation/resolution, increment camera epoch and report the correct calibration. At the proposed 4 m, recognition quality and usable field of view require testing. Never report height as floor AGL if the SDK value has only a takeoff-relative/unknown reference.

Send observations to Ground. Ground forwards a validated image request to vision; do not call xAI independently or send competing model-directed movement.

## Observation example

Example file: [examples/drone-observation.json](examples/drone-observation.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-drone-observation",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 2,
  "sent_at": "2026-11-04T13:00:10.000Z",
  "source": "drone",
  "destination": "ground",
  "kind": "drone.observation",
  "correlation_id": null,
  "expires_at": null,
  "simulated": true,
  "payload": {
    "device_id": "drone-01",
    "flight_state": "airborne",
    "battery_percent": 74,
    "pose": null,
    "height_estimate_m": 4.0,
    "height_reference": "floor_agl",
    "control_mode": "autonomous_verified",
    "beacon": {
      "beacon_id": "tello-demo-01",
      "bssid": "02:00:00:00:00:01",
      "ssid": "TELLO-DEMO",
      "beacon_epoch": 3,
      "hold_state": "stable",
      "verified_at": "2026-11-04T13:00:10.000Z",
      "hold_valid_until": "2026-11-04T13:00:12.000Z"
    },
    "frame": {
      "frame_id": "drone-downward-001",
      "image_ref": "artifact://demo-20261104-001/drone/downward-001.jpg",
      "sha256": "0f0479fff4658167e274ded2e2bdc58a9cc45ebdd667c955fb2a2f636906470f",
      "captured_at": "2026-11-04T13:00:10.000Z",
      "camera_id": "downward",
      "camera_epoch": 1,
      "width_px": 320,
      "height_px": 240,
      "camera_frame_id": "drone/camera_downward",
      "camera_to_body_calibration_id": "synthetic-calibration-v1",
      "simulated": true
    },
    "active_command_id": null
  }
}
```

## What Ground forwards to the vision teammate

Example file: [examples/drone-vision-request.json](examples/drone-vision-request.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-drone-vision-request",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 1,
  "sent_at": "2026-11-04T13:00:10.100Z",
  "source": "ground",
  "destination": "vision",
  "kind": "vision.request",
  "correlation_id": null,
  "expires_at": "2026-11-04T13:00:13.100Z",
  "simulated": true,
  "payload": {
    "request_id": "vision-drone-001",
    "provider": "xai",
    "model_id": "CONFIGURE_VERIFIED_IMAGE_MODEL",
    "prompt_version": "patrol-demo-v2.0",
    "stage": "drone_search",
    "frame": {
      "frame_id": "drone-downward-001",
      "image_ref": "artifact://demo-20261104-001/drone/downward-001.jpg",
      "sha256": "0f0479fff4658167e274ded2e2bdc58a9cc45ebdd667c955fb2a2f636906470f",
      "captured_at": "2026-11-04T13:00:10.000Z",
      "camera_id": "downward",
      "camera_epoch": 1,
      "width_px": 320,
      "height_px": 240,
      "camera_frame_id": "drone/camera_downward",
      "camera_to_body_calibration_id": "synthetic-calibration-v1",
      "simulated": true
    },
    "target_description": "A person in the operator-marked closed demo area.",
    "active_track_id": null,
    "scene_context": {
      "staged_demo": true,
      "area_closed_by_operator": true
    },
    "max_evidence_age_ms": 3000
  }
}
```

`artifact://` must resolve to actual image bytes before the xAI request. The example reference/hash is illustrative and has no matching captured photo. Ground drops stale/queued frames and runs at most one vision request concurrently by default. You keep local flight supervision active while that request runs.

## Failure behavior

- If directional control is currently unreliable, report controlled motion unavailable. Do not substitute unbounded random commands.
- If downward video is unsupported or unusable, report it and use only a separately approved front-camera/manual scenario or simulation.
- Beacon moving/unknown means Ground stops dog homing. Keep dog-to-drone observations and aircraft state separate.
- Missing/unknown landing is not grounded, even when an image was successfully captured.
- A local `is_flying` default or takeoff ACK is insufficient evidence of actual state after a lost reply.
- Prove the pinned SDK's actual no-retry behavior at the transport boundary. Ground sending one command is not proof of one wire takeoff.

Acceptance before real use: connection + fresh video; camera switching; controlled bounded move/hover; stable beacon; command deduplication; link/lease behavior; safe landing. Record observed results separately from synthetic examples.
