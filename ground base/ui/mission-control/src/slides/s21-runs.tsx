"use client";

import { useMemo, useState } from "react";
import { FileText, Search, Shield } from "lucide-react";
import { Card, CardTitle, Notice, Pill, SlidePage } from "@/components/console/frame";

const RUNS = [
  { id: "R-0279", mission: "M-0247 / E12", mode: "SIMULATION", start: "2025-01-26 09:02:11", duration: "00:24:31", status: "Completed" },
  { id: "R-0278", mission: "M-0247 / E12", mode: "SIMULATION", start: "2025-01-26 08:37:05", duration: "00:19:46", status: "Running" },
  { id: "R-0277", mission: "M-0246 / E11", mode: "REHEARSAL", start: "2025-01-26 07:58:18", duration: "00:18:07", status: "Completed" },
];

const EVENTS = [
  { n: "1280", time: "2025-01-26 08:56:27.418", source: "nav", severity: "INFO", message: "state.update" },
  { n: "1281", time: "2025-01-26 08:56:27.842", source: "vision", severity: "INFO", message: "perception.objects" },
  { n: "1282", time: "2025-01-26 08:56:28.019", source: "ctl", severity: "WARN", message: "latency.high" },
  { n: "1283", time: "2025-01-26 08:56:28.401", source: "plan", severity: "INFO", message: "waypoint.advance" },
  { n: "1284", time: "2025-01-26 08:56:28.907", source: "bus", severity: "INFO", message: "message.envelope_v2" },
];

