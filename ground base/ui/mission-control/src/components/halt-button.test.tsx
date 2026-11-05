import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HaltButton } from "./ui";

describe("HaltButton", () => {
  it("submits immediately without a confirmation dialog", () => {
    const onHalt = vi.fn();
    render(<HaltButton onHalt={onHalt} />);
    fireEvent.click(screen.getByRole("button", { name: /halt/i }));
    expect(onHalt).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
