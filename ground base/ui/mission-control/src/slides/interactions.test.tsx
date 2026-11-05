import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Slide04 } from "./s04-devices";
import { Slide05 } from "./s05-settings";
import { Slide06 } from "./s06-capabilities";
import { Slide07 } from "./s07-actions";
import { Slide08 } from "./s08-halt";
import { Slide09 } from "./s09-vision";
import { Slide13 } from "./s13-commands";
import { Slide15 } from "./s15-dog";
import { Slide20 } from "./s20-recovery";
import { Slide21 } from "./s21-runs";
import { Slide22 } from "./s22-metrics";
import { Slide23 } from "./s23-rehearsal";

describe("slide interactions", () => {
  it("keeps halt free of a confirmation dialog", () => {
    render(<Slide08 />);
    fireEvent.click(screen.getAllByRole("button", { name: /halt/i })[0]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("switches dog transport and keeps secrets refused", () => {
    render(<Slide05 />);
    fireEvent.click(screen.getByRole("radio", { name: "wifi" }));
    expect((screen.getByRole("radio", { name: "wifi" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("No secrets accepted")).toBeTruthy();
    expect(screen.getAllByText("UNSET").length).toBeGreaterThan(0);
  });

  it("shows the operational device fixture", () => {
    render(<Slide04 />);
    fireEvent.click(screen.getByRole("radio", { name: "Operational fixture" }));
    expect(screen.getByText("SOFTWARE SIMULATION ONLY · NOT HARDWARE ACCEPTANCE")).toBeTruthy();
    expect(screen.getAllByText(/back enclosure router/).length).toBeGreaterThan(0);
  });

  it("shows the rehearsal capability fixture and a disabled continue", () => {
    render(<Slide06 />);
    fireEvent.click(screen.getByRole("radio", { name: "Rehearsal fixture" }));
    expect(screen.getByText("REHEARSAL FIXTURES ONLY · NO PHYSICAL ACCEPTANCE")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("rejects a stale start confirmation", () => {
    render(<Slide07 />);
    expect(screen.getByText("Stale action rejected")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Confirm Start" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Close confirm" }));
    expect(screen.queryByText("Stale action rejected")).toBeNull();
  });

  it("filters vision requests down to the empty dropped bucket", () => {
    render(<Slide09 />);
    fireEvent.click(screen.getByRole("radio", { name: "Dropped" }));
    expect(screen.getAllByText(/Dropped \(0\)/).length).toBeGreaterThan(0);
  });

  it("filters timed-out commands", () => {
    render(<Slide13 />);
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "Timed Out" } });
    expect(screen.getByText("cmd-drone-x004")).toBeTruthy();
    expect(screen.queryByText("cmd-drone-x001")).toBeNull();
  });

  it("selects a different safe candidate", () => {
    render(<Slide15 />);
    fireEvent.click(screen.getByRole("radio", { name: /candidate-turn-left-01/ }));
    expect(screen.getAllByText(/candidate-turn-left-01/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Clearance · 0.7/)).toBeTruthy();
  });

  it("blocks a new ordinary run until recovery is verified", () => {
    render(<Slide20 />);
    expect((screen.getByRole("button", { name: "Start Ordinary Run" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Reset to Operational" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect((screen.getByRole("button", { name: "Reset to Operational" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("filters the journal to the warning row", () => {
    render(<Slide21 />);
    fireEvent.change(screen.getByRole("combobox", { name: "Severity" }), { target: { value: "WARN" } });
    expect(screen.getByText("latency.high")).toBeTruthy();
    expect(screen.queryByText("state.update")).toBeNull();
  });

  it("switches metrics to the empty journal without plotting zeros", () => {
    render(<Slide22 />);
    fireEvent.click(screen.getByRole("radio", { name: "Journal not supplied" }));
    expect(screen.getByText("No measured series")).toBeTruthy();
    expect(screen.getByText("ILLUSTRATIVE UI · NO MEASURED HARDWARE RUN")).toBeTruthy();
    expect(screen.queryByText("864")).toBeNull();
  });

  it("arms a simulated fault without leaving rehearsal", () => {
    render(<Slide23 />);
    fireEvent.click(screen.getByRole("checkbox", { name: /Stale frame/ }));
    expect(screen.getByText("Injection: selected faults")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start rehearsal" }));
    expect(screen.getByText(/happy_path is running in simulation/)).toBeTruthy();
  });
});
