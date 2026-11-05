import type { ReactNode } from "react";

export function SessionDrawer({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-6 rounded-2xl border border-line bg-surface p-4 shadow-sm" aria-label={`Live session · ${title}`}>
      <h2 className="font-display text-lg font-semibold text-ink">Live session · {title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}
