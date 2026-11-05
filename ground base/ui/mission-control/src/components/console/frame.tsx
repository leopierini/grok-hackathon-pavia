"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  Bell,
  Box,
  Camera,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  Compass,
  Crosshair,
  Flag,
  FlaskConical,
  Folder,
  Layers,
  Radio,
  Settings,
  Shield,
  Terminal,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { NAV_MAIN, SLIDES, type NavItem } from "@/slides/catalog";
import { HaltButton } from "@/components/ui";
import { useOptionalSession } from "@/components/provider";
import { cn } from "@/lib/cn";

const ICONS: Record<string, LucideIcon> = {
  mission: Flag,
  devices: Box,
  vision: Camera,
  navigation: Compass,
  commands: Terminal,
  runs: Activity,
  rehearsal: FlaskConical,
  coverage: ClipboardList,
  settings: Settings,
  evidence: Camera,
  capabilities: Layers,
  telemetry: Activity,
  "dog-command": Flag,
  targets: Crosshair,
  beacons: Radio,
  gates: Shield,
  activity: Activity,
};

export type Chip = { title: string; body: string; icon?: ReactNode };
export type Principle = { index: string; title: string; body: string; extra?: ReactNode };

export type TopBarSpec = {
  mode: string;
  note?: string;
  meta?: string[];
  halt?: boolean;
  latch?: string;
  alert?: string;
};

