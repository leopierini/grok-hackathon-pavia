"use client";

import { Activity, Cpu, HeartPulse, Usb } from "lucide-react";
import { Card, CardTitle, Pill, SlidePage } from "@/components/console/frame";
import { LineChart } from "@/components/console/charts";
import { DogMark } from "@/components/console/scenes";

const WINDOWS = [
  { id: "W-0104", time: "10:24:00", samples: "-56, -55, -54, -57, -55", median: "-55", quality: "valid", validity: "Valid" },
  { id: "W-0105", time: "10:25:00", samples: "-53, -52, -54, -53, -52", median: "-53", quality: "valid", validity: "Valid" },
  { id: "W-0106", time: "10:26:00", samples: "-58, -59, -57, -60, -58", median: "-58", quality: "valid", validity: "Valid" },
  { id: "W-0107", time: "10:27:00", samples: "-62, -61, -62, -63, -61", median: "-62", quality: "noisy", validity: "Noisy" },
  { id: "W-0108", time: "10:28:00", samples: "(missing)", median: "—", quality: "missing", validity: "Missing" },
];

export function Slide16() {
  return (
    <SlidePage
      id="16"
      active="telemetry"
      items={[
        { id: "telemetry", href: "/telemetry", label: "Telemetry" },
        { id: "navigation", href: "/navigation", label: "RSSI windows" },
        { id: "activity", href: "/telemetry", label: "Heartbeat" },
        { id: "devices", href: "/devices", label: "Device" },
        { id: "runs", href: "/runs", label: "Data states" },
        { id: "settings", href: "/settings", label: "Settings" },
      ]}
      topbar={{ mode: "SIMULATED", note: "Telemetry Console · Raspberry Pi (Dog)" }}
      chips={[
        { title: "Raspberry Pi on dog", body: "Onboard compute for telemetry and RF RSSI collection.", icon: <Cpu className="h-5 w-5" /> },
        { title: "Path · USB", body: "Telemetry path from Raspberry Pi to the operator console.", icon: <Usb className="h-5 w-5" /> },
        { title: "RSSI windows", body: "Windowed samples (dBm) with quality and validity.", icon: <Activity className="h-5 w-5" /> },
        { title: "Heartbeat", body: "Liveness signal from the Raspberry Pi (telemetry loop).", icon: <HeartPulse className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "RSSI ≠ distance", body: "RSSI is received signal strength in dBm and does not directly indicate distance." },
        { index: "02", title: "Comparability", body: "Clock · comparable (epochs aligned). Signals are comparable across windows when clocks and settings are consistent. Age · unknown." },
        { index: "03", title: "Key values (current)", body: "Median RSSI · -54 dBm. Quality · valid. Age · unknown. Clock · comparable." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-2xl font-semibold">Telemetry — Raspberry Pi on Dog</h2>
          <div className="flex gap-2">
            <Pill tone="sim">SIMULATED</Pill>
            <Pill tone="ok">RUNNING</Pill>
          </div>
        </div>
        <p className="text-sm text-muted">Live telemetry and RSSI (dBm) windows from the Raspberry Pi.</p>
        <div className="mt-4 grid gap-3 lg:grid-cols-[0.7fr_1.3fr]">
          <Card>
            <DogMark className="h-20 w-28" />
            <p className="font-semibold">Raspberry Pi on dog</p>
          </Card>
          <dl className="grid gap-2 sm:grid-cols-2">
            <Stat k="Path · USB" v="USB" />
            <Stat k="Median RSSI" v="-54 dBm" />
            <Stat k="Quality" v="valid" />
            <Stat k="Age" v="unknown" />
            <Stat k="Clock" v="comparable" />
            <Stat k="Heartbeat" v="Alive" />
          </dl>
        </div>
        <Card className="mt-3">
          <CardTitle title="RSSI (dBm) — Recent Windows" extra={<Pill tone="info">RSSI ≠ distance</Pill>} />
          <LineChart values={[-56, -52, -50, -54, -58, -57, -60, -62]} min={-90} max={-30} yTicks={[-30, -50, -70, -90]} caption="Recent RSSI windows around minus 54 dBm" />
        </Card>
        <Card className="mt-3">
          <CardTitle title="Data states (RSSI windows)" />
          <ul className="grid gap-2 text-sm sm:grid-cols-2">
            <li><Pill tone="ok">Valid</Pill> Complete, in-range, and stable.</li>
            <li><Pill tone="neutral">Missing</Pill> Expected window not received.</li>
            <li><Pill tone="warn">Empty</Pill> Window received but no samples.</li>
            <li><Pill tone="warn">Noisy</Pill> Samples present but high variance (outlier / unstable).</li>
          </ul>
        </Card>
        <Card className="mt-3">
          <CardTitle title="RSSI Window Samples (Raw, dBm)" extra={<span className="text-xs text-muted">Illustrative fixture values (simulated)</span>} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <caption className="sr-only">RSSI window samples</caption>
              <thead>
                <tr className="text-xs uppercase text-muted">
                  {["Window", "Time (HH:MM:SS)", "Samples (dBm)", "Median (dBm)", "Quality", "Validity"].map((header) => <th key={header} className="py-2">{header}</th>)}
                </tr>
              </thead>
              <tbody>
                {WINDOWS.map((window) => (
                  <tr key={window.id} className="border-t border-line">
                    <th scope="row" className="py-2 font-mono">{window.id}</th>
                    <td className="font-mono">{window.time}</td>
                    <td className="font-mono text-xs">{window.samples}</td>
                    <td className="font-mono">{window.median}</td>
                    <td>{window.quality}</td>
                    <td><Pill tone={window.validity === "Valid" ? "ok" : "warn"}>{window.validity}</Pill></td>
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

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2">
      <p className="text-xs text-muted">{k}</p>
      <p className="font-semibold">{v}</p>
    </div>
  );
}
