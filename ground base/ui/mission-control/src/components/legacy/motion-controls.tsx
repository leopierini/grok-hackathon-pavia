"use client";

import { useEffect, useRef, useState } from "react";
import type { SessionValue } from "@/components/provider";
import type { DogLimits } from "@/lib/types";

const DEFAULT_LIMITS: DogLimits = {
  forward_m_s: 0.18,
  side_m_s: 0.12,
  yaw_rad_s: 0.36,
  step_s: 0.6,
};

const DEFAULT_CEILING: DogLimits = {
  forward_m_s: 0.3,
  side_m_s: 0.2,
  yaw_rad_s: 0.6,
  step_s: 1,
};

export function MotionControls({ session }: { session: SessionValue | null }) {
  const live = session;
  const [limits, setLimits] = useState<DogLimits>(DEFAULT_LIMITS);
  const seeded = useRef(false);
  useEffect(() => {
    const reported = live?.snapshot?.dog_demo?.limits;
    if (seeded.current || !reported) return;
    seeded.current = true;
    setLimits(reported);
  }, [live]);
  const snapshot = live?.snapshot ?? null;
  const pending = live?.pending ?? null;
  const run = live?.run;
  const demo = snapshot?.dog_demo;
  const ceiling = demo?.ceiling ?? DEFAULT_CEILING;
  const armed = snapshot?.mission.armed === true;
  const blocked = pending !== null || !run || !snapshot;
  const viewHeld = demo?.active === true && demo?.view?.owns !== true;

  const releaseView = async () => {
    if (!run || !demo?.view?.owns) return true;
    const closed = await run("dog_view", { open: false });
    if (!closed?.ok) return false;
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    return true;
  };
  const ensureArmed = async () => {
    if (!run) return false;
    if (armed) return true;
    const result = await run("arm");
    return result?.ok === true;
  };
  const testDog = async (dog: "ethernet" | "sim") => {
    if (!run || !(await releaseView()) || !(await ensureArmed())) return;
    await run("dog_test", { dog, limits });
  };
  const startDog = async (dog: "ethernet" | "sim") => {
    if (!run || !(await releaseView()) || !(await ensureArmed())) return;
    await run("start", { scenario: "happy_path", pace_s: 0, seed: 0, dog, limits });
  };

  return (
    <div>
      <SpeedLimits limits={limits} ceiling={ceiling} onChange={setLimits} />
      <p className="mt-2 text-sm text-muted">
        Forward velocity, side velocity, turn rate, and step length are sent with the dog step. Turn rate is the yaw command.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          className="min-h-11 rounded-full bg-[#E85A67] px-4 text-sm font-bold text-white"
          disabled={blocked}
          onClick={async () => {
            const result = await run?.("start_patrol");
            if (result?.ok) window.location.href = "/live";
          }}
        >
          Start patrol (runs the whole demo)
        </button>
        <button type="button" className="min-h-11 rounded-full border border-line px-4 text-sm" disabled={blocked} onClick={() => void run?.("stop_patrol")}>
          Stop patrol
        </button>
        <button type="button" className="min-h-11 rounded-full border border-line px-4 text-sm" disabled={blocked} onClick={() => void run?.("probe")}>
          Check the cable
        </button>
        <button type="button" className="min-h-11 rounded-full bg-surface-2 px-4 text-sm" disabled={blocked || viewHeld} onClick={() => void testDog("ethernet")}>
          Try four short steps
        </button>
        <button type="button" className="min-h-11 rounded-full border border-line px-4 text-sm" disabled={blocked || viewHeld} onClick={() => void testDog("sim")}>
          Try the steps in practice
        </button>
        <button type="button" className="min-h-11 rounded-full border border-line px-4 text-sm" disabled={blocked || viewHeld} onClick={() => void startDog("ethernet")}>
          Run the short demo
        </button>
      </div>
    </div>
  );
}

function SpeedLimits({
  limits,
  ceiling,
  onChange,
}: {
  limits: DogLimits;
  ceiling: DogLimits;
  onChange: (limits: DogLimits) => void;
}) {
  return (
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      <LimitSlider label="Forward velocity" unit="m/s" min={0.05} max={ceiling.forward_m_s} value={limits.forward_m_s} onChange={(value) => onChange({ ...limits, forward_m_s: value })} />
      <LimitSlider label="Side velocity" unit="m/s" min={0.05} max={ceiling.side_m_s} value={limits.side_m_s} onChange={(value) => onChange({ ...limits, side_m_s: value })} />
      <LimitSlider label="Turn rate" unit="rad/s" min={0.05} max={ceiling.yaw_rad_s} value={limits.yaw_rad_s} onChange={(value) => onChange({ ...limits, yaw_rad_s: value })} />
      <LimitSlider label="Step length" unit="s" min={0.3} max={ceiling.step_s} value={limits.step_s} onChange={(value) => onChange({ ...limits, step_s: value })} />
    </div>
  );
}

function LimitSlider({
  label,
  unit,
  min,
  max,
  value,
  onChange,
}: {
  label: string;
  unit: string;
  min: number;
  max: number;
  value: number;
  onChange: (value: number) => void;
}) {
  const shown = Math.min(max, Math.max(min, value));
  return (
    <label className="block text-sm">
      <span className="flex justify-between gap-3">
        <span>{label}</span>
        <span className="font-mono">
          {shown.toFixed(2)} {unit}
        </span>
      </span>
      <input
        className="mt-1 block h-11 w-full accent-info"
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={0.01}
        value={shown}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}
