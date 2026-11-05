"use client";

import { Camera, Link2, Radio, Shield } from "lucide-react";
import { Card, CardTitle, Pill, SlidePage } from "@/components/console/frame";

export function Slide18() {
  return (
    <SlidePage
      id="18"
      active="targets"
      items={[
        { id: "targets", href: "/handoff", label: "Targets" },
        { id: "mission", href: "/cockpit", label: "Mission" },
        { id: "devices", href: "/devices", label: "Devices" },
        { id: "vision", href: "/vision", label: "Vision" },
        { id: "navigation", href: "/navigation", label: "Tracks" },
        { id: "commands", href: "/commands", label: "Commands" },
        { id: "runs", href: "/runs", label: "Data" },
        { id: "settings", href: "/settings", label: "Settings" },
      ]}
      topbar={{ mode: "SIMULATED", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "RSSI approach", body: "Use beacon/RSSI to approach and localize a target area.", icon: <Radio className="h-5 w-5" /> },
        { title: "Vision verification", body: "Acquire a clear target with a drone or dog camera.", icon: <Camera className="h-5 w-5" /> },
        { title: "Target handoff", body: "Handoff only when the vision track ID matches the current target.", icon: <Link2 className="h-5 w-5" /> },
        { title: "Review & control", body: "Review ambiguous or mismatched tracks before proceeding.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "No identity claim", body: "This workflow tracks a mission target (track ID) and detector confidence only. It does not identify or label a person." },
        { index: "02", title: "Separate provenance", body: "Drone observation: Drone camera. Dog camera: Dog (robot) camera." },
        { index: "03", title: "Confidence (detector)", body: "Detector confidence (for example 0.00–1.00). Indicates visual detection quality, not biometric identity." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Target handoff</p>
            <h2 className="font-display text-xl font-semibold">Current track · target-001</h2>
          </div>
          <Pill tone="sim">SIMULATED</Pill>
        </div>
        <p className="mt-1 text-sm text-muted">Acquire target via RSSI, then verify by vision. Handoff is enabled only when the vision track ID matches the current target.</p>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <Viewport title="Drone observation" provenance="Drone camera" rssi="RSSI -58 dBm" track="target-001" confidence="0.82" />
          <Viewport title="Dog camera" provenance="Dog camera" rssi="REC" track="target-001" confidence="0.87" />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Pill tone="ok">Same track · MATCH</Pill>
          <span aria-hidden>→</span>
          <Pill tone="info">Handoff · ready for review</Pill>
        </div>
        <h3 className="mt-4 font-semibold">Other target states (examples)</h3>
        <div className="mt-2 grid gap-3 lg:grid-cols-2">
          <Card>
            <p className="font-semibold text-warn">Ambiguous target · REVIEW</p>
            <p className="mt-1 text-sm text-muted">Vision track is uncertain (for example low confidence or multiple candidates). Review before handoff.</p>
            <p className="mt-2 text-sm">Current track target-001 · Vision track target-001 (conf. 0.56)</p>
            <button type="button" className="mt-2 min-h-11 rounded-xl border border-line px-3 text-sm">Review</button>
          </Card>
          <Card>
            <p className="font-semibold text-bad">Mismatched ID · BLOCKED</p>
            <p className="mt-1 text-sm text-muted">Vision track ID differs from the current target. Handoff is blocked. Verify and select the correct track.</p>
            <p className="mt-2 text-sm">Current track target-001 · Vision track target-003 (conf. 0.88)</p>
            <Pill tone="bad">Blocked</Pill>
          </Card>
        </div>
      </Card>
    </SlidePage>
  );
}

function Viewport({ title, provenance, rssi, track, confidence }: { title: string; provenance: string; rssi: string; track: string; confidence: string }) {
  return (
    <Card>
      <CardTitle title={title} extra={<span className="text-xs text-muted">{rssi}</span>} />
      <p className="text-xs text-muted">Provenance: {provenance}</p>
      <div className="mt-2 grid h-36 place-items-center rounded-xl bg-[#6f8f62] text-sm font-semibold text-white">target-001</div>
      <div className="mt-2 flex justify-between text-sm">
        <span>Track ID {track}</span>
        <span>Conf. {confidence}</span>
      </div>
    </Card>
  );
}
