// Information-transfer metrics.

// Achieved bitrate of Nuyujukian et al. 2021 (Technical Report 01: GPT-BCIs),
// Eqn. 2:
//   B = log2(N) * max(S_c - S_i, 0) / t
// The paper's "N - 1" accounts for a delete key; the web-grid task has none,
// so N = cells * click types is used directly.  The max(..., 0) clamp keeps a
// block with more misclicks than hits at 0 bits/s instead of a negative rate.

import type { Trial } from "@/types";

export function bitsPerTarget(cells: number, clickTypes = 1): number {
  if (cells < 1 || clickTypes < 1) {
    return 0;
  }
  return Math.log2(cells * clickTypes);
}

export interface BlockMetrics {
  attempts: number;
  hits: number;
  misclicks: number;
  net: number;
  bits: number;
  bps: number | null;
}

export function blockMetrics(
  trials: Trial[],
  elapsedSeconds: number | null,
  cells: number,
  clickTypes = 1,
): BlockMetrics {
  const hits = trials.filter((trial) => trial.outcome === "hit").length;
  const misclicks = trials.reduce((sum, trial) => sum + (trial.misclicks ?? 0), 0);
  const net = hits - misclicks;
  const bits = bitsPerTarget(cells, clickTypes);
  const bps =
    elapsedSeconds !== null && elapsedSeconds > 0 && trials.length > 0
      ? (Math.max(net, 0) * bits) / elapsedSeconds
      : null;
  return { attempts: trials.length, hits, misclicks, net, bits, bps };
}
