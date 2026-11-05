"use client";

import { useMemo, useState } from "react";
import { Layers, RefreshCw, Search, Shield } from "lucide-react";
import { Card, CardTitle, Flow, Pill, SlidePage } from "@/components/console/frame";

type Command = {
  id: string;
  device: string;
  action: string;
  lease: string;
  submitted: string;
  accepted: string;
  running: string;
  completed: string;
  rejected: string;
  timedOut: string;
  unknown: string;
  result: string;
};

const COMMANDS: Command[] = [
  { id: "cmd-drone-x001", device: "Go2 PRO", action: "track_step", lease: "Lease · 300 ms", submitted: "10:24:01", accepted: "10:24:01", running: "10:24:02", completed: "10:24:05", rejected: "—", timedOut: "—", unknown: "—", result: "SIMULATED" },
  { id: "cmd-drone-x002", device: "Go2 PRO", action: "set_mode", lease: "Lease · 300 ms", submitted: "10:23:41", accepted: "10:23:41", running: "—", completed: "10:23:42", rejected: "—", timedOut: "—", unknown: "—", result: "SIMULATED" },
  { id: "cmd-drone-x003", device: "Tello EDU", action: "capture_frame", lease: "Lease · 300 ms", submitted: "10:23:10", accepted: "10:23:11", running: "—", completed: "10:23:12", rejected: "—", timedOut: "—", unknown: "—", result: "SIMULATED" },
  { id: "cmd-drone-x004", device: "Go2 PRO", action: "track_step", lease: "Lease · 300 ms", submitted: "10:22:30", accepted: "10:22:31", running: "—", completed: "—", rejected: "—", timedOut: "10:22:35", unknown: "—", result: "SIMULATED" },
  { id: "cmd-drone-x005", device: "Tello EDU", action: "set_mode", lease: "Lease · 300 ms", submitted: "10:21:54", accepted: "—", running: "—", completed: "—", rejected: "—", timedOut: "—", unknown: "10:21:57", result: "SIMULATED" },
];

