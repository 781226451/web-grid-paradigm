// LSL state stream control (the marker stream is started with the session).

export interface LslSettings {
  stream: string;
  rate: number;
}

export async function setLsl(
  enabled: boolean,
  settings: LslSettings,
): Promise<string> {
  try {
    const response = await fetch("/api/lsl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled,
        stream: settings.stream,
        rate: settings.rate,
      }),
    });
    const data = (await response.json()) as { error?: string };
    if (!response.ok) {
      throw new Error(data.error ?? response.statusText);
    }
    return "";
  } catch (err) {
    return err instanceof Error ? err.message : String(err);
  }
}


