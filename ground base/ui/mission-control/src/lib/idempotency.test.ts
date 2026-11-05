import { describe, expect, it } from "vitest";
import { createIdempotencyKey, shouldReplayOnReload } from "./idempotency";

describe("idempotency", () => {
  it("creates a key and never replays a mutation after reload", () => {
    expect(createIdempotencyKey().length).toBeGreaterThan(8);
    expect(shouldReplayOnReload()).toBe(false);
  });
});
