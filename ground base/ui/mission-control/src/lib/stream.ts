import type { Snapshot, StreamEvent } from "./types";

export function parseEventData(raw: string): StreamEvent | null {
  try {
    const parsed = JSON.parse(raw) as Partial<StreamEvent>;
    if (!parsed || typeof parsed !== "object" || !parsed.snapshot) return null;
    if (typeof parsed.cursor !== "number") return null;
    return { cursor: parsed.cursor, snapshot: parsed.snapshot as Snapshot };
  } catch {
    return null;
  }
}

export function hasGap(last: number, next: number): boolean {
  return last > 0 && next > last + 1;
}

export function shouldApplyCursor(last: number, next: number): boolean {
  return next >= last;
}

export function backoffMs(current: number): number {
  if (!Number.isFinite(current) || current < 500) return 500;
  return Math.min(current * 2, 5000);
}
