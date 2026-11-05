import Link from "next/link";
import { SLIDES } from "@/slides/catalog";

export function ScreenIndex() {
  return (
    <section>
      <h1 className="font-display text-4xl font-semibold">All 24 screens</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">Each board is a custom console view. Use the pager on any screen to move one by one. Live session controls stay in the drawer under the matching screen.</p>
      <ol className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {SLIDES.map((slide) => (
          <li key={slide.id}>
            <Link href={slide.href} className="block min-h-24 rounded-2xl border border-line bg-surface p-4 shadow-sm hover:border-blue">
              <span className="font-mono text-xs font-bold text-blue">{slide.id} / 24</span>
              <span className="mt-1 block font-display text-lg font-semibold">{slide.title}</span>
              <span className="mt-1 block text-sm text-muted">{slide.lede}</span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
