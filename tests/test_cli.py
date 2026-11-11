from __future__ import annotations

from pathlib import Path

import pytest

from web_grid_paradigm.app.cli_args import (
    build_parser,
    load_config,
    load_config_resolved,
)
from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.i18n import STRINGS, Strings


def test_cli_overrides_config() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--input",
            "demo",
            "--rows",
            "6",
            "--cols",
            "7",
            "--targets",
            "12",
            "--show-cursor",
            "--windowed",
        ]
    )
    config = load_config(args)
    assert config.input == "demo"
    assert (config.rows, config.cols) == (6, 7)
    assert config.targets == 12
    assert config.hide_cursor is False
    assert config.fullscreen is False


def test_boolean_cli_flags_can_override_toml_in_both_directions(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "experiment.toml"
    config_path.write_text(
        "auto_exit = true\nhide_cursor = true\ndashboard = true\n",
        encoding="utf-8",
    )
    device_path = tmp_path / "device.toml"
    device_path.write_text(
        "lsl = true\nlsl_state = true\njoystick_invert_x = true\n"
        "joystick_invert_y = true\njoystick_center_on_open = true\n",
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args(
        [
            "--config",
            str(config_path),
            "--device-config",
            str(device_path),
            "--no-auto-exit",
            "--show-cursor",
            "--no-lsl",
            "--no-lsl-state",
            "--no-joystick-invert-x",
            "--no-joystick-invert-y",
            "--no-joystick-center",
            "--no-dashboard",
        ]
    )
    config = load_config(args)
    assert config.auto_exit is False
    assert config.hide_cursor is False
    assert config.lsl is False
    assert config.lsl_state is False
    assert config.joystick_invert_x is False
    assert config.joystick_invert_y is False
    assert config.joystick_center_on_open is False
    assert config.dashboard is False


def test_config_file_then_cli_override(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("subject = 'from-file'\nrows = 10\n", encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(["--config", str(path), "--rows", "5"])
    config = load_config(args)
    assert config.subject == "from-file"
    assert config.rows == 5


def test_config_sources_track_file_and_cli(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("subject = 'from-file'\nrows = 10\n", encoding="utf-8")
    parser = build_parser()
    resolved = load_config_resolved(
        parser.parse_args(["--config", str(path), "--rows", "5"])
    )
    assert resolved.sources["subject"] == "config"
    assert resolved.sources["rows"] == "cli"
    assert resolved.sources["dashboard_host"] == "default"
    assert resolved.config.rows == 5


def test_loader_logs_loaded_config_files(tmp_path: Path) -> None:
    from loguru import logger

    config_path = tmp_path / "experiment.toml"
    config_path.write_text("rows = 8\n", encoding="utf-8")
    device_path = tmp_path / "velocity_input.toml"
    device_path.write_text(
        "joystick_port = 'COM4'\ndemo_speed = 2.5\n", encoding="utf-8"
    )

    messages: list[str] = []
    sink_id = logger.add(
        lambda message: messages.append(str(message)), level="INFO"
    )
    try:
        load_config_resolved(
            build_parser().parse_args(
                [
                    "--config",
                    str(config_path),
                    "--device-config",
                    str(device_path),
                ]
            )
        )
    finally:
        logger.remove(sink_id)

    combined = "\n".join(messages)
    assert str(config_path) in combined
    assert str(device_path) in combined
    assert "1 key(s)" in combined
    assert "2 key(s)" in combined


def test_saved_config_file_is_accepted_by_cli(tmp_path: Path) -> None:
    config = ExperimentConfig(rows=8, joystick_port="COM4", dashboard_port=9000)
    path = config.save_toml(tmp_path / "config.toml", role="config")
    resolved = load_config_resolved(
        build_parser().parse_args(["--config", str(path)])
    )
    assert resolved.config.rows == 8
    assert resolved.config.dashboard_port == 9000
    assert resolved.config.joystick_port == ""
    assert resolved.sources["rows"] == "config"


def test_theme_can_be_selected_from_cli_and_config(tmp_path: Path) -> None:
    parser = build_parser()

    resolved = load_config_resolved(parser.parse_args(["--theme", "classic"]))
    assert resolved.config.theme == "classic"
    assert resolved.sources["theme"] == "cli"

    path = tmp_path / "theme.toml"
    path.write_text('theme = "classic"\n', encoding="utf-8")
    resolved = load_config_resolved(parser.parse_args(["--config", str(path)]))
    assert resolved.config.theme == "classic"
    assert resolved.sources["theme"] == "config"


def test_saved_device_file_is_accepted_by_cli(tmp_path: Path) -> None:
    config = ExperimentConfig(joystick_port="COM4", reward_port="COM9", rows=8)
    path = config.save_toml(tmp_path / "device.toml", role="device")
    resolved = load_config_resolved(
        build_parser().parse_args(["--device-config", str(path)])
    )
    assert resolved.config.joystick_port == "COM4"
    assert resolved.config.reward_port == "COM9"
    assert resolved.config.rows == 12
    assert resolved.sources["joystick_port"] == "device"


def test_run_refuses_a_dirty_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from web_grid_paradigm.app import cli

    monkeypatch.setattr(
        cli,
        "collect_code_version",
        lambda: {
            "branch": "dev",
            "commit": "abc1234",
            "commit_short": "abc1234",
            "dirty": True,
            "changes": [" M src/app.py"],
            "git": True,
        },
    )

    with pytest.raises(RuntimeError, match="require_clean_git"):
        cli._run(ExperimentConfig(require_clean_git=True))


def test_run_passes_config_files_to_recorder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    import types

    from loguru import logger

    from web_grid_paradigm.app import cli

    captured: dict[str, object] = {}

    def fake_run(config, recorder, monitor=None):
        captured["sources"] = dict(recorder.sources)
        captured["config_files"] = dict(recorder.config_files)
        return {}

    # Do not import the real runner/psychopy: this only exercises the
    # source/file hand-off inside _run.  The session log sink uses an
    # enqueued handler, which the sandbox cannot create, so use a plain sink.
    fake_runner = types.ModuleType("web_grid_paradigm.app.runner")
    fake_runner.run_experiment = fake_run  # type: ignore[attr-defined]
    fake_psychopy = types.ModuleType("psychopy")
    fake_psychopy.__version__ = "test"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "web_grid_paradigm.app.runner", fake_runner)
    monkeypatch.setitem(sys.modules, "psychopy", fake_psychopy)
    monkeypatch.setattr(
        cli,
        "add_session_log",
        lambda directory: logger.add(
            lambda message: None, level="DEBUG", enqueue=False
        ),
    )

    class View:
        config_sources = {"rows": "config"}
        config_files = {"joystick_port": "configs/velocity_input.toml"}

    config = ExperimentConfig(subject="sub-run", session="run", output_dir=tmp_path)
    cli._run(config, View())

    assert captured["sources"] == {"rows": "config"}
    assert captured["config_files"] == {
        "joystick_port": "configs/velocity_input.toml"
    }


def test_device_config_layers_device_settings_only(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment.toml"
    experiment.write_text("rows = 8\n", encoding="utf-8")
    velocity = tmp_path / "velocity_input.toml"
    velocity.write_text(
        "joystick_port = 'COM7'\njoystick_baud = 19200\n",
        encoding="utf-8",
    )
    reward = tmp_path / "reward.toml"
    reward.write_text("reward_port = 'COM3'\n", encoding="utf-8")
    parser = build_parser()
    resolved = load_config_resolved(
        parser.parse_args(
            [
                "--config",
                str(experiment),
                "--device-config",
                str(velocity),
                "--device-config",
                str(reward),
                "--joystick-baud",
                "9600",
            ]
        )
    )
    assert resolved.config.rows == 8
    assert resolved.config.joystick_port == "COM7"
    assert resolved.config.joystick_baud == 9600
    assert resolved.config.reward_port == "COM3"
    assert resolved.sources["rows"] == "config"
    assert resolved.sources["joystick_port"] == "device"
    assert resolved.sources["reward_port"] == "device"
    assert resolved.sources["joystick_baud"] == "cli"
    # A CLI override no longer claims the file it came from.
    assert resolved.config_files == {
        "joystick_port": str(velocity),
        "reward_port": str(reward),
    }


def test_config_rejects_device_keys(tmp_path: Path) -> None:
    experiment = tmp_path / "experiment.toml"
    experiment.write_text("rows = 8\njoystick_port = 'COM1'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="belong to device settings"):
        load_config_resolved(
            build_parser().parse_args(["--config", str(experiment)])
        )


def test_device_config_rejects_config_keys(tmp_path: Path) -> None:
    device = tmp_path / "device.toml"
    device.write_text("rows = 8\n", encoding="utf-8")
    with pytest.raises(ValueError, match="only device keys"):
        load_config_resolved(
            build_parser().parse_args(["--device-config", str(device)])
        )


def test_device_config_files_must_not_overlap(tmp_path: Path) -> None:
    first = tmp_path / "velocity_input.toml"
    first.write_text("joystick_port = 'COM7'\n", encoding="utf-8")
    second = tmp_path / "other.toml"
    second.write_text("joystick_port = 'COM8'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="both set joystick_port"):
        load_config_resolved(
            build_parser().parse_args(
                [
                    "--device-config",
                    str(first),
                    "--device-config",
                    str(second),
                ]
            )
        )


def test_device_config_rejects_sections(tmp_path: Path) -> None:
    device = tmp_path / "device.toml"
    device.write_text("[device]\njoystick_port = 'COM4'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tables are not supported"):
        load_config_resolved(
            build_parser().parse_args(["--device-config", str(device)])
        )


def test_legacy_device_flags_are_not_recognised() -> None:
    parser = build_parser()
    for flag in ("--lab-config", "--reward-config"):
        with pytest.raises(SystemExit):
            parser.parse_args([flag, "unused.toml"])


def test_missing_device_config_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config_resolved(
            build_parser().parse_args(
                ["--device-config", str(tmp_path / "nope.toml")]
            )
        )


def test_blocks_trials_and_grid_options() -> None:
    parser = build_parser()
    config = load_config(
        parser.parse_args(
            ["--blocks", "3", "--trials", "20", "--rows", "8", "--cols", "6",
             "--block-rest", "5"]
        )
    )
    assert (config.blocks, config.targets, config.rows, config.cols) == (3, 20, 8, 6)
    assert config.block_rest == 5
    assert config.total_trials == 60
    # --targets stays as an alias of --trials
    assert load_config(parser.parse_args(["--targets", "7"])).targets == 7


def test_i18n_tables_have_the_same_keys_and_format() -> None:
    assert set(STRINGS["zh"]) == set(STRINGS["en"])
    for language in ("zh", "en"):
        strings = Strings(language)
        assert strings["title"] == "BCI Web-Grid"
        assert "12" in strings.format("progress", current=12, total=40)
        assert "1.50" in strings.format("score", bps=1.5)
        # Every input mode shown on the intro page has a label.
        for key in ("mode_mouse", "mode_demo", "mode_joystick", "mode_lsl"):
            assert strings[key]


def test_joystick_and_lsl_options_are_mapped() -> None:
    parser = build_parser()
    joystick = load_config(
        parser.parse_args(
            [
                "--input",
                "joystick",
                "--joystick-port",
                "COM4",
                "--joystick-baud",
                "19200",
                "--joystick-address",
                "3",
                "--joystick-mode",
                "on_change",
                "--joystick-speed",
                "400",
                "--joystick-deadzone",
                "0.1",
                "--joystick-invert-x",
                "--joystick-invert-y",
                "--joystick-center",
                "--joystick-stale-after",
                "0.6",
            ]
        )
    )
    assert joystick.input == "joystick"
    assert joystick.joystick_port == "COM4"
    assert joystick.joystick_baud == 19200
    assert joystick.joystick_address == 3
    assert joystick.joystick_stream_mode == "on_change"
    assert joystick.joystick_speed == 400
    assert joystick.joystick_deadzone == 0.1
    assert joystick.joystick_invert_x and joystick.joystick_invert_y
    assert joystick.joystick_center_on_open is True
    assert joystick.joystick_stale_after == 0.6

    lsl = load_config(
        parser.parse_args(
            [
                "--input",
                "lsl",
                "--lsl-velocity-stream",
                "DecoderVelocity",
                "--lsl-velocity-type",
                "Velocity",
                "--lsl-velocity-timeout",
                "2",
                "--lsl-velocity-stale-after",
                "0.5",
            ]
        )
    )
    assert lsl.input == "lsl"
    assert lsl.lsl_velocity_stream == "DecoderVelocity"
    assert lsl.lsl_velocity_timeout == 2
    assert lsl.lsl_velocity_stale_after == 0.5


def test_iti_option_and_validation() -> None:
    parser = build_parser()
    assert load_config(parser.parse_args(["--iti", "1.5"])).iti == 1.5
    assert load_config(parser.parse_args([])).iti == 0.0
    import pytest

    with pytest.raises(ValueError, match="iti"):
        load_config(parser.parse_args(["--iti", "-1"]))
