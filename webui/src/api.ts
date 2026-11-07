// Typed access to the Python control panel API.

export interface StationState {
  phase?: string | null;
  subject?: string | null;
  session_id?: string | null;
  block?: number | null;
  trials_done?: number | null;
  [key: string]: unknown;
}

export interface Snapshot {
  status: string;
  control: boolean;
  state: StationState;
  [key: string]: unknown;
}

export async function fetchState(): Promise<Snapshot> {
  const response = await fetch("/api/state", { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`GET /api/state -> ${response.status}`);
  }
  return (await response.json()) as Snapshot;
}

export async function fetchConfig(): Promise<Record<string, unknown>> {
  const response = await fetch("/api/config", { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`GET /api/config -> ${response.status}`);
  }
  return (await response.json()) as Record<string, unknown>;
}
