import { describe, expect, it } from "vitest";
import { executionLabel } from "./commands";

describe("commands", () => {
  it("separates accepted from completed", () => {
    expect(executionLabel({ lifecycle: "accepted", execution_note: "other" })).toMatch(/not complete/);
    expect(executionLabel({ lifecycle: "completed", execution_note: "recorded" })).toBe("recorded");
  });
});