export function Slide13() {
  const [device, setDevice] = useState("All");
  const [action, setAction] = useState("All");
  const [status, setStatus] = useState("All");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("cmd-drone-x001");
  const rows = useMemo(
    () =>
      COMMANDS.filter((command) => (device === "All" || command.device === device) && (action === "All" || command.action === action) && (status === "All" || matchesStatus(command, status)) && command.id.includes(query.trim())),
    [device, action, status, query],
  );
  const current = rows.find((command) => command.id === selected) ?? rows[0];
  return (
    <SlidePage
      id="13"
      active="commands"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Rehearsal (Offline)" }}
      chips={[
        { title: "Command control", body: "Issue bounded actions with explicit lease and full lifecycle tracking.", icon: <Layers className="h-5 w-5" /> },
        { title: "Acknowledgements", body: "Capture and time-stamp state changes from the device.", icon: <RefreshCw className="h-5 w-5" /> },
        { title: "Lifecycle visibility", body: "Track through Accepted, Running, Completed, Rejected, Timed Out, Unknown.", icon: <RefreshCw className="h-5 w-5" /> },
        { title: "Rehearsal result", body: "Operations run in a safe rehearsal environment. SIMULATED.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principlesTitle="Command lifecycle"
      principlesNote="Standard lifecycle states for a single command."
      principles={[
        { index: "01", title: "Accepted is not completion", body: "Accepted means the device has received and agreed to the command. It does not mean the action has finished (not a completion signal)." },
        { index: "02", title: "No automatic retry", body: "If a command is Timed Out, there is no automatic retry. Operators must decide whether to reissue a new command." },
        { index: "03", title: "Landing is separate", body: "Landing is a distinct command (for example land) and is not part of the goal (for example track_step). Issue landing explicitly when needed." },
      ]}
    >
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-display text-xl font-semibold">Commands</h2>
            <p className="text-sm text-muted">Issue commands, monitor acknowledgements, and track the lifecycle.</p>
          </div>
          <Pill tone="sim">Rehearsal result · SIMULATED</Pill>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Select label="Device" value={device} options={["All", "Go2 PRO", "Tello EDU"]} onChange={setDevice} />
          <Select label="Action" value={action} options={["All", "track_step", "set_mode", "capture_frame"]} onChange={setAction} />
          <Select label="Status" value={status} options={["All", "Completed", "Timed Out", "Unknown"]} onChange={setStatus} />
          <label className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-line px-3 text-sm">
            <Search className="h-4 w-4" aria-hidden />
            <input aria-label="Search command ID" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search command ID" className="bg-transparent outline-none" />
          </label>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-xs">
            <caption className="sr-only">Command acknowledgements</caption>
            <thead>
              <tr className="text-muted">
                {["Command ID", "Device", "Action (bounded)", "Lease expiry", "Submitted", "Accepted", "Running", "Completed", "Rejected", "Timed Out", "Unknown"].map((header) => (
                  <th key={header} className="py-2">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((command) => (
                <tr key={command.id} className={`cursor-pointer border-t border-line ${command.id === current?.id ? "bg-info-bg" : ""}`} onClick={() => setSelected(command.id)}>
                  <th scope="row" className="py-2 font-mono">{command.id}</th>
                  <td>{command.device}</td>
                  <td className="font-mono">{command.action}</td>
                  <td>{command.lease}</td>
                  <td>{command.submitted}</td>
                  <td>{command.accepted}</td>
                  <td>{command.running}</td>
                  <td>{command.completed}</td>
                  <td>{command.rejected}</td>
                  <td>{command.timedOut}</td>
                  <td>{command.unknown}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {current ? (
          <Card className="mt-3">
            <CardTitle title={`${current.id} · ${current.action}`} extra={<span className="text-xs">Device: {current.device} · {current.lease} · Rehearsal result: {current.result}</span>} />
            <p className="text-sm font-semibold">ACK timeline ({current.id})</p>
            {current.id === "cmd-drone-x001" ? (
              <Flow steps={[{ title: "Submitted", detail: "10:24:01", tone: "ok" }, { title: "Accepted", detail: "10:24:01", tone: "ok" }, { title: "Running", detail: "10:24:02", tone: "info" }, { title: "Completed", detail: "10:24:05", tone: "ok" }]} />
            ) : (
              <p className="text-sm text-muted">Submitted {current.submitted}. Accepted {current.accepted}. Completed {current.completed}. Timed Out {current.timedOut}. Unknown {current.unknown}.</p>
            )}
            <ul className="mt-3 list-disc pl-5 text-sm text-muted">
              <li>A bounded navigation step for the selected device.</li>
              <li>Acknowledgements (ACKs) report lifecycle state changes with timestamps.</li>
              <li>Accepted is not completion.</li>
              <li>Rehearsal result: SIMULATED.</li>
            </ul>
          </Card>
        ) : <p className="mt-3 text-sm">No command matches that filter.</p>}
      </Card>
      <div className="mt-3">
        <Flow steps={[{ title: "Submitted", tone: "neutral" }, { title: "Accepted", tone: "ok" }, { title: "Running", tone: "info" }, { title: "Completed", tone: "ok" }]} />
        <p className="mt-2 text-xs font-semibold text-muted">Terminal branches</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Pill tone="bad">Rejected</Pill>
          <Pill tone="warn">Timed Out</Pill>
          <Pill tone="neutral">Unknown</Pill>
        </div>
      </div>
    </SlidePage>
  );
}

function matchesStatus(command: Command, status: string) {
  if (status === "Completed") return command.completed !== "—";
  if (status === "Timed Out") return command.timedOut !== "—";
  if (status === "Unknown") return command.unknown !== "—";
  return true;
}

function Select({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="text-sm">
      {label}
      <select aria-label={label} className="ml-2 min-h-11 rounded-xl border border-line bg-surface px-2" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    </label>
  );
}
