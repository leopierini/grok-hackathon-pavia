# Team message contract — drone-first demo v2

Protocol: **2.0-draft**. This is a proposed shared wire contract for the new meeting plan, not the legacy Python robot contract v1.0. Ground translates at a versioned boundary; do not silently add methods to another teammate's v1 implementation.

Start with the section **Demo specification and which JSON file goes to whom** in [ground.md](../ground.md). Then share the appropriate handoff:

| Teammate / direction | File |
| --- | --- |
| Drone observations → Ground → AI | [drone-to-ai.md](drone-to-ai.md) |
| AI proposals → Ground → approved drone commands | [ai-to-drone.md](ai-to-drone.md) |
| Dog observations → Ground → AI | [dog-to-ai.md](dog-to-ai.md) |
| AI proposals → Ground → dog application | [ai-to-dog.md](ai-to-dog.md) |
| Vision request/decision and image handling | [vision.md](vision.md) |
| Raspberry Pi RSSI and dog navigation | [rssi-and-navigation.md](rssi-and-navigation.md) |
| ACKs, failure events, and proposed logs | [events-and-logs.md](events-and-logs.md) |

Machine-readable examples live in `examples/`; [message.schema.json](message.schema.json) validates their structure. Examples are synthetic **simulated=true**, with illustrative timestamps/measurements, not a real flight record. Numeric values are not approved hardware settings. No example command is sent to a robot by opening these files.

## Communication graph

```text
drone adapter ---- observations ----> Ground ---- image request ----> vision/xAI
dog application -- observations ----> Ground <--- decision/proposal -- vision/xAI
Pi on dog -------- RSSI windows ----> Ground
dog planner ------ safe candidates -> Ground
                                    Ground ---- approved command --> dog/drone
                                    Ground <--- ACK/result --------- dog/drone
                                    Ground ---- journal -----------> local logs
```

“Drone to AI” and “AI to dog” are logical directions. Ground remains the intermediary. A device never exposes arbitrary motor tools directly to a cloud model. The Raspberry Pi is the RSSI receiver at the dog's position; the Tello is the radio source.

## Universal envelope

Every message has: `protocol_version`, `message_id`, `mission_id`, `epoch`, `seq`, `sent_at`, `source`, `destination`, `kind`, `correlation_id`, `expires_at`, `simulated`, and `payload`.

- IDs are opaque unique strings. Mission ID identifies one demonstration; epoch changes after reset/reconnect/rearm and invalidates old work. Sequence is monotonic **per publisher per epoch**, not a global clock.
- `message_id` identifies one immutable message. Retransmitting the same message does not authorize another action. `command_id` identifies one action attempt across its ACK/result lifecycle.
- UTC timestamps use RFC3339. Peers negotiate clock offset/error during connection; receivers also measure local arrival time with their monotonic clock. Clock uncertainty beyond the configured age budget blocks ordinary motion.
- `correlation_id` links responses to requests. A device ACK points to the command message; a vision decision points to its exact request. `frame_id`, `track_id`, `map_id/map_epoch`, `camera_epoch`, and `beacon_epoch` prevent unrelated evidence from being mixed.
- `expires_at` is required and non-null for ordinary commands/proposals/vision requests. A lease is enforced locally at the receiver, using remaining validity at receipt; reconnect never renews it.
- All examples have `simulated=true`. A real adapter returning synthetic evidence is rejected. Unknown quantities use `null` plus an explicit validity/source field, never invented zeroes.
- Strict message/payload schemas reject unknown fields. Future team log additions use a versioned schema revision and namespaced event details; preserve existing core fields.

## Transport and ownership

The wire format is JSON UTF-8. Ground's operator serves `/ws/robot/v2` on `127.0.0.1:8765` (one JSON object per text frame). Authentication is the `x-ground-operator-token` header, whose value is `GROUND_OPERATOR_TOKEN`. Those three values are published in `config/robot_v2.json`.

Image bytes are transferred/resolved separately through an authenticated local artifact mechanism; `artifact://...` is a reference, not an xAI API image URL. Vision must resolve it, verify the hash, and send actual bytes or a valid accessible image URL. A file path on one machine is not a file on another.

Pi's measurement radio and its telemetry delivery link must be documented separately. A Pi associated with/scanning the drone AP does not automatically have a route to the laptop. Verify a wired/USB/second-radio data path without interrupting dog control or Tello video. Do not change network routes or install services by assumption.

Only an authenticated selected Ground session may issue approved commands. Reject other sources and ordinary stale/foreign-epoch commands. An authorized halt/land safety request has priority and remains available during expired ordinary work; it must not require Grok approval.

## Receiver action rules

1. Validate version, direction, schema, session, epoch, sequence/duplicate identity, timestamps and capability.
2. For motion, validate the approved primitive/candidate, units, coordinate/map/camera identity, actual safety state, remaining lease, and current control ownership.
3. Same `command_id` and same payload returns the known ACK/result without executing again. Same ID with conflicting payload is rejected. Persist the bounded deduplication ledger across reconnect as needed.
4. ACK `accepted` means accepted, not completed. Supply running/final observations separately. A timeout may mean the command executed with a lost reply: query its result/status; do not create another takeoff/move attempt automatically.
5. Dog independently stops on local obstacles/expired lease/control loss. Drone independently applies its tested hover/landing/link-loss behavior. No cloud loop can guarantee delivery after link loss.
6. Ground logs received observation, request, model proposal, approval/rejection, command, each ACK, execution evidence, safety change and terminal outcome with correlation IDs.

## Proposed application functions/tools

These functions are Ground-facing APIs to implement, not raw SDK methods:

| Port | Frozen v2 operation |
| --- | --- |
| Dog | `connect(profile)`, `observe()`, `capture(camera_id)`, `execute(command)`, `halt(reason)`, `close()` |
| Drone | `connect(profile)`, `observe()`, `capture(camera_id)`, `execute(command)`, `hover(reason)`, `land(reason)`, `close()` |
| Pi RSSI | `connect(profile)`, `read_window(beacon_id, beacon_epoch)`, `close()` |
| Local navigation | `get_candidates(snapshot_id)`, `validate_candidate(candidate_id, map_epoch)`, `target_range(track_id)`; supplied by the dog teammate, no new SLAM implementation in Ground. |
| Vision | `assess_frame(request) -> vision.decision`, `metadata()`; xAI Grok is confirmed, model ID configurable. |
| Ground model tools | `inspect_latest_frame`, `propose_search`, `propose_reposition`, `propose_dispatch`, `propose_dog_step`, `propose_stop`, `request_review`; each produces a schema-validated proposal only. |
| Ground approved actions | `approve_and_send(proposal, snapshot)`, `halt_all(reason)`, `query_command(command_id)`, `record_event(event)`; deterministic gates own authorization. |

Method signatures use envelope objects from the schema; results are envelope ACKs/observations, not vendor objects. All I/O operations are asynchronous/bounded. Factories and imports never move hardware. Existing v1 factories can be reused only through an explicitly tested bridge; `run_route()` and `inspect()` do not magically implement RSSI steps or live scouting.
