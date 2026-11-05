"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { groundPath } from "@/lib/api";
import { Bars, Panel } from "@/components/ui";
import { chartableMetrics } from "@/lib/metrics";

export function RunDetailSession() {
  const params = useParams<{ id: string }>();
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void fetch(groundPath(`runs/${params.id}`))
      .then(async (response) => {
        const body = (await response.json()) as { report?: Record<string, unknown>; error?: { detail?: string } };
        if (!response.ok) setError(body.error?.detail ?? "Run was not found");
        else setReport(body.report ?? null);
      })
      .catch(() => setError("The operator API did not answer."));
  }, [params.id]);
  if (error) return <p className="text-sm">{error}</p>;
  if (!report) return <p className="text-sm">Loading run.</p>;
  const metrics = report.metrics as { metrics?: Record<string, { seconds?: number | null }> } | undefined;
  const rows = Object.entries(metrics?.metrics ?? {}).map(([name, value]) => ({ name, value: value?.seconds ?? null }));
  return (
    <div className="space-y-3">
      <Panel title={String(report.run_id ?? params.id)}>
        <p className="text-sm">Outcome {String(report.outcome ?? "unknown")}. Goal {String(report.goal_reached)}. Landing {String(report.landing_verified)}.</p>
        <p className="text-sm text-muted">{String(report.reason ?? "")}</p>
        <a className="text-sm underline" href={groundPath(`runs/${params.id}/export`)}>
          Export summary
        </a>
      </Panel>
      <Panel title="Measured timings">
        <Bars rows={chartableMetrics(rows)} caption="Only finite measured seconds are shown." />
      </Panel>
      <Panel title="Report">
        <pre className="overflow-auto text-xs">{JSON.stringify(report, null, 2)}</pre>
      </Panel>
    </div>
  );
}
