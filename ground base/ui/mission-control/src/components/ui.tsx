"use client";

import type { ReactNode } from "react";
import { haltSkipsConfirmation } from "@/lib/actions";
import { formatUnknown, statusLabel } from "@/lib/format";
import { chartableMetrics } from "@/lib/metrics";
import { rssiSeries } from "@/lib/navigation";
import type { Check, RssiPoint } from "@/lib/types";

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">{title}</h2>
      {children}
    </section>
  );
}

export function StatusText({ status, detail }: { status: string; detail?: string }) {
  const tone = status === "pass" || status === "present" || status === "simulated" ? "ok" : status === "fail" || status === "fault" || status === "refused" ? "bad" : status === "warn" || status === "stale" ? "warn" : "info";
  const classes = {
    ok: "bg-ok-bg text-ok",
    bad: "bg-bad-bg text-bad",
    warn: "bg-warn-bg text-warn",
    info: "bg-info-bg text-info",
  }[tone];
  return (
    <span className={`inline-flex items-center gap-2 rounded px-2 py-0.5 text-xs font-semibold ${classes}`}>
      {statusLabel(status)}
      {detail ? <span className="font-normal">{detail}</span> : null}
    </span>
  );
}

export function HaltButton({ onHalt, disabled }: { onHalt: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#E85A67] px-4 text-sm font-bold tracking-wide text-white disabled:opacity-50"
      onClick={() => {
        if (haltSkipsConfirmation()) onHalt();
      }}
      disabled={disabled}
    >
      <span className="h-2.5 w-2.5 rounded-[2px] bg-white" aria-hidden />
      HALT
    </button>
  );
}

export function DataTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header} scope="col" className="border-b border-line px-2 py-1 font-semibold">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="px-2 py-2 text-muted" colSpan={headers.length}>
                Nothing recorded.
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={index} className="align-top">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border-b border-line px-2 py-1">
                    {cell}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function KeyValue({ rows }: { rows: { label: string; value: unknown }[] }) {
  return (
    <dl className="grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1 text-sm">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="text-muted">{row.label}</dt>
          <dd className="font-mono text-xs">{formatUnknown(row.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ReadinessList({ checks }: { checks: Check[] }) {
  if (checks.length === 0) return <p className="text-sm text-muted">No readiness checks reported.</p>;
  return (
    <ul className="space-y-2">
      {checks.map((check) => (
        <li key={check.id} className="text-sm">
          <StatusText status={check.status} /> <span className="font-medium">{check.label}</span>
          <p className="text-muted">{check.detail}</p>
        </li>
      ))}
    </ul>
  );
}

export function Bars({ rows, caption }: { rows: { name: string; value: number | null }[]; caption: string }) {
  const points = chartableMetrics(rows);
  if (points.length === 0) return <p className="text-sm text-muted">{caption} Unknown measurements are omitted, not drawn as zero.</p>;
  const max = Math.max(...points.map((point) => point.value), 1);
  return (
    <div>
      <p className="mb-2 text-xs text-muted">{caption}</p>
      <ul className="space-y-1">
        {points.map((point) => (
          <li key={point.name} className="grid grid-cols-[minmax(8rem,1fr)_4rem] items-center gap-2 text-xs">
            <span className="truncate" title={point.name}>
              <span className="mr-2 inline-block h-2 rounded bg-info" style={{ width: `${(point.value / max) * 100}%` }} />
              {point.name}
            </span>
            <span className="font-mono">{point.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RssiChart({ points }: { points: RssiPoint[] }) {
  const series = rssiSeries(points);
  if (series.length === 0) return <p className="text-sm text-muted">No numeric RSSI samples. Missing samples are not plotted as 0 dBm.</p>;
  const values = series.map((point) => point.rssi_dbm);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 320;
  const height = 120;
  const coords = series.map((point, index) => {
    const x = (index / Math.max(series.length - 1, 1)) * (width - 16) + 8;
    const y = height - 12 - ((point.rssi_dbm - min) / span) * (height - 24);
    return `${x},${y}`;
  });
  return (
    <figure>
      <figcaption className="mb-1 text-xs text-muted">RSSI samples in dBm. This is not distance.</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="RSSI samples in dBm" className="w-full max-w-xl">
        <polyline fill="none" stroke="currentColor" strokeWidth="2" points={coords.join(" ")} />
      </svg>
      <p className="text-xs text-muted">
        Range {formatUnknown(min)} to {formatUnknown(max)} dBm.
      </p>
    </figure>
  );
}
