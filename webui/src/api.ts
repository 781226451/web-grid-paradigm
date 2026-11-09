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

export interface ConfigArchive {
  blob: Blob;
  filename: string;
}

/** Ask the panel for the submitted parameters as a ZIP archive. */
export async function fetchConfigArchive(
  values: Record<string, string | number | boolean>,
): Promise<ConfigArchive> {
  const response = await fetch("/api/config/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as { error?: string };
    throw new Error(data.error ?? `POST /api/config/export -> ${response.status}`);
  }
  return {
    blob: await response.blob(),
    filename: downloadName(response.headers.get("Content-Disposition")),
  };
}

/** The server names the archive; never trust it as a filesystem path. */
function downloadName(disposition: string | null): string {
  const match = /filename="?([^";]+)"?/i.exec(disposition ?? "");
  const name = match?.[1]?.trim() ?? "";
  return /^[A-Za-z0-9._-]+\.zip$/.test(name) ? name : "webgrid-config.zip";
}
