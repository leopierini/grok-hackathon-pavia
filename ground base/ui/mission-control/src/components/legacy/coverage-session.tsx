"use client";

import { useEffect, useState } from "react";
import { groundPath } from "@/lib/api";
import { DataTable, Panel } from "@/components/ui";

type Row = {
  id: string;
  title: string;
  ui: string;
  data: string;
  actions: string;
  provider: string;
  status: string;
  evidence: string;
  blocker: string;
};

export function CoverageSession() {
  const [rows, setRows] = useState<Row[]>([]);
  const [hardware, setHardware] = useState("");
  useEffect(() => {
    void fetch(groundPath("coverage"))
      .then((response) => response.json())
      .then((body: { rows?: Row[]; hardware?: string }) => {
        setRows(body.rows ?? []);
        setHardware(body.hardware ?? "");
      })
      .catch(() => setRows([]));
  }, []);
  return (
    <Panel title="Tasks 01–32">
      <p className="mb-2 text-sm">{hardware || "Task rows appear when the Ground API answers."} A card on this page is not mission completion.</p>
      <DataTable
        caption="Task coverage"
        headers={["Task", "Title", "UI", "Status", "Blocker"]}
        rows={rows.map((row) => [row.id, row.title, row.ui, row.status, row.blocker])}
      />
    </Panel>
  );
}
