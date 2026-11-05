"use client";

import { Layers, Radio, RefreshCw, Shield } from "lucide-react";
import { Card, CardTitle, Flow, Pill, SlidePage, StepRail } from "@/components/console/frame";
import { DroneMark } from "@/components/console/scenes";
import { HaltButton } from "@/components/ui";
import { useHaltAction } from "@/components/console/frame";

export function Slide12() {
  const halt = useHaltAction();
  return (
    <SlidePage
      id="12"
      active="mission"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Live observation", body: "Current flight state, height, reference, beacon epoch, and observation age.", icon: <Radio className="h-5 w-5" /> },
        { title: "Bounded action", body: "Single, policy-scoped primitive with guard and approval state.", icon: <Layers className="h-5 w-5" /> },
        { title: "Safety gating", body: "Withhold motion when directional control is unverified.", icon: <Shield className="h-5 w-5" /> },
        { title: "State coherence", body: "Drone movement invalidates a prior beacon hold.", icon: <RefreshCw className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Observation snapshot", body: "Flight state airborne. Height 4 m. Reference floor_agl. Beacon epoch 4. Observed 10:27:16. Age 0.6 s." },
        { index: "02", title: "Bounded action & guard", body: "Primitive track_step. Guard supervised. Directional control unverified. Motion permission false. Approval withheld (supervised). Profile limit mission_safe." },
        { index: "03", title: "State coherence", body: "Drone movement occurred while holding epoch 4. The prior beacon hold is invalidated. The action remains withheld until directional control is verified." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Mission</p>
            <h2 className="font-display text-2xl font-semibold">Site Survey — Sector A <Pill tone="sim">SIMULATION</Pill></h2>
            <p className="text-sm text-muted">Observation and bounded action (single primitive).</p>
          </div>
          <div className="flex gap-2">
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Switch to Live</button>
            <HaltButton onHalt={halt} />
          </div>
        </div>
        <div className="mt-4">
          <StepRail steps={[{ label: "Plan", state: "done" }, { label: "Initialize", state: "done" }, { label: "Execute", state: "current" }, { label: "Collect", state: "todo" }, { label: "Review", state: "todo" }, { label: "Complete", state: "todo" }]} />
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle title="Tello EDU" extra={<Pill tone="sim">SIMULATED OBSERVATION</Pill>} />
            <div className="grid place-items-center rounded-xl bg-surface-2 py-6"><DroneMark className="h-20 w-28" /></div>
            <dl className="mt-3 space-y-2 text-sm">
              <Row k="Flight state" v="airborne" />
              <Row k="Height" v="4 m" />
              <Row k="Reference" v="floor_agl" />
              <Row k="Beacon epoch" v="4" />
              <Row k="Observed" v="10:27:16 | Age: 0.6 s" />
            </dl>
          </Card>
          <Card>
            <CardTitle icon={<Layers className="h-4 w-4" />} title="One bounded primitive" />
            <p className="rounded-xl bg-info-bg px-3 py-3 font-mono text-sm font-semibold text-info">track_step</p>
            <ul className="mt-3 space-y-2 text-sm">
              <li>Guard · <Pill tone="ok">supervised</Pill></li>
              <li>Directional control · <Pill tone="warn">unverified</Pill></li>
              <li>Motion permission · <Pill tone="bad">false</Pill></li>
              <li>Approval · <Pill tone="ok">withheld (supervised)</Pill></li>
              <li>Profile limit · <Pill tone="info">mission_safe</Pill></li>
            </ul>
          </Card>
        </div>
        <Card className="mt-3">
          <CardTitle title="Beacon hold & movement (state update)" />
          <p className="mb-3 text-sm text-muted">Drone movement invalidates the prior beacon hold.</p>
          <Flow
            steps={[
              { title: "Beacon hold (epoch 4)", tone: "info" },
              { title: "Drone movement (airborne)", tone: "info" },
              { title: "Held state invalidated", detail: "previous beacon hold", tone: "bad" },
            ]}
          />
        </Card>
      </Card>
    </SlidePage>
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
