# Dog teammate → Ground → xAI Grok

You own the Go2 control application, actual movement, stop/deadman behavior, LiDAR, and any SLAM/local planning. Ground consumes a JSON interface and never implements your robot SDK or sends Grok output directly to motors.

## Required observations

| Data | Why Ground needs it |
| --- | --- |
| Connection and transport | Ethernet is current; Wi-Fi is an alternate accepted profile. Only one command owner. |
| Standing/stationary/avoidance | Unknown remains null. Ground needs actual readiness and stop evidence. |
| Pose/map identity | Needed to associate RSSI samples and planner candidates. Report validity, map epoch and timestamp. |
| Navigation mode | Distinguish SLAM + local planner from reactive avoidance; neither is assumed from LiDAR presence. |
| LiDAR freshness/clearance | Obstacle safety evidence. An obstacle range alone is not target-person range. |
| Front image | Fresh frame metadata and bytes reference for acquiring the staged target while following RSSI. |
| Current command and ACKs | Correlate accepted, running, completed, blocked, expired and unknown results. |

Example file: [examples/dog-observation.json](examples/dog-observation.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-dog-observation",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 2,
  "sent_at": "2026-11-04T13:00:10.000Z",
  "source": "dog",
  "destination": "ground",
  "kind": "dog.observation",
  "correlation_id": null,
  "expires_at": null,
  "simulated": true,
  "payload": {
    "device_id": "dog-01",
    "standing": true,
    "stationary": true,
    "avoidance_enabled": true,
    "transport": "ethernet",
    "pose": {
      "frame_id": "museum/map",
      "map_id": "museum-map-demo",
      "map_epoch": 1,
      "x_m": 0,
      "y_m": 0,
      "z_m": 0,
      "yaw_rad": 0.0,
      "observed_at": "2026-11-04T13:00:10.000Z",
      "valid": true
    },
    "navigation_mode": "slam_local_planner",
    "slam_state": "localized",
    "lidar_observed_at": "2026-11-04T13:00:10.000Z",
    "minimum_clearance_m": 0.8,
    "frame": {
      "frame_id": "dog-front-001",
      "image_ref": "artifact://demo-20261104-001/dog/front-001.jpg",
      "sha256": "6a3294c6b81ab68fc54d734be2436d1b317292a0367af713d65c0cd65c688537",
      "captured_at": "2026-11-04T13:00:10.000Z",
      "camera_id": "front",
      "camera_epoch": 1,
      "width_px": 1280,
      "height_px": 720,
      "camera_frame_id": "dog/camera_front",
      "camera_to_body_calibration_id": "synthetic-calibration-v1",
      "simulated": true
    },
    "active_command_id": null
  }
}
```

## Safe movement candidates

The dog teammate supplies bounded collision-checked candidates. Ground can rank/select them using RSSI or target-image evidence, but your app revalidates the candidate against its **current** local planner/obstacles before executing. A stale map/candidate never authorizes motion.

Example file: [examples/dog-navigation-candidates.json](examples/dog-navigation-candidates.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-dog-navigation-candidates",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 3,
  "sent_at": "2026-11-04T13:00:10.000Z",
  "source": "dog",
  "destination": "ground",
  "kind": "navigation.candidates",
  "correlation_id": null,
  "expires_at": null,
  "simulated": true,
  "payload": {
    "device_id": "dog-01",
    "snapshot_id": "nav-001",
    "map_id": "museum-map-demo",
    "map_epoch": 1,
    "navigation_mode": "slam_local_planner",
    "observed_at": "2026-11-04T13:00:10.000Z",
    "candidates": [
      {
        "candidate_id": "candidate-forward-01",
        "snapshot_id": "nav-001",
        "frame_id": "dog/base_link",
        "map_id": "museum-map-demo",
        "map_epoch": 1,
        "delta_x_m": 0.05,
        "delta_y_m": 0.0,
        "delta_yaw_rad": 0.0,
        "safe": true,
        "clearance_m": 0.8,
        "valid_until": "2026-11-04T13:00:10.500Z"
      }
    ],
    "blocked": false,
    "reason": "Synthetic local planner candidate, not a real route."
  }
}
```

Each candidate has a stable ID, snapshot/map epoch, coordinate frame, validity deadline and clearance result. If no candidate is safe, send an empty list with `blocked=true`; Ground stops/reviews rather than inventing a detour.

## What reaches vision

Ground forwards the validated frame in [dog-vision-request.json](examples/dog-vision-request.json). Vision reports whether the same staged person is visible, normalized boxes and a semantic action. Ground maintains track identity; a model must not identify a real individual or infer malicious intent from appearance.

## Pi relationship

The Raspberry Pi is physically on this dog. Synchronize its samples with the dog pose/map epoch, and document its mounting offset if the RSSI method uses antenna position. Pi network telemetry is separate from dog control. Do not assume the laptop can read the Pi over the Tello AP or that the broken router supplies the path.

Ethernet runs must respect cable length, routing, slack and a clear drone landing area. Wireless runs require separately tested simultaneous dog/drone/internet links. Neither mode silently hands over after a fault.
