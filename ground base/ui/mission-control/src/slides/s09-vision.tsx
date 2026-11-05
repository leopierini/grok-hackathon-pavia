"use client";

import { useState } from "react";
import { Camera, Plus, Shield, Zap } from "lucide-react";
import { Card, CardTitle, Pill, Segmented, SlidePage } from "@/components/console/frame";
import { SurveyScene } from "@/components/console/scenes";

const REQUESTS = [
  { id: "VR-0912", type: "Detect person", source: "dog front", status: "Completed", updated: "10:27:36", bucket: "Latest" },
  { id: "VR-0913", type: "Scene check", source: "drone down", status: "In-flight", updated: "10:28:02", bucket: "In-flight" },
];

const FRAMES = ["10:27:36.421", "10:27:36.921", "10:27:37.421", "10:27:37.921", "10:27:38.421"];

export function Slide09() {
  const [bucket, setBucket] = useState("Latest");
  const [requested, setRequested] = useState(false);
  const visible = bucket === "Dropped" ? [] : bucket === "In-flight" ? REQUESTS.filter((item) => item.bucket === "In-flight") : REQUESTS;
  return (
    <SlidePage
      id="09"
      active="vision"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Evidence console", body: "Timestamped frames from drone (downward), front camera, and dog.", icon: <Camera className="h-5 w-5" /> },
        { title: "Inspector", body: "Track, confidence, proposal, and reason with suggested action.", icon: <Camera className="h-5 w-5" /> },
        { title: "Vision request", body: "Create, track, and review requests (latest / in-flight / dropped).", icon: <Zap className="h-5 w-5" /> },
        { title: "Decision", body: "Structured verdict (for example person_visible) with clear authority.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principlesTitle="Key areas"
      principlesNote="How vision evidence is reviewed and turned into control decisions."
      principles={[
        { index: "01", title: "Evidence console", body: "Timestamped frame strip. Selected simulated frame with frame ID, epoch, time, age · unknown, and validation." },
        { index: "02", title: "Inspector", body: "Target track and confidence. Suggested action and image-space proposal. Reason (for example person_visible)." },
        { index: "03", title: "Decision & requests", body: "Decision · person_visible. Proposal only. No motor authority. Latest / in-flight / dropped requests." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-2xl font-semibold">Vision & Evidence</h2>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm">
              Model
              <select className="ml-2 min-h-11 rounded-xl border border-line bg-surface px-2" aria-label="Model" defaultValue="Vision-X (placeholder)">
                <option>Vision-X (placeholder)</option>
              </select>
            </label>
            <button type="button" className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-blue px-3 text-sm font-semibold text-white" onClick={() => setRequested(true)}>
              <Plus className="h-4 w-4" aria-hidden /> New Request
            </button>
          </div>
        </div>
        {requested ? <p className="mt-2 text-sm text-info">Request queued as a proposal. The scheduler decides. This page does not invent a motor command.</p> : null}
        <div className="mt-4 grid gap-3 xl:grid-cols-[1.3fr_0.7fr]">
          <div>
            <SurveyScene badge="SIMULATED SNAPSHOT" person />
            <p className="mt-2 text-xs font-semibold">dog-front-002</p>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted">
              <span>dog-front-002</span>
              <span>camera epoch 1</span>
              <span>capture time 10:27:36.421</span>
              <span>age · unknown</span>
              <span className="text-success">JPEG · valid</span>
            </div>
            <div className="mt-2 flex gap-2 overflow-x-auto">
              {FRAMES.map((frame) => (
                <figure key={frame} className="w-24 shrink-0">
                  <div className="h-14 rounded-md bg-[#c5d8e4]" />
                  <figcaption className="mt-1 font-mono text-[10px] text-muted">{frame}</figcaption>
                </figure>
              ))}
            </div>
          </div>
          <div className="space-y-3">
            <Card>
              <CardTitle title="Inspector" />
              <dl className="space-y-1 text-sm">
                <Row k="Target track" v="TRK-0347" />
                <Row k="Confidence" v="0.96" />
                <Row k="Suggested action" v="Observe" />
                <Row k="Proposal" v="Proposal only" />
                <Row k="Reason" v="person_visible" />
              </dl>
            </Card>
            <Card>
              <CardTitle title="Decision" />
              <p className="text-sm font-semibold text-success">Decision · person_visible</p>
              <div className="mt-2 flex gap-2">
                <Pill tone="info">Proposal only</Pill>
                <Pill tone="neutral">No motor authority</Pill>
              </div>
            </Card>
          </div>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle title="Vision request (linked)" extra={<Pill tone="ok">Completed</Pill>} />
            <dl className="text-sm">
              <Row k="Request ID" v="VR-0912" />
              <Row k="Type" v="Detect person" />
              <Row k="Source" v="dog front" />
              <Row k="Status" v="Completed" />
            </dl>
          </Card>
          <Card>
            <CardTitle title="Requests" />
            <Segmented label="Request buckets" options={["Latest", "In-flight", "Dropped"]} value={bucket} onChange={setBucket} />
            <p className="mt-2 text-xs text-muted">{bucket} ({visible.length})</p>
            <ul className="mt-2 space-y-2 text-sm">
              {visible.length === 0 ? <li>Dropped (0). No dropped request in this rehearsal snapshot.</li> : null}
              {visible.map((item) => (
                <li key={item.id} className="flex flex-wrap justify-between gap-2">
                  <span className="font-mono">{item.id}</span>
                  <span>{item.type}</span>
                  <span>{item.source}</span>
                  <Pill tone={item.status === "Completed" ? "ok" : "info"}>{item.status}</Pill>
                  <span className="font-mono text-xs">{item.updated}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </Card>
    </SlidePage>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 py-1">
      <dt className="text-muted">{k}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );
}
