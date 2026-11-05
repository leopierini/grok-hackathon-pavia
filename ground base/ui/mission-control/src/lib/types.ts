export type ActionState = { enabled: boolean; reason: string };

export type Check = {
  id: string;
  label: string;
  status: string;
  blocking: boolean;
  detail: string;
};

export type CommandAck = {
  state: string;
  reason_code?: string | null;
  verified?: boolean | null;
  observed_motion?: string | null;
  sent_at?: string | null;
  message_id?: string | null;
};

export type CommandRow = {
  command_id: string | null;
  message_id?: string | null;
  destination?: string | null;
  action?: string | null;
  lease_ms?: number | null;
  expires_at?: string | null;
  lifecycle: string;
  execution_note: string;
  acks: CommandAck[];
};

export type EvidenceFrame = {
  source?: string | null;
  camera_id?: string | null;
  frame_id: string;
  camera_epoch?: number | null;
  captured_at?: string | null;
  age_ms: number | null;
  stale: boolean | null;
  stale_reason: string;
  calibration_id?: string | null;
  sha256?: string | null;
  image_ref?: string | null;
  simulated?: boolean | null;
  provenance?: string;
  media?: string;
  validation_status: string;
};

export type RssiPoint = { at?: string | null; rssi_dbm: number; quality?: string | null };

export type Snapshot = {
  transport: string;
  connection: string;
  updated_at: string;
  cursor: number;
  session_epoch: number;
  kernel: {
    contract_v1: string;
    protocol_v2: string;
    kernel_schema: string;
    log_schema: string;
    log_schema_status: string;
    providers: { task_id: string; slot: string }[];
    missing_providers: string[];
  };
  mission: {
    run_id: string | null;
    mission_id: string | null;
    mission_epoch: number | null;
    phase: string;
    phase_history: { phase: string; reason: string; at?: string }[];
    foundation_phase: string | null;
    armed: boolean;
    worker: string;
    scenario: string | null;
    seed: number | null;
    dog_transport: string | null;
    goal_reached: boolean;
    landing_verified: boolean;
    recovery_required: boolean;
    outcome: string | null;
    reason: string;
    halt_latched: boolean;
    halt_accepted: boolean;
    halt_delivered: boolean | null;
    supervised: boolean;
    waiting_for: string | null;
    active_operation: string | null;
    active_command_id: string | null;
    live_call_count: number;
    observed_at: string | null;
  };
  devices: Record<string, Device>;
  readiness: Check[];
  links: { name: string; medium: string | null; detail: string }[];
  commands: CommandRow[];
  chain: { id: string; label: string; state: string; detail: string }[];
  evidence: EvidenceFrame[];
  vision: {
    request: Record<string, unknown> | null;
    decision: Record<string, unknown> | null;
    proposal: unknown;
    model_id?: string | null;
    prompt_version?: string | null;
    waiting: boolean;
    provider_result: unknown;
    latency_note: string;
  };
  navigation: {
    navigation_mode: string | null;
    pose: unknown;
    map_id: string | null;
    map_epoch: number | null;
    map_renderable: boolean;
    map_reason: string;
    candidates: Record<string, unknown>[];
    blocked: boolean | null;
    candidate_reason?: string | null;
    beacon: Record<string, unknown> | null;
    rssi_points: RssiPoint[];
    rssi_windows: unknown[];
    selection: unknown;
    dog_motion_note: string;
  };
  safety: {
    halt_latched: boolean;
    halt_accepted: boolean;
    halt_delivered: boolean | null;
    recovery_required: boolean;
    reason: string;
    late_model: { kind?: string; detail?: string }[];
    step_control: StepControl | null;
  };
  activity: ActivityRow[];
  journal_count: number;
  provider_journal: Record<string, unknown>[];
  writer_state: string;
  metrics: unknown;
  metric_chart: { name: string; value: number }[];
  config: OperatorConfig;
  config_apply: Record<string, string>;
  unset: { field: string; detail: string }[];
  actions: Record<string, ActionState>;
  next_action: string;
  live_blockers: string[];
  scenarios: { id: string; detail: string }[];
  patrol?: {
    phase: string;
    detail: string;
    situation: string;
    summary: string;
    land_called: boolean;
    frames: { source: string; artifact_id: string }[];
    calls: { name: string; target: string; status: string; sent: boolean; reason: string }[];
  };
  dog_demo?: {
    profile: string;
    dog: string;
    laptop: string;
    drone: string;
    pi: string;
    active: boolean;
    view?: {
      open: boolean;
      ready: boolean;
      owns: boolean;
      detail: string;
    };
    last: Record<string, unknown> | null;
    limits?: DogLimits;
    ceiling?: DogLimits;
  };
};

export type DogLimits = {
  forward_m_s: number;
  side_m_s: number;
  yaw_rad_s: number;
  step_s: number;
};

export type Device = {
  name: string;
  role: string;
  mode: string;
  provenance: string;
  connection: string;
  profile: string | null;
  last_observation_at?: string | null;
  detail: string;
  telemetry?: Record<string, unknown>;
  error?: string | null;
};

export type ActivityRow = {
  cursor?: number;
  summary?: string;
  severity?: string;
  source?: string;
  kind?: string;
  category?: string;
  writer_state?: string;
  published?: boolean;
  ledger?: string;
  message_id?: string | null;
  command_id?: string | null;
  request_id?: string | null;
  track_id?: string | null;
  payload?: unknown;
};

export type StepControl = {
  revision?: number;
  halted?: boolean;
  active_step_id?: string | null;
  mission_remaining_s?: number;
  steps?: {
    step_id: string;
    label: string;
    status: string;
    reason: string;
    allowed_actions?: { set_budget?: boolean; wait_more?: boolean; retry?: boolean };
    attempts?: { attempt_id: string; pending?: boolean; error?: string | null }[];
  }[];
};

export type OperatorConfig = {
  dog_transport: "ethernet" | "wifi";
  connection_profiles: Record<string, string>;
  modes: { dog: string; drone: string; grok: string };
  pi_data_path: string | null;
  vision: { model_id: string; prompt_version: string };
  cameras: { drone: string[]; dog: string[] };
  evidence_age_ms: number;
  image_sample_ms: number;
  vision_timeout_ms: number;
  command_lease_ms: number;
  flight_profile: { name: string; enabled: boolean };
  calibration_id: string | null;
  dog_range_max_m: number | null;
  drone_horizontal_max_m: number | null;
  output_root: string;
  pace_s: number;
  secrets?: string;
};

export type StreamEvent = { cursor: number; snapshot: Snapshot };
