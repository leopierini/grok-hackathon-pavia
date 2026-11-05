import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Snapshot } from "@/lib/types";
import { HomeSession } from "./home-session";
import { RehearsalSession } from "./rehearsal-session";
import { CommandsSession } from "./commands-session";
import { SettingsSession } from "./settings-session";

const harness = vi.hoisted(() => ({
  run: vi.fn(async () => ({ ok: true })),
  pending: null as string | null,
  error: null as string | null,
  snapshot: null as Snapshot | null,
}));

vi.mock("@/components/provider", () => ({
  useSession: () => ({
    snapshot: harness.snapshot,
    run: harness.run,
    pending: harness.pending,
    error: harness.error,
  }),
}));

vi.mock("@/hooks/useTheme", () => ({ useTheme: () => ({ theme: "dark", setTheme: vi.fn() }) }));

function snapshot(overrides: { patrolPhase?: string; armed?: boolean } = {}): Snapshot {
  return {
    transport: "ethernet",
    connection: "live",
    updated_at: "2026-11-04T13:00:12Z",
    cursor: 4,
    session_epoch: 1,
    kernel: {
      contract_v1: "1.0",
      protocol_v2: "2.0-draft",
      kernel_schema: "kernel",
      log_schema: "proposed-1",
      log_schema_status: "proposed_pending_team",
      providers: [],
      missing_providers: [],
    },
    mission: {
      run_id: "run-1",
      mission_id: "demo-20261104-001",
      mission_epoch: 1,
      phase: "SCOUT",
      phase_history: [{ phase: "CONNECT", reason: "checking links", at: "2026-11-04T13:00:10Z" }],
      foundation_phase: "IDLE",
      armed: overrides.armed ?? false,
      worker: "idle",
      scenario: "happy_path",
      seed: 0,
      dog_transport: "ethernet",
      goal_reached: false,
      landing_verified: false,
      recovery_required: false,
      outcome: null,
      reason: "",
      halt_latched: false,
      halt_accepted: false,
      halt_delivered: null,
      supervised: false,
      waiting_for: null,
      active_operation: null,
      active_command_id: null,
      live_call_count: 0,
      observed_at: "2026-11-04T13:00:10Z",
    },
    devices: {},
    readiness: [],
    links: [],
    commands: [],
    chain: [],
    evidence: [],
    vision: {
      request: null,
      decision: null,
      proposal: null,
      waiting: false,
      provider_result: null,
      latency_note: "unknown",
    },
    navigation: {
      navigation_mode: null,
      pose: null,
      map_id: null,
      map_epoch: null,
      map_renderable: false,
      map_reason: "no map",
      candidates: [],
      blocked: null,
      beacon: null,
      rssi_points: [],
      rssi_windows: [],
      selection: null,
      dog_motion_note: "",
    },
    safety: {
      halt_latched: false,
      halt_accepted: false,
      halt_delivered: null,
      recovery_required: false,
      reason: "",
      late_model: [],
      step_control: {
        revision: 2,
        active_step_id: "g15",
        steps: [
          {
            step_id: "g15",
            label: "schedule",
            status: "running",
            reason: "none",
            allowed_actions: { wait_more: true, retry: true },
            attempts: [{ attempt_id: "attempt-1" }],
          },
        ],
      },
    },
    activity: [],
    journal_count: 0,
    provider_journal: [],
    writer_state: "enqueued",
    metrics: null,
    metric_chart: [],
    config: {
      dog_transport: "ethernet",
      connection_profiles: {},
      modes: { dog: "fake", drone: "fake", grok: "fake" },
      pi_data_path: "usb",
      vision: { model_id: "CONFIGURE_VERIFIED_IMAGE_MODEL", prompt_version: "patrol-demo-v2.0" },
      cameras: { drone: [], dog: [] },
      evidence_age_ms: 3000,
      image_sample_ms: 1000,
      vision_timeout_ms: 5000,
      command_lease_ms: 500,
      flight_profile: { name: "proposed_4m_floor_agl", enabled: false },
      calibration_id: null,
      dog_range_max_m: null,
      drone_horizontal_max_m: null,
      output_root: "artifacts",
      pace_s: 0,
    },
    config_apply: {},
    unset: [],
    actions: {
      arm: { enabled: true, reason: "ready" },
      supervised: { enabled: true, reason: "ready" },
      start: { enabled: true, reason: "ready" },
      reset: { enabled: true, reason: "ready" },
    },
    next_action: "Continue the rehearsal.",
    live_blockers: [],
    scenarios: [{ id: "happy_path", detail: "Readiness through landing." }],
    patrol: {
      phase: overrides.patrolPhase ?? "idle",
      detail: "Patrol is idle.",
      situation: "awaiting_ai",
      summary: "No call yet.",
      land_called: false,
      frames: [],
      calls: [],
    },
    dog_demo: {
      profile: "dog.ethernet",
      dog: "192.168.123.161",
      laptop: "192.168.123.222",
      drone: "tello",
      pi: "usb",
      active: false,
      last: null,
      limits: { forward_m_s: 0.18, side_m_s: 0.12, yaw_rad_s: 0.36, step_s: 0.6 },
      ceiling: { forward_m_s: 0.3, side_m_s: 0.2, yaw_rad_s: 0.6, step_s: 1 },
    },
  };
}