export function Slide21() {
  const [run, setRun] = useState("R-0278");
  const [source, setSource] = useState("All Sources");
  const [severity, setSeverity] = useState("All Severities");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("1284");
  const events = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return EVENTS.filter((event) => (source === "All Sources" || event.source === source) && (severity === "All Severities" || event.severity === severity) && `${event.n} ${event.message} ${event.source}`.toLowerCase().includes(needle));
  }, [source, severity, query]);
  const event = EVENTS.find((item) => item.n === selected);
  return (
    <SlidePage
      id="21"
      active="runs"
      topbar={{ mode: "SIMULATION", note: "Local Operator Console · Offline Capable" }}
      chips={[
        { title: "Run history", body: "Browse past and active simulation runs with status and key context.", icon: <FileText className="h-5 w-5" /> },
        { title: "Event journal", body: "Searchable, paginated chronological log of system events.", icon: <Search className="h-5 w-5" /> },
        { title: "Message inspector", body: "Structured view of the selected message, including v2 envelope and validation.", icon: <Search className="h-5 w-5" /> },
        { title: "Schema (proposed)", body: "Team schema is proposed-1 and remains provisional.", icon: <Shield className="h-5 w-5" /> },
      ]}
      principles={[
        { index: "01", title: "Run history", body: "Select a run to load its chronological journal and inspect individual messages." },
        { index: "02", title: "Event journal", body: "Search and paginate events in order. Filter by source and severity. Select an event to view its v2 envelope." },
        { index: "03", title: "Message inspector", body: "Shows envelope fields (message_id, correlation_id, mission/epoch, publisher seq, timestamp, protocol version). Displays validation (accepted/rejected) and operator-feed writer state (queued/flushed/published)." },
      ]}
    >
      <Notice tone="warn" title="The proposed team schema remains provisional.">
        Interface and envelope details may change before finalization.
      </Notice>
      <Card className="mt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-xl font-semibold">Runs & Logs</h2>
          <div className="flex gap-2">
            <Pill tone="info">protocol · 2.0-draft</Pill>
            <Pill tone="neutral">legacy contract · v1.0 unchanged</Pill>
          </div>
        </div>
        <div className="mt-3 grid gap-3 xl:grid-cols-[1fr_0.8fr]">
          <div className="space-y-3">
            <Card>
              <CardTitle title="Run History" />
              <table className="w-full text-left text-xs">
                <caption className="sr-only">Run history</caption>
                <thead>
                  <tr className="text-muted">{["Run ID", "Mission / Epoch", "Mode", "Start (UTC)", "Duration", "Status"].map((header) => <th key={header} className="py-2">{header}</th>)}</tr>
                </thead>
                <tbody>
                  {RUNS.map((item) => (
                    <tr key={item.id} className={`border-t border-line ${item.id === run ? "bg-info-bg" : ""}`}>
                      <th scope="row">
                        <label className="inline-flex min-h-11 items-center gap-2 font-mono">
                          <input type="radio" name="run" checked={run === item.id} onChange={() => setRun(item.id)} />
                          {item.id}
                        </label>
                      </th>
                      <td>{item.mission}</td>
                      <td>{item.mode}</td>
                      <td className="font-mono">{item.start}</td>
                      <td className="font-mono">{item.duration}</td>
                      <td><Pill tone={item.status === "Running" ? "info" : "ok"}>{item.status}</Pill></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card>
              <CardTitle title="Event Journal" extra={<span className="text-xs">Run: {run} · 1,284 events · 1 / 26</span>} />
              <div className="flex flex-wrap gap-2">
                <label className="inline-flex min-h-11 items-center gap-2 text-sm">
                  <Search className="h-4 w-4" aria-hidden />
                  <input aria-label="Search journal" value={query} onChange={(event) => setQuery(event.target.value)} className="rounded-xl border border-line bg-surface px-2 py-1" placeholder="Search journal" />
                </label>
                <select aria-label="Source" className="min-h-11 rounded-xl border border-line bg-surface px-2" value={source} onChange={(event) => setSource(event.target.value)}>
                  {["All Sources", "nav", "vision", "ctl", "plan", "bus"].map((item) => <option key={item}>{item}</option>)}
                </select>
                <select aria-label="Severity" className="min-h-11 rounded-xl border border-line bg-surface px-2" value={severity} onChange={(event) => setSeverity(event.target.value)}>
                  {["All Severities", "INFO", "WARN"].map((item) => <option key={item}>{item}</option>)}
                </select>
              </div>
              <table className="mt-2 w-full text-left text-xs">
                <caption className="sr-only">Event journal</caption>
                <thead>
                  <tr className="text-muted"><th className="py-2">#</th><th>Timestamp (UTC)</th><th>Source</th><th>Severity</th><th>Event / Message</th></tr>
                </thead>
                <tbody>
                  {events.map((item) => (
                    <tr key={item.n} className={`cursor-pointer border-t border-line ${selected === item.n ? "bg-info-bg" : ""}`} onClick={() => setSelected(item.n)}>
                      <td className="py-2 font-mono">{item.n}</td>
                      <td className="font-mono">{item.time}</td>
                      <td>{item.source}</td>
                      <td><Pill tone={item.severity === "WARN" ? "warn" : "info"}>{item.severity}</Pill></td>
                      <td className="font-mono">{item.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {events.length === 0 ? <p className="mt-2 text-sm">No journal rows match that filter.</p> : null}
            </Card>
          </div>
          <Card>
            <CardTitle title="Message Inspector" extra={<Pill>v2</Pill>} />
            {event ? (
              <div className="space-y-1 text-sm">
                <p className="font-mono font-semibold">message.envelope_v2</p>
                <p className="font-mono text-xs"># {event.n} · {event.source} · {event.severity}</p>
                <h3 className="pt-2 font-semibold">Envelope (v2)</h3>
                <Field k="message_id" v={event.n === "1284" ? "msg-9f3a2b71" : `msg-${event.n}`} />
                <Field k="correlation_id" v="corr-7e4d2c36" />
                <Field k="mission / epoch" v="M-0247 / E12" />
                <Field k="publisher seq" v="004892" />
                <Field k="timestamp" v={`${event.time}Z`} />
                <Field k="protocol version" v="2.0-draft" />
                <p className="pt-2">Validation <Pill tone="ok">Accepted</Pill></p>
                <p>Operator-feed Writer <Pill tone="info">writer · queued</Pill></p>
                <p>schema · proposed-1</p>
                <p>team log list · pending</p>
              </div>
            ) : <p className="text-sm">Select an event.</p>}
          </Card>
        </div>
      </Card>
    </SlidePage>
  );
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line py-1">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-xs">{v}</span>
    </div>
  );
}
