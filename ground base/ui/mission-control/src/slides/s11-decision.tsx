"use client";

import { Camera, Lock, Shield, TriangleAlert } from "lucide-react";
import { Card, CardTitle, Notice, Pill, SlidePage } from "@/components/console/frame";
import { SurveyScene } from "@/components/console/scenes";

export function Slide11() {
  return (
    <SlidePage
      id="11"
      active="vision"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Model result inspector", body: "View model, prompt, frame, detections and tracks, decision, proposal, and validation.", icon: <Camera className="h-5 w-5" /> },
        { title: "Controlled decisions", body: "AI may propose actions. Ground policy decides and authorizes.", icon: <Shield className="h-5 w-5" /> },
        { title: "Rejection handling", body: "Clear states for stale or mismatched frame and unknown model.", icon: <TriangleAlert className="h-5 w-5" /> },
        { title: "Auditable review", body: "Deterministic record for safe mission operations.", icon: <Lock className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Decision & evidence", body: "Model · placeholder. Prompt · patrol-demo-v2.0. Frame link and preview. Detections / Tracks." },
        { index: "02", title: "Proposal & policy", body: "Suggested · switch to dog vision. Proposal · reposition. Proposal only. No motor authority." },
        { index: "03", title: "Validation & rejection", body: "Review required is a policy decision. Reject stale or mismatched frame. Reject unknown model. AI may propose. Ground policy decides." },
      ]}
    >
      <div className="mb-3 flex flex-wrap gap-2">
        <Pill tone="info">AI may propose, Ground policy decides.</Pill>
        <Pill tone="sim">Proposal only</Pill>
        <Pill tone="bad">No motor authority</Pill>
      </div>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-xl font-semibold">Decision review</h2>
          <p className="text-xs text-muted">Model · placeholder · Prompt · patrol-demo-v2.0</p>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <div>
            <SurveyScene badge="Frame · #F-003842" person />
            <p className="mt-2 text-sm font-semibold text-blue">person_visible</p>
          </div>
          <div className="space-y-2 text-sm">
            <p className="font-semibold text-success">Decision · person_visible</p>
            <p>Confidence · 0.91</p>
            <div className="h-2 rounded-full bg-surface-2"><div className="h-full w-[91%] rounded-full bg-blue" /></div>
            <p>Uncertainty · 0.09</p>
            <div className="h-2 rounded-full bg-surface-2"><div className="h-full w-[9%] rounded-full bg-cyan" /></div>
            <p>Detections · 1 · Tracks · 1</p>
            <p>Suggested action · Suggested · switch to dog vision</p>
            <p>Image-space proposal · Proposal · reposition</p>
            <p className="text-xs text-muted">Frame link · #F-003842</p>
          </div>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle title="Reason" />
            <p className="text-sm">A person-sized object is visible with high confidence. Switch to dog vision and reposition to improve coverage and context before proceeding.</p>
          </Card>
          <Card>
            <CardTitle title="Validation outcome" />
            <div className="flex flex-wrap gap-2">
              <Pill tone="ok">Review required</Pill>
              <Pill tone="bad">Review required</Pill>
            </div>
          </Card>
        </div>
      </Card>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Notice tone="bad" title="Stale / mismatched frame">
          Frame · #F-003799 (stale). The frame is stale or does not match the current mission state. Reject model result. <Pill tone="bad">Rejected</Pill>
        </Notice>
        <Notice tone="bad" title="Unknown model">
          Model · unknown. The model is not in the allowed list for this mission. Reject for safety. <Pill tone="bad">Rejected</Pill>
        </Notice>
      </div>
    </SlidePage>
  );
}
