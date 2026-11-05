"use client";

import { useEffect, useState } from "react";

export type ThemeName = "dark" | "light";

export function readTheme(storage: Pick<Storage, "getItem"> | null): ThemeName {
  const saved = storage?.getItem("gmc-theme");
  return saved === "light" ? "light" : "dark";
}

export function useTheme(): { theme: ThemeName; setTheme: (theme: ThemeName) => void } {
  const [theme, setThemeState] = useState<ThemeName>("dark");

  useEffect(() => {
    setThemeState(readTheme(window.localStorage));
  }, []);

  function setTheme(next: ThemeName) {
    setThemeState(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem("gmc-theme", next);
  }

  return { theme, setTheme };
}
