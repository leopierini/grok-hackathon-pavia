import { describe, expect, it } from "vitest";
import { controlState, haltSkipsConfirmation, requiresRecoveryToken } from "./actions";
import type { Snapshot } from "./types";

const mission = {
  goal_reached: true,
  landing_verified: false,
  recovery_required: true,
} as Snapshot["mission"];

describe("actions", () => {
  it("does not ask halt for confirmation", () => {
    expect(haltSkipsConfirmation()).toBe(true);
  });

  it("requires a token while landing is unresolved", () => {
    expect(requiresRecoveryToken(mission)).toBe(true);
    expect(
      requiresRecoveryToken({ ...mission, landing_verified: true, recovery_required: false }),
    ).toBe(false);
  });

  it("reads enablement from the backend action map", () => {
    expect(controlState({ halt: { enabled: true, reason: "now" } }, "halt")).toEqual({
      enabled: true,
      reason: "now",
    });
    expect(controlState(undefined, "arm").enabled).toBe(false);
  });
});
