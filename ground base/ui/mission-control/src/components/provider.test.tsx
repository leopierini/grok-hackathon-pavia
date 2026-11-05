import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useSession } from "./provider";

describe("useSession", () => {
  it("requires the operator provider", () => {
    expect(() => renderHook(() => useSession())).toThrow(/OperatorProvider/);
  });
});
