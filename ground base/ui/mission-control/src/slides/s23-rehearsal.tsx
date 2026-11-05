"use client";

import { useState } from "react";
import { AlertTriangle, FileText, FlaskConical, Shield } from "lucide-react";
import { Card, CardTitle, Notice, Pill, SlidePage } from "@/components/console/frame";

const SEQUENCE = [
  ["1", "Initialize", "Load scenario, allocate resources.", "00:00", true],
  ["2", "Takeoff (drone)", "Start and stabilize at mission altitude.", "00:18", true],
  ["3", "Site survey", "Capture coverage and evidence.", "00:46", true],
  ["4", "Ground traverse", "Go2 PRO to waypoint 1–3.", "01:20", false],
  ["5", "Collect evidence", "Vision capture and storage.", "—", false],
  ["6", "Review & finalize", "Generate report and artifacts.", "—", false],
];

const FAULTS = [
  ["Stale frame", "Use an outdated frame (for example frame −1)."],
  ["Delayed AI", "Add inference latency (for example +1.5 s)."],
  ["Controlled motion unavailable", "Disable controlled motion (hold/stop)."],
  ["Moving beacon / noisy RSSI", "Vary beacon and add RSSI noise."],
  ["Blocked planner", "Prevent route planning (returns block)."],
  ["Wrong target", "Provide an incorrect target (distractor)."],
  ["Missing proximity evidence", "Omit required proximity evidence."],
  ["Link loss", "Simulate comms loss (for example 10–30 s)."],
];

const ARTIFACTS = [
  ["rehearsal_report_happy_path.pdf", "1.4 MB"],
  ["run_log.json", "86 KB"],
  ["evidence_preview.zip", "42 MB"],
  ["metrics.csv", "120 KB"],
];

const BRIEF = ["Site check", "Verify drone teammate", "4 m proposal (optional)", "Arm supervised session", "Monitor", "HALT"];

