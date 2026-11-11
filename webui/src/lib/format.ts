// Small formatting helpers shared by the monitoring components.

export const TARGET_COLORS: Record<number, string> = {
  1: "#0a84ff",
  2: "#ff9500",
  3: "#af52de",
};

export const PHASE_LABELS: Record<string, string> = {
  starting: "启动中",
  intro: "指导语",
  countdown: "倒计时",
  run: "运行中",
  iti: "trial 间休息",
  rest: "block 间休息",
  done: "已结束",
  aborted: "已中止",
  stopping: "正在中止",
  finishing: "收尾中…",
  idle: "空闲",
};

export function fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "–";
  }
  return value.toFixed(digits);
}

export function phaseLabel(phase: string | null | undefined, status: string): string {
  if (status === "stopping") {
    return PHASE_LABELS.stopping;
  }
  if (phase === "done" && status === "running") {
    return PHASE_LABELS.finishing;
  }
  if (!phase) {
    return status === "idle" ? PHASE_LABELS.idle : status;
  }
  return PHASE_LABELS[phase] ?? phase;
}
