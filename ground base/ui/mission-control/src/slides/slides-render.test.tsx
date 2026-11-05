import type { ReactElement } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Slide01 } from "./s01-mission";
import { Slide02 } from "./s02-cockpit";
import { Slide03 } from "./s03-header";
import { Slide04 } from "./s04-devices";
import { Slide05 } from "./s05-settings";
import { Slide06 } from "./s06-capabilities";
import { Slide07 } from "./s07-actions";
import { Slide08 } from "./s08-halt";
import { Slide09 } from "./s09-vision";
import { Slide10 } from "./s10-evidence";
import { Slide11 } from "./s11-decision";
import { Slide12 } from "./s12-drone";
import { Slide13 } from "./s13-commands";
import { Slide14 } from "./s14-beacon";
import { Slide15 } from "./s15-dog";
import { Slide16 } from "./s16-telemetry";
import { Slide17 } from "./s17-leases";
import { Slide18 } from "./s18-handoff";
import { Slide19 } from "./s19-proximity";
import { Slide20 } from "./s20-recovery";
import { Slide21 } from "./s21-runs";
import { Slide22 } from "./s22-metrics";
import { Slide23 } from "./s23-rehearsal";
import { Slide24 } from "./s24-system";

const CASES: [string, () => ReactElement, string[]][] = [
  ["01", Slide01, ["Site Survey — Sector A", "Go2 PRO", "Tello EDU", "Execute: waypoint 1–3", "Operator confirm"]],
  ["02", Slide02, ["Site Survey – Sector A", "GO2 PRO", "Execute: Scout area", "32%", "Epoch E2025-03-08T10:27Z"]],
  ["03", Slide03, ["Idle / Unarmed", "In-progress", "Fault / Recovery Required", "DOG_VISION", "Epoch fencing"]],
  ["04", Slide04, ["DOG · ETHERNET", "xAI Grok", "UPLINK · UNKNOWN", "No automatic handover", "Directional control unverified"]],
  ["05", Slide05, ["Calibration", "UNSET", "4 m floor-AGL", "No secrets accepted", "Command lease ms"]],
  ["06", Slide06, ["Control permission · false", "Directional drone control", "Withheld", "Admitted 4 / 6", "Readiness gate incomplete", "Physical evidence", "xAI Grok (provider)"]],
  ["07", Slide07, ["Confirm Start", "Stale action rejected", "Epoch changed to 13", "Awaiting confirmation", "Arm required"]],
  ["08", Slide08, ["HALT LATCHED", "Delivered · unknown", "Lease expired", "Verified stop · unknown", "Link-loss"]],
  ["09", Slide09, ["dog-front-002", "TRK-0347", "0.96", "VR-0912", "person_visible", "VR-0913"]],
  ["10", Slide10, ["dog-front-002", "CAM-002", "1920 × 1080", "2,604,781 bytes", "Age · unknown", "synthetic-calibration-v1", "Allowlist · permitted"]],
  ["11", Slide11, ["#F-003842", "0.91", "patrol-demo-v2.0", "#F-003799", "No motor authority", "switch to dog vision"]],
  ["12", Slide12, ["floor_agl", "track_step", "Motion permission", "false", "Beacon hold (epoch 4)", "10:27:16"]],
  ["13", Slide13, ["cmd-drone-x001", "cmd-drone-x004", "10:22:35", "cmd-drone-x005", "10:21:57", "Accepted is not completion"]],
  ["14", Slide14, ["B-017", "00:00:37", "RSSI is not distance", "Gate closed", "IN MOTION", "24 dB"]],
  ["15", Slide15, ["slam_local_planner", "museum-map-demo", "No map image published", "candidate-forward-01", "Not a real route", "0.8"]],
  ["16", Slide16, ["-54 dBm", "W-0104", "W-0108", "noisy", "Heartbeat", "Alive", "RSSI ≠ distance"]],
  ["17", Slide17, ["candidate-forward-01", "move_local", "Lease · 300 ms", "T + 276 ms", "Stationary · unknown", "Expired lease is not proof of stop"]],
  ["18", Slide18, ["target-001", "RSSI -58 dBm", "Same track · MATCH", "target-003", "0.88", "No identity claim"]],
  ["19", Slide19, ["Goal · unresolved", "Dog range · unknown", "Drone horizontal offset · unknown", "No RSSI arrival inference", "Obstacle clearance"]],
  ["20", Slide20, ["Demo goal · REACHED", "Landing · UNKNOWN", "Recovery · REQUIRED", "Ordinary run · blocked", "M-0247"]],
  ["21", Slide21, ["R-0278", "message.envelope_v2", "msg-9f3a2b71", "protocol · 2.0-draft", "schema · proposed-1", "latency.high"]],
  ["22", Slide22, ["2.314 s", "6.783 s", "18.427 s", "864", "Unknown ≠ zero", "no verified landing event"]],
  ["23", Slide23, ["happy_path", "rehearsal_report_happy_path.pdf", "Stale frame", "Unknown landing", "Goal ≠ landing", "Operator brief"]],
  ["24", Slide24, ["#F6FAFF", "#1769FF", "#E85A67", "Space Grotesk", "Foundation & protocol", "24 / 24", "#081220", "Create Mission", "4 tasks per module", "M-0316"]],
];

describe("concept slides", () => {
  it.each(CASES)("slide %s renders its board data", (_id, View, needles) => {
    render(<View />);
    for (const needle of needles) expect(screen.getAllByText((_, node) => node?.textContent?.includes(needle) ?? false).length).toBeGreaterThan(0);
  });
});
