import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Shell } from "./shell";

vi.mock("next/navigation", () => ({ usePathname: () => "/devices" }));
vi.mock("@/hooks/useTheme", () => ({ useTheme: () => ({ theme: "light", setTheme: vi.fn() }) }));

describe("shell pager", () => {
  it("shows the devices slide between its neighbors", () => {
    render(
      <Shell>
        <p>Devices body</p>
      </Shell>,
    );
    expect(screen.getByText(/04 \/ 24/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Previous screen/ }).getAttribute("href")).toBe("/mission-state");
    expect(screen.getByRole("link", { name: /Next screen/ }).getAttribute("href")).toBe("/settings");
    expect(screen.getByRole("link", { name: "All screens" }).getAttribute("href")).toBe("/screens");
  });
});
