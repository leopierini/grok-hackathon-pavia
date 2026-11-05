"use client";

import { useState } from "react";
import { Camera, Check, CircleHelp, Flag, Layers, Shield, UserRound } from "lucide-react";
import { Card, CardTitle, CheckRow, Pill, SlidePage, StepRail, Thumb, Timeline, useHaltAction } from "@/components/console/frame";
import { SurveyScene } from "@/components/console/scenes";
import { HaltButton } from "@/components/ui";

export function Slide01() {
  const halt = useHaltAction();
  const [liveNote, setLiveNote] = useState<string | null>(null);
  return (
    <SlidePage
      id="01"
      active="mission"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Precise operations", body: "Plan, execute, and monitor robot and drone missions with clear state and control.", icon: <Flag className="h-5 w-5" /> },
        { title: "Verified evidence", body: "Capture and organize mission evidence with traceability.", icon: <Layers className="h-5 w-5" /> },
        { title: "Operator authority", body: "A human-in-the-loop console with clear, decisive operational control.", icon: <UserRound className="h-5 w-5" /> },
        { title: "Graceful unknown states", body: "Make uncertainty explicit and provide safe, guided next actions.", icon: <CircleHelp className="h-5 w-5" /> },
      ]}
      principlesTitle="Design Principles"
      principlesNote="Core UI/UX principles for Ground Mission Control"
      principles={[
        { index: "01", title: "Precise operations", body: "Clear mission phases, device readiness, and gated progress for reliable execution." },
        { index: "02", title: "Verified evidence", body: "Structured capture, preview, and traceable records for review and analysis." },
        { index: "03", title: "Human authority", body: "The operator stays in control with clear state, explicit mode (simulation or live), and a persistent HALT action.", extra: <HaltButton onHalt={halt} /> },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-blue">
              <Flag className="h-3.5 w-3.5" aria-hidden /> Mission
            </p>
            <h2 className="mt-1 font-display text-2xl font-semibold">
              Site Survey — Sector A <Pill tone="sim">SIMULATION</Pill>
            </h2>
            <p className="text-sm text-muted">Rehearsal mission (offline). Validate plan, coverage, and evidence flow.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm font-semibold" onClick={() => setLiveNote("Live transport is refused. This console stays in simulation.")}>
              Switch to Live
            </button>
            <HaltButton onHalt={halt} />
          </div>
        </div>
        {liveNote ? <p className="mt-3 text-sm text-warn">{liveNote}</p> : null}
        <div className="mt-4">
          <StepRail
            steps={[
              { label: "Plan", state: "done" },
              { label: "Initialize", state: "done" },
              { label: "Execute", state: "current" },
              { label: "Collect", state: "todo" },
              { label: "Review", state: "todo" },
              { label: "Complete", state: "todo" },
            ]}
          />
        </div>
        <div className="mt-4 grid gap-3 xl:grid-cols-[0.9fr_1.2fr_0.9fr]">
          <Card>
            <CardTitle title="Devices (2)" />
            <DeviceLine name="Go2 PRO" kind="Unitree Go2 PRO" role="Field robot" status="Ready" />
            <DeviceLine name="Tello EDU" kind="Tello EDU" role="Aerial drone" status="Ready" />
          </Card>
          <Card>
            <CardTitle icon={<Camera className="h-4 w-4" />} title="Vision · Evidence Preview" extra={<Pill tone="sim">SIM</Pill>} />
            <SurveyScene />
            <div className="mt-2 flex gap-2">
              <Thumb label="A" />
              <Thumb label="B" />
              <Thumb label="C" />
              <button type="button" className="grid h-12 w-16 place-items-center rounded-md border border-dashed border-line text-[10px] font-semibold text-muted">
                Add View
              </button>
            </div>
          </Card>
          <Card>
            <CardTitle title="Activity Timeline" />
            <Timeline
              items={[
                { label: "Rehearsal started", time: "10:24", state: "done" },
                { label: "Devices ready (Go2 PRO, Tello EDU)", time: "10:25", state: "done" },
                { label: "Execute: waypoint 1–3", time: "10:27", state: "current" },
                { label: "Collecting evidence", time: "—", state: "todo" },
                { label: "Review & confirm", time: "—", state: "todo" },
              ]}
            />
          </Card>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-[1.4fr_0.8fr]">
          <Card>
            <CardTitle icon={<Shield className="h-4 w-4" />} title="Readiness Gates" />
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <CheckRow label="Plan valid" detail="Mission plan & area" />
              <CheckRow label="Devices ready" detail="Go2 PRO & Tello EDU" />
              <CheckRow label="Evidence path" detail="Capture & storage" />
              <CheckRow ok={false} tone="info" label="Operator confirm" detail="Proceed / Halt" />
            </ul>
          </Card>
          <Card>
            <CardTitle icon={<CircleHelp className="h-4 w-4" />} title="Simulation Mode (Rehearsal)" />
            <p className="text-sm text-muted">Runs locally without physical devices.</p>
          </Card>
        </div>
      </Card>
    </SlidePage>
  );
}

function DeviceLine({ name, kind, role, status }: { name: string; kind: string; role: string; status: string }) {
  return (
    <div className="mb-3 flex items-center gap-3 border-b border-line pb-3 last:mb-0 last:border-b-0 last:pb-0">
      <span className="grid h-10 w-10 place-items-center rounded-lg bg-surface-2 text-xs font-bold">{name.slice(0, 2)}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{name}</span>
        <span className="block text-xs text-muted">{kind} · {role}</span>
      </span>
      <Pill tone="ok">
        <Check className="h-3 w-3" aria-hidden /> {status}
      </Pill>
    </div>
  );
}
