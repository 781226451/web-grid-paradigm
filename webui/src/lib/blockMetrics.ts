// Current-block view used by the progress bar and the KPI row.

import { computed } from "vue";

import { blockMetrics } from "@/lib/metrics";
import { station } from "@/stores/station";

export function useBlockMetrics() {
  const config = computed(() => station.state.config ?? {});

  const cells = computed(() => {
    const grid = station.state.grid;
    if (grid) {
      return grid.rows * grid.cols;
    }
    return Number(config.value.rows ?? 0) * Number(config.value.cols ?? 0);
  });

  const clickTypes = computed(() => Number(config.value.click_types ?? 1));

  /** Block wall time, extrapolated between SSE messages while it runs. */
  const elapsed = computed(() => {
    const base = station.state.block_elapsed;
    if (base === null || base === undefined) {
      return null;
    }
    const running = ["run", "feedback", "iti"].includes(String(station.state.phase));
    return base + (running ? (performance.now() - station.receivedAt) / 1000 : 0);
  });

  const trials = computed(() =>
    station.trials.filter((trial) => trial.block === station.state.block),
  );

  const stats = computed(() =>
    blockMetrics(trials.value, elapsed.value, cells.value, clickTypes.value),
  );

  return { config, cells, clickTypes, elapsed, trials, stats };
}
