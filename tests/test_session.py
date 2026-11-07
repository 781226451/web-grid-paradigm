from __future__ import annotations

import dataclasses
import random

import pytest

from web_grid_paradigm.config import ExperimentConfig
from web_grid_paradigm.geometry import Cell, Layout
from web_grid_paradigm.session import Phase, SessionEngine


def make_config(**overrides: object) -> ExperimentConfig:
    base = ExperimentConfig(
        rows=4,
        cols=4,
        targets=3,
        max_seconds=0,
        feedback=0.2,
        countdown_seconds=0,
        trial_timeout=10.0,
        seed=1,
    )
    return dataclasses.replace(base, **overrides)


def make_engine(**overrides: object) -> SessionEngine:
    config = make_config(**overrides)
    layout = Layout.create(800, 600, config.rows, config.cols)
    return SessionEngine(config, layout, random.Random(config.seed))


def centre(engine: SessionEngine, cell: Cell | None = None) -> tuple[float, float]:
    target_cell = cell or engine.target.cell  # type: ignore[union-attr]
    return engine.layout.centre_px(target_cell)


def test_hit_moves_to_feedback_and_scores() -> None:
    engine = make_engine()
    target = engine.begin(0.0)
    x, y = centre(engine)
    outcome = engine.update(0.2, x, y, [1])

    assert outcome.trial is not None
    trial = outcome.trial
    assert trial.outcome == "hit"
    assert trial.correct is True
    assert trial.rt == pytest.approx(0.2)
    assert trial.path_efficiency == pytest.approx(1.0)
    assert engine.phase is Phase.FEEDBACK
    assert engine.stats.hits == 1
    assert engine.feedback_until == pytest.approx(0.4)
    assert engine.target is not None and engine.target.cell == target.cell


def test_misclick_does_not_end_the_trial() -> None:
    engine = make_engine()
    engine.begin(0.0)
    wrong = next(
        cell for cell in engine.layout.iter_cells() if cell != engine.target.cell
    )
    x, y = centre(engine, wrong)
    outcome = engine.update(0.3, x, y, [1])

    assert outcome.trial is None
    assert len(outcome.clicks) == 1
    assert outcome.clicks[0].correct is False
    assert engine.stats.misclicks == 1
    assert engine.phase is Phase.RUNNING
    assert engine.stats.attempts == 0


def test_target_requires_the_matching_click_type() -> None:
    engine = make_engine(click_types=3)
    engine.begin(0.0)
    target = engine.target
    assert target is not None
    wrong_button = 1 if target.required_button != 1 else 2
    x, y = centre(engine)

    outcome = engine.update(0.2, x, y, [wrong_button])
    assert outcome.trial is None
    assert outcome.clicks[0].correct is False
    assert engine.stats.misclicks == 1
    assert engine.phase is Phase.RUNNING

    outcome = engine.update(0.4, x, y, [target.required_button])
    assert outcome.trial is not None
    assert outcome.trial.correct is True
    assert outcome.trial.required_button == target.required_button
    assert outcome.trial.button == target.required_button


def test_timeout_ends_the_trial() -> None:
    engine = make_engine(trial_timeout=1.0)
    engine.begin(0.0)
    x, y = centre(engine)
    outcome = engine.update(1.01, x, y, [])

    assert outcome.trial is not None
    assert outcome.trial.outcome == "timeout"
    assert outcome.trial.reason == "trial_timeout"
    assert engine.stats.timeouts == 1
    assert engine.stats.attempts == 1
    assert engine.phase is Phase.FEEDBACK


def test_dwell_selection() -> None:
    engine = make_engine(selection="dwell", dwell_time=0.5, trial_timeout=5.0)
    engine.begin(0.0)
    x, y = centre(engine)

    first = engine.update(0.2, x, y, [])
    assert first.trial is None
    assert engine.dwell_progress == pytest.approx(0.4)

    second = engine.update(0.45, x, y, [])
    assert second.trial is None
    assert engine.dwell_progress == pytest.approx(0.9)

    third = engine.update(0.51, x, y, [])
    assert third.trial is not None
    assert third.trial.outcome == "hit"
    assert third.trial.dwell is True
    assert third.trial.button is None


def test_dwell_resets_when_cursor_leaves_target() -> None:
    engine = make_engine(selection="dwell", dwell_time=0.5, trial_timeout=5.0)
    engine.begin(0.0)
    x, y = centre(engine)
    wrong = next(
        cell for cell in engine.layout.iter_cells() if cell != engine.target.cell
    )
    wx, wy = centre(engine, wrong)

    engine.update(0.2, x, y, [])
    assert engine.dwell_progress == pytest.approx(0.4)
    engine.update(0.3, wx, wy, [])
    assert engine.dwell_progress == 0.0
    engine.update(0.4, x, y, [])
    assert engine.dwell_progress == pytest.approx(0.2)


