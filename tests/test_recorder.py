from __future__ import annotations

import csv
import json
from pathlib import Path

from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.geometry import Cell
from web_grid_paradigm.core.session import TrialResult
from web_grid_paradigm.recorder import SessionRecorder


def make_config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        subject="sub-01",
        session="test",
        output_dir=tmp_path / "data",
        targets=1,
        max_seconds=0,
        rows=4,
        cols=4,
    )


def test_recorder_writes_config_events_trials_and_summary(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    with SessionRecorder(config, psychopy_version="test-version") as recorder:
        assert recorder.dir.name == "ses-test"
        assert (recorder.dir / "config.json").exists()
        recorder.event(
            "target_onset", 1.0, cell=Cell(1, 2), target_index=1, x=0.1, y=-0.2
        )
        recorder.trial(
            TrialResult(
                index=1,
                cell=Cell(1, 2),
                required_button=1,
                onset=1.0,
                offset=2.5,
                outcome="hit",
                reason="click",
                correct=True,
                rt=1.5,
                misclicks=0,
                button=1,
                path_px=100.0,
                straight_px=90.0,
                path_efficiency=0.9,
                dwell=False,
            )
        )
        recorder.write_summary({"hits": 1, "bps": 2.0})
        summary_path = recorder.summary_path
        assert summary_path.exists()

    with (recorder.dir / "events.csv").open(encoding="utf-8-sig", newline="") as handle:
        events = list(csv.DictReader(handle))
    assert events[0]["event"] == "target_onset"
    assert events[0]["cell"] == "r2c3"
    assert events[0]["row"] == "2"
    assert events[0]["col"] == "3"

    with (recorder.dir / "trials.csv").open(encoding="utf-8-sig", newline="") as handle:
        trials = list(csv.DictReader(handle))
    assert trials[0]["outcome"] == "hit"
    assert trials[0]["path_efficiency"] == "0.900000"

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["results"]["bps"] == 2.0
    assert data["config"]["subject"] == "sub-01"
    meta = json.loads((recorder.dir / "config.json").read_text(encoding="utf-8"))
    assert meta["psychopy_version"] == "test-version"


def test_session_directory_collision_gets_suffix(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    first = SessionRecorder(config)
    first.close()
    second = SessionRecorder(config)
    try:
        assert second.dir.name == "ses-test-2"
        assert second.dir != first.dir
    finally:
        second.close()


def test_closed_recorder_ignores_writes(tmp_path: Path) -> None:
    recorder = SessionRecorder(make_config(tmp_path))
    recorder.close()
    recorder.event("late", 1.0)
    assert recorder.events_path.read_text(encoding="utf-8-sig").count("\n") == 1
