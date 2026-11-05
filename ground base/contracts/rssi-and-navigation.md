# Raspberry Pi on dog — RSSI and navigation contract

The user confirms a Raspberry Pi is mounted on top of the dog. Its responsibility is measuring **the Tello's signal at the dog**, then delivering structured windows to Ground. Pi model, radio, power, network data path and timestamp synchronization remain to be recorded. The old router's failure is not evidence that the Pi can or cannot provide those functions.

## Pi → Ground payload

Example file: [examples/pi-rssi-window.json](examples/pi-rssi-window.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-pi-rssi-window",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 2,
  "sent_at": "2026-11-04T13:00:10.000Z",
  "source": "pi",
  "destination": "ground",
  "kind": "rssi.window",
  "correlation_id": null,
  "expires_at": null,
  "simulated": true,
  "payload": {
    "receiver_id": "pi-01",
    "receiver_mount": "dog",
    "interface": "wlan-measurement",
    "beacon_id": "tello-demo-01",
    "bssid": "02:00:00:00:00:01",
    "beacon_epoch": 3,
    "window_start": "2026-11-04T13:00:09.600Z",
    "window_end": "2026-11-04T13:00:09.800Z",
    "clock_error_ms": 15,
    "samples": [
      {
        "sample_id": "rssi-0",
        "captured_at": "2026-11-04T13:00:09.600Z",
        "rssi_dbm": -62,
        "pose": {
          "frame_id": "museum/map",
          "map_id": "museum-map-demo",
          "map_epoch": 1,
          "x_m": 0.0,
          "y_m": 0,
          "z_m": 0,
          "yaw_rad": 0.0,
          "observed_at": "2026-11-04T13:00:09.600Z",
          "valid": true
        }
      },
      {
        "sample_id": "rssi-1",
        "captured_at": "2026-11-04T13:00:09.700Z",
        "rssi_dbm": -60,
        "pose": {
          "frame_id": "museum/map",
          "map_id": "museum-map-demo",
          "map_epoch": 1,
          "x_m": 0.1,
          "y_m": 0,
          "z_m": 0,
          "yaw_rad": 0.0,
          "observed_at": "2026-11-04T13:00:09.700Z",
          "valid": true
        }
      },
      {
        "sample_id": "rssi-2",
        "captured_at": "2026-11-04T13:00:09.800Z",
        "rssi_dbm": -58,
        "pose": {
          "frame_id": "museum/map",
          "map_id": "museum-map-demo",
          "map_epoch": 1,
          "x_m": 0.2,
          "y_m": 0,
          "z_m": 0,
          "yaw_rad": 0.0,
          "observed_at": "2026-11-04T13:00:09.800Z",
          "valid": true
        }
      }
    ],
    "median_rssi_dbm": -60,
    "spread_db": 4,
    "quality": "valid"
  }
}
```

Identify the exact BSSID, not merely a matching SSID. Report physical receiver placement, interface, window times, synchronization error, individual samples and associated dog poses. Valid RSSI is dBm (normally negative); stronger means closer to zero. Preserve raw samples and filtered statistics. No signal is `quality=unavailable` with empty samples/null statistics, never 0 dBm.

Samples at different poses are comparable only with the same stable drone beacon epoch and compatible map/radio configuration. If a drone repositions, increment beacon epoch, stop dog guidance and discard the old gradient window. A rotating omnidirectional antenna does not inherently supply a bearing. Demonstrate a calibrated directional sweep or use spatial samples with known safe probe positions.

## Recommended bounded guidance loop

1. Require current verified hover, matching beacon identity/epoch, current Pi heartbeat and clock quality.
2. Require dog navigation health, fresh LiDAR, valid map/candidates, actual control link and tether approval where applicable.
3. Filter out stale/invalid/noisy samples; calculate robust relative improvement with hysteresis and a maximum exploration budget.
4. Select only among current safe candidate IDs. An exploratory probe is still a planned, bounded move, not an inference that RSSI already gave an absolute heading.
5. Ground issues one leased dog command; the dog app revalidates its local safety. Wait for stopped execution evidence before taking the next comparison sample.
6. When dog vision acquires the same target reliably, switch to the local visual-approach policy. Do not keep chasing RSSI instead of the actual target.
7. Weak/noisy/flat RSSI, unreachable peak, map loss, no safe candidates or expired hold yields stop/review, not arrival.

SLAM/map generation and obstacle planning belong to the dog teammate. Ground receives [safe candidates](examples/dog-navigation-candidates.json); it does not implement a new SLAM stack. Reactive avoidance may be an explicitly labeled restricted mode, but cannot supply a fabricated map/pose.

## Success data

Example file: [examples/proximity-evidence.json](examples/proximity-evidence.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-proximity-evidence",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 8,
  "sent_at": "2026-11-04T13:00:11.000Z",
  "source": "ground",
  "destination": "ground",
  "kind": "proximity.evidence",
  "correlation_id": null,
  "expires_at": null,
  "simulated": true,
  "payload": {
    "track_id": "target-001",
    "dog": {
      "range_m": 1.2,
      "source": "operator",
      "association_valid": true,
      "observed_at": "2026-11-04T13:00:11.000Z",
      "stationary": true
    },
    "drone": {
      "horizontal_offset_m": 1.0,
      "source": "operator",
      "observed_at": "2026-11-04T13:00:11.000Z",
      "hold_state": "stable"
    },
    "thresholds": {
      "dog_range_max_m": 1.5,
      "drone_horizontal_max_m": 1.5
    },
    "operator_confirmed": true
  }
}
```

Thresholds are illustrative and must be agreed for the actual space. Dog range must be associated with the target; minimum obstacle clearance is a different value. Drone distance here is horizontal ground-plane offset, distinct from its proposed height. Both observations must be current for the same track, with dog stopped and aircraft stable. If measurement is unavailable, use an explicit operator-verification mode or return unresolved.

Radio measurements, model confidence and a person-shaped box do not prove metric distance. No conversion from RSSI directly to meters is authorized by this contract.
