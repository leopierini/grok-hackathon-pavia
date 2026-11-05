"use client";

import { useState } from "react";
import { requiresRecoveryToken } from "@/lib/actions";
import { useSession } from "@/components/provider";
import { useTheme } from "@/hooks/useTheme";
import { Panel, StatusText } from "@/components/ui";

export function RehearsalSession() {
  const { snapshot, run, pending } = useSession();
  const { theme, setTheme } = useTheme();
  const [scenario, setScenario] = useState("happy_path");
  const [token, setToken] = useState("");
  const [doc, setDoc] = useState("");
  if (!snapshot) return <p className="text-sm text-muted">The operator session has not connected. Scenario, Arm, Supervised, Start, and Reset appear when the Ground API answers.</p>;
  const needsToken = requiresRecoveryToken(snapshot.mission);
  return (
    <div className="space-y-3">
      <Panel title="Scenario">
        <label className="text-sm" htmlFor="scenario">
          Offline scenario
        </label>
        <select
          id="scenario"
          className="mt-1 block rounded border border-line bg-surface px-2 py-2"
          value={scenario}
          onChange={(event) => setScenario(event.target.value)}
        >
          {snapshot.scenarios.map((item) => (
            <option key={item.id} value={item.id}>
              {item.id}
            </option>
          ))}
        </select>
        <p className="mt-2 text-sm text-muted">{snapshot.scenarios.find((item) => item.id === scenario)?.detail}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="rounded border border-line px-3 py-2 text-sm" disabled={!snapshot.actions.arm?.enabled || pending === "arm"} onClick={() => void run("arm")}>
            Arm session {snapshot.session_epoch}
          </button>
          <button type="button" className="rounded border border-line px-3 py-2 text-sm" disabled={!snapshot.actions.supervised?.enabled} onClick={() => void run("supervised")}>
            Supervised
          </button>
          <button type="button" className="rounded bg-info-bg px-3 py-2 text-sm font-semibold text-info" disabled={!snapshot.actions.start?.enabled || pending === "start"} onClick={() => void run("start", { scenario, pace_s: snapshot.config.pace_s, seed: 0 })}>
            Start
          </button>
        </div>
        <p className="mt-2 text-sm">{snapshot.actions.start?.reason}</p>
      </Panel>
      <Panel title="Reset">
        <p className="text-sm">{snapshot.actions.reset?.reason}</p>
        {needsToken && snapshot.actions.reset?.enabled ? (
          <label className="mt-2 block text-sm">
            Recovery token
            <input className="mt-1 block rounded border border-line bg-surface px-2 py-1" value={token} onChange={(event) => setToken(event.target.value)} />
          </label>
        ) : null}
        <button type="button" className="mt-2 rounded border border-line px-3 py-2 text-sm" disabled={!snapshot.actions.reset?.enabled} onClick={() => void run("reset", needsToken ? { recovery_token: token } : {})}>
          Reset
        </button>
      </Panel>
      <Panel title="Documents and theme">
        <div className="flex flex-wrap gap-2">
          {["operator-guide", "ui-architecture", "ui-coverage"].map((name) => (
            <button key={name} type="button" className="rounded border border-line px-3 py-2 text-sm" onClick={() => void fetch(`/api/ground/docs/${name}`).then((response) => response.json()).then((body: { text?: string }) => setDoc(body.text ?? "Document unavailable"))}>
              {name}
            </button>
          ))}
          <button type="button" className="rounded border border-line px-3 py-2 text-sm" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            Theme {theme}
          </button>
        </div>
        {doc ? <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs">{doc}</pre> : null}
      </Panel>
      <Panel title="Coverage pointer">
        <p className="text-sm">Software task progress is on the Coverage page. It is separate from the mission phase <StatusText status={snapshot.mission.phase} />.</p>
      </Panel>
    </div>
  );
}
