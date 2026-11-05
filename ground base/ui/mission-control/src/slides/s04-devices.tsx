"use client";

import { useState, type ReactNode } from "react";
import { AlertTriangle, Layers, Link2, Shield } from "lucide-react";
import { Card, CardTitle, Notice, Pill, Segmented, SlidePage } from "@/components/console/frame";
import { DogMark, DroneMark, PiMark, XaiMark } from "@/components/console/scenes";

type Cell = { label: string; tone: "ok" | "warn" | "bad" | "sim" | "neutral" };

const MATRIX: { capability: string; cells: Cell[] }[] = [
  {
    capability: "Mobility / Control",
    cells: [
      { label: "PASS", tone: "ok" },
      { label: "SIMULATED", tone: "sim" },
      { label: "—", tone: "neutral" },
      { label: "—", tone: "neutral" },
    ],
  },
  {
    capability: "Vision (Real)",
    cells: [
      { label: "UNKNOWN", tone: "warn" },
      { label: "PASS", tone: "ok" },
      { label: "PASS", tone: "ok" },
      { label: "UNKNOWN", tone: "warn" },
    ],
  },
  {
    capability: "Mission / Analysis",
    cells: [
      { label: "SIMULATED", tone: "sim" },
      { label: "SIMULATED", tone: "sim" },
      { label: "SIMULATED", tone: "sim" },
      { label: "UNAVAILABLE", tone: "bad" },
    ],
  },
  {
    capability: "Uplink (Remote)",
    cells: [
      { label: "UNKNOWN", tone: "warn" },
      { label: "UNKNOWN", tone: "warn" },
      { label: "UNKNOWN", tone: "warn" },
      { label: "UNAVAILABLE", tone: "bad" },
    ],
  },
];

export function Slide04() {
  const [tab, setTab] = useState("Overview");
  const [view, setView] = useState("Capability matrix");
  return (
    <SlidePage
      id="04"
      active="devices"
      topbar={{ mode: "OPERATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Configured is not verified", body: "A configured setting does not confirm end-to-end operation.", icon: <Layers className="h-5 w-5" /> },
        { title: "Readiness at a glance", body: "Devices, paths, and capabilities with clear status.", icon: <Link2 className="h-5 w-5" /> },
        { title: "Known limits", body: "No automatic handover. Directional control unverified.", icon: <AlertTriangle className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Configured is not verified", body: "A configuration (for example Ethernet, Wi-Fi, USB) does not confirm end-to-end operation." },
        { index: "02", title: "Wi-Fi profile does not repair router", body: "Applying a Wi-Fi profile (for example Tello EDU) does not fix a faulty or missing back enclosure router." },
        { index: "03", title: "Real vision requires verified uplink", body: "A real vision feed depends on a verified, stable internet uplink. It is not assumed in simulation." },
        { index: "04", title: "No automatic transport handover", body: "Transport is operator-controlled. No handover is performed automatically." },
      ]}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Segmented label="Devices presentation" options={["Capability matrix", "Operational fixture"]} value={view} onChange={setView} />
      </div>
      {view === "Capability matrix" ? <MatrixView tab={tab} setTab={setTab} /> : <FixtureView />}
    </SlidePage>
  );
}

function MatrixView({ tab, setTab }: { tab: string; setTab: (value: string) => void }) {
  return (
    <div className="space-y-3">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Devices</p>
            <h2 className="font-display text-2xl font-semibold">Devices & Readiness</h2>
            <p className="text-sm text-muted">Inventory, connection paths, and capability status.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Pill tone="sim">SIMULATION</Pill>
            <Pill tone="bad">No automatic handover</Pill>
          </div>
        </div>
        <div className="mt-3">
          <Segmented label="Device sections" options={["Overview", "Capability Matrix", "Paths", "Issues"]} value={tab} onChange={setTab} />
        </div>
        {tab === "Overview" || tab === "Paths" ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <caption className="sr-only">Device path, real vision, and result</caption>
              <thead>
                <tr className="text-xs uppercase text-muted">
                  <th className="py-2">Device</th>
                  <th>Path</th>
                  <th>Real Vision</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                <DeviceRow name="Go2 PRO" path="DOG · ETHERNET" vision="UNKNOWN" result="PASS" visionTone="warn" resultTone="ok" />
                <DeviceRow name="Tello EDU" path="DRONE · WI-FI" vision="PASS" result="PASS" visionTone="ok" resultTone="ok" />
                <DeviceRow name="Raspberry Pi" path="PI · USB" vision="PASS" result="PASS" visionTone="ok" resultTone="ok" />
                <DeviceRow name="xAI Grok" path="UPLINK · UNKNOWN" vision="UNKNOWN" result="UNAVAILABLE" visionTone="warn" resultTone="bad" />
              </tbody>
            </table>
          </div>
        ) : null}
        {tab === "Issues" ? (
          <ul className="mt-3 space-y-1 text-sm text-bad">
            <li>Router unavailable.</li>
            <li>Wi-Fi setting does not repair it.</li>
            <li>xAI Grok uplink unavailable.</li>
            <li>Directional control unverified.</li>
          </ul>
        ) : null}
        {tab === "Capability Matrix" ? <Matrix /> : null}
      </Card>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Product name="Go2 PRO" status="PASS" tone="ok" art={<DogMark />} lines={["Quadruped mobility", "Onboard vision stream"]} />
        <Product name="Tello EDU" status="PASS" tone="ok" art={<DroneMark />} lines={["Aerial capture (local)", "Mission execution (rehearsal)"]} />
        <Product name="Raspberry Pi" status="PASS" tone="ok" art={<PiMark />} lines={["Compute on dog (USB)", "Vision processing / bridge"]} />
        <Product name="xAI Grok" status="UNAVAILABLE" tone="bad" art={<XaiMark />} lines={["AI reasoning & analysis", "Mission context understanding"]} />
      </div>
      {tab !== "Capability Matrix" ? <Matrix /> : null}
      <div className="grid gap-3 lg:grid-cols-2">
        <Notice tone="bad" title="Blockers (Current)">
          <ul className="list-disc pl-4">
            <li>Router unavailable.</li>
            <li>Wi-Fi setting does not repair it.</li>
            <li>xAI Grok uplink unavailable.</li>
            <li>Directional control unverified.</li>
          </ul>
        </Notice>
        <Card>
          <CardTitle icon={<Shield className="h-4 w-4" />} title="Admitted-Capability Summary" />
          <ul className="space-y-2 text-sm">
            <li><Pill tone="ok">Verified</Pill> Local device access and basic operation.</li>
            <li><Pill tone="warn">Unverified</Pill> End-to-end directional control not confirmed.</li>
            <li><Pill tone="sim">Simulated</Pill> Rehearsal and analysis only.</li>
          </ul>
          <p className="mt-3 text-sm font-semibold">No automatic handover.</p>
        </Card>
      </div>
    </div>
  );
}