export function Slide23() {
  const [scenario, setScenario] = useState("happy_path");
  const [faults, setFaults] = useState<Record<string, boolean>>({});
  const [started, setStarted] = useState(false);
  const [report, setReport] = useState(false);
  return (
    <SlidePage
      id="23"
      active="rehearsal"
      topbar={{ mode: "SIMULATION", note: "Rehearsal Workspace · Offline (No Field Devices)" }}
      chips={[
        { title: "Offline rehearsal", body: "Run end-to-end scenarios in simulation with controllable conditions.", icon: <FlaskConical className="h-5 w-5" /> },
        { title: "Fault injection", body: "Systematic fault cases to validate resilience and handling.", icon: <AlertTriangle className="h-5 w-5" /> },
        { title: "Operator runbook", body: "A concise, time-boxed procedure for safe, repeatable operation.", icon: <FileText className="h-5 w-5" /> },
        { title: "Evidence & report", body: "Save detailed artifacts for review, analysis, and traceability.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Goal ≠ landing", body: "Goal is mission success (for example coverage, evidence, state transition), which is different from landing." },
        { index: "02", title: "Simulation only", body: "Fault injection is simulation only. It is not physical acceptance." },
        { index: "03", title: "Operator brief · 2 min", body: "Confirm site, area bounds, and constraints. Confirm the drone teammate is ready. The 4 m proposal is optional and venue-approved. Arm and start in supervised simulation. Monitor state, evidence, and progress. Stop immediately on any unsafe or unexpected condition." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-2xl font-semibold">Rehearsal</h2>
          <div className="flex flex-wrap gap-2">
            <label className="text-sm">
              Scenario
              <select aria-label="Scenario" className="ml-2 min-h-11 rounded-xl border border-line bg-surface px-2" value={scenario} onChange={(event) => setScenario(event.target.value)}>
                <option value="happy_path">happy_path</option>
                <option value="link_loss">link_loss</option>
                <option value="stale_frame">stale_frame</option>
              </select>
            </label>
            <button type="button" className="min-h-11 rounded-xl bg-blue px-3 text-sm font-semibold text-white" onClick={() => setStarted(true)}>Start rehearsal</button>
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm" onClick={() => setReport(true)}>Inspect report</button>
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm" onClick={() => { setStarted(false); setFaults({}); setReport(false); }}>Reset</button>
          </div>
        </div>
        {started ? <p className="mt-2 text-sm text-info">Rehearsal {scenario} is running in simulation. No field device is connected.</p> : null}
        {report ? <p className="mt-2 text-sm">Report preview: rehearsal_report_{scenario}.pdf · partial until review and finalize.</p> : null}
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle title="Preflight summary" />
            <ul className="space-y-1 text-sm">
              <li>Scenario: {scenario}</li>
              <li>Map & site: Site A (sim)</li>
              <li>Devices: Go2 PRO (sim), Tello EDU (sim)</li>
              <li>Initial state: IDLE / ready</li>
              <li>Injection: {Object.values(faults).some(Boolean) ? "selected faults" : "none (baseline)"}</li>
            </ul>
          </Card>
          <Card>
            <CardTitle title="Event sequence (ordered)" />
            <ol className="space-y-2 text-sm">
              {SEQUENCE.map((step) => (
                <li key={String(step[0])} className="flex items-start justify-between gap-2">
                  <span><span className="font-semibold">{step[0]}. {step[1]}</span><span className="block text-xs text-muted">{step[2]}</span></span>
                  <span className="font-mono text-xs">{step[4] && started ? step[3] : step[3]} {step[4] ? "✓" : ""}</span>
                </li>
              ))}
            </ol>
          </Card>
        </div>
        <Card className="mt-3">
          <CardTitle title="Saved report artifacts" />
          <ul className="space-y-1 text-sm">
            {ARTIFACTS.map((item) => (
              <li key={item[0]} className="flex justify-between font-mono text-xs"><span>{item[0]}</span><span>{item[1]}</span></li>
            ))}
          </ul>
        </Card>
      </Card>
      <Card className="mt-3">
        <CardTitle title="Fault injection" extra={<Pill tone="sim">SIMULATION ONLY</Pill>} />
        <p className="text-sm text-muted">Not physical acceptance.</p>
        <ul className="mt-3 grid gap-2 md:grid-cols-2">
          {FAULTS.map((fault) => (
            <li key={fault[0]}>
              <label className="flex min-h-11 items-start gap-2 rounded-xl border border-line px-3 py-2 text-sm">
                <input type="checkbox" checked={Boolean(faults[fault[0]])} onChange={(event) => setFaults((current) => ({ ...current, [fault[0]]: event.target.checked }))} />
                <span><span className="font-semibold">{fault[0]}</span><span className="block text-xs text-muted">{fault[1]}</span></span>
              </label>
            </li>
          ))}
          <li>
            <label className="flex min-h-11 items-start gap-2 rounded-xl border border-line px-3 py-2 text-sm">
              <input type="checkbox" checked={Boolean(faults["Unknown landing"])} onChange={(event) => setFaults((current) => ({ ...current, "Unknown landing": event.target.checked }))} />
              <span><span className="font-semibold">Unknown landing</span><span className="block text-xs text-muted">Landing area not recognized / outside known regions.</span></span>
            </label>
          </li>
        </ul>
      </Card>
      <Card className="mt-3">
        <CardTitle title="Operator brief · 2 min" extra={<span className="text-xs text-muted">A concise, time-boxed runbook for the rehearsal (simulation).</span>} />
        <ol className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
          {BRIEF.map((step, index) => (
            <li key={step} className="rounded-xl border border-line p-3 text-sm">
              <span className="font-bold text-blue">{index + 1}</span>
              <p className="font-semibold">{step}</p>
            </li>
          ))}
        </ol>
        <div className="mt-3">
          <Notice tone="info" title="Goal ≠ landing">
            Goal is mission success (coverage, evidence, state transition), which is different from landing.
          </Notice>
        </div>
      </Card>
    </SlidePage>
  );
}
