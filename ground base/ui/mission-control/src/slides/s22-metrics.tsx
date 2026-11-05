"use client";

import { useState } from "react";
import { Clock, Database, Shield, Timer } from "lucide-react";
import { Card, CardTitle, Notice, Pill, Segmented, SlidePage } from "@/components/console/frame";

const INTERVALS = [
  ["Connect", "Run start → link established", "2.314 s", "Comm log · Tr (rehearsal, monotonic)"],
  ["Drone acquisition", "Drone first seen → locked", "6.783 s", "Vision log · Tr (rehearsal, monotonic)"],
  ["Dog acquisition", "Dog first seen → locked", "4.218 s", "Vision log · Tr (rehearsal, monotonic)"],
  ["Goal", "Goal issued → goal reached", "18.427 s", "Mission journal · Tr (rehearsal, monotonic)"],
  ["Landing latency · unknown", "— / unknown", "— / unknown", "Journal · Tr · Reason · no verified landing event"],
  ["Dropped frames · unknown", "— / unknown", "— / unknown", "Video log · Tr · Reason · no acquisition timestamp"],
];

const COUNTS = [
  ["Commands sent", "47", "Command log · Tr"],
  ["State transitions", "12", "Mission journal · Tr"],
  ["Vision detections", "864", "Vision log · Tr"],
  ["Beacon resets", "2", "Beacon log · Tr"],
];

const UNKNOWN_ROWS = [
  ["Connect", "—", "Journal not supplied"],
  ["Drone acquisition", "—", "Journal not supplied"],
  ["Dog acquisition", "—", "Journal not supplied"],
  ["Goal latency", "Unknown", "No timestamp pair"],
  ["Landing latency", "Unknown", "No verified landing event"],
  ["Dropped frames", "Unknown", "Journal not supplied"],
  ["Beacon resets", "Unknown", "Journal not supplied"],
];

