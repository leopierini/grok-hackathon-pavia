"use client";

import { useEffect, useRef, useState } from "react";
import { groundPath } from "@/lib/api";
import { useSession } from "@/components/provider";
import { Panel } from "@/components/ui";

type LidarView = {
  pts?: number[];
  stale?: boolean;
  nearest_ahead_m?: number | null;
  age_s?: number | null;
  reason?: string | null;
  radius_m?: number;
  clear?: { m?: number[] };
};

const CLEAR_ENOUGH_M = 0.5;

function roomIn(bins: number[] | undefined, index: number): number | null {
  const value = bins?.[index];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function DogSensors() {
  const { snapshot, run, pending } = useSession();
  const view = snapshot?.dog_demo?.view;
  const live = view?.ready === true || snapshot?.dog_demo?.active === true;
  const [tick, setTick] = useState(0);
  const [lidar, setLidar] = useState<LidarView | null>(null);
  const [lidarError, setLidarError] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  const busy = pending !== null;

  useEffect(() => {
    if (!live) return undefined;
    const id = window.setInterval(() => setTick((value) => value + 1), 80);
    return () => window.clearInterval(id);
  }, [live]);

  useEffect(() => {
    if (!live) return undefined;
    let cancelled = false;
    const pull = () => {
      fetch(groundPath("dog/lidar"))
        .then(async (response) => {
          const body = (await response.json()) as { ok?: boolean; view?: LidarView; detail?: string; error?: { detail?: string } };
          if (cancelled) return;
          if (body.ok && body.view) {
            setLidar(body.view);
            setLidarError("");
          } else {
            setLidarError(body.error?.detail || body.detail || "The range view is not ready.");
          }
        })
        .catch(() => {
          if (!cancelled) setLidarError("The range view did not answer.");
        });
    };
    pull();
    const id = window.setInterval(pull, 500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [live]);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const ctx = node.getContext("2d");
    if (!ctx) return;
    const size = node.width;
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = "#121417";
    ctx.fillRect(0, 0, size, size);
    const radius = lidar?.radius_m || 4;
    const scale = (size / 2 - 16) / radius;
    const cx = size / 2;
    const cy = size / 2;
    ctx.strokeStyle = "#3c4350";
    ctx.beginPath();
    ctx.arc(cx, cy, radius * scale, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx, 16);
    ctx.strokeStyle = "#8fd0ad";
    ctx.stroke();
    const pts = lidar?.pts ?? [];
    ctx.strokeStyle = "#3f2a2a";
    ctx.beginPath();
    ctx.arc(cx, cy, CLEAR_ENOUGH_M * scale, 0, Math.PI * 2);
    ctx.stroke();
    for (let index = 0; index + 2 < pts.length; index += 3) {
      const forward = pts[index] / 100;
      const left = pts[index + 1] / 100;
      const close = Math.hypot(forward, left) < CLEAR_ENOUGH_M;
      ctx.fillStyle = close ? "#e7d7a1" : "#d4d4d8";
      ctx.fillRect(cx - left * scale, cy - forward * scale, 2, 2);
    }
    ctx.fillStyle = "#f4f6f8";
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.fill();
  }, [lidar]);

  if (!snapshot) return null;
  const bins = lidar?.clear?.m;
  const directions = [
    ["Ahead", roomIn(bins, 0)],
    ["Left", roomIn(bins, 6)],
    ["Right", roomIn(bins, 18)],
    ["Behind", roomIn(bins, 12)],
  ] as const;
  return (
    <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1.4fr)_minmax(16rem,0.8fr)]">
      <Panel title="Camera">
        <p className="text-sm text-muted">{view?.detail ?? "Open a view to see the dog. A view does not move it."}</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="min-h-11 rounded-full border border-line px-4 text-sm" disabled={busy} onClick={() => void run("dog_view", { open: true, dog: "sim" })}>
            Practice view
          </button>
          <button type="button" className="min-h-11 rounded-full bg-surface-2 px-4 text-sm" disabled={busy} onClick={() => void run("dog_view", { open: true, dog: "ethernet" })}>
            Live view
          </button>
          <button type="button" className="min-h-11 rounded-full px-4 text-sm text-muted" disabled={busy || view?.open !== true} onClick={() => void run("dog_view", { open: false })}>
            Close
          </button>
        </div>
        {live ? (
          // The address changes so the browser asks for the next picture.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={`${groundPath("dog/live.jpg")}?t=${tick}`} alt="Live view from the dog camera" className="max-h-[32rem] w-full rounded-2xl bg-black object-contain" />
        ) : (
          <div className="flex min-h-64 items-center justify-center rounded-2xl bg-surface text-sm text-muted">The camera is closed.</div>
        )}
      </Panel>
      <Panel title="Around the dog">
        <ul className="space-y-2 text-sm">
          {directions.map(([label, metres]) => {
            const blocked = metres == null || metres < CLEAR_ENOUGH_M;
            return (
              <li key={label} className="flex items-baseline justify-between gap-3">
                <span>{label}</span>
                <span className={blocked ? "text-warn" : "text-ok"}>
                  {metres == null ? "Unknown" : blocked ? `${metres.toFixed(2)} m, too close` : `${metres.toFixed(2)} m clear`}
                </span>
              </li>
            );
          })}
        </ul>
        <p className="text-sm text-muted">{lidarError || lidar?.reason || "The pale ring is half a metre. Points inside it are too close to step toward."}</p>
        <canvas ref={canvas} width={360} height={360} aria-label="Range around the dog" className="w-full rounded-2xl bg-black" />
      </Panel>
    </div>
  );
}
