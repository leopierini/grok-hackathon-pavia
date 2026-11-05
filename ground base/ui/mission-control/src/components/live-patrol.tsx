"use client";

import { useCallback, useEffect, useState } from "react";
import { groundPath } from "@/lib/api";
import { HaltButton, KeyValue, Panel, StatusText } from "@/components/ui";

type Reading = {
  camera: string;
  target_state: string;
  confidence: number | null;
  box_xyxy_norm: number[] | null;
  reason: string;
  latency_ms?: number;
  frame?: string;
};

type LiveEvent = { seq: number; ts: string; kind: string; component: string; detail: string; incident_id: string | null };

type LiveState = {
  ok: boolean;
  connected: boolean;
  phase: string;
  error?: string | null;
  config: { drone: string; dog: string; arm_dog: boolean; grok: string; takeoff: boolean; target?: string };
  halt_latched?: boolean;
  incident?: { id: string; detected_at: string; alert: string | null; spoken: string[]; dog_reading: Reading | null } | null;
  drone?: Record<string, unknown> & { link?: string };
  dog?: Record<string, unknown> & { link?: string };
  grok?: { name: string; calls: number; errors: number; in_flight: boolean; last_error?: string; last_latency_ms?: number };
  readings?: { drone: Reading | null; dog: Reading | null };
  tracking?: { enabled: boolean; nudges: number };
  events?: LiveEvent[];
};

const HOT = new Set(["drone_target_acquired", "dog_target_acquired", "alert", "dog_voice", "halt", "halt_sent", "drone_link_lost", "dog_alert"]);

