"use client";

import { Card, Pill, SlidePage } from "@/components/console/frame";
import { HaltButton } from "@/components/ui";
import { useHaltAction } from "@/components/console/frame";
import { useTheme } from "@/hooks/useTheme";

const COLORS = [
  ["Canvas", "#F6FAFF"],
  ["Surface", "#FFFFFF"],
  ["Graphite", "#111B2C"],
  ["Deep", "#14243A"],
  ["Border", "#D6E4F5"],
  ["Electric Blue", "#1769FF"],
  ["Cyan", "#39C7F4"],
  ["Success", "#16A879"],
  ["Warning", "#F2A33A"],
  ["Error", "#E85A67"],
  ["Muted", "#66768F"],
  ["Dark Canvas", "#0B1220"],
  ["Dark Surface", "#111C2D"],
  ["Text", "#16243A"],
  ["Dark Canvas alt", "#081220"],
];

const COVERAGE = [
  ["1", "Foundation & protocol", "01 11"],
  ["2", "Devices & readiness", "02 08 12 30"],
  ["3", "Mission & workflow", "03 09 13 26 27"],
  ["4", "Runs & metrics", "04 29 31"],
  ["5", "Commands & safety", "05 07 10 17 18 23 24 28"],
  ["6", "Vision & evidence", "06 14 15 16"],
  ["7", "Navigation & handoff", "19 20 21 22 25"],
  ["8", "Rehearsal", "32"],
];

const SPACING = [4, 8, 12, 16, 24, 32, 40, 48, 64];
const RADII = [0, 4, 8, 12, 16, 24];
const TYPE_SCALE = [
  ["H1", "40 / 48", "Space Grotesk Bold"],
  ["H2", "28 / 36", "Space Grotesk Semibold"],
  ["H3", "20 / 28", "Space Grotesk Semibold"],
  ["Body L", "16 / 24", "Inter Medium"],
  ["Body", "14 / 20", "Inter Regular"],
  ["Small", "12 / 16", "Inter Regular"],
  ["Mono", "13 / 20", "JetBrains Mono"],
];
const MODULES = [
  ["Mission", "01, 02, 03, 04", "4"],
  ["Devices", "05, 06, 07, 08", "4"],
  ["Vision", "09, 10, 11, 12", "4"],
  ["Navigation", "13, 14, 15, 16", "4"],
  ["Commands", "17, 18, 19, 20", "4"],
  ["Runs", "21, 22, 23, 24", "4"],
  ["Rehearsal", "25, 26, 27, 28", "4"],
  ["Settings", "29, 30, 31, 32", "4"],
];
const WORKFLOWS = [
  ["01", "Mission & setup", "01–04", "4 / 4"],
  ["02", "Devices & connectivity", "05–07", "3 / 3"],
  ["03", "Simulation & mode", "08–10", "3 / 3"],
  ["04", "Vision & evidence", "11–14", "4 / 4"],
  ["05", "Commands & execution", "15–18", "4 / 4"],
  ["06", "Navigation & planning", "19–21", "3 / 3"],
  ["07", "Handoff & control", "22–25", "4 / 4"],
  ["08", "Review, logs & rehearsal", "26–32", "7 / 7"],
];
const SAMPLE_ROWS = [
  ["M-0247", "Drone", "Ready", "SIMULATION", "10:27:18"],
  ["M-0315", "Robot", "Armed", "SCOUT", "10:26:49"],
  ["M-0316", "Gate", "Warning", "HOLD", "10:25:12"],
];

