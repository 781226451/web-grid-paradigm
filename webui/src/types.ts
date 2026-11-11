// Wire types for the SSE payload published by web_grid_paradigm.panel.state.

export interface GridInfo {
  rows: number;
  cols: number;
  left: number;
  top: number;
  pitch: number;
  line: number;
}

export interface TargetInfo {
  row: number;
  col: number;
  label: string;
  button: number;
  index: number;
}

export interface ExperimentConfigView {
  rows?: number;
  cols?: number;
  blocks?: number;
  targets?: number;
  iti?: number;
  block_rest?: number;
  countdown_seconds?: number;
  selection?: string;
  dwell_time?: number;
  input?: string;
  max_seconds?: number;
  reward?: string;
  reward_amount?: number;
  reward_duration_ms?: number;
  reward_policy?: string;
  reward_ratio?: number;
  reward_port?: string;
  reward_baud?: number;
  lsl?: boolean;
  lsl_stream?: string;
  [key: string]: unknown;
}

export interface StationState {
  phase?: string | null;
  subject?: string | null;
  session_id?: string | null;
  data_dir?: string | null;
  config?: ExperimentConfigView | null;
  grid?: GridInfo | null;
  block?: number | null;
  trials_done?: number | null;
  target?: TargetInfo | null;
  cursor?: [number, number] | null;
  dwell_progress?: number | null;
  block_elapsed?: number | null;
  block_bps?: number | null;
  fps?: number | null;
  flash_until?: number | null;
  aborted?: boolean | null;
  reward_mode?: string | null;
  reward_policy?: string | null;
  reward_count?: number | null;
  reward_total?: number | null;
  error?: string | null;
  [key: string]: unknown;
}

export interface Trial {
  block: number;
  trial: number;
  cell: string;
  outcome: "hit" | "timeout";
  reason?: string;
  rt: number;
  misclicks: number;
  path_efficiency: number | null;
}

export interface BlockResult {
  block: number;
  attempts: number;
  hits: number;
  misclicks: number;
  timeouts: number;
  bps: number;
  mean_rt_s: number | null;
  duration_s: number;
  aborted: boolean;
}

export interface RunResult {
  id: number;
  status: string;
  subject: string;
  blocks: number;
  trials_per_block: number;
  rows: number;
  cols: number;
  hits: number | null;
  attempts: number | null;
  bps: number | null;
  data_dir: string;
}

export interface LslStatus {
  enabled: boolean;
  live: boolean;
  stream: string;
  rate: number;
  sent: number;
  consumers: number;
  error: string | null;
}

export interface RewardDeviceStatus {
  connected: boolean;
  port: string;
  baud: number;
  sent: number;
  errors: number;
  error: string | null;
  ports: { device: string; description: string }[];
}

export interface Snapshot {
  reset: boolean;
  server_time: number;
  status: string;
  control: boolean;
  state: StationState;
  trial_offset: number;
  trials: Trial[];
  blocks: BlockResult[];
  runs: RunResult[];
  logs: string[];
  lsl?: LslStatus;
  reward_device?: RewardDeviceStatus;
}
