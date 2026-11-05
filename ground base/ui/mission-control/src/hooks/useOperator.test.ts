import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useOperator } from "./useOperator";

class FakeSource {
  static instances: FakeSource[] = [];
  listeners = new Map<string, (event: Event) => void>();
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeSource.instances.push(this);
  }
  addEventListener(name: string, listener: (event: Event) => void) {
    this.listeners.set(name, listener);
  }
  close() {}
  emit(name: string, data: unknown) {
    this.listeners.get(name)?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

describe("useOperator", () => {
  it("loads a snapshot and does not post a mutation on mount", async () => {
    FakeSource.instances = [];
    vi.stubGlobal("EventSource", FakeSource);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useOperator());
    const source = FakeSource.instances[0];
    source.emit("snapshot", {
      cursor: 1,
      snapshot: { cursor: 1, session_epoch: 2, mission: { phase: "IDLE" }, actions: {} },
    });
    await waitFor(() => expect(result.current.snapshot?.session_epoch).toBe(2));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.stream).toBe("live");
  });
});
