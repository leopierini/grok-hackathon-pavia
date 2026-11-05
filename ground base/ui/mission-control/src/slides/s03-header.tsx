"use client";

import { Layers, Shield } from "lucide-react";
import { Card, Pill, SlidePage } from "@/components/console/frame";
import { HaltButton } from "@/components/ui";
import { useHaltAction } from "@/components/console/frame";

const PHASES = ["IDLE", "CONNECT", "SCOUT", "TRACK", "HOLD", "HOME", "DOG_VISION", "PROXIMITY", "LAND", "DONE"];

export function Slide03() {
  const halt = useHaltAction();
  return (
    <SlidePage
      id="03"
      active="mission"
      topbar={{ mode: "SIMULATION", note: "Operator", meta: ["M-0247", "Epoch 12", "Connected"] }}
      chips={[
        { title: "Persistent header", body: "Mission, epoch, connection, mode, device modes, phase, arming, fault, and HALT.", icon: <Layers className="h-5 w-5" /> },
        { title: "Authoritative state", body: "Phase is authoritative across the system.", icon: <Shield className="h-5 w-5" /> },
        { title: "Epoch fencing", body: "Monotonic epoch (e.g., Epoch 12) for safe, consistent mission control.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Epoch fencing", body: "Monotonic epoch (e.g., Epoch 12). Gates commands and state transitions. Prevents stale or out-of-order control." },
        { index: "02", title: "Backend authority", body: "Mission phase is authoritative from the backend. Header reflects the backend state (phase, arming, fault). Persistent across views; the HALT control is always available." },
      ]}
    >
      <div className="space-y-3">
        <HeaderState
          index="01"
          title="Idle / Unarmed"
          mode="SIMULATION"
          phase="IDLE"
          arming="UNARMED"
          devices="Robot: Standby · Drone: Standby"
          connection="Connected"
          alert=""
          onHalt={halt}
        />
        <HeaderState
          index="02"
          title="In-progress"
          mode="SIMULATION"
          phase="SCOUT"
          arming="ARMED"
          devices="Robot: Active · Drone: Active"
          connection="Connected"
          alert=""
          onHalt={halt}
        />
        <HeaderState
          index="03"
          title="Fault / Recovery Required"
          mode="RECOVERY"
          phase="HOLD"
          arming="UNARMED"
          devices="Robot: Safe · Drone: Safe"
          connection="Connected"
          alert="RECOVERY REQUIRED"
          onHalt={halt}
        />
        <Card>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="font-display text-lg font-semibold">Mission phase rail</h2>
            <Pill tone="info">Phase is authoritative</Pill>
            <p className="text-sm text-muted">Single source of truth for mission progression and branching.</p>
          </div>
          <ol className="flex flex-wrap items-center gap-2 text-[11px] font-semibold text-muted">
            {PHASES.map((phase, index) => (
              <li key={phase} className="flex items-center gap-2">
                <span className={`grid h-5 w-5 place-items-center rounded-full border ${phase === "DONE" ? "border-success text-success" : "border-line"}`}>{phase === "DONE" ? "✓" : ""}</span>
                {phase}
                {index < PHASES.length - 1 ? <span aria-hidden>→</span> : null}
              </li>
            ))}
          </ol>
          <div className="mt-4 flex flex-wrap gap-3">
            <span className="rounded-full bg-bad-bg px-3 py-1 text-xs font-bold text-bad">FAULT</span>
            <span className="rounded-full bg-warn-bg px-3 py-1 text-xs font-bold text-warn">ABORTED</span>
          </div>
        </Card>
        <div className="grid gap-3 md:grid-cols-2">
          <Compact tone="light" />
          <Compact tone="dark" />
        </div>
      </div>
    </SlidePage>
  );
}

function HeaderState({
  index,
  title,
  mode,
  phase,
  arming,
  devices,
  connection,
  alert,
  onHalt,
}: {
  index: string;
  title: string;
  mode: string;
  phase: string;
  arming: string;
  devices: string;
  connection: string;
  alert: string;
  onHalt: () => void;
}) {
  return (
    <Card>
      <p className="text-xs font-bold text-blue">{index}</p>
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      <div className="mt-3 overflow-hidden rounded-xl bg-deep text-white">
        <div className="flex flex-wrap items-center gap-2 px-3 py-2 text-[11px]">
          <span>GROUND / MISSION CONTROL</span>
          <span>M-0247</span>
          <span>Epoch 12</span>
          <span className="text-success">{connection}</span>
          <span className={alert ? "rounded-full bg-danger px-2 py-0.5 font-bold" : "rounded-full bg-blue px-2 py-0.5 font-bold"}>{alert || mode}</span>
          <span className="ml-auto">Operator</span>
        </div>
        <div className="flex flex-wrap items-center gap-2 bg-[#0e1a2c] px-3 py-2 text-[11px]">
          <Stat k="Mission" v="M-0247" />
          <Stat k="Epoch" v="Epoch 12" />
          <Stat k="Connection" v={connection} />
          <Stat k="Mode" v={alert ? "RECOVERY" : mode} />
          <Stat k="Device modes" v={devices} />
          <Stat k="Phase" v={phase} />
          <Stat k="Arming" v={arming} />
          {alert ? <span className="rounded-full bg-danger px-2 py-0.5 font-bold">Fault {alert}</span> : null}
          <span className="ml-auto">
            <HaltButton onHalt={onHalt} />
          </span>
        </div>
      </div>
    </Card>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <span className="rounded-lg bg-white/5 px-2 py-1">
      <span className="block text-[9px] uppercase text-slate-400">{k}</span>
      {v}
    </span>
  );
}

function Compact({ tone }: { tone: "light" | "dark" }) {
  const dark = tone === "dark";
  return (
    <div className={`rounded-xl px-3 py-2 text-xs ${dark ? "bg-deep text-white" : "border border-line bg-white text-ink"}`}>
      <p className="mb-1 text-[10px] uppercase tracking-wide text-muted">{dark ? "Dark header (compact)" : "Light header (compact)"}</p>
      <p>GROUND / MISSION CONTROL · M-0247 · Epoch 12 · SIMULATION</p>
    </div>
  );
}
