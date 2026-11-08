// Parameter form state: schema, current values and the start/stop actions.

import { reactive } from "vue";

import { station } from "@/stores/station";

export interface FieldSchema {
  name: string;
  label: string;
  type: "text" | "int" | "float" | "bool" | "choice";
  group: string;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  hint?: string;
  /** When set, the field is configured in the device dialog for this input mode. */
  dialog?: string;
}

interface ConfigStore {
  loaded: boolean;
  schema: FieldSchema[];
  groups: string[];
  values: Record<string, string | number | boolean>;
  sources: Record<string, string>;
  baseValues: Record<string, string | number | boolean>;
  baseSources: Record<string, string>;
  scopes: Record<string, string>;
  editable: Record<string, boolean>;
  control: boolean;
  busy: boolean;
  error: string;
  message: string;
  starting: boolean;
}

export const form = reactive<ConfigStore>({
  loaded: false,
  schema: [],
  groups: [],
  values: {},
  sources: {},
  baseValues: {},
  baseSources: {},
  scopes: {},
  editable: {},
  control: true,
  busy: false,
  error: "",
  message: "",
  starting: false,
});

const SOURCE_LABELS: Record<string, string> = {
  default: "默认",
  config: "配置文件",
  lab: "lab.toml",
  reward: "奖励配置",
  cli: "CLI",
  webui: "WebUI",
};

export function sourceLabel(source: string | undefined): string {
  if (!source) return "";
  return SOURCE_LABELS[source] ?? source;
}

export function setValue(name: string, value: string | number | boolean): void {
  form.values[name] = value;
  form.sources[name] = "webui";
}

export function resetConfig(): void {
  form.values = { ...form.baseValues };
  form.sources = { ...form.baseSources };
  form.error = "";
  form.message = "";
}

export function isBusy(): boolean {
  return station.status !== "idle";
}

export async function loadConfig(): Promise<void> {
  try {
    const response = await fetch("/api/config", { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`GET /api/config -> ${response.status}`);
    }
    const data = (await response.json()) as {
      schema: FieldSchema[];
      groups: string[];
      values: Record<string, string | number | boolean>;
      sources?: Record<string, string>;
      base_values?: Record<string, string | number | boolean>;
      base_sources?: Record<string, string>;
      scopes?: Record<string, string>;
      editable?: Record<string, boolean>;
      control: boolean;
    };
    form.schema = data.schema;
    form.groups = data.groups;
    form.values = { ...data.values };
    form.sources = { ...(data.sources ?? {}) };
    form.baseValues = { ...(data.base_values ?? data.values) };
    form.baseSources = { ...(data.base_sources ?? data.sources ?? {}) };
    form.scopes = { ...(data.scopes ?? {}) };
    form.editable = { ...(data.editable ?? {}) };
    form.control = data.control;
    form.loaded = true;
    form.error = "";
  } catch (err) {
    form.error = `无法读取参数表单: ${err instanceof Error ? err.message : String(err)}`;
  }
}

function payload(): Record<string, string | number | boolean> {
  const body: Record<string, string | number | boolean> = {};
  for (const field of form.schema) {
    const value = form.values[field.name];
    if (value !== undefined) {
      body[field.name] = value;
    }
  }
  return body;
}

export async function startRun(): Promise<void> {
  if (isBusy() || form.starting) {
    return;
  }
  form.starting = true;
  form.error = "";
  form.message = "";
  try {
    const response = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
    const data = (await response.json()) as { error?: string };
    if (!response.ok) {
      throw new Error(data.error ?? response.statusText);
    }
    form.message = "已启动，正在打开实验窗口…";
  } catch (err) {
    form.error = `无法启动：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    form.starting = false;
  }
}

export async function stopRun(): Promise<void> {
  form.error = "";
  try {
    const response = await fetch("/api/stop", { method: "POST" });
    const data = (await response.json()) as { stopping?: boolean; error?: string };
    if (!response.ok) {
      throw new Error(data.error ?? response.statusText);
    }
    form.message = data.stopping ? "已请求中止（等同按 Esc）" : "当前没有运行中的实验";
  } catch (err) {
    form.error = `中止失败：${err instanceof Error ? err.message : String(err)}`;
  }
}

export function clearMessages(): void {
  form.error = "";
  form.message = "";
}
