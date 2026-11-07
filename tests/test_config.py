from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from web_grid_paradigm.config import ExperimentConfig


def test_defaults_are_valid() -> None:
    config = ExperimentConfig()
    config.validate()
    assert config.rows == 12 and config.cols == 12
    assert config.fullscreen is True
    assert config.data_dir.parts[-2] == "sub-01"
    assert config.data_dir.name.startswith("ses-")


def test_toml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
        [webgrid]
        subject = "sub-07"
        rows = 12
        cols = 12
        targets = 80
        max_seconds = 600.0
        input = "udp"
        udp_port = 9100
        selection = "dwell"
        dwell_time = 0.8
        trial_timeout = 10.0
        output_dir = "results"
        """,
        encoding="utf-8",
    )
    config = ExperimentConfig.from_toml(path)
    assert config.subject == "sub-07"
    assert (config.rows, config.cols) == (12, 12)
    assert config.selection == "dwell"
    assert config.output_dir == Path("results")
    config.validate()


def test_top_level_toml_table_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('subject = "sub-02"\nrows = 4\n', encoding="utf-8")
    config = ExperimentConfig.from_toml(path)
    assert config.subject == "sub-02"
    assert config.rows == 4


def test_unknown_toml_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("subject = 'x'\nrow = 4\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown configuration key"):
        ExperimentConfig.from_toml(path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"rows": 1},
        {"cols": 60},
        {"targets": 0},
        {"click_types": 4},
        {"input": "keyboard2"},
        {"selection": "blink"},
        {"smoothing": 1.0},
        {"subject": "../escape"},
        {"marker_udp": "localhost"},
        {"selection": "dwell", "dwell_time": 0.0},
        {"selection": "dwell", "dwell_time": 2.0, "trial_timeout": 1.0},
        {"window_width": 320},
    ],
)
def test_invalid_settings_rejected(overrides: dict) -> None:
    config = dataclasses.replace(ExperimentConfig(), **overrides)
    with pytest.raises(ValueError):
        config.validate()


def test_session_id_uses_explicit_value() -> None:
    config = ExperimentConfig(subject="sub-01", session="run-03")
    assert config.session_id == "run-03"
    assert config.data_dir == Path("data") / "sub-01" / "ses-run-03"


def test_shipped_example_config_is_valid() -> None:
    path = Path(__file__).resolve().parents[1] / "configs" / "default.toml"
    config = ExperimentConfig.from_toml(path)
    config.validate()
    assert config.rows == 12 and config.cols == 12
    assert config.input == "mouse"
    assert config.fullscreen is True