def test_retime_onset_controls_reaction_time() -> None:
    engine = make_engine()
    engine.begin(0.0)
    engine.retime_onset(0.1)
    x, y = centre(engine)
    outcome = engine.update(0.3, x, y, [1])
    assert outcome.trial is not None
    assert outcome.trial.onset == pytest.approx(0.1)
    assert outcome.trial.rt == pytest.approx(0.2)


def test_session_ends_after_target_count() -> None:
    engine = make_engine(targets=1)
    engine.begin(0.0)
    x, y = centre(engine)
    outcome = engine.update(0.2, x, y, [1])
    assert outcome.trial is not None
    assert engine.advance(0.39) is None
    assert engine.phase is Phase.FEEDBACK
    assert engine.advance(0.4) is None
    assert engine.phase is Phase.DONE
    assert engine.session_end == pytest.approx(0.4)


def test_advance_starts_next_target() -> None:
    engine = make_engine(targets=3)
    engine.begin(0.0)
    x, y = centre(engine)
    first_cell = engine.target.cell
    engine.update(0.2, x, y, [1])
    next_target = engine.advance(0.4)
    assert next_target is not None
    assert engine.phase is Phase.RUNNING
    assert next_target.index == 2
    assert next_target.cell != first_cell


def test_advance_uses_current_pointer_position() -> None:
    engine = make_engine(targets=3)
    engine.begin(0.0)
    x, y = centre(engine)
    engine.update(0.2, x, y, [1])
    next_target = engine.advance(0.4, 123.0, -45.0)
    assert next_target is not None
    assert next_target.start_px == (123.0, -45.0)


def test_session_limit_ends_mid_trial() -> None:
    engine = make_engine(max_seconds=0.5, trial_timeout=0)
    engine.begin(0.0)
    x, y = centre(engine)
    outcome = engine.update(0.6, x, y, [])
    assert outcome.trial is not None
    assert outcome.trial.reason == "session_limit"
    assert engine.advance(0.8) is None
    assert engine.phase is Phase.DONE


def test_abort_marks_summary() -> None:
    engine = make_engine()
    engine.begin(0.0)
    engine.abort(1.0)
    summary = engine.summary(2.0)
    assert engine.phase is Phase.DONE
    assert summary["aborted"] is True
    assert summary["duration_s"] == pytest.approx(1.0)


def test_new_block_does_not_repeat_previous_last_cell() -> None:
    config = ExperimentConfig(rows=5, cols=7, targets=2, blocks=2)
    layout = Layout.create(1280, 800, 5, 7)
    for seed in range(200):
        rng = random.Random(seed)
        first = SessionEngine(config, layout, rng)
        last = first.begin(0.0).cell
        second = SessionEngine(config, layout, rng, avoid_first=last)
        assert second.begin(0.0).cell != last


def _hit(engine: SessionEngine, t: float) -> None:
    x, y = centre(engine)
    assert engine.update(t, x, y, [1]).trial is not None


def test_iti_follows_feedback_before_next_target() -> None:
    engine = make_engine(iti=1.0, feedback=0.2)
    first = engine.begin(0.0)
    _hit(engine, 0.5)  # feedback until 0.7
    assert engine.advance(0.6) is None and engine.phase is Phase.FEEDBACK
    assert engine.advance(0.7) is None
    assert engine.phase is Phase.ITI
    assert engine.iti_until == pytest.approx(1.7)
    # Inputs during the ITI do nothing.
    x, y = centre(engine, first.cell)
    assert engine.update(1.0, x, y, [1]).trial is None
    assert engine.advance(1.6) is None and engine.phase is Phase.ITI
    nxt = engine.advance(1.7)
    assert nxt is not None and nxt.index == 2
    assert engine.phase is Phase.RUNNING


def test_no_iti_after_last_trial_and_zero_iti_skips() -> None:
    engine = make_engine(iti=1.0, targets=1)
    engine.begin(0.0)
    _hit(engine, 0.3)
    engine.advance(10.0)
    assert engine.phase is Phase.DONE

    engine = make_engine(iti=0.0)
    engine.begin(0.0)
    _hit(engine, 0.3)
    assert engine.advance(10.0) is not None  # straight to the next target
