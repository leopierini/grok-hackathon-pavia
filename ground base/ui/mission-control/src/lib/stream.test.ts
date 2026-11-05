import { describe, expect, it } from "vitest";
import { backoffMs, hasGap, parseEventData, shouldApplyCursor } from "./stream";

describe("stream", () => {
  it("parses a snapshot event and rejects junk", () => {
    const event = parseEventData(JSON.stringify({ cursor: 3, snapshot: { cursor: 3 } }));
    expect(event?.cursor).toBe(3);
    expect(parseEventData("not-json")).toBeNull();
    expect(parseEventData(JSON.stringify({ cursor: 1 }))).toBeNull();
  });

  it("detects gaps and ignores older cursors", () => {
    expect(hasGap(4, 6)).toBe(true);
    expect(hasGap(4, 5)).toBe(false);
    expect(hasGap(0, 8)).toBe(false);
    expect(shouldApplyCursor(4, 4)).toBe(true);
    expect(shouldApplyCursor(4, 3)).toBe(false);
  });

  it("backs off and caps the reconnect delay", () => {
    expect(backoffMs(0)).toBe(500);
    expect(backoffMs(500)).toBe(1000);
    expect(backoffMs(4000)).toBe(5000);
  });
});
