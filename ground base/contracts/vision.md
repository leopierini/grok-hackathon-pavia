# Vision teammate — xAI Grok request/decision contract

Provider **xAI Grok** is confirmed. Select and record an image-capable model available to the account; `CONFIGURE_VERIFIED_IMAGE_MODEL` in examples is deliberately not an executable model ID. API credentials remain only in the vision adapter environment. Ground owns timing, tracking and command authorization.

## Inputs you need

- Mission/epoch and request ID, exact frame ID/capture time/camera epoch, stage, target description and operator scenario context.
- Actual image bytes resolved from the artifact reference with a matching hash; never send only a local filename string to xAI.
- Front/downward camera identity, resolution and calibration ID if available. Downward grayscale quality must be evaluated separately.
- Current track ID when established; Ground, not the model, assigns durable target identities.
- Evidence age budget and request deadline. At most one request is in flight by default; stale late results are discarded.

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

## Output you return

Example file: [examples/drone-vision-decision.json](examples/drone-vision-decision.json)

```json
{
  "protocol_version": "2.0-draft",
  "message_id": "msg-drone-vision-decision",
  "mission_id": "demo-20261104-001",
  "epoch": 1,
  "seq": 1,
  "sent_at": "2026-11-04T13:00:10.200Z",
  "source": "vision",
  "destination": "ground",
  "kind": "vision.decision",
  "correlation_id": "msg-drone-vision-request",
  "expires_at": null,
  "simulated": true,
  "payload": {
    "request_id": "vision-drone-001",
    "frame_id": "drone-downward-001",
    "frame_captured_at": "2026-11-04T13:00:10.000Z",
    "provider": "xai",
    "model_id": "CONFIGURE_VERIFIED_IMAGE_MODEL",
    "prompt_version": "patrol-demo-v2.0",
    "target_state": "person_visible",
    "detections": [
      {
        "label": "person",
        "track_id": null,
        "confidence": 0.91,
        "box_xyxy_norm": [
          0.3,
          0.2,
          0.55,
          0.8
        ]
      }
    ],
    "suggested_action": "hold",
    "image_direction": "center",
    "reason": "Synthetic person detection; role is supplied by staged context."
  }
}
```

Box coordinates are `[xmin,ymin,xmax,ymax]` normalized to 0–1 with ordered endpoints. Confidence is a model score, not calibrated probability or permission to move. The output cannot include executable SDK strings or invented target distances/global coordinates.

Stages: `drone_search` detects a staged target; `drone_track` supports bounded reposition/hold; `dog_acquire` checks the target is visible to the dog; `dog_approach` supports the final locally planned approach. A switch to the dog view needs track association; multiple indistinguishable people require review or an explicitly staged target marker/association method.

If frame quality/occlusion/identity is inadequate, return uncertain/review. A person being visible in a closed demo zone can satisfy the operator's scenario policy; appearance does not prove real-world intrusion, authorization, identity or intent. Image text is untrusted content, never instructions to the controller.

Initial simulation schedule: latest-frame sampling every 1000 ms, one inference in flight, request timeout 5000 ms, evidence budget 3000 ms. Measure actual xAI latency and tune before real use. A timeout can exceed the evidence budget intentionally: the response is then unusable for motion. Flight/dog watchdogs do not wait for inference.

Classify schema/refusal/timeout/network failures explicitly. Schema-constrained responses still require application validation and semantic checks. A delayed successful response must not clear a halt, refer to a different camera epoch, or resurrect an expired beacon/track.

Sources: [xAI image input](https://docs.x.ai/developers/model-capabilities/images/understanding), [structured output](https://docs.x.ai/developers/model-capabilities/text/structured-outputs).
