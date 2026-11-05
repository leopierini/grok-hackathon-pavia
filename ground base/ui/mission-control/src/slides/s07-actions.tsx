"use client";

import { useState } from "react";
import { Camera, RefreshCw, Shield, Zap } from "lucide-react";
import { Card, CardTitle, Notice, Pill, SlidePage } from "@/components/console/frame";
import { SurveyScene } from "@/components/console/scenes";
import { HaltButton } from "@/components/ui";
import { useHaltAction } from "@/components/console/frame";

const ACTIONS = [
  { action: "State", status: "ENABLED", arm: "ENABLED", start: "PENDING", supervised: "DISABLED", halt: "ENABLED", reset: "DISABLED", quit: "ENABLED" },
];

const REASONS = ["—", "—", "Awaiting confirmation", "Arm required", "—", "Not in run (idle)", "—"];

export function Slide07() {
  const halt = useHaltAction();
  const [open, setOpen] = useState(true);
  const [refreshed, setRefreshed] = useState(false);
  return (
    <SlidePage
      id="07"
      active="mission"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Scoped confirmation", body: "Arm, Start, Supervised, and Reset require a scoped confirm (mission, epoch, stage).", icon: <Shield className="h-5 w-5" /> },
        { title: "Ground recheck", body: "Actions rechecked by Ground before execution.", icon: <Shield className="h-5 w-5" /> },
        { title: "Immediate Halt", body: "Halt submits without confirmation, independent of pending AI requests.", icon: <Zap className="h-5 w-5" /> },
        { title: "Explicit reasons", body: "Clear enabled and disabled reasons and stale-epoch rejection.", icon: <RefreshCw className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Scoped confirmations", body: "Arm, Start, Supervised, and Reset require confirmation. Scope: mission, epoch, stage (for example M-0427, Epoch 12, SCOUT). Actions are rechecked by Ground before execution." },
        { index: "02", title: "Action states & reasons", body: "Status shows availability at a glance. Enabled means the action can be requested. Disabled carries a reason such as Arm required or Not in run. Start is shown as Pending while awaiting confirmation." },
        { index: "03", title: "Stale epoch rejection", body: "Prevents execution on an outdated context. Example: stale action rejected because the epoch changed to 13. Refresh and confirm again with the current epoch." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Mission</p>
            <h2 className="font-display text-2xl font-semibold">Site Survey — Sector A <Pill tone="sim">SIMULATION</Pill></h2>
            <p className="text-sm text-muted">Mission M-0427 · Epoch 12 · Stage SCOUT</p>
          </div>
          <div className="flex gap-2">
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm" onClick={() => setRefreshed(true)}>
              Switch to Live
            </button>
            <HaltButton onHalt={halt} />
          </div>
        </div>
        {refreshed ? <p className="mt-2 text-sm text-warn">Live transport is refused. Epoch 12 remains the displayed rehearsal context.</p> : null}
        <div className="mt-3 flex flex-wrap gap-2">
          {["Arm", "Start", "Supervised", "Reset"].map((label) => (
            <button key={label} type="button" className="min-h-11 rounded-full border border-line px-4 text-sm font-semibold" onClick={() => setOpen(true)}>
              {label}
            </button>
          ))}
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[0.7fr_1fr_0.9fr]">
          <Card>
            <CardTitle title="Status" />
            <dl className="space-y-2 text-sm">
              <Line k="Mission" v="M-0427" />
              <Line k="Epoch" v="12" />
              <Line k="Stage" v="SCOUT" />
              <Line k="Mode" v="SIMULATION" />
              <Line k="Arm" v="UNARMED" />
              <Line k="Run" v="IDLE" />
            </dl>
          </Card>
          <Card>
            <CardTitle icon={<Camera className="h-4 w-4" />} title="Vision · Site View" extra={<Pill tone="sim">SIM</Pill>} />
            <SurveyScene />
          </Card>
          {open ? (
            <Card>
              <div className="flex items-center justify-between">
                <h3 className="font-display text-lg font-semibold">Confirm Start</h3>
                <button type="button" className="min-h-11 min-w-11" aria-label="Close confirm" onClick={() => setOpen(false)}>×</button>
              </div>
              <p className="text-sm text-info">Actions rechecked by Ground</p>
              <dl className="mt-3 space-y-1 text-sm">
                <Line k="Mission" v="M-0427" />
                <Line k="Epoch" v="12" />
                <Line k="Stage" v="SCOUT" />
                <Line k="Action" v="Start" />
              </dl>
              <div className="mt-3">
                <Notice tone="warn" title="Stale action rejected">
                  Epoch changed to 13. Refresh and confirm again.
                </Notice>
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm" onClick={() => setOpen(false)}>Cancel</button>
                <button type="button" className="min-h-11 rounded-xl bg-surface-2 px-3 text-sm font-semibold" disabled>Confirm Start</button>
              </div>
            </Card>
          ) : (
            <Card>
              <p className="text-sm text-muted">Confirmation is closed. Arm, Start, Supervised, and Reset open a scoped confirm.</p>
            </Card>
          )}
        </div>
      </Card>
      <Card className="mt-3">
        <CardTitle title="Action availability & reasons" extra={<span className="text-xs text-muted">Command set, enablement, and disabled reasons (current context: M-0427 / Epoch 12 / SCOUT).</span>} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <caption className="sr-only">Action availability</caption>
            <thead>
              <tr className="text-xs uppercase text-muted">
                {["Action", "Status", "Arm", "Start", "Supervised", "Halt", "Reset", "Quit"].map((header) => (
                  <th key={header} className="py-2">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ACTIONS.map((row) => (
                <tr key={row.action} className="border-t border-line">
                  <th scope="row">{row.action}</th>
                  {[row.status, row.arm, row.start, row.supervised, row.halt, row.reset, row.quit].map((cell, index) => (
                    <td key={`${row.action}-${index}`} className="py-2"><StateCell value={cell} /></td>
                  ))}
                </tr>
              ))}
              <tr className="border-t border-line text-xs text-muted">
                <th scope="row">Reason (if disabled)</th>
                {REASONS.map((reason, index) => (
                  <td key={`${reason}-${index}`} className="py-2">{reason}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </SlidePage>
  );
}

function Line({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{k}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );
}

function StateCell({ value }: { value: string }) {
  const tone = value === "ENABLED" ? "ok" : value === "PENDING" ? "info" : value === "DISABLED" ? "neutral" : "neutral";
  return <Pill tone={tone}>{value}</Pill>;
}