async function post(path: string, body: Record<string, unknown> = {}): Promise<{ ok?: boolean; detail?: string }> {
  try {
    const response = await fetch(groundPath(`live/${path}`), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return (await response.json()) as { ok?: boolean; detail?: string };
  } catch (error) {
    return { ok: false, detail: String(error) };
  }
}

function linkStatus(link: unknown): string {
  return link === "up" ? "pass" : link === "down" ? "fail" : "warn";
}

function Camera({ camera, reading, live }: { camera: "drone" | "dog"; reading: Reading | null | undefined; live: boolean }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!live) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const next = () => {
      if (stop) return;
      const img = new Image();
      const url = `${groundPath(`live/frame/${camera}.jpg`)}?t=${Date.now()}`;
      img.onload = () => {
        if (!stop) setSrc(url);
        timer = setTimeout(next, 200);
      };
      img.onerror = () => {
        timer = setTimeout(next, 700); // 204 = no fresh frame; keep the last one
      };
      img.src = url;
    };
    next();
    return () => {
      stop = true;
      if (timer) clearTimeout(timer);
    };
  }, [camera, live]);
  const box = reading && reading.target_state === "person_visible" ? reading.box_xyxy_norm : null;
  return (
    <div className="relative aspect-[4/3] overflow-hidden rounded-xl border border-line bg-black">
      {src ? <img src={src} alt={`${camera} camera`} className="h-full w-full object-contain" /> : (
        <p className="absolute inset-0 flex items-center justify-center text-sm text-white/60">No {camera} frame yet</p>
      )}
      {box ? (
        <div
          className="absolute rounded border-[3px] border-[#E85A67]"
          style={{ left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` }}
        />
      ) : null}
      <span className="absolute left-2 top-2 rounded bg-black/60 px-2 py-0.5 font-mono text-xs text-white">
        {reading ? `${reading.target_state}${reading.confidence != null ? ` ${Math.round(reading.confidence * 100)}%` : ""} · ${reading.latency_ms ?? "?"} ms` : "no Grok reading yet"}
      </span>
    </div>
  );
}

export function LivePatrol() {
  const [state, setState] = useState<LiveState | null>(null);
  const [note, setNote] = useState<string>("");

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(groundPath("live/state"), { cache: "no-store" });
      setState((await response.json()) as LiveState);
    } catch {
      /* API not up yet */
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 500);
    return () => clearInterval(id);
  }, [refresh]);

  const act = useCallback(
    async (path: string, body: Record<string, unknown> = {}) => {
      const result = await post(path, body);
      setNote(result.ok === false ? `Refused: ${result.detail ?? ""}` : result.detail ?? "");
      refresh();
    },
    [refresh],
  );

  const halt = useCallback(() => {
    void act("halt");
  }, [act]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const tag = (event.target as HTMLElement | null)?.tagName;
      if ((event.key === "q" || event.key === "Q") && tag !== "INPUT" && tag !== "TEXTAREA") halt();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [halt]);

  const connected = state?.connected === true;
  const drone = state?.drone ?? {};
  const dog = state?.dog ?? {};
  const grok = state?.grok;
  const readings = state?.readings ?? { drone: null, dog: null };
  const incident = state?.incident;
  const button = "min-h-11 rounded-xl border border-line bg-surface px-4 text-sm font-semibold disabled:opacity-40";

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface p-4">
        <div className="mr-2">
          <h1 className="font-display text-2xl font-semibold">Live patrol</h1>
          <p className="text-sm text-muted">One Start runs the whole demo: takeoff, scan, detect, track, dog approach, warning, landing. Halt stops everything.</p>
        </div>
        <span className="rounded-full bg-info-bg px-3 py-1 font-mono text-sm font-semibold uppercase text-info">{state?.phase ?? "…"}</span>
        {state && typeof (state as { elapsed_s?: number }).elapsed_s === "number" ? <span className="font-mono text-xs text-muted">{(state as { elapsed_s?: number }).elapsed_s}s</span> : null}
        {incident ? <span className="font-mono text-xs text-muted">{incident.id} · {incident.detected_at.slice(11, 19)}Z</span> : null}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {!connected ? (
            <button type="button" className={button} onClick={() => act("connect")}>Connect peers</button>
          ) : (
            <button type="button" className={button} onClick={() => act("disconnect")}>Disconnect</button>
          )}
          <button type="button" className={`${button} bg-ok-bg text-ok`} onClick={() => act("start")}>Start patrol</button>
          <button type="button" className={`${button} bg-warn-bg text-warn`} disabled={!connected} onClick={() => act("stop")}>Stop patrol</button>
          <HaltButton onHalt={halt} />
        </div>
        <p className="w-full text-sm">Looking for: <span className="font-semibold">{state?.config.target ?? "—"}</span></p>
        {note ? <p className="w-full text-sm text-muted">{note}</p> : null}
        {state?.error ? <p className="w-full text-sm text-bad">{state.error}</p> : null}
      </header>

      {incident?.alert ? (
        <div className="rounded-2xl border border-bad bg-bad-bg p-4 text-sm">
          <p className="font-semibold text-bad">ALERT · {incident.alert}</p>
          <p className="mt-1 text-muted">Spoken by the dog: {incident.spoken.length ? incident.spoken.join(" / ") : "—"}</p>
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr_380px]">
        <section className="space-y-3 rounded-2xl border border-line bg-surface p-4">
          <div className="flex items-center justify-between">
            <Panel title="Drone camera"><span /></Panel>
            <StatusText status={linkStatus(drone.link)} detail={String(drone.link ?? "unknown")} />
          </div>
          <Camera camera="drone" reading={readings.drone} live={connected} />
          <KeyValue rows={[
            { label: "Flight", value: drone.state },
            { label: "Battery", value: drone.battery == null ? "—" : `${drone.battery}%${drone.battery_low ? " LOW" : ""}` },
            { label: "Height", value: drone.h == null ? "—" : `${drone.h} cm` },
            { label: "Video", value: drone.video },
            { label: "Grok sees", value: readings.drone?.reason ?? "—" },
            { label: "Tracking", value: `${state?.tracking?.enabled ? "on" : "off"} · ${state?.tracking?.nudges ?? 0} yaw nudges` },
          ]} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={state?.tracking?.enabled ?? false} disabled={!connected}
              onChange={(event) => act("track", { enabled: event.target.checked })} />
            Drone yaws to keep the person centred (bounded, no translation)
          </label>
          <p className="text-xs text-muted">Pilot page: {state?.config.drone}. Takeoff and land are always available there.</p>
        </section>

        <section className="space-y-3 rounded-2xl border border-line bg-surface p-4">
          <div className="flex items-center justify-between">
            <Panel title="Dog camera"><span /></Panel>
            <StatusText status={linkStatus(dog.link)} detail={String(dog.link ?? "unknown")} />
          </div>
          <Camera camera="dog" reading={readings.dog} live={connected} />
          <KeyValue rows={[
            { label: "Mode", value: `${state?.config.dog ?? "—"}${state?.config.arm_dog ? " (armed)" : " (speak + halt only)"}` },
            { label: "Standing", value: dog.standing },
            { label: "Avoidance", value: dog.avoidance_enabled },
            { label: "Motion lock", value: dog.motion_lock ?? "none" },
            { label: "Steps taken", value: dog.moves ?? 0 },
            { label: "Grok sees", value: readings.dog?.reason ?? "—" },
            { label: "Error", value: String(dog.error ?? dog.frame_error ?? "none") },
          ]} />
          <p className="text-xs text-muted">Automatic: the dog turns toward the person, walks in 1 s steps (0.3 m/s cap), checks LiDAR before every forward step, and stops at standoff.</p>
        </section>

        <section className="space-y-3 rounded-2xl border border-line bg-surface p-4">
          <div className="flex items-center justify-between">
            <Panel title="Grok & event journal"><span /></Panel>
            <span className="font-mono text-xs text-muted">
              {grok ? `${grok.name} · ${grok.calls} calls · ${grok.errors} err${grok.in_flight ? " · thinking" : ""}` : ""}
            </span>
          </div>
          {grok?.last_error ? <p className="text-xs text-bad">{grok.last_error}</p> : null}
          <ol className="max-h-[620px] space-y-1 overflow-auto font-mono text-xs">
            {[...(state?.events ?? [])].reverse().map((event) => (
              <li key={event.seq} className="border-b border-line pb-1">
                <span className="text-muted">{event.ts.slice(11, 23)}</span>{" "}
                <span className="text-info">{event.component}/{event.kind}</span>{" "}
                <span className={HOT.has(event.kind) ? "font-semibold text-bad" : ""}>{event.detail}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>
      <p className="text-xs text-muted">Halt: red button or Q on this page, or the header Halt on any screen. It lands the drone and lays the dog down, and it does not wait for Grok.</p>
    </div>
  );
}