function Matrix() {
  return (
    <Card>
      <CardTitle title="Capability & Path Matrix" extra={<span className="flex gap-2"><Pill tone="ok">PASS</Pill><Pill tone="warn">UNKNOWN</Pill><Pill tone="bad">UNAVAILABLE</Pill><Pill tone="sim">SIMULATED</Pill></span>} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <caption className="sr-only">Capability and path matrix</caption>
          <thead>
            <tr className="text-xs text-muted">
              <th className="py-2">Capability</th>
              <th>Go2 PRO · DOG · ETHERNET</th>
              <th>Tello EDU · DRONE · WI-FI</th>
              <th>Raspberry Pi · PI · USB</th>
              <th>xAI Grok · UPLINK · UNKNOWN</th>
            </tr>
          </thead>
          <tbody>
            {MATRIX.map((row) => (
              <tr key={row.capability} className="border-t border-line">
                <th scope="row" className="py-2 font-medium">{row.capability}</th>
                {row.cells.map((cell, index) => (
                  <td key={`${row.capability}-${index}`} className="py-2">
                    <Pill tone={cell.tone}>{cell.label}</Pill>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function FixtureView() {
  return (
    <Card>
      <Notice tone="info" title="SOFTWARE SIMULATION ONLY · NOT HARDWARE ACCEPTANCE">
        UI mockup for a mission control case study. All values are mock data for UI illustration only.
      </Notice>
      <h2 className="mt-3 font-display text-xl font-semibold">Operational Readiness Matrix</h2>
      <p className="text-xs font-semibold text-blue">SIMULATION / ILLUSTRATIVE FIXTURE</p>
      <table className="mt-3 w-full text-left text-sm">
        <caption className="sr-only">Operational readiness fixture</caption>
        <thead>
          <tr className="text-xs uppercase text-muted">
            <th className="py-2">#</th>
            <th>Device</th>
            <th>Configuration / Interface</th>
            <th>Operational State</th>
          </tr>
        </thead>
        <tbody>
          <tr><td>1</td><td>Go2 PRO</td><td>dog Ethernet configured</td><td><Pill tone="sim">SIMULATED</Pill></td></tr>
          <tr><td>2</td><td>Tello EDU</td><td>Wi-Fi AP</td><td><Pill tone="sim">SIMULATED</Pill></td></tr>
          <tr><td>3</td><td>Raspberry Pi on dog</td><td>USB path</td><td><Pill tone="sim">SIMULATED</Pill></td></tr>
          <tr><td>4</td><td>real vision uplink</td><td>internet</td><td><Pill tone="warn">UNKNOWN</Pill></td></tr>
        </tbody>
      </table>
      <div className="mt-3">
        <Notice tone="bad" title="Blockers (Prevent Test Execution)">
          <p>B1 directional drone control · UNKNOWN · WITHHELD</p>
          <p>B2 back enclosure router · UNAVAILABLE</p>
        </Notice>
      </div>
    </Card>
  );
}

function DeviceRow({ name, path, vision, result, visionTone, resultTone }: { name: string; path: string; vision: string; result: string; visionTone: "ok" | "warn"; resultTone: "ok" | "bad" }) {
  return (
    <tr className="border-t border-line">
      <th scope="row" className="py-2 font-medium">{name}</th>
      <td className="font-mono text-xs">{path}</td>
      <td><Pill tone={visionTone}>{vision}</Pill></td>
      <td><Pill tone={resultTone}>{result}</Pill></td>
    </tr>
  );
}

function Product({ name, status, tone, art, lines }: { name: string; status: string; tone: "ok" | "bad"; art: ReactNode; lines: string[] }) {
  return (
    <Card>
      <div className="flex items-center justify-between">
        {art}
        <Pill tone={tone}>{status}</Pill>
      </div>
      <h3 className="mt-2 font-semibold">{name}</h3>
      <ul className="mt-2 space-y-1 text-sm text-muted">
        {lines.map((line) => (
          <li key={line}>✓ {line}</li>
        ))}
      </ul>
    </Card>
  );
}
