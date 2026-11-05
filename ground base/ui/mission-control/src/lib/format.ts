export function formatUnknown(value: unknown): string {
  if (value === null || value === undefined || value === "") return "unknown";
  if (typeof value === "number" && !Number.isFinite(value)) return "unknown";
  return String(value);
}

export function formatAge(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return "age unknown";
  const sign = ms < 0 ? "-" : "";
  const abs = Math.abs(ms);
  if (abs < 1000) return `${sign}${abs} ms`;
  return `${sign}${(abs / 1000).toFixed(1)} s`;
}

export function formatDbm(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "unknown dBm";
  return `${value} dBm`;
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pass: "pass",
    fail: "fail",
    unknown: "unknown",
    present: "present",
    missing: "missing",
    connected: "connected",
    disconnected: "disconnected",
    simulated: "simulated",
    refused: "refused",
    unavailable: "unavailable",
  };
  return labels[status] ?? status;
}
