# Ground Mission Control — 24 UI concept slides

This folder contains 24 portrait PNG design boards for the Ground operator console. They are visual proposals based on the Ground UI specification, implementation assignments, and supplied screenshots. They are not application code, completed implementation evidence, or hardware acceptance. Any sample telemetry is illustrative and should be treated according to its visible `SIMULATION`, `UNKNOWN`, or fixture label.

## Slide index

| Slide | File | View / focus | Task coverage |
| --- | --- | --- | --- |
| 01 | `01-ground-mission-control.png` | Product overview and design principles | 01–32 overview |
| 02 | `02-mission-control-cockpit.png` | Mission Control cockpit | 03, 05, 09, 13, 26, 27 |
| 03 | `03-mission-state-header.png` | Persistent header, mission phases, fault states | 03, 07, 09, 10 |
| 04 | `04-devices-readiness.png` | Devices, simultaneous links, readiness blockers | 02, 08, 12, 30 |
| 05 | `05-settings-profiles.png` | Connection profiles, budgets, unset thresholds | 02 |
| 06 | `06-capability-admission.png` | Reported capabilities and admission gates | 12 |
| 07 | `07-operator-actions.png` | Scoped operator commands and confirmations | 07 |
| 08 | `08-halt-recovery.png` | Priority halt, cleanup, and recovery | 10, 28 |
| 09 | `09-vision-evidence-workspace.png` | Vision requests, snapshots, and review | 06, 15 |
| 10 | `10-frame-provenance.png` | JPEG validation and frame provenance | 06, 14 |
| 11 | `11-xai-decision-review.png` | xAI decision review and policy boundary | 16 |
| 12 | `12-drone-telemetry-bounded-action.png` | Tello EDU observations and bounded action | 13, 17, 19 |
| 13 | `13-command-acknowledgements.png` | Command lifecycle and ACK states | 05, 18 |
| 14 | `14-beacon-rssi-navigation.png` | Stable beacon hold and RSSI gating | 19, 22 |
| 15 | `15-dog-navigation-candidates.png` | Dog navigation health and safe candidates | 20, 22 |
| 16 | `16-pi-rssi-windows.png` | Raspberry Pi telemetry and RSSI windows | 21 |
| 17 | `17-dog-command-leases.png` | Leased dog steps, ACKs, stationary evidence | 23, 24 |
| 18 | `18-rssi-vision-handoff.png` | Same-track RSSI-to-camera handoff | 25 |
| 19 | `19-proximity-goal-gate.png` | Independent dog-range and drone-offset evidence | 26 |
| 20 | `20-goal-landing-recovery.png` | Goal result, landing result, and recovery | 27, 10 |
| 21 | `21-runs-event-journal.png` | Run history, event journal, v2 inspector | 04, 11, 29 |
| 22 | `22-run-metrics.png` | Timing and quality metrics with honest unknowns | 31 |
| 23 | `23-offline-rehearsal-runbook.png` | Fault injection, offline rehearsal, operator brief | 32 |
| 24 | `24-design-system-coverage.png` | Light/dark system, tokens, and 32-task coverage | 01–32 |

The final slide groups task IDs by operator UI surface. For the detailed task state and verification evidence, use the repository’s `docs/ground/ui-coverage.md`.

## Visual system

| Token | Value |
| --- | --- |
| Canvas | `#F6FAFF` |
| Surface | `#FFFFFF` |
| Graphite | `#111B2C` |
| Deep | `#14243A` |
| Border | `#D6E4F5` |
| Electric Blue | `#1769FF` |
| Cyan | `#39C7F4` |
| Success | `#16A879` |
| Warning | `#F2A33A` |
| Error | `#E85A67` |
| Muted | `#66768F` |
| Dark Canvas | `#0B1220` |
| Dark Surface | `#111C2D` |
| Text | `#16243A` |

Typography direction: Space Grotesk for headings, Inter for interface text, JetBrains Mono for IDs and technical values. Status color is paired with a word or icon; color alone does not convey state.

## Generation notes

- Generated with the built-in image generation tool, using the prior eight UI boards as composition references and the supplied Ground screenshots/specification as product references.
- Shared visual brief: 24 cohesive portrait UI case-study boards; clean white technical-grid canvas; graphite/slate operator screens; electric-blue and cyan accents; compact, readable breakdowns; desktop-first operations UI; clear simulation, unknown, blocked, and recovery states.
- A few boards were regenerated to correct invented readiness and metric values. Use the files in this folder as the selected final versions.
