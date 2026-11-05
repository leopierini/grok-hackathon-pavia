"use client";

import { CircleHelp, Layers, Radio, Target } from "lucide-react";
import { Card, CardTitle, Notice, Pill, SlidePage } from "@/components/console/frame";
import { HaltButton } from "@/components/ui";
import { useHaltAction } from "@/components/console/frame";

export function Slide19() {
  const halt = useHaltAction();
  return (
    <SlidePage
      id="19"
      active="mission"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Proximity evidence", body: "Combine independent range and offset evidence.", icon: <Target className="h-5 w-5" /> },
        { title: "Separate checks", body: "Keep altitude and obstacle clearance independent.", icon: <Layers className="h-5 w-5" /> },
        { title: "Configurable gate", body: "Each evidence has its own source and threshold.", icon: <Layers className="h-5 w-5" /> },
        { title: "Unresolved by default", body: "If evidence or threshold is unknown or unset, the goal remains unresolved.", icon: <CircleHelp className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Altitude ≠ horizontal offset", body: "Altitude measures vertical separation. Horizontal offset measures lateral distance to the target. They are independent gates." },
        { index: "02", title: "Clearance ≠ proximity", body: "Obstacle clearance ensures a safe path from obstacles. It does not indicate goal arrival. Keep clearance and proximity separate." },
        { index: "03", title: "No RSSI arrival inference", body: "Do not infer goal arrival from RSSI alone (signal strength is not a reliable proxy). Use configured proximity evidence (range and offset) instead." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Mission</p>
            <h2 className="font-display text-2xl font-semibold">Goal Gate — Proximity <Pill tone="sim">SIMULATION</Pill></h2>
            <p className="text-sm text-muted">Evaluate independent evidence for goal arrival. All required gates must be satisfied.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Switch to Live</button>
            <HaltButton onHalt={halt} />
          </div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1.3fr_0.7fr]">
          <Card>
            <CardTitle title="Proximity evidence" extra={<span className="text-xs">Evidence freshness · Unknown</span>} />
            <Evidence title="Dog range · unknown" source="Unknown" threshold="Unset" />
            <Evidence title="Drone horizontal offset · unknown" source="Unknown" threshold="Unset" />
            <p className="mt-3 text-sm">Altitude · Separate gate (not a substitute for proximity). <Pill tone="warn">Unknown</Pill></p>
            <p className="mt-2 text-sm">Obstacle clearance · Separate gate (not a substitute for proximity). <Pill tone="warn">Unknown</Pill></p>
          </Card>
          <Card>
            <p className="rounded-xl bg-warn-bg px-3 py-3 text-sm font-semibold text-warn">Goal · unresolved</p>
            <ol className="mt-3 flex gap-2 text-xs text-muted">
              <li>Evidence</li><li>Evaluate</li><li>Goal</li>
            </ol>
            <h3 className="mt-4 font-semibold">Decision explanation</h3>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-muted">
              <li>Goal cannot be resolved.</li>
              <li>Required evidence is unknown and/or threshold is unset.</li>
              <li>Await valid dog range and drone horizontal offset with configured thresholds.</li>
              <li>Altitude and obstacle clearance are evaluated separately.</li>
              <li>No RSSI arrival inference.</li>
            </ul>
          </Card>
        </div>
      </Card>
      <div className="mt-3">
        <Notice tone="info" title="No RSSI arrival inference">
          <Radio className="mr-1 inline h-4 w-4" aria-hidden /> Signal strength is not a reliable proxy for arrival.
        </Notice>
      </div>
    </SlidePage>
  );
}

function Evidence({ title, source, threshold }: { title: string; source: string; threshold: string }) {
  return (
    <div className="mt-3 rounded-xl border border-line p-3">
      <p className="font-semibold">{title}</p>
      <p className="text-sm text-muted">Source · {source}</p>
      <p className="text-sm text-muted">Threshold · {threshold}</p>
    </div>
  );
}
