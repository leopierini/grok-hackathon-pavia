"use client";

import { Clock, Lock, Shield, Target } from "lucide-react";
import { Card, CardTitle, Flow, Notice, Pill, SlidePage } from "@/components/console/frame";
import { DogMark } from "@/components/console/scenes";
import { HaltButton } from "@/components/ui";
import { useHaltAction } from "@/components/console/frame";

const ACKS = [
  ["1", "T + 0 ms", "Accepted", "candidate-forward-01 accepted (approved, safe)."],
  ["2", "T + 28 ms", "Running", "move_local running (lease active)."],
  ["3", "T + 276 ms", "Completed", "step completed within lease (≤ 300 ms)."],
  ["4", "—", "Rejected step", "(none) · not triggered in this run."],
];

export function Slide17() {
  const halt = useHaltAction();
  return (
    <SlidePage
      id="17"
      active="dog-command"
      items={[
        { id: "dog-command", href: "/leases", label: "Dog command" },
        { id: "commands", href: "/commands", label: "ACK track" },
        { id: "evidence", href: "/evidence", label: "Evidence" },
        { id: "navigation", href: "/dog", label: "Leases" },
        { id: "rehearsal", href: "/rehearsal", label: "Rehearsal" },
        { id: "settings", href: "/settings", label: "Settings" },
      ]}
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Safe candidate only", body: "Execute only an approved, safe candidate.", icon: <Shield className="h-5 w-5" /> },
        { title: "Bounded lease", body: "Short, explicit lease (for example 300 ms) for a single step.", icon: <Clock className="h-5 w-5" /> },
        { title: "ACK track", body: "Record Accepted, Running, Completed, or Rejected step.", icon: <Target className="h-5 w-5" /> },
        { title: "Verified stationary", body: "Separate, explicit evidence of stationary state (not inferred).", icon: <Lock className="h-5 w-5" /> },
      ]}
      principlesTitle="Key takeaways"
      principlesNote="Command leases, acknowledgements, and safety invariants (rehearsal/simulated)."
      principles={[
        { index: "01", title: "Safe, single-step command", body: "Use an approved, safe candidate (candidate-forward-01). Execute one bounded step (move_local). Lease · 300 ms." },
        { index: "02", title: "Full ACK track", body: "Explicit states: Accepted, Running, Completed, Rejected step. Time-stamped and ordered for clear traceability." },
        { index: "03", title: "Safety invariants", body: "Priority HALT is always available. Lease expiry is not proof of stop. Expired motion is never auto-repeated. Stationary evidence is separate (Stationary · unknown)." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase text-blue">Dog command</p>
            <h2 className="font-display text-2xl font-semibold">Dog command <Pill tone="sim">Rehearsal / Simulated</Pill></h2>
            <p className="text-sm text-muted">Execute a vetted, lease-bound command as a single, safe step. Acknowledge each state.</p>
          </div>
          <div className="text-right">
            <p className="mb-1 text-xs font-semibold text-danger">Priority HALT</p>
            <HaltButton onHalt={halt} />
          </div>
        </div>
        <div className="mt-4 grid items-center gap-3 lg:grid-cols-[0.5fr_1fr_0.7fr]">
          <DogMark className="h-24 w-32" />
          <div>
            <p className="font-mono text-sm font-semibold">candidate-forward-01</p>
            <p className="font-mono text-sm">move_local</p>
            <p className="text-sm">Lease · 300 ms</p>
          </div>
          <Card>
            <p className="text-xs text-muted">Candidate status</p>
            <p className="font-semibold text-success">Approved (safe)</p>
            <p className="text-xs text-muted">Single step · Rehearsal / Simulated</p>
          </Card>
        </div>
        <div className="mt-4">
          <Flow steps={[{ title: "Accepted", tone: "ok" }, { title: "Running", tone: "info" }, { title: "Completed", tone: "ok" }, { title: "Rejected step", tone: "bad" }]} />
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <Card>
            <CardTitle title="ACK track (detailed)" extra={<Pill tone="sim">Rehearsal / Simulated</Pill>} />
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Dog command acknowledgements</caption>
              <thead>
                <tr className="text-xs uppercase text-muted"><th className="py-2">#</th><th>Time (rel)</th><th>ACK state</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {ACKS.map((row) => (
                  <tr key={row[0]} className="border-t border-line">
                    <td className="py-2">{row[0]}</td>
                    <td className="font-mono">{row[1]}</td>
                    <td><Pill tone={row[2] === "Rejected step" ? "bad" : row[2] === "Running" ? "info" : "ok"}>{row[2]}</Pill></td>
                    <td>{row[3]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card>
            <CardTitle title="Verified-stationary evidence" extra={<Pill tone="sim">Rehearsal / Simulated</Pill>} />
            <p className="text-sm font-semibold">Stationary · unknown</p>
            <dl className="mt-2 space-y-1 text-sm">
              <div className="flex justify-between"><dt className="text-muted">Source</dt><dd>Rehearsal evidence (simulated)</dd></div>
              <div className="flex justify-between"><dt className="text-muted">Scope</dt><dd>independent stationary check</dd></div>
              <div className="flex justify-between"><dt className="text-muted">Result</dt><dd>Unknown (not verified stationary)</dd></div>
            </dl>
            <p className="mt-2 text-xs text-muted">This is separate evidence and not inferred from the command ACK.</p>
          </Card>
        </div>
      </Card>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Notice tone="warn" title="Expired lease is not proof of stop">
          A lease expiring (for example 300 ms elapsed) only bounds the command; it does not confirm the robot has stopped.
        </Notice>
        <Notice tone="info" title="Expired motion is never auto-repeated">
          An expired or incomplete motion is not automatically retried. A new, explicit, approved candidate is required.
        </Notice>
      </div>
    </SlidePage>
  );
}
