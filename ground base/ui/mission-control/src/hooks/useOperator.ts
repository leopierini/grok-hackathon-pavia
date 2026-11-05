"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { actionBody, groundPath } from "@/lib/api";
import { createIdempotencyKey, shouldReplayOnReload } from "@/lib/idempotency";
import { backoffMs, hasGap, parseEventData, shouldApplyCursor } from "@/lib/stream";
import type { Snapshot } from "@/lib/types";

export type StreamState = "connecting" | "live" | "disconnected";

export function useOperator() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [stream, setStream] = useState<StreamState>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const cursor = useRef(0);
  const snapshotRef = useRef<Snapshot | null>(null);
  snapshotRef.current = snapshot;

  useEffect(() => {
    if (shouldReplayOnReload()) return undefined;
    let stopped = false;
    let source: EventSource | null = null;
    let delay = 500;
    let timer = 0;

    const connect = () => {
      source = new EventSource(groundPath("events"));
      const apply = (event: Event) => {
        const parsed = parseEventData((event as MessageEvent).data);
        if (!parsed) return;
        if (hasGap(cursor.current, parsed.cursor)) setError("Event stream gap. Session was resynchronized.");
        if (shouldApplyCursor(cursor.current, parsed.snapshot.cursor ?? parsed.cursor)) {
          cursor.current = parsed.snapshot.cursor ?? parsed.cursor;
          setSnapshot(parsed.snapshot);
        }
        setStream("live");
      };
      source.addEventListener("snapshot", apply);
      source.addEventListener("event", apply);
      source.addEventListener("resync", apply);
      source.onopen = () => {
        if (!stopped) setStream("live");
        delay = 500;
      };
      source.onerror = () => {
        source?.close();
        if (stopped) return;
        setStream("disconnected");
        timer = window.setTimeout(connect, delay);
        delay = backoffMs(delay);
      };
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      source?.close();
    };
  }, []);

  const run = useCallback(async (name: string, extra: Record<string, unknown> = {}) => {
    const current = snapshotRef.current;
    if (!current) {
      setError("The session snapshot has not loaded.");
      return { ok: false };
    }
    setPending(name);
    setError(null);
    try {
      const response = await fetch(groundPath(`actions/${name}`), {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "idempotency-key": createIdempotencyKey(),
        },
        body: JSON.stringify(actionBody(current.session_epoch, extra)),
      });
      const body = (await response.json()) as { ok?: boolean; detail?: string; error?: { detail?: string }; snapshot?: Snapshot };
      if (body.snapshot) {
        snapshotRef.current = body.snapshot;
        setSnapshot(body.snapshot);
        cursor.current = body.snapshot.cursor;
      }
      if (!body.ok) setError(body.error?.detail || body.detail || "Action rejected");
      return body;
    } catch {
      setError("The operator API did not answer.");
      return { ok: false };
    } finally {
      setPending(null);
    }
  }, []);

  return { snapshot, stream, error, pending, run };
}
