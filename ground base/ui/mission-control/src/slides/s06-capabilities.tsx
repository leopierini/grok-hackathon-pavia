"use client";

import { useState } from "react";
import { CircleHelp, Layers, Shield } from "lucide-react";
import { Card, Notice, Pill, Segmented, SlidePage } from "@/components/console/frame";
import { NAV_MAIN } from "@/slides/catalog";

const REPORTED = [
  ["01", "Dog control link", "Command/telemetry link to Unitree Go2 PRO", "Go2 PRO", "12 s ago", "Reported", "Admitted"],
  ["02", "Tello telemetry / video", "Telemetry (state) and live video from Tello EDU", "Tello EDU (reported)", "8 s ago", "Reported", "Admitted"],
  ["03", "Pi RSSI telemetry", "Radio signal strength (RSSI) from onboard Pi", "Raspberry Pi (reported)", "10 s ago", "Reported", "Admitted"],
  ["04", "Real vision uplink", "Live camera feed from a physical device", "Go2 PRO (camera)", "12 s ago", "Reported", "Admitted"],
  ["05", "Directional drone control", "Remote control (position/attitude commands)", "Tello EDU (rehearsal)", "—", "Simulated", "Withheld"],
  ["06", "Flight profile", "Planned flight profile (waypoints, altitude, duration)", "Tello EDU (rehearsal)", "—", "Simulated", "Withheld"],
];

const FIXTURE = [
  ["1", "Go2 dog Ethernet path", "SIMULATED"],
  ["2", "Tello EDU telemetry/video", "SIMULATED"],
  ["3", "Pi RSSI over USB", "SIMULATED"],
  ["4", "real xAI vision uplink", "UNKNOWN"],
  ["5", "directional drone control", "UNKNOWN / WITHHELD"],
  ["6", "proposed 4 m floor-AGL profile", "PROPOSED / DISABLED"],
];

