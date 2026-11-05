"use client";

import { useState } from "react";
import { groundPath } from "@/lib/api";
import type { OperatorConfig } from "@/lib/types";
import { useSession } from "@/components/provider";
import { Panel } from "@/components/ui";

export function SettingsSession() {
  const { snapshot } = useSession();
  const [draft, setDraft] = useState<OperatorConfig | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  if (!snapshot) return <p className="text-sm text-muted">The operator session has not connected. Transport, vision budgets, and Validate and save appear when the Ground API answers.</p>;
  const config = draft ?? snapshot.config;
  async function save() {
    const payload = { ...config };
    delete payload.secrets;
    const response = await fetch(groundPath("config"), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = (await response.json()) as { ok?: boolean; detail?: string; error?: { detail?: string } };
    setMessage(body.ok ? body.detail ?? "Saved" : body.error?.detail ?? "Rejected");
  }
  return (
    <div className="space-y-3">
      <Panel title="Connection">
        <label className="block text-sm">
          Dog transport
          <select className="mt-1 block rounded border border-line bg-surface px-2 py-1" value={config.dog_transport} onChange={(event) => setDraft({ ...config, dog_transport: event.target.value as "ethernet" | "wifi" })}>
            <option value="ethernet">ethernet</option>
            <option value="wifi">wifi</option>
          </select>
        </label>
        <p className="mt-2 text-sm text-muted">Ethernet and Wi-Fi are separate profiles. Saving does not hand over a live link.</p>
        <label className="mt-3 block text-sm">
          Pi data path
          <select className="mt-1 block rounded border border-line bg-surface px-2 py-1" value={config.pi_data_path ?? ""} onChange={(event) => setDraft({ ...config, pi_data_path: event.target.value || null })}>
            <option value="usb">usb</option>
            <option value="wire">wire</option>
            <option value="second_radio">second radio</option>
            <option value="">unset</option>
          </select>
        </label>
      </Panel>
      <Panel title="Vision and budgets">
        <label className="block text-sm">
          Model id
          <input className="mt-1 block w-full rounded border border-line bg-surface px-2 py-1 font-mono text-xs" value={config.vision.model_id} onChange={(event) => setDraft({ ...config, vision: { ...config.vision, model_id: event.target.value } })} />
        </label>
        <label className="mt-2 block text-sm">
          Prompt version
          <input className="mt-1 block w-full rounded border border-line bg-surface px-2 py-1 font-mono text-xs" value={config.vision.prompt_version} onChange={(event) => setDraft({ ...config, vision: { ...config.vision, prompt_version: event.target.value } })} />
        </label>
        <label className="mt-2 block text-sm">
          Evidence age ms
          <input type="number" className="mt-1 block rounded border border-line bg-surface px-2 py-1" value={config.evidence_age_ms} onChange={(event) => setDraft({ ...config, evidence_age_ms: Number(event.target.value) })} />
        </label>
        <label className="mt-2 block text-sm">
          Command lease ms
          <input type="number" className="mt-1 block rounded border border-line bg-surface px-2 py-1" value={config.command_lease_ms} onChange={(event) => setDraft({ ...config, command_lease_ms: Number(event.target.value) })} />
        </label>
        <p className="mt-2 text-sm text-muted">Changes apply on the next idle session. The API rejects invalid values. Secrets are not accepted in this form.</p>
      </Panel>
      <Panel title="Unset and flight profile">
        <ul className="text-sm">
          {snapshot.unset.map((item) => (
            <li key={item.field}>
              <span className="font-medium">{item.field}.</span> {item.detail}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-sm">Flight profile {config.flight_profile.name} enabled {String(config.flight_profile.enabled)}.</p>
      </Panel>
      <button type="button" className="rounded bg-info-bg px-3 py-2 text-sm font-semibold text-info" onClick={() => void save()}>
        Validate and save
      </button>
      {message ? <p className="text-sm">{message}</p> : null}
    </div>
  );
}
