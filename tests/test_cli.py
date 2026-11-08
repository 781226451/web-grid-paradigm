from __future__ import annotations

from pathlib import Path

from web_grid_paradigm.cli_args import build_parser, load_config
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
            "--no-instructions",
            "--marker-udp",
            "127.0.0.1:9001",
        ]
    )
    config = load_config(args)
    assert config.input == "demo"
    assert (config.rows, config.cols) == (6, 7)
    assert config.targets == 12
    assert config.hide_cursor is False
    assert config.fullscreen is False
    assert config.skip_instructions is True
    assert config.marker_udp == "127.0.0.1:9001"


def test_config_file_then_cli_override(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("subject = 'from-file'\nrows = 10\n", encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(["--config", str(path), "--rows", "5"])
    config = load_config(args)
    assert config.subject == "from-file"
    assert config.rows == 5


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
