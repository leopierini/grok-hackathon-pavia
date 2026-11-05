import { describe, expect, it } from "vitest";
import { actionBody, groundPath } from "./api";

describe("api", () => {
  it("builds same-origin paths and includes the session epoch", () => {
    expect(groundPath("/actions/halt")).toBe("/api/ground/actions/halt");
    expect(actionBody(3, { scenario: "happy_path" })).toEqual({
      session_epoch: 3,
      scenario: "happy_path",
    });
  });
});
