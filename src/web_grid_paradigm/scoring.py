"""Scoring for the web-grid task.

The score follows the information-transfer logic used by web-grid tasks:
each selection carries ``log2(grid cells × click types)`` bits, and the
throughput is the *net* number of correct selections per minute multiplied by
those bits.  Misclicks subtract one target from the net count, which is why
accuracy matters as much as speed.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


def bits_per_target(n_cells: int, click_types: int = 1) -> float:
    """Information carried by one selection (bits)."""
    if n_cells < 1:
        raise ValueError("n_cells must be >= 1")
    if click_types < 1:
        raise ValueError("click_types must be >= 1")
    return math.log2(n_cells * click_types)


@dataclass
class SessionStats:
    """Accumulated behavioural results of one session."""

    hits: int = 0
    misclicks: int = 0
    timeouts: int = 0
    aborted: bool = False
    durations: list[float] = field(default_factory=list)
    path_efficiencies: list[float] = field(default_factory=list)

    # ------------------------------------------------------------------
    def add_trial(
        self, *, hit: bool, rt: float | None, efficiency: float | None
    ) -> None:
        if hit:
            self.hits += 1
            if rt is not None:
                self.durations.append(max(0.0, rt))
        else:
            self.timeouts += 1
        if efficiency is not None and math.isfinite(efficiency):
            self.path_efficiencies.append(efficiency)

    def add_misclick(self) -> None:
        self.misclicks += 1

    # ------------------------------------------------------------------
    @property
    def attempts(self) -> int:
        return self.hits + self.timeouts

    @property
    def net_targets(self) -> int:
        """Net correct targets: hits minus misclicks."""
        return self.hits - self.misclicks

    @property
    def hit_rate(self) -> float:
        return self.hits / self.attempts if self.attempts else 0.0

    @property
    def mean_rt(self) -> float | None:
        return statistics.fmean(self.durations) if self.durations else None

    @property
    def median_rt(self) -> float | None:
        return statistics.median(self.durations) if self.durations else None

    @property
    def mean_path_efficiency(self) -> float | None:
        return (
            statistics.fmean(self.path_efficiencies) if self.path_efficiencies else None
        )

    # ------------------------------------------------------------------
    def ntpm(self, duration_s: float) -> float:
        """Net correct targets per minute (can be negative)."""
        if duration_s <= 0:
            return 0.0
        return self.net_targets / (duration_s / 60.0)

    def bps(self, duration_s: float, n_cells: int, click_types: int = 1) -> float:
        """Net information-transfer rate in bits per second."""
        return self.ntpm(duration_s) * bits_per_target(n_cells, click_types) / 60.0

    # ------------------------------------------------------------------
    def summary(self, duration_s: float, n_cells: int, click_types: int = 1) -> dict:
        return {
            "attempts": self.attempts,
            "hits": self.hits,
            "misclicks": self.misclicks,
            "timeouts": self.timeouts,
            "net_targets": self.net_targets,
            "hit_rate": self.hit_rate,
            "duration_s": duration_s,
            "ntpm": self.ntpm(duration_s),
            "bits_per_target": bits_per_target(n_cells, click_types),
            "bps": self.bps(duration_s, n_cells, click_types),
            "mean_rt_s": self.mean_rt,
            "median_rt_s": self.median_rt,
            "mean_path_efficiency": self.mean_path_efficiency,
            "aborted": self.aborted,
        }


def merge_stats(
    blocks: list[tuple[SessionStats, float]], n_cells: int, click_types: int = 1
) -> dict:
    """Session totals over ``(stats, duration_s)`` blocks.

    Rates are computed on the summed in-block time, so inter-block rests do
    not lower NTPM/BPS.
    """
    total = SessionStats()
    duration = 0.0
    for stats, block_duration in blocks:
        total.hits += stats.hits
        total.misclicks += stats.misclicks
        total.timeouts += stats.timeouts
        total.aborted = total.aborted or stats.aborted
        total.durations.extend(stats.durations)
        total.path_efficiencies.extend(stats.path_efficiencies)
        duration += block_duration
    return total.summary(duration, n_cells, click_types)
