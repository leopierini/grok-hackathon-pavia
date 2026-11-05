import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Slide02 } from "./s02-cockpit";

describe("cockpit phase rail", () => {
  it("links each phase and keeps the speed sliders on the mission card", () => {
    render(<Slide02 />);
    expect(screen.getByRole("link", { name: "Open CONNECT" }).getAttribute("href")).toBe("/devices");
    expect(screen.getByRole("link", { name: "Open SCOUT" }).getAttribute("href")).toBe("/vision");
    expect(screen.getByRole("link", { name: "Open TRACK" }).getAttribute("href")).toBe("/commands");
    expect(screen.getByRole("link", { name: "Open HOLD" }).getAttribute("href")).toBe("/navigation");
    expect(screen.getByRole("link", { name: "Open HOME" }).getAttribute("href")).toBe("/dog");
    expect(screen.getByRole("link", { name: "Open DOG VISION" }).getAttribute("href")).toBe("/handoff");
    expect(screen.getByRole("link", { name: "Open PROXIMITY" }).getAttribute("href")).toBe("/proximity");
    expect(screen.getByRole("link", { name: "Open LAND" }).getAttribute("href")).toBe("/recovery");
    expect(screen.getByRole("link", { name: "Open DONE" }).getAttribute("href")).toBe("/runs");
    expect(screen.getByRole("link", { name: "Log" }).getAttribute("href")).toBe("/runs");
    expect(screen.getByRole("slider", { name: "Forward velocity" })).toBeTruthy();
    expect(screen.getByRole("slider", { name: "Side velocity" })).toBeTruthy();
    expect(screen.getByRole("slider", { name: "Turn rate" })).toBeTruthy();
    expect(screen.getByRole("slider", { name: "Step length" })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Start patrol" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
