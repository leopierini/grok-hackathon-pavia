import { describe, expect, it } from "vitest";
import { formatAge, formatDbm, formatUnknown, statusLabel } from "./format";

describe("format", () => {
  it("keeps null unknown and keeps a real zero", () => {
    expect(formatUnknown(null)).toBe("unknown");
    expect(formatUnknown(undefined)).toBe("unknown");
    expect(formatUnknown("")).toBe("unknown");
    expect(formatUnknown(0)).toBe("0");
    expect(formatUnknown(Number.NaN)).toBe("unknown");
  });

  it("formats age and rssi without turning missing into zero", () => {
    expect(formatAge(null)).toBe("age unknown");
    expect(formatAge(250)).toBe("250 ms");
    expect(formatAge(1500)).toBe("1.5 s");
    expect(formatDbm(null)).toBe("unknown dBm");
    expect(formatDbm(-62)).toBe("-62 dBm");
  });

  it("labels status text", () => {
    expect(statusLabel("pass")).toBe("pass");
    expect(statusLabel("custom")).toBe("custom");
  });
});
