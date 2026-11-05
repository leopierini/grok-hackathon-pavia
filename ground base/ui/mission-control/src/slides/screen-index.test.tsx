import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScreenIndex } from "./screen-index";

describe("screen index", () => {
  it("links every concept slide", () => {
    render(<ScreenIndex />);
    expect(screen.getAllByRole("link").length).toBe(24);
    expect(screen.getByRole("link", { name: /Frame provenance/ }).getAttribute("href")).toBe("/evidence");
    expect(screen.getByRole("link", { name: /Design-System Specification/ }).getAttribute("href")).toBe("/design-system");
  });
});
