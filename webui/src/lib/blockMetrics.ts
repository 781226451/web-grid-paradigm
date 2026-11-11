// Live block values shared by the progress bar and the KPI row.

import { computed } from "vue";

import { station } from "@/stores/station";

export function useBlockMetrics() {
  /** Wall-clock block time, extrapolated between SSE messages while it runs. */
  const elapsed = computed(() => {
    const base = station.state.block_elapsed;
    if (base === null || base === undefined) {
      return null;
    }
    const running = ["run", "iti"].includes(String(station.state.phase));
    return base + (running ? (performance.now() - station.receivedAt) / 1000 : 0);
  });

  /** Server-computed BPS on active target time (ITI excluded). */
  const bps = computed(() => station.state.block_bps ?? null);

  return { elapsed, bps };
}
