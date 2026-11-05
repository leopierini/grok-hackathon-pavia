"use client";

import { useEffect, useState } from "react";

export function ageLabel(now: number, updatedAt: string | null): string {
  if (!updatedAt) return "update time unknown";
  const then = Date.parse(updatedAt);
  if (!Number.isFinite(then)) return "update time unknown";
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  return `API update ${seconds}s ago`;
}

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}
