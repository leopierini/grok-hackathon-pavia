"use client";

import { Camera, Clock, Hash, Lock, Shield } from "lucide-react";
import { Card, CardTitle, Field, Flow, Pill, SlidePage, Thumb } from "@/components/console/frame";
import { SurveyScene } from "@/components/console/scenes";

const FIELDS: { label: string; value: string; status: string; tone: "ok" | "warn" }[] = [
  { label: "Image ID", value: "dog-front-002", status: "Valid", tone: "ok" },
  { label: "Source", value: "Source · dog", status: "Valid", tone: "ok" },
  { label: "Camera ID", value: "CAM-002", status: "Valid", tone: "ok" },
  { label: "Camera epoch", value: "Camera epoch · 1", status: "Valid", tone: "ok" },
  { label: "Captured", value: "Captured · timestamped", status: "Valid", tone: "ok" },
  { label: "Age", value: "Age · unknown", status: "Unknown", tone: "warn" },
  { label: "Stale reason", value: "Stale reason · age is unknown", status: "Unknown", tone: "warn" },
  { label: "Dimensions", value: "1920 × 1080", status: "Valid", tone: "ok" },
  { label: "Calibration", value: "Calibration · synthetic-calibration-v1", status: "Valid", tone: "ok" },
  { label: "SHA-256", value: "9f2a6e5d4c3b8e1a7d0e7f8c6b3d9a", status: "Valid", tone: "ok" },
  { label: "JPEG bytes", value: "2,604,781 bytes (valid JPEG)", status: "Valid", tone: "ok" },
  { label: "Validation", value: "Validation · OK", status: "Valid", tone: "ok" },
];

export function Slide10() {
  return (
    <SlidePage
      id="10"
      active="evidence"
      items={[
        { id: "mission", href: "/cockpit", label: "Mission" },
        { id: "devices", href: "/devices", label: "Devices" },
        { id: "evidence", href: "/evidence", label: "Evidence" },
        { id: "vision", href: "/vision", label: "Vision" },
        { id: "navigation", href: "/navigation", label: "Navigation" },
        { id: "commands", href: "/commands", label: "Commands" },
        { id: "runs", href: "/runs", label: "Runs" },
        { id: "rehearsal", href: "/rehearsal", label: "Rehearsal" },
        { id: "settings", href: "/settings", label: "Settings" },
      ]}
      topbar={{ mode: "EVIDENCE", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Provenance", body: "Source, device, camera ID, epoch, and capture time.", icon: <Camera className="h-5 w-5" /> },
        { title: "Integrity", body: "Cryptographic digest (SHA-256) and JPEG byte validation.", icon: <Shield className="h-5 w-5" /> },
        { title: "Validation", body: "Allowlist, format, and consistency checks with clear states.", icon: <Hash className="h-5 w-5" /> },
        { title: "Staleness", body: "Age assessment and explicit stale reason (for example age is unknown).", icon: <Clock className="h-5 w-5" /> },
      ]}
      principlesTitle="Key Capabilities"
      principlesNote="Frame-level provenance, integrity, and staleness assessment."
      principles={[
        { index: "01", title: "Provenance", body: "Trace the frame to its source, camera ID, and epoch for accountable mission evidence." },
        { index: "02", title: "Integrity", body: "Verify content with SHA-256 and JPEG byte validation to ensure data integrity." },
        { index: "03", title: "Staleness", body: "Assess frame age and report the explicit stale reason. Here, age is unknown, so the frame is not treated as fresh." },
        { index: "04", title: "Access policy", body: "Only allowlisted image IDs can be opened from the inspector to control access during operations.", extra: <span className="inline-flex gap-2"><span className="rounded-full bg-warn-bg px-2 py-1 text-xs font-semibold text-warn">Age · unknown</span><span className="rounded-full bg-ok-bg px-2 py-1 text-xs font-semibold text-ok">Allowlist · permitted</span></span> },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-xl font-semibold">JPEG Evidence <Pill tone="sim">SIMULATED</Pill></h2>
          <p className="font-mono text-sm">dog-front-002</p>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <SurveyScene badge="JPEG" dog />
            <div className="mt-2 flex gap-2">
              <Thumb label="dog" />
              <Thumb label="path" />
              <Thumb label="yard" />
            </div>
          </div>
          <div>
            {FIELDS.map((field) => (
              <Field key={field.label} label={field.label} value={field.value} status={<Pill tone={field.tone}>{field.status}</Pill>} />
            ))}
          </div>
        </div>
        <div className="mt-4">
          <CardTitle icon={<Lock className="h-4 w-4" />} title="Frame validation pipeline" extra={<span className="text-xs text-muted">Allowlist, bytes, hash, and policy checks.</span>} />
          <Flow
            steps={[
              { title: "Allowlist", detail: "Open permitted", tone: "ok" },
              { title: "JPEG bytes", detail: "Valid", tone: "ok" },
              { title: "SHA-256", detail: "Match", tone: "ok" },
              { title: "Validation", detail: "OK", tone: "ok" },
            ]}
          />
        </div>
      </Card>
    </SlidePage>
  );
}
