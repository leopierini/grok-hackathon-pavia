import { describe, expect, it } from "vitest";
import { mapAvailable, rssiSeries } from "./navigation";

describe("navigation", () => {
  it("keeps only numeric rssi and refuses a missing map", () => {
    expect(rssiSeries([{ rssi_dbm: -60 }, { rssi_dbm: Number.NaN }])).toEqual([{ rssi_dbm: -60 }]);
    expect(mapAvailable({ map_renderable: false })).toBe(false);
    expect(mapAvailable(null)).toBe(false);
  });
});
