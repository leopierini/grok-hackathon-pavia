"use client";

import { useState } from "react";
import { Layers, Lock, Settings, Shield } from "lucide-react";
import { Card, CardTitle, Notice, Pill, SlidePage } from "@/components/console/frame";

const ROWS = ["Dog transport", "Pi data path", "Model ID", "Prompt version", "Evidence age ms", "Command lease ms", "Flight profile"];

export function Slide05() {
  const [transport, setTransport] = useState<"ethernet" | "wifi">("ethernet");
  const [piPath, setPiPath] = useState(true);
  const [profile, setProfile] = useState(false);
  const [column, setColumn] = useState("Current (Active)");
  return (
    <SlidePage
      id="05"
      active="settings"
      topbar={{ mode: "SETTINGS", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Connection", body: "Select dog transport and Pi data path.", icon: <Settings className="h-5 w-5" /> },
        { title: "Vision & budgets", body: "Model, prompt, evidence age, and command lease.", icon: <Layers className="h-5 w-5" /> },
        { title: "Profiles", body: "Calibration, range, and flight profile.", icon: <Shield className="h-5 w-5" /> },
        { title: "Safety & control", body: "No secrets, apply when idle, and require validation.", icon: <Lock className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Thresholds unset", body: "Calibration and dog range are UNSET. Set thresholds before use." },
        { index: "02", title: "4 m profile disabled", body: "The proposed 4 m floor-AGL profile is not enabled (Enabled · false)." },
        { index: "03", title: "Secrets refused", body: "No secrets accepted (for example credentials, keys, or tokens)." },
        { index: "04", title: "Idle + validation", body: "Edits apply when idle, and changes need validation before taking effect." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-2xl font-semibold">Settings</h2>
            <p className="text-sm text-muted">Operational configuration for the dog, Pi, vision, and mission control.</p>
          </div>
          <div className="flex gap-2">
            <Pill tone="info">Edits apply when idle</Pill>
            <Pill tone="warn">Changes need validation</Pill>
          </div>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle title="Connection" />
            <fieldset>
              <legend className="text-sm font-medium">Dog transport</legend>
              <div className="mt-2 flex gap-2">
                <Radio name="transport" label="ethernet" checked={transport === "ethernet"} onChange={() => setTransport("ethernet")} />
                <Radio name="transport" label="wifi" checked={transport === "wifi"} onChange={() => setTransport("wifi")} />
              </div>
            </fieldset>
            <fieldset className="mt-3">
              <legend className="text-sm font-medium">Pi data path</legend>
              <div className="mt-2">
                <Radio name="pi" label="usb" checked={piPath} onChange={() => setPiPath(true)} />
              </div>
            </fieldset>
          </Card>
          <div className="space-y-3">
            <button type="button" className="flex min-h-11 w-full items-center justify-between rounded-xl border border-line px-3 text-left text-sm">
              <span>Calibration · <strong className="text-danger">UNSET</strong></span>
              <span className="text-xs text-muted">Thresholds and calibration values are not set.</span>
            </button>
            <button type="button" className="flex min-h-11 w-full items-center justify-between rounded-xl border border-line px-3 text-left text-sm">
              <span>Dog range · <strong className="text-danger">UNSET</strong></span>
              <span className="text-xs text-muted">Operating thresholds are not set.</span>
            </button>
            <div className="rounded-xl border border-line p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">Flight profile · <Pill tone="warn">PROPOSED</Pill></p>
                <label className="inline-flex min-h-11 items-center gap-2 text-sm">
                  Enabled · {profile ? "true" : "false"}
                  <input type="checkbox" checked={profile} onChange={(event) => setProfile(event.target.checked)} aria-label="Enable 4 m floor-AGL profile" />
                </label>
              </div>
              <p className="text-xs text-muted">4 m floor-AGL (proposed)</p>
            </div>
            <Notice tone="bad" title="No secrets accepted">
              Credentials, keys, and tokens are refused.
            </Notice>
          </div>
          <Card className="lg:col-span-2">
            <CardTitle title="Vision & budgets" />
            <div className="grid gap-3 sm:grid-cols-2">
              <Labeled label="Model ID" />
              <Labeled label="Prompt version" />
              <Labeled label="Evidence age ms" />
              <Labeled label="Command lease ms" />
            </div>
          </Card>
        </div>
        <Card className="mt-3">
          <CardTitle title="Profile comparison" />
          <p className="text-sm text-muted">Compare current, proposed, and baseline profiles.</p>
          <div className="mt-2 flex flex-wrap gap-3 text-sm">
            {["Current (Active)", "Proposed (4 m)", "Baseline"].map((item) => (
              <label key={item} className="inline-flex min-h-11 items-center gap-2">
                <input type="radio" name="profile-column" checked={column === item} onChange={() => setColumn(item)} />
                {item}
              </label>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">Showing {column}. Unset values stay unknown.</p>
          <table className="mt-2 w-full text-left text-sm">
            <caption className="sr-only">Profile comparison</caption>
            <thead>
              <tr className="text-xs text-muted">
                <th className="py-2">Item</th>
                <th>Current (Active)</th>
                <th>Proposed (4 m)</th>
                <th>Baseline</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row} className="border-t border-line">
                  <th scope="row" className="py-2 font-medium">{row}</th>
                  <td className="font-mono">—</td>
                  <td className="font-mono">—</td>
                  <td className="font-mono">—</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </Card>
    </SlidePage>
  );
}

function Radio({ name, label, checked, onChange }: { name: string; label: string; checked: boolean; onChange: () => void }) {
  return (
    <label className={`inline-flex min-h-11 items-center gap-2 rounded-full border px-3 text-sm ${checked ? "border-blue bg-info-bg" : "border-line"}`}>
      <input type="radio" name={name} checked={checked} onChange={onChange} />
      {label}
    </label>
  );
}

function Labeled({ label }: { label: string }) {
  return (
    <label className="block text-sm">
      {label}
      <select className="mt-1 min-h-11 w-full rounded-xl border border-line bg-surface px-3" aria-label={label} defaultValue="">
        <option value="">—</option>
      </select>
    </label>
  );
}
