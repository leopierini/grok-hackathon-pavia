export function chartableMetrics(rows: { name: string; value: number | null }[]): { name: string; value: number }[] {
  return rows.filter((row): row is { name: string; value: number } => typeof row.value === "number" && Number.isFinite(row.value));
}
