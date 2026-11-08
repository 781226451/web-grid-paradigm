from __future__ import annotations

import math

import pytest

from web_grid_paradigm.core.scoring import SessionStats, bits_per_target, merge_stats


def test_merge_stats_sums_blocks_on_in_block_time() -> None:
    a = SessionStats(hits=3, misclicks=1, durations=[1.0, 2.0, 3.0])
    b = SessionStats(hits=2, timeouts=1, durations=[4.0, 5.0])
    merged = merge_stats([(a, 30.0), (b, 30.0)], n_cells=16)
    assert merged["hits"] == 5
    assert merged["misclicks"] == 1
    assert merged["timeouts"] == 1
    assert merged["attempts"] == 6
    assert merged["duration_s"] == 60.0
    assert merged["ntpm"] == pytest.approx(4.0)  # (5 - 1) per minute
    assert merged["mean_rt_s"] == pytest.approx(3.0)


def test_bits_per_target() -> None:
    assert bits_per_target(64) == pytest.approx(6.0)
    assert bits_per_target(64, 3) == pytest.approx(math.log2(192))
    with pytest.raises(ValueError):
        bits_per_target(0)
    with pytest.raises(ValueError):
        bits_per_target(4, 0)


def test_session_metrics() -> None:
    stats = SessionStats()
    for rt in (1.0, 2.0, 3.0):
        stats.add_trial(hit=True, rt=rt, efficiency=0.8)
    for _ in range(2):
        stats.add_misclick()
    stats.add_trial(hit=False, rt=None, efficiency=None)

    assert stats.attempts == 4
    assert stats.hits == 3
    assert stats.misclicks == 2
    assert stats.timeouts == 1
    assert stats.net_targets == 1
    assert stats.hit_rate == pytest.approx(0.75)
    assert stats.mean_rt == pytest.approx(2.0)
    assert stats.median_rt == pytest.approx(2.0)
    assert stats.mean_path_efficiency == pytest.approx(0.8)
    assert stats.ntpm(120.0) == pytest.approx(0.5)
    assert stats.bps(120.0, 64, 1) == pytest.approx(0.05)

    summary = stats.summary(120.0, 64, 1)
    assert summary["bits_per_target"] == pytest.approx(6.0)
    assert summary["bps"] == pytest.approx(0.05)
    assert summary["attempts"] == 4


def test_negative_and_zero_duration() -> None:
    stats = SessionStats(hits=1, misclicks=3)
    assert stats.net_targets == -2
    assert stats.ntpm(60.0) < 0
    # Paper Eqn. 2 clamps the net count at zero: no negative bitrate.
    assert stats.bps(60.0, 16) == 0.0
    assert stats.ntpm(0.0) == 0.0
    assert stats.bps(0.0, 16) == 0.0


def test_bps_follows_the_achieved_bitrate_formula() -> None:
    """B = log2(N) * max(correct - incorrect, 0) / t  (Technical Report 01, Eqn. 2)."""
    stats = SessionStats(hits=8, misclicks=2)
    # N = 16 -> log2(16) = 4 bits/selection, net = 6, t = 60 s.
    assert stats.bps(60.0, 16) == pytest.approx(4 * 6 / 60)

    # One misclick per hit: net is 0, so the rate clamps to zero.
    stats = SessionStats(hits=4, misclicks=4)
    assert stats.bps(30.0, 16) == 0.0

    # Click types count as extra symbols: N = cells * click types.
    stats = SessionStats(hits=3, misclicks=0)
    assert stats.bps(10.0, 8, 2) == pytest.approx(3 * 4 / 10)

