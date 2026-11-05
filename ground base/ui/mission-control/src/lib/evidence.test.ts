import { describe, expect, it } from "vitest";
import { evidenceIsStale, sameFrame } from "./evidence";

describe("evidence", () => {
  it("does not treat a missing stale flag as fresh", () => {
    expect(evidenceIsStale({ stale: null })).toBe("unknown");
    expect(evidenceIsStale({ stale: true })).toBe("stale");
    expect(evidenceIsStale({ stale: false })).toBe("fresh");
  });

  it("binds an overlay only to the same frame", () => {
    expect(sameFrame("frame-a", "frame-a")).toBe(true);
    expect(sameFrame("frame-a", "frame-b")).toBe(false);
    expect(sameFrame(null, "frame-a")).toBe(false);
  });
});
