"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { groundPath } from "@/lib/api";
import { useSession } from "@/components/provider";
import { DataTable, Panel } from "@/components/ui";

type RunSummary = {
  run_id?: string;
  scenario?: string;
  phase?: string;
  outcome?: string;
  goal_reached?: boolean;
  landing_verified?: boolean;
  recovery_required?: boolean;
};

export function RunsSession() {
  const { snapshot } = useSession();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [journal, setJournal] = useState<Record<string, unknown>[]>([]);
  const [filter, setFilter] = useState({ source: "", severity: "" });
  useEffect(() => {
    void fetch(groundPath("runs"))
      .then((response) => response.json())
      .then((body: { runs?: RunSummary[] }) => setRuns(body.runs ?? []))
      .catch(() => setRuns([]));
  }, [snapshot?.cursor]);
  useEffect(() => {
    const params = new URLSearchParams({ limit: "50", source: filter.source, severity: filter.severity });
    void fetch(groundPath(`journal?${params.toString()}`))
      .then((response) => response.json())
      .then((body: { rows?: Record<string, unknown>[] }) => setJournal(body.rows ?? []))
      .catch(() => setJournal([]));
  }, [snapshot?.cursor, filter.source, filter.severity]);
  if (!snapshot) return <p className="text-sm text-muted">The operator session has not connected. Run history and the journal appear when the Ground API answers.</p>;
  return (
    <div className="space-y-3">
      <Panel title="Run history">
        <DataTable
          caption="Runs"
          headers={["Run", "Scenario", "Phase", "Goal", "Landing", "Recovery"]}
          rows={runs.map((run) => [
            run.run_id ? <Link key={run.run_id} href={`/runs/${run.run_id}`}>{run.run_id}</Link> : "unknown",
            run.scenario ?? "unknown",
            run.phase ?? "unknown",
            run.goal_reached ? "reached" : "unresolved",
            run.landing_verified ? "verified" : "not verified",
            run.recovery_required ? "required" : "not required",
          ])}
        />
      </Panel>
      <Panel title="Journal">
        <p className="mb-2 text-sm">Writer state {snapshot.writer_state}. Operator rows stay enqueued until task 29 reports flushed or published.</p>
        <div className="mb-2 flex gap-2">
          <label className="text-sm">
            Source
            <input className="ml-2 rounded border border-line bg-surface px-2 py-1" value={filter.source} onChange={(event) => setFilter({ ...filter, source: event.target.value })} />
          </label>
          <label className="text-sm">
            Severity
            <input className="ml-2 rounded border border-line bg-surface px-2 py-1" value={filter.severity} onChange={(event) => setFilter({ ...filter, severity: event.target.value })} />
          </label>
        </div>
        <DataTable
          caption="Journal rows"
          headers={["Summary", "Source", "Ledger", "Writer", "Published"]}
          rows={journal.map((row) => [
            String(row.summary ?? "row"),
            String(row.source ?? ""),
            String(row.ledger ?? "operator_feed"),
            String(row.writer_state ?? "enqueued"),
            String(row.published ?? false),
          ])}
        />
      </Panel>
      <Panel title="Provider ledger">
        <DataTable
          caption="Task 29 records"
          headers={["Event", "Writer", "Published"]}
          rows={snapshot.provider_journal.map((row) => [
            String(row.event_name ?? row.kind ?? "record"),
            String(row.writer_state ?? "queued"),
            String(row.published ?? false),
          ])}
        />
      </Panel>
    </div>
  );
}
