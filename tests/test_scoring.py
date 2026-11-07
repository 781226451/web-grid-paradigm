from __future__ import annotations

import math

import pytest

from web_grid_paradigm.scoring import SessionStats, bits_per_target


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
    assert stats.bps(60.0, 16) < 0
    assert stats.ntpm(0.0) == 0.0
    assert stats.bps(0.0, 16) == 0.0
