| Task | Owned tests | Cases × seeds | Scope evidence |
| --- | ---: | ---: | --- |
| 11: Validate v2 envelopes and keep the v1 robot contract unchanged | 17 | 6 × 3 | Strict envelopes/directions/identity; command ACKs share the issued ID; sequence replay and old-epoch cached replay rejected. |
| 12: Admit device capabilities and arm only reported features | 19 | 9 × 3 | Per-peer validated capabilities and real/fake separation; no invented controlled motion, Pi link, height, or radio. |
| 13: Ingest drone observations and preserve height reference | 31 | 5 × 3 | Observation identity, camera, pose and missing measurements; frame bytes and beacon hold delegated to their owners. |
| 14: Check camera epoch, frame provenance, and image bytes | 23 | 15 × 3 | Actual JPEG bytes, hash, dimensions, artifact containment and frame identity; immutable evidence cannot establish hardware freshness. |
| 15: Schedule vision requests and drop stale frames | 37 | 12 × 3 | One in-flight vision request, newest pending frame, expiry and clock-error-plus-age budget; capture precision preserved. |
| 16: Validate xAI decisions and withhold motor authority | 12 | 18 × 3 | Real stage entry wired; exact request/frame/track/camera/model/prompt correlation and local expiry/authority checks; no motor calls. |
| 17: Approve one bounded drone primitive at a time | 38 | 18 × 3 | Allowlisted bounded drone command approval; current safety rechecked before cache replay; conflicting request IDs and mutable cache results rejected. |
| 18: Track drone acknowledgements and preserve unknown landing | 35 | 11 × 3 | ACK lifecycle, duplicate/terminal conflict handling, unknown result queries, and no automatic second takeoff. |
| 19: Require a stable beacon hold and advance beacon epoch after motion | 33 | 10 × 3 | Moving/expired beacon blocks dog permission; fresh hold and beacon epoch required; authoritative halt wins. |
| 20: Accept dog navigation health and safe local candidates | 43 | 17 × 3 | Accept only peer-reported safe candidate IDs with frame/map/expiry/tether constraints; no SLAM implementation or invented detour. |
| 21: Validate Raspberry Pi RSSI windows sampled on the dog | 35 | 10 × 3 | Pi RSSI window BSSID/epoch/time/pose/quality validation, null no-signal handling; no dBm-to-meters conversion. |
| 22: Choose an RSSI step only from safe dog candidates | 14 | 26 × 3 | Comparable RSSI windows, bounded exploration/hysteresis/no-progress stops; actual selection result exposed to composition. |
| 23: Issue leased dog commands and a priority halt | 23 | 16 × 3 | Leased dog commands require current authority, stationary/standing/avoidance and cable bounds; changed motion under one selection ID rejected. |
| 24: Track dog acknowledgements and rejected steps | 19 | 14 × 3 | ACK accepted/running/completed are separate; active/uncertain commands block another step; verified stationary and faulted replay checked. |
| 25: Hand the dog from RSSI to its own camera | 26 | 18 × 3 | Two fresh same-track dog front-camera hits; ambiguous/wrong track goes to review; approach and goal remain separate. |
| 26: Accept the demo goal only from separate proximity evidence | 9 | 24 × 3 | Separate dog range and drone horizontal offset, thresholds/freshness/sources; no goal from RSSI, obstacle clearance or one 3D distance. |
| 27: Separate demo-goal completion from landing recovery | 20 | 10 × 3 | Goal and aircraft recovery independent; unknown landing stays latched until new verified recovery evidence; prior legitimate trace allowed. |
| 28: Halt, drop the link, and expire leases without waiting for Grok | 20 | 17 × 3 | Immediate halt/link-loss/lease-expiry latch and independent stop requests; pending work and reset gates preserved. |
| 29: Journal v2 messages and keep the proposed team log schema | 23 | 8 × 3 | Correlation-preserving redacted v2 journal composed with the real G04 disk writer; open binding, modes, ticket and clock metadata repaired. |
| 30: Check Ethernet, Wi-Fi, and the Pi data path before arming | 18 | 21 × 3 | Ethernet/Wi-Fi/Pi/internet topology validation, cable acceptance and missing-path refusal; no radio fallback or OS route mutation. |
| 31: Compute demo timings and leave unknown values empty | 24 | 8 × 3 | Metrics from actual composed journal records with one clock domain; missing values/accuracy stay null with reasons. |
| 32: Rehearse the drone-first demo offline and write the operator script | 12 | 13 × 3 | Owned isolated rehearsal stays independent; separate composed runner exercises real G11–31 providers and all Ground base services. |
