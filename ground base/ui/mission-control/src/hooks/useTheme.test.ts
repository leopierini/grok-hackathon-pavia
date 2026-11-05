import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { readTheme, useTheme } from "./useTheme";

describe("useTheme", () => {
  it("reads only the saved light or dark choice", () => {
    expect(readTheme({ getItem: () => "light" })).toBe("light");
    expect(readTheme({ getItem: () => "nope" })).toBe("dark");
    expect(readTheme(null)).toBe("dark");
  });

  it("stores the theme on the document", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("light"));
    expect(result.current.theme).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("gmc-theme")).toBe("light");
  });
});
