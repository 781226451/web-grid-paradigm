// Reward device connection and one-shot self-test.

import { station } from "@/stores/station";

export interface DeviceStatus {
  connected: boolean;
  port: string;
  baud: number;
  sent: number;
  errors: number;
  error: string | null;
  ports: { device: string; description: string }[];
}

export function device(): DeviceStatus {
  return (
    station.rewardDevice ?? {
      connected: false,
      port: "",
      baud: 9600,
      sent: 0,
      errors: 0,
      error: null,
      ports: [],
    }
  );
}

export async function connectReward(port: string, baud: number): Promise<string> {
  try {
    const response = await fetch("/api/reward/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ port, baud }),
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

export async function disconnectReward(): Promise<string> {
  try {
    const response = await fetch("/api/reward/disconnect", { method: "POST" });
    if (!response.ok) {
      const data = (await response.json()) as { error?: string };
      throw new Error(data.error ?? response.statusText);
    }
    return "";
  } catch (err) {
    return err instanceof Error ? err.message : String(err);
  }
}

export async function testReward(payload: Record<string, unknown>): Promise<string> {
  try {
    const response = await fetch("/api/reward/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = (await response.json()) as { error?: string; command?: string; sink?: string };
    if (!response.ok) {
      throw new Error(data.error ?? response.statusText);
    }
    return `已发送：${data.command ?? ""}（${data.sink ?? ""}）`;
  } catch (err) {
    return `失败：${err instanceof Error ? err.message : String(err)}`;
  }
}