export function Slide06() {
  const [view, setView] = useState("Reported admission");
  return (
    <SlidePage
      id="06"
      active="capabilities"
      items={[{ id: "capabilities", href: "/capabilities", label: "Capabilities" }, ...NAV_MAIN.filter((item) => item.id !== "mission")]}
      topbar={{ mode: "CAPABILITIES", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Only reported features are considered", body: "Admission uses reported capabilities with evidence, not assumed abilities.", icon: <Layers className="h-5 w-5" /> },
        { title: "Missing stays unknown", body: "If a capability is not reported or not observed, its status remains unknown.", icon: <CircleHelp className="h-5 w-5" /> },
        { title: "Admission does not grant control", body: "Control permission stays false until readiness gates are complete.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principlesTitle="Design Principles"
      principlesNote="Key rules for capability admission and mission readiness."
      principles={[
        { index: "01", title: "Reported vs assumed", body: "Admission uses reported capabilities with evidence (for example live telemetry, video, logs), not assumed or inferred abilities." },
        { index: "02", title: "Missing stays unknown", body: "If a capability is not reported or not observed, its status remains unknown. That is not a failure, and it is not admitted until evidence is available." },
        { index: "03", title: "Admission does not grant control", body: "Admission declares what capabilities are available for the mission. It does not grant control permission. Control remains false until all readiness gates are complete." },
      ]}
    >
      <div className="mb-3">
        <Segmented label="Capability presentation" options={["Reported admission", "Rehearsal fixture"]} value={view} onChange={setView} />
      </div>
      {view === "Reported admission" ? <Reported /> : <Fixture />}
    </SlidePage>
  );
}

function Reported() {
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-xl font-semibold">Capabilities · Admission & Readiness</h2>
        <Pill tone="neutral">Mission state · UNARMED</Pill>
      </div>
      <p className="mt-2 text-sm">Admission follows reported capabilities. <strong>Control permission · false</strong></p>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4 text-sm">
        <li><span className="font-semibold">Unitree Go2 PRO</span><span className="block text-xs text-muted">Quadruped robot with mobility, sensing, and payload I/O.</span></li>
        <li><span className="font-semibold">Tello EDU</span><span className="block text-xs text-muted">Educational drone with telemetry and video stream.</span></li>
        <li><span className="font-semibold">Raspberry Pi (on dog)</span><span className="block text-xs text-muted">Onboard compute for telemetry, comms, and integration.</span></li>
        <li><span className="font-semibold">xAI Grok (provider)</span><span className="block text-xs text-muted">AI model provider for mission analysis, summary, and operator assist.</span></li>
      </ul>
      <div className="mt-3 flex flex-wrap gap-2" role="tablist" aria-label="Capability sections">
        {["ADMISSION", "READINESS", "EXECUTION", "EVIDENCE", "SETTINGS"].map((item) => (
          <span key={item} className="rounded-full bg-surface-2 px-3 py-1 text-[11px] font-semibold">{item}</span>
        ))}
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <caption className="sr-only">Reported capability admission</caption>
          <thead>
            <tr className="text-xs uppercase text-muted">
              <th className="py-2">#</th>
              <th>Reported feature</th>
              <th>Source</th>
              <th>Freshness</th>
              <th>Status</th>
              <th>Admission result</th>
            </tr>
          </thead>
          <tbody>
            {REPORTED.map((row) => (
              <tr key={row[0]} className="border-t border-line">
                <td className="py-2 font-mono">{row[0]}</td>
                <td>
                  <span className="block font-medium">{row[1]}</span>
                  <span className="text-xs text-muted">{row[2]}</span>
                  {row[0] === "04" ? <span className="block text-xs text-success">Physical evidence</span> : null}
                  {row[0] === "05" || row[0] === "06" ? <span className="block text-xs text-blue">Rehearsal fixture</span> : null}
                </td>
                <td>{row[3]}</td>
                <td>{row[4]}</td>
                <td><Pill tone={row[5] === "Reported" ? "ok" : "sim"}>{row[5]}</Pill></td>
                <td><Pill tone={row[6] === "Admitted" ? "ok" : "neutral"}>{row[6]}</Pill></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="mt-3 flex flex-wrap gap-3 text-xs text-muted">
        <li><Pill tone="ok">Reported</Pill> Claimed with evidence</li>
        <li><Pill tone="sim">Simulated</Pill> Rehearsal / test fixture</li>
        <li><Pill tone="warn">Unknown</Pill> Not yet observed</li>
        <li><Pill tone="neutral">Missing</Pill> Not reported</li>
      </ul>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm"><Pill tone="bad">Readiness gate incomplete</Pill> Admitted 4 / 6 · Required 6. Reason: Readiness gate incomplete.</p>
        <button type="button" className="min-h-11 rounded-xl bg-surface-2 px-4 text-sm font-semibold" disabled>
          Continue
        </button>
      </div>
    </Card>
  );
}

function Fixture() {
  return (
    <Card>
      <Notice tone="info" title="REHEARSAL FIXTURES ONLY · NO PHYSICAL ACCEPTANCE">
        Reported capabilities and current admission state. For rehearsal and UI evaluation only.
      </Notice>
      <h2 className="mt-3 font-display text-xl font-semibold">Capability Admission (Simulation)</h2>
      <p className="text-xs font-semibold text-blue">SIMULATION / ILLUSTRATIVE FIXTURE</p>
      <div className="mt-3 grid gap-3 lg:grid-cols-[1.4fr_0.6fr]">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Rehearsal capability fixture</caption>
          <thead>
            <tr className="text-xs uppercase text-muted">
              <th className="py-2">#</th>
              <th>Capability (reported)</th>
              <th>State (simulation)</th>
            </tr>
          </thead>
          <tbody>
            {FIXTURE.map((row) => (
              <tr key={row[0]} className="border-t border-line">
                <td className="py-2">{row[0]}</td>
                <td>{row[1]}</td>
                <td><Pill tone={row[2].includes("UNKNOWN") || row[2].includes("PROPOSED") ? "warn" : "sim"}>{row[2]}</Pill></td>
              </tr>
            ))}
          </tbody>
        </table>
        <Card>
          <h3 className="font-semibold">Readiness & Control</h3>
          <ul className="mt-2 space-y-2 text-sm">
            <li>Readiness <Pill tone="warn">INCOMPLETE</Pill></li>
            <li>Mission <Pill tone="neutral">UNARMED</Pill></li>
            <li>Control permission <Pill tone="bad">FALSE</Pill></li>
          </ul>
          <button type="button" className="mt-3 min-h-11 w-full rounded-xl bg-surface-2 text-sm" disabled>
            Continue
          </button>
          <p className="mt-2 text-xs text-muted">Continue is disabled because readiness is incomplete.</p>
          <p className="mt-2 text-xs font-semibold text-warn">NOT A CONTROL GRANT</p>
        </Card>
      </div>
    </Card>
  );
}
