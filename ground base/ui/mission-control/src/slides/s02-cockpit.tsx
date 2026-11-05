"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Activity, Camera, Check, HeartPulse, Layers } from "lucide-react";
import { Card, CardTitle, Pill, Progress, SlidePage, Timeline } from "@/components/console/frame";
import { DogMark, DroneMark, SurveyScene } from "@/components/console/scenes";
import { useOptionalSession } from "@/components/provider";
import { MotionControls } from "@/components/legacy/motion-controls";

const PHASES: { label: string; href: string }[] = [
  { label: "CONNECT", href: "/devices" },
  { label: "SCOUT", href: "/vision" },
  { label: "TRACK", href: "/commands" },
  { label: "HOLD", href: "/navigation" },
  { label: "HOME", href: "/dog" },
  { label: "DOG VISION", href: "/handoff" },
  { label: "PROXIMITY", href: "/proximity" },
  { label: "LAND", href: "/recovery" },
  { label: "DONE", href: "/runs" },
];

export function Slide02() {
  const session = useOptionalSession();
  return (
    <SlidePage
      id="02"
      active="mission"
      topbar={{
        mode: "SIMULATION",
        note: "Local Operator Console · Offline Capable",
        meta: ["Mission M-0427", "Epoch E2025-03-08T10:27Z", "Phase SCOUT"],
        latch: "Safety Latch",
        halt: true,
      }}
      chips={[
        { title: "Phase", body: "Ordered mission steps that drive execution (e.g., SCOUT, TRACK).", icon: <Layers className="h-5 w-5" /> },
        { title: "Physical state", body: "Real-world condition of devices and links (e.g., healthy, degraded).", icon: <HeartPulse className="h-5 w-5" /> },
        { title: "Outcome", body: "Result of the mission or run (e.g., success, needs review, halted).", icon: <Check className="h-5 w-5" /> },
      ]}
      principlesTitle="Cockpit rules"
      principles={[
        { index: "01", title: "Persistent status", body: "Always-on mission, epoch, mode, phase, safety latch, and HALT for immediate control." },
        { index: "02", title: "Context-sensitive actions", body: "Actions adapt to the current phase and device state (e.g., execute, collect, review)." },
        { index: "03", title: "State clarity", body: "Keep phase (mission step), physical state (device health), and outcome (run result) distinct and clearly visible." },
      ]}
    >
      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-blue">Mission</p>
        <h2 className="font-display text-2xl font-semibold">
          Site Survey – Sector A <Pill tone="sim">SIMULATION</Pill>
        </h2>
        <p className="text-sm text-muted">Rover + drone, environment survey and evidence capture.</p>
        <ol className="mt-4 flex flex-wrap items-center gap-2" aria-label="Authoritative phase">
          {PHASES.map((phase) => {
            const done = phase.label === "CONNECT";
            const current = phase.label === "SCOUT";
            return (
              <li key={phase.label} className="flex items-center gap-2 text-[11px] font-semibold">
                <Link href={phase.href} aria-label={`Open ${phase.label}`} className="inline-flex min-h-11 items-center gap-2 rounded-full px-1">
                  <span className={`grid h-5 w-5 place-items-center rounded-full border ${done ? "border-success bg-success text-white" : current ? "border-blue bg-blue text-white" : "border-line text-muted"}`}>
                    {done ? "✓" : current ? "●" : ""}
                  </span>
                  <span className={current ? "text-blue" : done ? "text-success" : "text-muted"}>{phase.label}</span>
                </Link>
              </li>
            );
          })}
          <li>
            <Link href="/runs" className="inline-flex min-h-11 items-center rounded-full border border-line px-3 text-sm font-semibold">
              Log
            </Link>
          </li>
        </ol>
        <Card className="mt-4">
          <CardTitle title="Dog motion" extra={<Pill tone="sim">SIMULATION</Pill>} />
          <p className="text-sm text-muted">Set the speeds used by the cable step, the practice step, and the short demo.</p>
          <MotionControls session={session} />
        </Card>
        <div className="mt-4 grid gap-3 xl:grid-cols-[0.85fr_1.15fr_0.85fr]">
          <Card>
            <CardTitle title="Devices (2)" />
            <HealthLine mark={<DogMark className="h-10 w-14" />} name="GO2 PRO" role="Field robot" status="Healthy" />
            <HealthLine mark={<DroneMark className="h-8 w-14" />} name="Tello EDU" role="Aerial drone" status="Healthy" />
          </Card>
          <Card>
            <CardTitle icon={<Camera className="h-4 w-4" />} title="Vision · Evidence Preview" extra={<Pill tone="sim">SIMULATED</Pill>} />
            <SurveyScene badge="SIMULATED" />
          </Card>
          <Card>
            <CardTitle icon={<Activity className="h-4 w-4" />} title="Active Operation" />
            <p className="text-sm font-semibold text-success">Execute: Scout area</p>
            <dl className="mt-3 space-y-2 text-sm">
              <Row k="Area" v="Sector A – West" />
              <Row k="Plan" v="Site survey (Sim)" />
              <Row k="Progress" v="32%" />
            </dl>
            <div className="mt-2">
              <Progress value={32} />
            </div>
          </Card>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle icon={<HeartPulse className="h-4 w-4" />} title="Device Health" />
            <ul className="space-y-2">
              <CheckLine label="Robots" value="2 / 2 Healthy" />
              <CheckLine label="Links" value="Nominal" />
              <CheckLine label="Sensors" value="Nominal" />
            </ul>
          </Card>
          <Card>
            <CardTitle title="Chronological Feed" />
            <Timeline
              items={[
                { label: "Rehearsal started", time: "10:24", state: "done" },
                { label: "Devices ready (GO2 PRO, Tello EDU)", time: "10:25", state: "done" },
                { label: "Execute: Scout area", time: "10:27", state: "current" },
                { label: "Collecting evidence", time: "10:28", state: "todo" },
                { label: "Review & next step", time: "10:30", state: "todo" },
              ]}
            />
          </Card>
        </div>
      </Card>
    </SlidePage>
  );
}

function HealthLine({ mark, name, role, status }: { mark: ReactNode; name: string; role: string; status: string }) {
  return (
    <div className="mb-3 flex items-center gap-2 border-b border-line pb-3 last:mb-0 last:border-0">
      {mark}
      <span className="flex-1">
        <span className="block text-sm font-semibold">{name}</span>
        <span className="block text-xs text-muted">{role}</span>
      </span>
      <Pill tone="ok">{status}</Pill>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{k}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );
}

function CheckLine({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex items-center justify-between text-sm">
      <span className="font-medium text-success">✓ {label}</span>
      <span>{value}</span>
    </li>
  );
}