export function SlidePage({
  id,
  chips,
  principlesTitle = "Key details",
  principlesNote,
  principles,
  active,
  items = NAV_MAIN,
  topbar,
  children,
}: {
  id: string;
  chips?: Chip[];
  principlesTitle?: string;
  principlesNote?: string;
  principles?: Principle[];
  active: string;
  items?: NavItem[];
  topbar: TopBarSpec;
  children: ReactNode;
}) {
  const meta = SLIDES.find((slide) => slide.id === id);
  return (
    <article data-screen={id} className="space-y-6">
      <header className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-info">
            <Crosshair className="h-4 w-4" aria-hidden />
            Ground / Mission Control
          </p>
          <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
            {meta?.id}. {meta?.title}
          </h1>
          <p className="mt-2 text-lg text-muted">{meta?.lede}</p>
        </div>
        <RobotMark />
      </header>
      {chips && chips.length > 0 ? (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {chips.map((chip) => (
            <li key={chip.title} className="flex gap-3 rounded-2xl border border-line bg-surface/80 p-3">
              <span className="mt-0.5 text-blue">{chip.icon}</span>
              <span>
                <span className="block text-sm font-semibold text-ink">{chip.title}</span>
                <span className="mt-1 block text-sm leading-5 text-muted">{chip.body}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <ConsoleFrame active={active} items={items} topbar={topbar}>
        {children}
      </ConsoleFrame>
      {principles && principles.length > 0 ? (
        <section aria-label={principlesTitle}>
          <div className="mb-3 flex flex-wrap items-baseline gap-3">
            <h2 className="font-display text-2xl font-semibold text-ink">{principlesTitle}</h2>
            {principlesNote ? <p className="text-sm text-muted">{principlesNote}</p> : null}
          </div>
          <ul className={`grid gap-3 ${principles.length > 3 ? "md:grid-cols-2 xl:grid-cols-4" : "md:grid-cols-3"}`}>
            {principles.map((item) => (
              <li key={item.index} className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
                <p className="text-xs font-bold text-blue">{item.index}</p>
                <h3 className="mt-1 font-display text-lg font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted">{item.body}</p>
                {item.extra ? <div className="mt-3">{item.extra}</div> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}

function RobotMark() {
  return (
    <div className="hidden items-end gap-3 lg:flex" aria-hidden>
      <svg viewBox="0 0 120 70" className="h-14 w-24 text-graphite">
        <circle cx="22" cy="18" r="9" fill="none" stroke="currentColor" strokeWidth="3" />
        <circle cx="98" cy="18" r="9" fill="none" stroke="currentColor" strokeWidth="3" />
        <circle cx="22" cy="52" r="9" fill="none" stroke="currentColor" strokeWidth="3" />
        <circle cx="98" cy="52" r="9" fill="none" stroke="currentColor" strokeWidth="3" />
        <rect x="46" y="26" width="28" height="16" rx="4" fill="currentColor" />
      </svg>
      <svg viewBox="0 0 140 90" className="h-20 w-28 text-graphite">
        <rect x="22" y="34" width="78" height="30" rx="12" fill="currentColor" opacity="0.85" />
        <rect x="70" y="16" width="32" height="24" rx="8" fill="currentColor" />
        <rect x="28" y="64" width="8" height="18" fill="currentColor" />
        <rect x="48" y="64" width="8" height="18" fill="currentColor" />
        <rect x="78" y="64" width="8" height="18" fill="currentColor" />
        <rect x="98" y="64" width="8" height="18" fill="currentColor" />
      </svg>
    </div>
  );
}

export function ConsoleFrame({
  active,
  items = NAV_MAIN,
  topbar,
  children,
}: {
  active: string;
  items?: NavItem[];
  topbar: TopBarSpec;
  children: ReactNode;
}) {
  const session = useOptionalSession();
  const halt = () => {
    if (session) void session.run("halt");
  };
  return (
    <div className="overflow-hidden rounded-[28px] border border-white/60 bg-chrome shadow-console">
      <div className="flex min-h-[760px] flex-col lg:flex-row">
        <nav aria-label="Console" className="flex gap-1 overflow-x-auto bg-graphite p-2 lg:w-[124px] lg:flex-col lg:overflow-visible lg:px-2 lg:py-4">
          {items.map((item) => {
            const Icon = ICONS[item.id] ?? CircleHelp;
            const current = item.id === active;
            return (
              <Link
                key={item.id}
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "flex min-h-11 w-full min-w-[76px] flex-col items-center justify-center gap-1 rounded-xl px-1 py-2 text-center text-[10px] font-semibold uppercase leading-tight tracking-normal",
                  current ? "bg-blue text-white" : "text-slate-300 hover:bg-white/10",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="flex min-w-0 flex-1 flex-col bg-chrome-2">
          <header className="flex flex-wrap items-center gap-3 px-4 py-3 text-white">
            <p className="flex items-center gap-2 text-xs font-semibold tracking-[0.14em]">
              <Crosshair className="h-4 w-4" aria-hidden />
              GROUND / MISSION CONTROL
            </p>
            {topbar.meta?.map((item) => (
              <span key={item} className="rounded-full bg-white/10 px-2 py-1 text-[11px]">
                {item}
              </span>
            ))}
            <span className="inline-flex min-h-9 items-center gap-1 rounded-full bg-blue px-3 text-xs font-semibold">
              {topbar.mode}
              <ChevronDown className="h-3.5 w-3.5" aria-hidden />
            </span>
            {topbar.latch ? <span className="text-xs text-cyan">{topbar.latch}</span> : null}
            {topbar.alert ? (
              <span className="rounded-full bg-danger px-2 py-1 text-[11px] font-semibold">{topbar.alert}</span>
            ) : null}
            <span className="text-xs text-slate-300">{topbar.note}</span>
            <span className="ml-auto flex items-center gap-2">
              <Folder className="h-4 w-4 text-slate-300" aria-hidden />
              <Bell className="h-4 w-4 text-slate-300" aria-hidden />
              <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-2 py-1 text-xs">
                <span className="h-2 w-2 rounded-full bg-success" aria-hidden />
                <UserRound className="h-3.5 w-3.5" aria-hidden />
                Operator
              </span>
              {topbar.halt ? <HaltButton onHalt={halt} /> : null}
            </span>
          </header>
          <div className="m-3 min-w-0 flex-1 rounded-[22px] bg-canvas p-3 sm:p-4">{children}</div>
        </div>
      </div>
    </div>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn("rounded-2xl border border-line bg-surface p-4 shadow-sm", className)}>{children}</section>;
}

export function CardTitle({ icon, title, extra }: { icon?: ReactNode; title: string; extra?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      {icon ? <span className="text-blue">{icon}</span> : null}
      <h2 className="font-display text-base font-semibold text-ink">{title}</h2>
      <span className="ml-auto">{extra}</span>
    </div>
  );
}

const PILL = {
  ok: "bg-ok-bg text-ok",
  bad: "bg-bad-bg text-bad",
  warn: "bg-warn-bg text-warn",
  info: "bg-info-bg text-info",
  sim: "bg-blue/10 text-blue",
  neutral: "bg-surface-2 text-muted",
} as const;

export function Pill({ tone = "neutral", children }: { tone?: keyof typeof PILL; children: ReactNode }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold", PILL[tone])}>{children}</span>;
}

export function CheckRow({ ok = true, label, detail, tone = "ok" }: { ok?: boolean; label: string; detail?: string; tone?: "ok" | "warn" | "bad" | "info" }) {
  const mark = ok ? "✓" : tone === "bad" ? "✕" : "!";
  const color = tone === "ok" ? "text-success" : tone === "bad" ? "text-danger" : tone === "warn" ? "text-warning" : "text-blue";
  return (
    <li className="flex items-start gap-2 text-sm">
      <span className={cn("mt-0.5 font-bold", color)} aria-hidden>
        {mark}
      </span>
      <span>
        <span className="font-medium text-ink">{label}</span>
        {detail ? <span className="mt-0.5 block text-xs text-muted">{detail}</span> : null}
      </span>
    </li>
  );
}

export function StepRail({ steps }: { steps: { label: string; state: "done" | "current" | "todo" | "halt" }[] }) {
  return (
    <ol className="flex flex-wrap items-center gap-2">
      {steps.map((step, index) => (
        <li key={step.label} className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex min-h-8 items-center gap-2 rounded-full px-2 text-xs font-semibold",
              step.state === "done" && "text-success",
              step.state === "current" && "text-blue",
              step.state === "halt" && "text-danger",
              step.state === "todo" && "text-muted",
            )}
          >
            <span
              className={cn(
                "grid h-5 w-5 place-items-center rounded-full border text-[10px]",
                step.state === "done" && "border-success bg-success text-white",
                step.state === "current" && "border-blue bg-blue text-white",
                step.state === "halt" && "border-danger bg-danger text-white",
                step.state === "todo" && "border-line",
              )}
              aria-hidden
            >
              {step.state === "done" ? "✓" : step.state === "halt" ? "■" : index + 1}
            </span>
            {step.label}
          </span>
          {index < steps.length - 1 ? <span className="h-px w-4 bg-line" aria-hidden /> : null}
        </li>
      ))}
    </ol>
  );
}

export function Timeline({ items }: { items: { label: string; time: string; state: "done" | "current" | "todo" }[] }) {
  return (
    <ol className="space-y-2">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-2 text-sm">
          <span
            className={cn(
              "h-3 w-3 rounded-full border",
              item.state === "done" && "border-success bg-success",
              item.state === "current" && "border-blue bg-blue",
              item.state === "todo" && "border-line bg-surface",
            )}
            aria-hidden
          />
          <span className={cn("flex-1", item.state === "current" ? "font-semibold text-blue" : "text-ink")}>{item.label}</span>
          <span className="font-mono text-xs text-muted">{item.time}</span>
        </li>
      ))}
    </ol>
  );
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn" | "bad" | "ok"; title?: string; children: ReactNode }) {
  const styles = {
    info: "border-blue/30 bg-info-bg text-info",
    warn: "border-warning/40 bg-warn-bg text-warn",
    bad: "border-danger/40 bg-bad-bg text-bad",
    ok: "border-success/40 bg-ok-bg text-ok",
  }[tone];
  return (
    <div className={cn("rounded-xl border px-3 py-2 text-sm", styles)}>
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={title ? "mt-1" : undefined}>{children}</div>
    </div>
  );
}

export function Field({ label, value, status }: { label: string; value: string; status?: ReactNode }) {
  return (
    <div className="flex items-center gap-3 border-b border-line py-2 text-sm last:border-b-0">
      <span className="w-36 shrink-0 text-muted">{label}</span>
      <span className="min-w-0 flex-1 font-mono text-ink">{value}</span>
      {status}
    </div>
  );
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-surface-2" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label="Progress">
      <div className="h-full rounded-full bg-blue" style={{ width: `${value}%` }} />
    </div>
  );
}

export function Flow({ steps }: { steps: { title: string; detail?: string; tone?: "ok" | "bad" | "info" | "warn" | "neutral" }[] }) {
  const toneClass = {
    ok: "border-success/40 bg-ok-bg",
    bad: "border-danger/40 bg-bad-bg",
    info: "border-blue/30 bg-info-bg",
    warn: "border-warning/40 bg-warn-bg",
    neutral: "border-line bg-surface-2",
  };
  return (
    <ol className="flex flex-wrap items-stretch gap-2">
      {steps.map((step, index) => (
        <li key={`${step.title}-${index}`} className="flex items-center gap-2">
          <div className={cn("rounded-xl border px-3 py-2 text-sm", toneClass[step.tone ?? "neutral"])}>
            <p className="font-semibold text-ink">{step.title}</p>
            {step.detail ? <p className="text-xs text-muted">{step.detail}</p> : null}
          </div>
          {index < steps.length - 1 ? <span className="text-muted" aria-hidden>→</span> : null}
        </li>
      ))}
    </ol>
  );
}

export function useHaltAction() {
  const session = useOptionalSession();
  return () => {
    if (session) void session.run("halt");
  };
}

export function Thumb({ label }: { label: string }) {
  return (
    <div className="h-12 w-16 overflow-hidden rounded-md border border-line" aria-hidden>
      <svg viewBox="0 0 64 48" className="h-full w-full">
        <rect width="64" height="48" fill="#c5d8e4" />
        <rect y="18" width="64" height="30" fill="#b7a888" />
        <text x="4" y="14" fontSize="7" fill="#16243A">
          {label}
        </text>
      </svg>
    </div>
  );
}

export function EmptyMap({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="grid min-h-40 place-items-center rounded-xl border border-dashed border-line bg-surface-2 p-6 text-center">
      <div>
        <p className="font-semibold text-ink">{title}</p>
        <p className="mt-1 text-sm text-muted">{detail}</p>
      </div>
    </div>
  );
}

export function Segmented({
  options,
  value,
  onChange,
  label,
}: {
  options: string[];
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1 rounded-full bg-surface-2 p-1">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={option === value}
          onClick={() => onChange(option)}
          className={cn("min-h-9 rounded-full px-3 text-xs font-semibold", option === value ? "bg-surface text-ink shadow-sm" : "text-muted")}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
