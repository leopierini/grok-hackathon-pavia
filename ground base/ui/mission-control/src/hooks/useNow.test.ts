import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ageLabel, useNow } from "./useNow";

describe("useNow", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("describes API age without moving the mission phase", () => {
    expect(ageLabel(5_000, new Date(0).toISOString())).toMatch(/API update/);
    expect(ageLabel(0, null)).toBe("update time unknown");
  });

  it("ticks forward on the interval", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useNow(1000));
    const first = result.current;
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBeGreaterThanOrEqual(first);
  });
});
