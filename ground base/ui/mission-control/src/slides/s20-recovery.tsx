"use client";

import { useState } from "react";
import { Lock, Shield, Target } from "lucide-react";
import { Card, CardTitle, Notice, Pill, SlidePage, StepRail } from "@/components/console/frame";
import { SurveyScene } from "@/components/console/scenes";

const CHECKS = ["Identify fault cause", "Execute recovery actions", "Verify recovery (required)", "Clear fault state", "Reset to operational"];

export function Slide20() {
  const [done, setDone] = useState([true, true, false, false, false]);
  const [verified, setVerified] = useState(false);
  return (
    <SlidePage
      id="20"
      active="mission"
      topbar={{ mode: "SIMULATED", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Goal ≠ landing", body: "Mission goal can be reached even if landing outcome is unknown.", icon: <Target className="h-5 w-5" /> },
        { title: "Landing is a separate result", body: "Landing has its own command and result (landed / unknown).", icon: <Target className="h-5 w-5" /> },
        { title: "Recovery required", body: "A fault persists and recovery must be executed and verified.", icon: <Shield className="h-5 w-5" /> },
        { title: "No new ordinary run", body: "Ordinary mission run is blocked until recovery is verified.", icon: <Lock className="h-5 w-5" /> },
      ]}
      principlesTitle="Key Takeaways"
      principlesNote="Outcomes, separation of results, and run-control rules."
      principles={[
        { index: "01", title: "Demo goal · REACHED", body: "The mission goal (for example site survey) is completed and validated." },
        { index: "02", title: "Landing · UNKNOWN", body: "Landing has its own result. Here, the outcome is unknown, not confirmed as landed." },
        { index: "03", title: "Recovery · REQUIRED", body: "A fault persists and recovery is required. The system remains in a recovery-required state until verification." },
        { index: "04", title: "No new ordinary run", body: "A new ordinary mission run cannot be started. Reset to operational requires verified recovery." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Mission Result</p>
            <h2 className="font-display text-2xl font-semibold">Site Survey — Sector A <Pill tone="sim">SIMULATED</Pill></h2>
            <p className="text-sm text-muted">Mission M-0247 · Mode: SIMULATION · Epoch 12</p>
          </div>
          <div className="flex gap-2">
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Run History</button>
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm" disabled>New Run</button>
          </div>
        </div>
        <div className="mt-4">
          <StepRail steps={[{ label: "Plan", state: "done" }, { label: "Initialize", state: "done" }, { label: "Execute", state: "done" }, { label: "Result", state: "current" }, { label: "Recover", state: "todo" }, { label: "Reset", state: "todo" }]} />
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <Card>
            <CardTitle title="Outcome Summary" />
            <p><Pill tone="ok">Demo goal · REACHED</Pill></p>
            <p className="mt-2"><Pill tone="warn">Landing · UNKNOWN</Pill></p>
            <p className="mt-2"><Pill tone="bad">Recovery · REQUIRED</Pill></p>
          </Card>
          <Card>
            <CardTitle title="Mission View (Final)" extra={<Pill tone="sim">SIM</Pill>} />
            <SurveyScene />
          </Card>
          <Card>
            <CardTitle title="Run Status" />
            <ul className="space-y-2 text-sm">
              <li>Demo goal reached · 10:27</li>
              <li>Landing · unknown · 10:30</li>
              <li>Recovery · required (fault) · 10:30</li>
              <li className="font-semibold text-bad">Ordinary run · blocked</li>
            </ul>
            <p className="mt-2 text-xs text-muted">Reset requires verified recovery.</p>
          </Card>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-3">
          <Card>
            <CardTitle title="Landing Command / Result" />
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Command Landing</button>
            <label className="mt-2 flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" /> Abort Landing
            </label>
            <p className="mt-2 text-sm"><Pill tone="warn">Landing · UNKNOWN</Pill></p>
            <p className="text-xs text-muted">Landing outcome is not confirmed (for example loss of state, view, or contact).</p>
          </Card>
          <Card>
            <CardTitle title="Recovery Checklist" />
            <ul className="space-y-2">
              {CHECKS.map((item, index) => (
                <li key={item}>
                  <label className="flex min-h-11 items-center gap-2 text-sm">
                    <input type="checkbox" checked={index === 2 ? verified : done[index]} onChange={(event) => {
                      if (index === 2) setVerified(event.target.checked);
                      else setDone((current) => current.map((value, itemIndex) => itemIndex === index ? event.target.checked : value));
                    }} />
                    {index + 1}. {item}
                  </label>
                </li>
              ))}
            </ul>
            <button type="button" className="min-h-11 rounded-xl bg-blue px-3 text-sm font-semibold text-white" onClick={() => setVerified(true)}>Verify</button>
          </Card>
          <Card>
            <CardTitle title="Next Action" />
            <Notice tone="bad" title="No new ordinary run">
              Ordinary mission run is blocked until recovery is verified.
            </Notice>
            <button type="button" className="mt-3 min-h-11 w-full rounded-xl border border-line text-sm" disabled>Start Ordinary Run</button>
            <button type="button" className="mt-2 min-h-11 w-full rounded-xl border border-line text-sm" disabled={!verified}>Reset to Operational</button>
          </Card>
        </div>
      </Card>
    </SlidePage>
  );
}
