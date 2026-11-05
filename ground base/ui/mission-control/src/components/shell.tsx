"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft, ChevronRight, LayoutGrid } from "lucide-react";
import { neighbors, slideForPath } from "@/slides/catalog";
import { useTheme } from "@/hooks/useTheme";

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const slide = slideForPath(pathname);
  const { theme, setTheme } = useTheme();
  const adjacent = slide ? neighbors(slide.id) : null;
  return (
    <div className="canvas-grid min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-20 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-3 py-4 sm:px-5">
        <div className="flex flex-wrap items-center gap-3">
          {adjacent && slide ? (
            <>
              <Link href={adjacent.prev.href} aria-label={`Previous screen ${adjacent.prev.title}`} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-line bg-surface">
                <ChevronLeft className="h-4 w-4" aria-hidden />
              </Link>
              <p className="font-mono text-sm font-semibold text-ink">
                {slide.id} / 24
                <span className="ml-2 font-sans font-medium text-muted">{slide.title}</span>
              </p>
              <Link href={adjacent.next.href} aria-label={`Next screen ${adjacent.next.title}`} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-line bg-surface">
                <ChevronRight className="h-4 w-4" aria-hidden />
              </Link>
            </>
          ) : (
            <p className="text-sm font-semibold">All screens</p>
          )}
          <Link href="/screens" className="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-surface px-3 text-sm font-semibold">
            <LayoutGrid className="h-4 w-4" aria-hidden />
            All screens
          </Link>
          <button type="button" className="min-h-11 rounded-full border border-line bg-surface px-3 text-sm" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            Theme {theme === "dark" ? "dark" : "light"}
          </button>
        </div>
        <main id="main">{children}</main>
      </div>
    </div>
  );
}
