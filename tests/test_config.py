from __future__ import annotations

import dataclasses
import tomllib
from pathlib import Path

import pytest

from web_grid_paradigm.core.config import ExperimentConfig


def test_defaults_are_valid() -> None:
    config = ExperimentConfig()
    config.validate()
    assert config.rows == 12 and config.cols == 12
    assert config.fullscreen is True
    assert config.data_dir.parts[-2] == "sub-01"
    assert config.data_dir.name.startswith("ses-")


def test_default_toml_matches_config_fields_and_defaults() -> None:
    project_root = Path(__file__).resolve().parents[1]
    data = tomllib.loads(
        (project_root / "configs" / "default.toml").read_text(encoding="utf-8")
    )
    fields = {field.name for field in dataclasses.fields(ExperimentConfig)}
    assert set(data) == fields

    defaults = ExperimentConfig()
    for name in fields:
        expected = getattr(defaults, name)
        if name == "output_dir":
            expected = str(expected)
        assert data[name] == expected, name


def test_reward_example_matches_supported_keys() -> None:
    from web_grid_paradigm.app.cli_args import REWARD_KEYS

    project_root = Path(__file__).resolve().parents[1]
    data = tomllib.loads(
        (project_root / "configs" / "reward.example.toml").read_text(
            encoding="utf-8"
        )
    )
    assert set(data) == set(REWARD_KEYS)


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


def test_legacy_udp_toml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "old.toml"
    path.write_text(
        """
        input = "udp"
        udp_host = "0.0.0.0"
        udp_port = 9000
        smoothing = 0.3
        """,
        encoding="utf-8",
    )
    # UDP is gone for good: neither its mode nor its settings are accepted.
    with pytest.raises(ValueError, match="unknown configuration key"):
        ExperimentConfig.from_toml(path)

    path.write_text("input = 'udp'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="input must be one of"):
        ExperimentConfig.from_toml(path)


def test_legacy_keyboard_toml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "old.toml"
    path.write_text("input = 'keyboard'\nkeyboard_step = 0.02\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown configuration key"):
        ExperimentConfig.from_toml(path)

    path.write_text("input = 'keyboard'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="input must be one of"):
        ExperimentConfig.from_toml(path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"rows": 1},
        {"cols": 60},
        {"targets": 0},
        {"click_types": 4},
        {"input": "keyboard2"},
        {"input": "udp"},
        {"input": "keyboard"},
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
