export type SlideMeta = {
  id: string;
  href: string;
  title: string;
  lede: string;
  nav: string;
};

export const SLIDES: SlideMeta[] = [
  { id: "01", href: "/", title: "Ground Mission Control", lede: "Precise operations. Verified evidence. Human authority.", nav: "mission" },
  { id: "02", href: "/cockpit", title: "Mission Control cockpit", lede: "One mission. One authoritative phase.", nav: "mission" },
  { id: "03", href: "/mission-state", title: "Mission state & persistent header", lede: "Persistent, authoritative mission state with epoch fencing and explicit fault handling.", nav: "mission" },
  { id: "04", href: "/devices", title: "Devices & Readiness", lede: "Device inventory, connection paths, and capability readiness for operations.", nav: "devices" },
  { id: "05", href: "/settings", title: "Settings & connection profiles", lede: "Configure transport, telemetry, vision, budgets, and flight profile.", nav: "settings" },
  { id: "06", href: "/capabilities", title: "Capability admission & readiness", lede: "Declare, verify, and admit capabilities for controlled mission execution.", nav: "capabilities" },
  { id: "07", href: "/actions", title: "Operator actions & scoped confirmations", lede: "Actions rechecked by Ground. Scoped to mission, epoch, and stage.", nav: "mission" },
  { id: "08", href: "/halt", title: "Halt, cleanup & safe recovery", lede: "Priority safety path for halted operations, cleanup, and controlled recovery.", nav: "mission" },
  { id: "09", href: "/vision", title: "Vision & evidence workspace", lede: "Review multi-view evidence, inspect targets, and issue vision requests.", nav: "vision" },
  { id: "10", href: "/evidence", title: "Frame provenance & validation", lede: "Inspect a single frame’s provenance, integrity, and validation results.", nav: "evidence" },
  { id: "11", href: "/decisions", title: "xAI decision review", lede: "Inspect model result, proposal, and validation for controlled mission decisions.", nav: "vision" },
  { id: "12", href: "/drone", title: "Drone telemetry & bounded action", lede: "Bounded, policy-guarded drone operation with observation, guard result, and movement invalidating a prior beacon hold.", nav: "mission" },
  { id: "13", href: "/commands", title: "Command lifecycle & acknowledgements", lede: "Command submission, acknowledgements, and lifecycle states with clear, verifiable records.", nav: "commands" },
  { id: "14", href: "/navigation", title: "Beacon hold & RSSI navigation", lede: "Beacon-referenced navigation with RSSI, stable hold, and motion-aware gating.", nav: "navigation" },
  { id: "15", href: "/dog", title: "Dog navigation & safe candidates", lede: "Stationary robotics rehearsal. Navigation status, planner health, and approved safe candidates.", nav: "navigation" },
  { id: "16", href: "/telemetry", title: "Pi telemetry & RSSI windows", lede: "Raspberry Pi telemetry on the dog, USB path, heartbeat, and RSSI window samples with quality, age, clock comparability, and data states.", nav: "telemetry" },
  { id: "17", href: "/leases", title: "Dog command leases & acknowledgements", lede: "Single-step, lease-bound command with full ACK track and verified-stationary evidence.", nav: "dog-command" },
  { id: "18", href: "/handoff", title: "RSSI-to-vision handoff", lede: "Two-stage target acquisition: beacon/RSSI approach, then vision verification.", nav: "targets" },
  { id: "19", href: "/proximity", title: "Proximity goal gate", lede: "Fuses independent proximity evidence to decide goal arrival.", nav: "mission" },
  { id: "20", href: "/recovery", title: "Goal, landing & recovery", lede: "Separate results for mission goal, landing, and recovery, with independent actions and controls.", nav: "mission" },
  { id: "21", href: "/runs", title: "Runs, event journal & inspector", lede: "Operational run history, chronological event journal, and structured message inspection.", nav: "runs" },
  { id: "22", href: "/metrics", title: "Run metrics & performance summary", lede: "Measured intervals, operation counts, and run health with explicit data sources and clock basis.", nav: "runs" },
  { id: "23", href: "/rehearsal", title: "Offline rehearsal & operator runbook", lede: "Rehearse missions offline, inject faults, and follow a concise operator runbook.", nav: "rehearsal" },
  { id: "24", href: "/design-system", title: "Design-System Specification", lede: "Final UI design system: tokens, components, patterns, and screen coverage.", nav: "mission" },
];

export type NavItem = { id: string; href: string; label: string };

export const NAV_MAIN: NavItem[] = [
  { id: "mission", href: "/cockpit", label: "Mission" },
  { id: "devices", href: "/devices", label: "Devices" },
  { id: "vision", href: "/vision", label: "Vision" },
  { id: "navigation", href: "/navigation", label: "Navigation" },
  { id: "commands", href: "/commands", label: "Commands" },
  { id: "runs", href: "/runs", label: "Runs" },
  { id: "rehearsal", href: "/rehearsal", label: "Rehearsal" },
  { id: "coverage", href: "/coverage", label: "Coverage" },
  { id: "settings", href: "/settings", label: "Settings" },
];

export function slideForPath(pathname: string): SlideMeta | null {
  if (pathname === "/coverage") return SLIDES.find((slide) => slide.id === "24") ?? null;
  if (pathname.startsWith("/runs/") && pathname !== "/runs") return SLIDES.find((slide) => slide.id === "21") ?? null;
  return SLIDES.find((slide) => slide.href === pathname) ?? null;
}

export function neighbors(id: string): { prev: SlideMeta; next: SlideMeta; index: number } {
  const index = Math.max(0, SLIDES.findIndex((slide) => slide.id === id));
  const prev = SLIDES[(index - 1 + SLIDES.length) % SLIDES.length];
  const next = SLIDES[(index + 1) % SLIDES.length];
  return { prev, next, index };
}
