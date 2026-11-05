# Slide prompt set

## Shared direction

Create a cohesive 24-slide portrait UI/UX case study for **GROUND / MISSION CONTROL**, a local robotics operator console. Use the supplied Ground screenshots and implementation specification for product context and the earlier eight slide boards only for editorial composition. Use a bright white technical-grid presentation canvas with graphite/slate application surfaces, electric-blue and cyan focus accents, restrained semantic green/amber/red, and precise accessible hierarchy. Each board has a title, slide number, dominant desktop UI mockup, and concise component callouts. Keep the app operator-focused. Mark illustrative data as simulation; keep missing values unknown; separate mission phase, physical state, goal, landing, and recovery. Do not imply hardware acceptance or implementation completion.

## Individual slide briefs

1. **Ground Mission Control** — Introduce the operator console, drone-first mission dashboard, devices, evidence, readiness, and design principles.
2. **Mission Control cockpit** — Show the persistent status header, mission phase rail, simulated evidence workspace, device health, active operation, and activity feed.
3. **Mission state & persistent header** — Compare idle, in-progress, and fault/recovery header states; show authoritative phases and epoch fencing.
4. **Devices & Readiness** — Show Go2 PRO, Tello EDU, Raspberry Pi, Grok, simultaneous connection paths, and truthful simulated/unknown/unavailable blockers.
5. **Settings & connection profiles** — Show dog transport, Pi path, vision identity, budgets, unset thresholds, and the proposed disabled flight profile.
6. **Capability admission & readiness** — Show only reported capability states, fixture labeling, incomplete readiness, unarmed state, and no control grant.
7. **Operator actions & scoped confirmations** — Show status, arm, start, supervised, halt, reset, quit, action reasons, and stale-epoch rejection.
8. **Halt, cleanup & safe recovery** — Separate halt request, backend acceptance, delivery, verified stop, cleanup, lease expiry, and recovery.
9. **Vision & evidence workspace** — Show timestamped snapshots, vision requests, detections/tracks, proposals, and no AI motor authority.
10. **Frame provenance & validation** — Show JPEG validation, source, camera epoch, frame ID, capture time, calibration, hash, and unknown freshness.
11. **xAI decision review** — Show model identity, prompt, decision, uncertainty, track, proposal, validation, and rejection cases.
12. **Drone telemetry & bounded action** — Show Tello EDU flight state, height reference, observation age, beacon epoch, and one guarded primitive.
13. **Command lifecycle & acknowledgements** — Show submitted/accepted/running/completed/rejected/timed-out/unknown states, leases, and no automatic retry.
14. **Beacon hold & RSSI navigation** — Show dBm signal trend, stable hold, hold invalidation after drone movement, and dog-stop gating.
15. **Dog navigation & safe candidates** — Show planner health and candidate metadata without drawing an unpublished map.
16. **Pi telemetry & RSSI windows** — Show USB path, heartbeat, dBm samples, quality, age, clock comparability, and missing/noisy states.
17. **Dog command leases & acknowledgements** — Show candidate-scoped step, expiry, ACK track, separate stationary evidence, and priority halt.
18. **RSSI-to-vision handoff** — Show same-track verification across drone and dog camera sources plus ambiguous/mismatched review states.
19. **Proximity goal gate** — Show separate dog-range and drone-horizontal-offset evidence with unset thresholds and unresolved outcome.
20. **Goal, landing & recovery** — Show goal reached with landing unknown, recovery required, and ordinary new run blocked.
21. **Runs, event journal & inspector** — Show run history, ordered journal, v2 envelope fields, writer state, and provisional schema status.
22. **Run metrics & performance summary** — Show an empty/partial metrics view with unknown values, explicit reasons, and no fabricated series.
23. **Offline rehearsal & operator runbook** — Show scenario selection, ordered events, fault injection, report artifacts, and the short rehearsal brief.
24. **Design-system specification** — Show light/dark surfaces, exact palette, typography, spacing, component states, and the verified 01–32 task-to-screen mapping.
