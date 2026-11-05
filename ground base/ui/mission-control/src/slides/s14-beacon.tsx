"use client";

import { Lock, Radio, Shield } from "lucide-react";
import { Card, CardTitle, Flow, Pill, SlidePage } from "@/components/console/frame";
import { LineChart } from "@/components/console/charts";
import { HaltButton } from "@/components/ui";
import { useHaltAction } from "@/components/console/frame";

const SAMPLES = [-52, -51, -50, -51, -50, -49, -50, -51, -50, -52, -70, -72, -68, -74, -71, -73];

export function Slide14() {
  const halt = useHaltAction();
  return (
    <SlidePage
      id="14"
      active="navigation"
      items={[
        { id: "mission", href: "/cockpit", label: "Mission" },
        { id: "devices", href: "/devices", label: "Devices" },
        { id: "vision", href: "/vision", label: "Vision" },
        { id: "navigation", href: "/navigation", label: "Navigation" },
        { id: "beacons", href: "/navigation", label: "Beacons" },
        { id: "gates", href: "/proximity", label: "Gates" },
        { id: "activity", href: "/runs", label: "Activity" },
        { id: "rehearsal", href: "/rehearsal", label: "Rehearsal" },
        { id: "settings", href: "/settings", label: "Settings" },
      ]}
      topbar={{ mode: "SIMULATED", note: "Local Operator Console · Robotics Rehearsal" }}
      chips={[
        { title: "Beacon hold", body: "Maintain a stable hold on a selected beacon within an epoch.", icon: <Radio className="h-5 w-5" /> },
        { title: "RSSI navigation", body: "Use beacon RSSI (dBm) for relative navigation and hold validation.", icon: <Radio className="h-5 w-5" /> },
        { title: "Motion-aware gating", body: "Drone motion invalidates the current hold; the dog remains stopped until a fresh hold.", icon: <Lock className="h-5 w-5" /> },
      ]}
      principlesTitle="Causal sequence"
      principlesNote="Event sequence and control outcome (stationary robotics rehearsal)."
      principles={[
        { index: "01", title: "Beacon epoch 4 · hold stable", body: "B-017 · Epoch 4. Hold stable. Timer 00:00:37." },
        { index: "02", title: "Drone motion · hold invalidated", body: "Drone motion invalidates the current hold. Reacquire and stabilize a fresh hold before movement resumes." },
        { index: "03", title: "Dog remains stopped", body: "The movement gate stays closed while the hold is invalid. The dog moves only after a fresh, stable hold is confirmed." },
        { index: "04", title: "New hold required", body: "Reacquire B-017. Establish fresh hold. Then allow dog move." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Navigation</p>
            <h2 className="font-display text-2xl font-semibold">Beacon navigation <Pill tone="sim">SIMULATED</Pill></h2>
            <p className="text-sm text-muted">RSSI-driven navigation with beacon hold, motion gating, and dog safety control.</p>
          </div>
          <div className="flex items-center gap-2">
            <Pill tone="info">Rehearsal (Stationary)</Pill>
            <HaltButton onHalt={halt} />
          </div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[0.7fr_1.3fr]">
          <Card>
            <dl className="space-y-2 text-sm">
              <Row k="Beacon" v="B-017" />
              <Row k="Epoch" v="4" />
              <Row k="Hold state" v="STABLE" />
              <Row k="Stable-hold timer" v="00:00:37" />
              <Row k="Sample freshness" v="0.34 s ago · FRESH" />
              <Row k="Signal quality" v="GOOD" />
              <Row k="SNR (est.)" v="24 dB" />
            </dl>
          </Card>
          <Card>
            <CardTitle title="RSSI (dBm) — Beacon B-017" extra={<Pill tone="warn">RSSI is not distance</Pill>} />
            <LineChart values={SAMPLES} min={-100} max={-30} yTicks={[-30, -50, -70, -90]} markAt={10} caption="RSSI stays near minus 50 dBm, then drops after drone motion" />
            <p className="text-xs text-danger">Drone motion · hold invalidated</p>
          </Card>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle title="Device status & gating" />
            <p className="text-sm">Drone · <Pill tone="bad">IN MOTION</Pill></p>
            <p className="mt-2 text-sm">Dog (Go2 PRO) · <Pill tone="neutral">STOPPED</Pill></p>
          </Card>
          <Card>
            <CardTitle icon={<Shield className="h-4 w-4" />} title="Dog movement gate" />
            <ul className="space-y-1 text-sm">
              <li>Hold valid (epoch 4)</li>
              <li>Fresh hold required</li>
              <li><Pill tone="bad">Gate closed</Pill></li>
            </ul>
          </Card>
        </div>
      </Card>
      <div className="mt-3">
        <Flow
          steps={[
            { title: "Beacon epoch 4 · hold stable", detail: "Timer 00:00:37", tone: "ok" },
            { title: "Drone motion · hold invalidated", tone: "bad" },
            { title: "Dog remains stopped", detail: "Gate closed", tone: "neutral" },
            { title: "New hold required", detail: "Reacquire B-017", tone: "info" },
          ]}
        />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <Card><h3 className="font-semibold">RSSI is not distance</h3><p className="mt-2 text-sm text-muted">RSSI is signal strength (dBm), not a distance measurement. Use RSSI trends with hold and quality checks for navigation.</p></Card>
        <Card><h3 className="font-semibold">New hold required</h3><p className="mt-2 text-sm text-muted">Drone motion invalidates the current hold. Reacquire and stabilize a fresh hold (same or new epoch) before movement resumes.</p></Card>
        <Card><h3 className="font-semibold">Dog remains stopped</h3><p className="mt-2 text-sm text-muted">The movement gate stays closed while the hold is invalid. The dog moves only after a fresh, stable hold is confirmed.</p></Card>
      </div>
    </SlidePage>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{k}</dt>
      <dd className="font-semibold">{v}</dd>
    </div>
  );
}
