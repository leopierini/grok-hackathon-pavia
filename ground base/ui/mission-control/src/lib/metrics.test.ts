import { describe, expect, it } from "vitest";
import { chartableMetrics } from "./metrics";

describe("metrics", () => {
  it("drops null and non-finite values instead of plotting them as zero", () => {
    expect(
      chartableMetrics([
        { name: "goal", value: null },
        { name: "hold", value: 1.2 },
        { name: "bad", value: Number.NaN },
      ]),
    ).toEqual([{ name: "hold", value: 1.2 }]);
  });
});