export function Slide22() {
  const [view, setView] = useState("Measured rehearsal");
  return (
    <SlidePage
      id="22"
      active="runs"
      topbar={{ mode: "SIMULATION", note: "Run: M-0247 (Rehearsal) · Epoch 12" }}
      chips={[
        { title: "Run metrics", body: "Measured phase intervals, counts, and data quality for a single run.", icon: <Timer className="h-5 w-5" /> },
        { title: "Reproducible", body: "Explicit computation, source, and clock basis for every metric.", icon: <Clock className="h-5 w-5" /> },
        { title: "Honest data", body: "Includes unknowns with reasons (for example no landing event).", icon: <Database className="h-5 w-5" /> },
        { title: "Simulation", body: "Rehearsal (SIMULATION) with deterministic computation.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principlesTitle="Key results & computation"
      principlesNote="Reproducible computation, data sources, and explicit handling of unknowns."
      principles={[
        { index: "01", title: "Reproducible computation", body: "Goal latency = t_goal − t_goal_issued = 18.427 s. Drone acquisition = t_drone_lock − t_drone_first = 6.783 s. Dog acquisition = t_dog_lock − t_dog_first = 4.218 s. Connect = t_link − t_run_start = 2.314 s." },
        { index: "02", title: "Data provenance", body: "Source · rehearsal clock. Multi-sensor log (vision, telemetry, journal). Clock basis: Tr (rehearsal, monotonic). Run: M-0247 · Epoch 12. Mode: SIMULATION (rehearsal)." },
        { index: "03", title: "Unknown ≠ zero", body: "Unmeasured values are reported as “— / unknown” with an explicit reason. They are not plotted or treated as zero." },
        { index: "04", title: "Missing data (reasons)", body: "Landing latency · unknown — Reason · no verified landing event. Dropped frames · unknown — Reason · no acquisition timestamp. Other fields · — / unknown — Reason · empty journal, when the journal is not supplied." },
      ]}
    >
      <div className="mb-3">
        <Segmented label="Metrics presentation" options={["Measured rehearsal", "Journal not supplied"]} value={view} onChange={setView} />
      </div>
      {view === "Measured rehearsal" ? <Measured /> : <UnknownJournal />}
    </SlidePage>
  );
}

function Measured() {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-display text-2xl font-semibold">Run metrics <Pill tone="sim">SIMULATION</Pill></h2>
          <p className="text-sm text-muted">Run M-0247 · rehearsal · reproducible metrics, sources, and clock basis.</p>
        </div>
        <Pill tone="info">Reproducible computation</Pill>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-sm">
        <Pill tone="ok">Run state · Completed (rehearsal)</Pill>
        <Pill tone="info">Source · rehearsal clock</Pill>
        <Pill tone="neutral">Clock basis · Tr (rehearsal, monotonic)</Pill>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardTitle title="Measured intervals" />
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Measured intervals</caption>
            <thead>
              <tr className="text-xs uppercase text-muted"><th className="py-2">Phase (from → to)</th><th>Interval (s)</th><th>Source · rehearsal clock</th></tr>
            </thead>
            <tbody>
              {INTERVALS.map((row) => (
                <tr key={row[0]} className="border-t border-line">
                  <th scope="row" className="py-2">
                    <span className="block">{row[0]}</span>
                    <span className="text-xs font-normal text-muted">{row[1]}</span>
                  </th>
                  <td className="font-mono">{row[2]}</td>
                  <td className="text-xs">{row[3]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <div className="space-y-3">
          <Card>
            <CardTitle title="Run timeline (measured + unknown)" />
            <ol className="space-y-1 text-sm">
              <li>Connect 2.314 s</li>
              <li>Drone acquisition 6.783 s</li>
              <li>Dog acquisition 4.218 s</li>
              <li>Goal 18.427 s</li>
              <li>Landing — / unknown</li>
            </ol>
          </Card>
          <Card>
            <CardTitle title="Operation counts" />
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Operation counts</caption>
              <thead><tr className="text-xs text-muted"><th>Operation</th><th>Count</th><th>Source</th></tr></thead>
              <tbody>
                {COUNTS.map((row) => (
                  <tr key={row[0]} className="border-t border-line"><td className="py-1">{row[0]}</td><td className="font-mono">{row[1]}</td><td className="text-xs">{row[2]}</td></tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>
      <div className="mt-3">
        <Notice tone="warn" title="Unknown ≠ zero">
          Unmeasured values are reported as “— / unknown” with an explicit reason (for example no landing event, no acquisition timestamp, empty journal). They are not plotted or treated as zero.
        </Notice>
      </div>
    </Card>
  );
}

function UnknownJournal() {
  return (
    <Card>
      <Notice tone="info" title="ILLUSTRATIVE UI · NO MEASURED HARDWARE RUN">
        This is a simulation / illustrative fixture for a case study. No telemetry, no physical execution, and no acceptance results.
      </Notice>
      <h2 className="mt-3 font-display text-xl font-semibold">Run Metrics & Performance <Pill tone="sim">SIMULATION</Pill></h2>
      <p className="text-sm text-muted">Rehearsal run metrics summary (simulation). Data not provided; values are unknown.</p>
      <p className="mt-2 text-sm"><Pill tone="neutral">Rehearsal Report · Partial (No Data)</Pill></p>
      <table className="mt-3 w-full text-left text-sm">
        <caption className="sr-only">Unknown metrics</caption>
        <thead><tr className="text-xs uppercase text-muted"><th className="py-2">Measurement</th><th>Value (Run)</th><th>Reason / Data Availability</th></tr></thead>
        <tbody>
          {UNKNOWN_ROWS.map((row) => (
            <tr key={row[0]} className="border-t border-line"><th scope="row" className="py-2 font-medium">{row[0]}</th><td className="font-mono">{row[1]}</td><td>{row[2]}</td></tr>
          ))}
        </tbody>
      </table>
      <Card className="mt-3">
        <CardTitle title="Metric Trend (Rehearsal)" />
        <p className="text-sm font-semibold">No measured series</p>
        <p className="text-sm text-muted">No time series available. Journal not supplied. Unknown is not zero.</p>
      </Card>
      <div className="mt-3 grid gap-2 sm:grid-cols-3 text-sm">
        <p>Source · Unknown · Reason: journal not supplied.</p>
        <p>Clock · Unknown · Reason: no timestamp source.</p>
        <p>Provenance · Unknown · Reason: data not provided.</p>
      </div>
      <Card className="mt-3">
        <CardTitle title="Rehearsal Report (Partial)" />
        <p className="text-sm"><Pill tone="warn">Partial (No Data)</Pill></p>
        <ul className="mt-2 list-disc pl-5 text-sm text-muted">
          <li>No run journal supplied.</li>
          <li>No measured telemetry.</li>
          <li>No verified landing event.</li>
          <li>Metrics are unknown, not zero.</li>
        </ul>
      </Card>
    </Card>
  );
}
