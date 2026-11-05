import { describe, expect, it } from "vitest";
import { NAV_MAIN, SLIDES, neighbors, slideForPath } from "./catalog";

describe("slide catalog", () => {
  it("lists all 24 concept screens with unique routes", () => {
    expect(SLIDES).toHaveLength(24);
    expect(new Set(SLIDES.map((slide) => slide.id)).size).toBe(24);
    expect(new Set(SLIDES.map((slide) => slide.href)).size).toBe(24);
    expect(SLIDES[0].href).toBe("/");
    expect(SLIDES[23].title).toBe("Design-System Specification");
  });

  it("resolves pager neighbors and special paths", () => {
    expect(neighbors("01").next.id).toBe("02");
    expect(neighbors("24").next.id).toBe("01");
    expect(slideForPath("/devices")?.id).toBe("04");
    expect(slideForPath("/runs/R-0278")?.id).toBe("21");
    expect(slideForPath("/coverage")?.id).toBe("24");
    expect(slideForPath("/screens")).toBeNull();
  });

  it("keeps the operator console destinations", () => {
    expect(NAV_MAIN.map((item) => item.label)).toEqual(["Mission", "Devices", "Vision", "Navigation", "Commands", "Runs", "Rehearsal", "Coverage", "Settings"]);
  });
});
