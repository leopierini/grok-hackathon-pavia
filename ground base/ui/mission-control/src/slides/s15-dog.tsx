"use client";

import { useState } from "react";
import { Map, Shield, Target } from "lucide-react";
import { Card, CardTitle, EmptyMap, Pill, SlidePage } from "@/components/console/frame";
import { DogMark } from "@/components/console/scenes";

const CANDIDATES = [
  { id: "candidate-forward-01", safe: "Safe · true", clearance: "0.8", frame: "base_link", expiry: "2025-03-08 10:45:00", source: "Synthetic candidate" },
  { id: "candidate-turn-left-01", safe: "Safe · true", clearance: "0.7", frame: "base_link", expiry: "2025-03-08 10:45:00", source: "Synthetic candidate" },
  { id: "candidate-turn-right-01", safe: "Safe · true", clearance: "0.7", frame: "base_link", expiry: "2025-03-08 10:45:00", source: "Synthetic candidate" },
];

export function Slide15() {
  const [selected, setSelected] = useState(CANDIDATES[0].id);
  const current = CANDIDATES.find((item) => item.id === selected) ?? CANDIDATES[0];
  return (
    <SlidePage
      id="15"
      active="navigation"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Dog navigation", body: "Plan and evaluate safe motion for the dog robot.", icon: <Target className="h-5 w-5" /> },
        { title: "Planner health", body: "Runtime state of slam_local_planner (ready, blocked, and so on).", icon: <Shield className="h-5 w-5" /> },
        { title: "Map identity", body: "Active map context (for example museum-map-demo) for the rehearsal.", icon: <Map className="h-5 w-5" /> },
        { title: "Safe candidates", body: "Approved motion candidates with clearance, frame, and expiry.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principlesTitle="Key details"
      principlesNote="Navigation components and the selected safe candidate."
      principles={[
        { index: "01", title: "slam_local_planner", body: "Planner for dog navigation. Current state: Blocked. Health: Ready (runtime OK)." },
        { index: "02", title: "museum-map-demo", body: "Active map identity. No map image published. Navigation is blocked." },
        { index: "03", title: current.id, body: `${current.safe}. Clearance · ${current.clearance}. Synthetic candidate.` },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Mission</p>
            <h2 className="font-display text-2xl font-semibold">Dog navigation</h2>
            <p className="text-sm text-muted">Rehearsal navigation (stationary). Evaluate safe candidates and planner state.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="info">slam_local_planner</Pill>
            <Pill tone="neutral">museum-map-demo</Pill>
            <Pill tone="bad">BLOCKED</Pill>
          </div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle title="Dog (pose)" />
            <DogMark className="h-20 w-28" />
            <p className="font-semibold">Go2 PRO</p>
            <dl className="mt-2 text-sm">
              <Row k="Mode" v="Rehearsal" />
              <Row k="State" v="Stationary" />
              <Row k="Pose" v="Known (fixed)" />
            </dl>
          </Card>
          <Card>
            <CardTitle title="Map (museum-map-demo)" />
            <EmptyMap title="No map image published" detail="No map to draw" />
          </Card>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-[0.8fr_1.2fr]">
          <Card>
            <CardTitle title="Planner health" />
            <dl className="text-sm">
              <Row k="Planner" v="slam_local_planner" />
              <Row k="State" v="Blocked" />
              <Row k="Health" v="Ready" />
              <Row k="Map" v="museum-map-demo" />
            </dl>
          </Card>
          <Card>
            <p className="text-sm font-semibold text-bad">Not a real route</p>
            <p className="text-sm text-muted">Navigation is blocked. No route is displayed.</p>
          </Card>
        </div>
        <Card className="mt-3">
          <CardTitle title="Approved safe candidates" extra={<Pill tone="sim">Synthetic candidate</Pill>} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <caption className="sr-only">Approved safe candidates</caption>
              <thead>
                <tr className="text-xs uppercase text-muted">
                  <th className="py-2">#</th>
                  <th>Candidate ID</th>
                  <th>Safe</th>
                  <th>Clearance</th>
                  <th>Frame</th>
                  <th>Expiry</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {CANDIDATES.map((candidate, index) => (
                  <tr key={candidate.id} className="border-t border-line">
                    <td>{index + 1}</td>
                    <td>
                      <label className="inline-flex min-h-11 items-center gap-2 font-mono">
                        <input type="radio" name="candidate" checked={selected === candidate.id} onChange={() => setSelected(candidate.id)} />
                        {candidate.id}
                      </label>
                    </td>
                    <td><Pill tone="ok">{candidate.safe}</Pill></td>
                    <td>{candidate.clearance}</td>
                    <td>{candidate.frame}</td>
                    <td className="font-mono text-xs">{candidate.expiry}</td>
                    <td>{candidate.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
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