export function Slide24() {
  const halt = useHaltAction();
  const { theme, setTheme } = useTheme();
  return (
    <SlidePage
      id="24"
      active="mission"
      topbar={{ mode: "SIMULATION", note: "Design proposal" }}
      chips={[{ title: "Design proposal", body: "Not implementation evidence or hardware verification. Tokens, components, patterns, and screen coverage.", icon: <span className="font-mono text-xs">Aa</span> }]}
      principlesTitle="Design coverage · 32 implementation assignments"
      principlesNote="UI surface mapping only. Status verified separately."
      principles={COVERAGE.map((row) => ({ index: row[0].padStart(2, "0"), title: row[1], body: `Coverage IDs ${row[2]}` }))}
    >
      <p className="mb-3 rounded-xl bg-info-bg px-3 py-2 text-sm font-semibold text-info">DESIGN PROPOSAL · NOT IMPLEMENTATION OR HARDWARE VERIFICATION</p>
      <div className="grid gap-3 lg:grid-cols-2">
        <Mini tone="light" />
        <Mini tone="dark" />
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Card>
          <h2 className="font-display text-lg font-semibold">Color Palette (tokens)</h2>
          <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {COLORS.map((color) => (
              <li key={color[1]} className="rounded-xl border border-line p-2">
                <span className="block h-8 rounded-md border border-line" style={{ background: color[1] }} />
                <span className="mt-1 block text-xs font-semibold">{color[0]}</span>
                <span className="font-mono text-[11px] text-muted">{color[1]}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h2 className="font-display text-lg font-semibold">Typography</h2>
          <p className="text-xs text-muted">Space Grotesk / Inter / JetBrains Mono</p>
          <p className="mt-3 font-display text-4xl">Aa <span className="text-base">Space Grotesk — Headings & display</span></p>
          <p className="mt-2 text-base">Aa Inter — UI text, labels, navigation</p>
          <p className="mt-2 font-mono text-sm">Aa JetBrains Mono — Code, IDs, technical data</p>
          <h3 className="mt-4 font-semibold">Buttons & Chips</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" className="min-h-11 rounded-xl bg-blue px-3 text-sm font-semibold text-white">Primary</button>
            <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Secondary</button>
            <button type="button" className="min-h-11 rounded-xl bg-surface-2 px-3 text-sm">Tertiary</button>
            <HaltButton onHalt={halt} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Pill tone="sim">SIMULATION</Pill>
            <Pill tone="ok">Ready</Pill>
            <Pill tone="info">Executing</Pill>
            <Pill tone="warn">Incomplete</Pill>
            <Pill tone="neutral">Unknown</Pill>
          </div>
          <h3 className="mt-4 font-semibold">State Semantics</h3>
          <ul className="mt-2 space-y-1 text-sm">
            <li><Pill tone="ok">Success</Pill> Valid / ready</li>
            <li><Pill tone="info">Active</Pill> Executing / in progress</li>
            <li><Pill tone="warn">Warning</Pill> Attention / review</li>
            <li><Pill tone="bad">Error</Pill> Blocked / invalid</li>
            <li><Pill tone="neutral">Neutral</Pill> Not started / unknown</li>
            <li><Pill tone="warn">Pending</Pill> Not started or waiting</li>
            <li><Pill tone="info">Info</Pill> Context, advisory, or status detail</li>
          </ul>
        </Card>
      </div>
      <Card className="mt-3">
        <h2 className="font-display text-lg font-semibold">Spacing (8 px grid)</h2>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          {SPACING.map((size) => (
            <div key={size}>
              <div className="rounded-md bg-blue/20" style={{ width: size, height: size }} />
              <p className="mt-1 text-[10px] text-muted">{size} px</p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted">4 Micro · 8 Tight · 12 Compact · 16 Default · 24 Section · 32 Group · 40 Layout · 48 · 64 Page</p>
        <h3 className="mt-4 font-semibold">Corner radius</h3>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          {RADII.map((radius) => (
            <div key={radius}>
              <div className="h-10 w-10 border border-blue bg-blue/10" style={{ borderRadius: radius }} />
              <p className="mt-1 text-[10px] text-muted">r{radius}</p>
            </div>
          ))}
        </div>
      </Card>
      <Card className="mt-3">
        <h2 className="font-display text-lg font-semibold">Type scale</h2>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">Type scale</caption>
          <thead><tr className="text-xs uppercase text-muted"><th className="py-2">Style</th><th>Size / line</th><th>Face</th></tr></thead>
          <tbody>
            {TYPE_SCALE.map((row) => (
              <tr key={row[0]} className="border-t border-line"><td className="py-2 font-semibold">{row[0]}</td><td className="font-mono text-xs">{row[1]}</td><td>{row[2]}</td></tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card className="mt-3">
        <h2 className="font-display text-lg font-semibold">Buttons, badges, and operator table</h2>
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" className="min-h-11 rounded-xl bg-blue px-3 text-sm font-semibold text-white">Execute</button>
          <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Plan</button>
          <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Review</button>
          <button type="button" className="min-h-11 rounded-xl bg-transparent px-3 text-sm">Ghost</button>
          <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">New</button>
          <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Cancel</button>
          <button type="button" className="min-h-11 rounded-xl bg-surface-2 px-3 text-sm" disabled>Execute (Disabled)</button>
          <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm">Switch to Live</button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {["SIM", "LIVE", "READY", "ARMED", "HOLD", "RECOVERY", "FAULT", "BLOCKED", "Running", "Offline", "Draft", "Verified", "Attention"].map((badge) => (
            <Pill key={badge} tone={badge === "FAULT" || badge === "BLOCKED" ? "bad" : badge === "HOLD" || badge === "Attention" || badge === "RECOVERY" ? "warn" : badge === "READY" || badge === "Verified" || badge === "ARMED" ? "ok" : "info"}>{badge}</Pill>
          ))}
        </div>
        <table className="mt-4 w-full text-left text-sm">
          <caption className="sr-only">Operator sample rows</caption>
          <thead><tr className="text-xs uppercase text-muted"><th className="py-2">ID</th><th>Type</th><th>Status</th><th>Mode</th><th>Last Update</th></tr></thead>
          <tbody>
            {SAMPLE_ROWS.map((row) => (
              <tr key={row[0]} className="border-t border-line"><td className="py-2 font-mono">{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td><td className="font-mono text-xs">{row[4]}</td></tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Card><h3 className="font-semibold">Empty state</h3><p className="mt-1 text-sm text-muted">No missions yet. Create a mission or import a plan to get started.</p><button type="button" className="mt-3 min-h-11 rounded-xl bg-blue px-3 text-sm font-semibold text-white">Create Mission</button></Card>
        <Card><h3 className="font-semibold">Unknown state</h3><p className="mt-1 text-sm text-muted">State unknown. No status resolved. Check connection and retry.</p><button type="button" className="mt-3 min-h-11 rounded-xl border border-line px-3 text-sm">Retry</button></Card>
        <Card><h3 className="font-semibold">Blocked state</h3><p className="mt-1 text-sm text-muted">Blocked. Action is blocked by mission policy or a prerequisite.</p><button type="button" className="mt-3 min-h-11 rounded-xl border border-line px-3 text-sm">View Requirement</button></Card>
        <Card><h3 className="font-semibold">Fault state</h3><p className="mt-1 text-sm text-muted">Fault detected. A fault was reported by the device.</p><button type="button" className="mt-3 min-h-11 rounded-xl bg-[#E85A67] px-3 text-sm font-semibold text-white">Recovery Plan</button></Card>
      </div>
      <Card className="mt-3">
        <h2 className="font-display text-lg font-semibold">Design coverage map — Task IDs 01–32</h2>
        <p className="text-sm text-muted">Distribution of task IDs to operator UI modules. Design coverage only, not implementation status.</p>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">Task module map</caption>
          <thead><tr className="text-xs uppercase text-muted"><th className="py-2">Module</th><th>Task IDs</th><th>Count</th></tr></thead>
          <tbody>
            {MODULES.map((row) => (
              <tr key={row[0]} className="border-t border-line"><td className="py-2">{row[0]}</td><td className="font-mono text-xs">{row[1]}</td><td>{row[2]}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-sm">Coverage summary: total task IDs 32. Modules 8. Distribution 4 tasks per module. UI design coverage only. Not all tasks are implemented.</p>
      </Card>
      <Card className="mt-3">
        <h2 className="font-display text-lg font-semibold">Implementation coverage — 32 tasks across 8 operator workflows</h2>
        <ul className="mt-2 grid gap-2 md:grid-cols-2">
          {WORKFLOWS.map((row) => (
            <li key={row[0]} className="rounded-xl border border-line px-3 py-2 text-sm">
              <span className="font-semibold">{row[0]} {row[1]}</span>
              <span className="mt-1 block font-mono text-xs text-muted">{row[2]} · {row[3]}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm font-semibold">Overall coverage 01–32 · 8 operator workflows · 32 implementation tasks · 24 / 24 slides</p>
      </Card>
      <Card className="mt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-lg font-semibold">Theme preview</h2>
          <button type="button" className="min-h-11 rounded-xl border border-line px-3 text-sm" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            Switch to {theme === "dark" ? "light" : "dark"}
          </button>
        </div>
        <p className="mt-2 text-sm text-muted">Current document theme: {theme}. Light and dark surfaces use the tokens above.</p>
      </Card>
      <Card className="mt-3">
        <h2 className="font-display text-lg font-semibold">Coverage table</h2>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">Design coverage assignments</caption>
          <thead><tr className="text-xs uppercase text-muted"><th className="py-2">#</th><th>Task area</th><th>Coverage IDs (screens)</th></tr></thead>
          <tbody>
            {COVERAGE.map((row) => (
              <tr key={row[0]} className="border-t border-line"><td className="py-2">{row[0]}</td><td>{row[1]}</td><td className="font-mono text-xs">{row[2]}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-center text-xs font-semibold tracking-wide text-muted">24 / 24 · 24 visual concept slides</p>
      </Card>
    </SlidePage>
  );
}

function Mini({ tone }: { tone: "light" | "dark" }) {
  const dark = tone === "dark";
  return (
    <Card>
      <p className="text-sm font-semibold">{dark ? "Dark UI (core surface)" : "Light UI (core surface)"}</p>
      <div className={`mt-2 overflow-hidden rounded-xl ${dark ? "bg-[#0B1220] text-white" : "bg-white text-[#16243A]"}`}>
        <div className={`flex gap-2 px-2 py-2 text-[10px] ${dark ? "bg-[#111C2D]" : "bg-[#14243A] text-white"}`}>
          <span className="rounded bg-blue px-1">MISSION</span>
          <span>DEVICES</span>
          <span>VISION</span>
          <span className="ml-auto">SIMULATION</span>
        </div>
        <div className="p-3 text-xs">
          <p className="font-semibold">Site Survey — Sector A</p>
          <p className="text-[10px] opacity-70">Plan · Initialize · Execute</p>
        </div>
      </div>
    </Card>
  );
}
