from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path

import pytest

from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.settings import (
    BOOTSTRAP_FIELDS,
    CONFIG_FILE_FIELDS,
    DEVICE_FIELDS,
    EXPERIMENT_FIELDS,
    FIELD_SCOPES,
    SCOPE_BOOTSTRAP,
    SCOPE_DEVICE,
    SCOPE_EXPERIMENT,
    scope_for,
)


def test_defaults_are_valid() -> None:
    config = ExperimentConfig()
    config.validate()
    assert config.rows == 12 and config.cols == 12
    assert config.fullscreen is True
    assert config.data_dir.parts[-2] == "sub-01"
    assert config.data_dir.name.startswith("ses-")


def test_every_config_field_has_exactly_one_scope() -> None:
    fields = {field.name for field in dataclasses.fields(ExperimentConfig)}
    assert set(FIELD_SCOPES) == fields
    assert not (BOOTSTRAP_FIELDS & EXPERIMENT_FIELDS)
    assert not (BOOTSTRAP_FIELDS & DEVICE_FIELDS)
    assert not (EXPERIMENT_FIELDS & DEVICE_FIELDS)
    assert scope_for("dashboard_host") == SCOPE_BOOTSTRAP
    assert scope_for("rows") == SCOPE_EXPERIMENT
    assert scope_for("joystick_port") == SCOPE_DEVICE


def test_default_toml_covers_experiment_and_startup() -> None:
    project_root = Path(__file__).resolve().parents[1]
    data = tomllib.loads(
        (project_root / "configs" / "default.toml").read_text(encoding="utf-8")
    )
    assert set(data) == set(CONFIG_FILE_FIELDS)

    defaults = ExperimentConfig()
    for name in CONFIG_FILE_FIELDS:
        expected = getattr(defaults, name)
        if name == "output_dir":
            expected = str(expected)
        assert data[name] == expected, name


def test_device_example_modules_partition_device_fields() -> None:
    configs = Path(__file__).resolve().parents[1] / "configs"
    modules = (
        "velocity_input.example.toml",
        "reward.example.toml",
        "lsl_outputs.example.toml",
    )
    seen: set[str] = set()
    for name in modules:
        data = tomllib.loads((configs / name).read_text(encoding="utf-8"))
        assert not (set(data) & seen), f"{name} overlaps another module"
        seen |= set(data)
    assert seen == set(DEVICE_FIELDS)


def test_toml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
        subject = "sub-07"
        rows = 12
        cols = 12
        targets = 80
        max_seconds = 600.0
        input = "demo"
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
    "body",
    [
        "[webgrid]\nrows = 8\n",
        "[reward]\nreward_port = 'COM3'\n",
        "[device]\njoystick_port = 'COM4'\n",
    ],
)
def test_toml_sections_are_rejected(tmp_path: Path, body: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match="tables are not supported"):
        ExperimentConfig.from_toml(path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"rows": 1},
        {"cols": 60},
        {"targets": 0},
        {"click_types": 4},
        {"input": "invalid"},
        {"selection": "blink"},
        {"subject": "../escape"},
        {"selection": "dwell", "dwell_time": 0.0},
        {"selection": "dwell", "dwell_time": 2.0, "trial_timeout": 1.0},
        {"window_width": 320},
        {"input": "joystick"},  # port missing
        {"joystick_baud": 0},
        {"joystick_address": 65},
        {"joystick_stream_mode": "burst"},
        {"joystick_speed": 0.0},
        {"joystick_deadzone": 1.0},
        {"joystick_stale_after": 0.0},
        {"lsl_velocity_timeout": 0.0},
        {"lsl_velocity_stale_after": 0.0},
        {"input": "lsl", "lsl_velocity_stream": "", "lsl_velocity_type": ""},
        {"input": "lsl", "lsl_velocity_stream": ""},
        {"input": "lsl", "lsl_velocity_type": ""},
    ],
)
def test_invalid_settings_rejected(overrides: dict) -> None:
    config = dataclasses.replace(ExperimentConfig(), **overrides)
    with pytest.raises(ValueError):
        config.validate()


def test_joystick_and_lsl_settings_validate() -> None:
    ExperimentConfig(input="joystick", joystick_port="COM4").validate()
    ExperimentConfig(
        input="joystick",
        joystick_port="/dev/ttyUSB0",
        joystick_baud=19200,
        joystick_address=3,
        joystick_stream_mode="on_change",
        joystick_speed=400.0,
        joystick_deadzone=0.1,
        joystick_invert_x=True,
        joystick_invert_y=True,
        joystick_center_on_open=True,
        joystick_stale_after=0.6,
    ).validate()
    ExperimentConfig(input="lsl").validate()
    ExperimentConfig(
        input="lsl",
        lsl_velocity_stream="DecoderVelocity",
        lsl_velocity_type="Velocity",
        lsl_velocity_timeout=2.0,
        lsl_velocity_stale_after=0.5,
    ).validate()


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