describe("live operator controls", () => {
  beforeEach(() => {
    HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as unknown as typeof HTMLCanvasElement.prototype.getContext;
    harness.run.mockClear();
    harness.run.mockResolvedValue({ ok: true });
    harness.pending = null;
    harness.error = null;
    harness.snapshot = snapshot();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ ok: true, detail: "Saved", text: "guide" }) })));
  });

  it("sends patrol, cable, and dog actions through the operator run function", async () => {
    render(<HomeSession />);
    fireEvent.click(screen.getByRole("button", { name: "Start patrol" }));
    expect(harness.run).toHaveBeenCalledWith("start_patrol");

    fireEvent.click(screen.getByRole("button", { name: "Check the cable" }));
    expect(harness.run).toHaveBeenCalledWith("probe");

    fireEvent.change(screen.getByRole("slider", { name: "Forward velocity" }), { target: { value: "0.22" } });
    fireEvent.change(screen.getByRole("slider", { name: "Turn rate" }), { target: { value: "0.4" } });
    fireEvent.click(screen.getByRole("button", { name: "Try the steps in practice" }));
    await vi.waitFor(() =>
      expect(harness.run).toHaveBeenCalledWith(
        "dog_test",
        expect.objectContaining({
          dog: "sim",
          limits: expect.objectContaining({ forward_m_s: 0.22, yaw_rad_s: 0.4, side_m_s: 0.12, step_s: 0.6 }),
        }),
      ),
    );
    expect(harness.run).toHaveBeenCalledWith("arm");

    fireEvent.click(screen.getByRole("button", { name: "Try four short steps" }));
    await vi.waitFor(() => expect(harness.run).toHaveBeenCalledWith("dog_test", expect.objectContaining({ dog: "ethernet" })));

    fireEvent.click(screen.getByRole("button", { name: "Run the short demo" }));
    await vi.waitFor(() =>
      expect(harness.run).toHaveBeenCalledWith(
        "start",
        expect.objectContaining({ scenario: "happy_path", dog: "ethernet", pace_s: 0, seed: 0 }),
      ),
    );
    expect(screen.getByRole("link", { name: "Open SCOUT" }).getAttribute("href")).toBe("/vision");
    expect(screen.getByRole("link", { name: "Open TRACK" }).getAttribute("href")).toBe("/commands");
    expect(screen.getByRole("link", { name: "Open HOLD" }).getAttribute("href")).toBe("/navigation");
    expect(screen.getByRole("link", { name: "Log" }).getAttribute("href")).toBe("/runs");
  });

  it("keeps the speed controls visible before the session connects", () => {
    harness.snapshot = null;
    render(<HomeSession />);
    expect((screen.getByRole("button", { name: "Start patrol" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("slider", { name: "Turn rate" })).toBeTruthy();
  });

  it("stops patrol only while a patrol is waiting", () => {
    harness.snapshot = snapshot({ patrolPhase: "waiting" });
    render(<HomeSession />);
    expect((screen.getByRole("button", { name: "Start patrol" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Stop patrol" }));
    expect(harness.run).toHaveBeenCalledWith("stop_patrol");
  });

  it("opens and closes the dog camera through dog_view", () => {
    render(<HomeSession />);
    fireEvent.click(screen.getByRole("button", { name: "Practice view" }));
    expect(harness.run).toHaveBeenCalledWith("dog_view", { open: true, dog: "sim" });
    fireEvent.click(screen.getByRole("button", { name: "Live view" }));
    expect(harness.run).toHaveBeenCalledWith("dog_view", { open: true, dog: "ethernet" });
  });

  it("arms, starts, and resets a rehearsal scenario", () => {
    render(<RehearsalSession />);
    fireEvent.click(screen.getByRole("button", { name: /Arm session/ }));
    expect(harness.run).toHaveBeenCalledWith("arm");
    fireEvent.click(screen.getByRole("button", { name: "Supervised" }));
    expect(harness.run).toHaveBeenCalledWith("supervised");
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(harness.run).toHaveBeenCalledWith("start", { scenario: "happy_path", pace_s: 0, seed: 0 });
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(harness.run).toHaveBeenCalledWith("reset", { recovery_token: "" });
  });

  it("posts wait and retry for the active command step", async () => {
    render(<CommandsSession />);
    fireEvent.click(screen.getByRole("button", { name: "Wait longer" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry if allowed" }));
    await vi.waitFor(() => expect(harness.run).toHaveBeenCalledWith("status"));
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    await vi.waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2));
    const bodies = fetchMock.mock.calls.map((call) => JSON.parse(String(call[1].body)) as { action: string });
    expect(bodies.map((body) => body.action).sort()).toEqual(["retry", "wait_more"]);
  });

  it("saves connection and vision settings to the config endpoint", async () => {
    render(<SettingsSession />);
    fireEvent.click(screen.getByRole("button", { name: "Validate and save" }));
    await screen.findByText("Saved");
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/ground/config");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });
});
