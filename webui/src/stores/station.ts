// Live station state fed by the Server-Sent Events stream.

import { reactive } from "vue";

import type {
  BlockResult,
  LslStatus,
  RewardDeviceStatus,
  RunResult,
  Snapshot,
  StationState,
  Trial,
} from "@/types";

const MAX_LOGS = 400;

interface StationStore {
  connected: boolean;
  status: string;
  control: boolean;
  state: StationState;
  trials: Trial[];
  blocks: BlockResult[];
  runs: RunResult[];
  logs: string[];
  lsl: LslStatus | null;
  rewardDevice: RewardDeviceStatus | null;
  serverOffset: number; // server clock - browser clock, in seconds
  receivedAt: number; // performance.now() of the last message
  error: string;
}

export const station = reactive<StationStore>({
  connected: false,
  status: "idle",
  control: true,
  state: {},
  trials: [],
  blocks: [],
  runs: [],
  logs: [],
  lsl: null,
  rewardDevice: null,
  serverOffset: 0,
  receivedAt: 0,
  error: "",
});

let source: EventSource | null = null;

function apply(message: Snapshot): void {
  station.serverOffset = message.server_time - Date.now() / 1000;
  station.receivedAt = performance.now();
  station.status = message.status;
  station.control = message.control;
  station.state = message.state ?? {};

  if (message.reset) {
    station.trials = [];
    station.logs = [];
  }
  // `trial_offset` is how many trials the browser already has; anything after
  // it is new, which keeps the payload small at 10-30 Hz.
  station.trials.length = message.trial_offset;
  station.trials.push(...message.trials);

  station.blocks = message.blocks;
  station.runs = message.runs;
  station.lsl = message.lsl ?? station.lsl;
  station.rewardDevice = message.reward_device ?? station.rewardDevice;

  if (message.logs.length) {
    station.logs.push(...message.logs);
    if (station.logs.length > MAX_LOGS) {
      station.logs.splice(0, station.logs.length - MAX_LOGS);
    }
  }
}

export function connect(): void {
  if (source !== null) {
    return;
  }
  source = new EventSource("/events");
  source.onopen = () => {
    station.connected = true;
    station.error = "";
  };
  source.onmessage = (event: MessageEvent<string>) => {
    try {
      apply(JSON.parse(event.data) as Snapshot);
    } catch (err) {
      station.error = `无法解析推送数据: ${String(err)}`;
    }
  };
  source.onerror = () => {
    station.connected = false;
    station.error = "与控制台的连接断开，正在自动重连…";
  };
}

export function disconnect(): void {
  source?.close();
  source = null;
  station.connected = false;
}

/** Current server time (seconds), for elapsed clocks and flash effects. */
export function serverNow(): number {
  return Date.now() / 1000 + station.serverOffset;
}

export function resetLogs(): void {
  station.logs = [];
}
