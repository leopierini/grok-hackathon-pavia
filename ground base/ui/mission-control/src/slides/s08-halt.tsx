"use client";

import { useState } from "react";
import { Camera, Link2, Shield, Timer } from "lucide-react";
import { Card, CardTitle, CheckRow, Flow, Pill, SlidePage, StepRail, Timeline } from "@/components/console/frame";
import { SurveyScene } from "@/components/console/scenes";
import { HaltButton } from "@/components/ui";
import { useHaltAction } from "@/components/console/frame";

const CHECKS = [
  "Confirm backend safe recovery.",
  "Confirm disarmed state.",
  "Complete operation cleanup (logs, artifacts, locks).",
  "Review evidence and fault context.",
];

export function Slide08() {
  const halt = useHaltAction();
  const [checked, setChecked] = useState<boolean[]>([false, false, false, false]);
  const ready = checked.every(Boolean);
  return (
    <SlidePage
      id="08"
      active="mission"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Priority safety path", body: "HALT, cleanup, and safe recovery flow.", icon: <Shield className="h-5 w-5" /> },
        { title: "HALT LATCHED", body: "Persistent until backend confirms safe recovery.", icon: <Shield className="h-5 w-5" /> },
        { title: "Lease expired ≠ stopped", body: "Control lease expired only; does not confirm a physical stop.", icon: <Link2 className="h-5 w-5" /> },
        { title: "Late AI result cannot clear halt", body: "Out-of-order or late AI results are ignored for safety.", icon: <Timer className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Recovery required", body: "Operation remains in recovery-required state (unknown landing)." },
        { index: "02", title: "Lease expired ≠ stopped", body: "Control lease expired only; no confirmation of a physical stop or landing." },
        { index: "03", title: "Late AI result cannot clear halt", body: "Out-of-order or late AI results are ignored and cannot clear the HALT." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Mission</p>
            <h2 className="font-display text-2xl font-semibold">Site Survey – Sector A <Pill tone="sim">SIMULATION</Pill></h2>
            <p className="text-sm text-muted">Rehearsal mission (offline). HALT latched; recovery required.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Switch to Live</button>
            <HaltButton onHalt={halt} />
          </div>
        </div>
        <div className="mt-4">
          <StepRail
            steps={[
              { label: "Plan", state: "done" },
              { label: "Initialize", state: "done" },
              { label: "Halt", state: "halt" },
              { label: "Cleanup", state: "todo" },
              { label: "Recover", state: "todo" },
              { label: "Reset", state: "todo" },
            ]}
          />
        </div>
        <div className="mt-4 grid gap-3 xl:grid-cols-3">
          <Card>
            <CardTitle title="Devices (2)" />
            <p className="text-sm font-semibold">Go2 PRO <Pill tone="bad">HALT</Pill></p>
            <p className="text-xs text-muted">Unitree Go2 PRO · Field robot</p>
            <p className="mt-3 text-sm font-semibold">Tello EDU <Pill tone="neutral">idle</Pill></p>
            <p className="text-xs text-muted">Tello EDU · Aerial drone</p>
          </Card>
          <Card>
            <CardTitle icon={<Camera className="h-4 w-4" />} title="Vision · Evidence Preview" extra={<Pill tone="sim">SIM</Pill>} />
            <SurveyScene />
          </Card>
          <Card>
            <CardTitle title="Activity Timeline" />
            <Timeline
              items={[
                { label: "HALT request", time: "10:24", state: "done" },
                { label: "Accepted · yes", time: "10:25", state: "done" },
                { label: "Delivered · unknown", time: "10:27", state: "current" },
                { label: "Verified stop · unknown", time: "—", state: "todo" },
                { label: "Pending cleanup", time: "—", state: "todo" },
                { label: "Recovery required", time: "—", state: "todo" },
              ]}
            />
          </Card>
        </div>
        <ul className="mt-3 flex flex-wrap gap-2 text-xs font-semibold">
          <li><Pill tone="bad">HALT LATCHED</Pill></li>
          <li><Pill tone="warn">Cleanup · Pending</Pill></li>
          <li><Pill tone="bad">Link-loss</Pill></li>
          <li><Pill tone="warn">Lease expired</Pill></li>
          <li><Pill tone="neutral">Reset unavailable</Pill></li>
        </ul>
        <p className="mt-2 text-xs text-muted">Reset requires backend safe recovery and disarmed state.</p>
      </Card>
      <Card className="mt-3">
        <CardTitle title="Halt flow timeline" extra={<span className="text-xs text-muted">Request to verified stop (status and delivery).</span>} />
        <Flow
          steps={[
            { title: "Request", tone: "info" },
            { title: "Accepted · yes", tone: "ok" },
            { title: "Delivered · unknown", tone: "warn" },
            { title: "Verified stop · unknown", tone: "warn" },
          ]}
        />
      </Card>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Card>
          <CardTitle title="State & fault" />
          <ul className="space-y-2 text-sm">
            <li className="flex justify-between"><span>Link-loss · Control link not available.</span><Pill tone="bad">Link-loss</Pill></li>
            <li className="flex justify-between"><span>Lease · Control lease expired.</span><Pill tone="warn">Lease expired ≠ stopped</Pill></li>
            <li className="flex justify-between"><span>Landing · Landing state unknown.</span><Pill tone="bad">Recovery required</Pill></li>
          </ul>
        </Card>
        <Card>
          <CardTitle title="Recovery checklist" />
          <ul className="space-y-2">
            {CHECKS.map((item, index) => (
              <li key={item}>
                <label className="flex min-h-11 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={checked[index]}
                    onChange={(event) => setChecked((current) => current.map((value, itemIndex) => (itemIndex === index ? event.target.checked : value)))}
                  />
                  {item}
                </label>
              </li>
            ))}
          </ul>
          <button type="button" className="mt-2 min-h-11 rounded-xl border border-line px-3 text-sm" disabled={!ready}>
            {ready ? "Reset available after backend confirmation" : "Reset unavailable"}
          </button>
        </Card>
      </div>
      <ul className="sr-only">
        <CheckRow label="HALT latched" />
      </ul>
    </SlidePage>
  );
}
