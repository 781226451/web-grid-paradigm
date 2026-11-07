from __future__ import annotations

from pathlib import Path

from web_grid_paradigm.cli import _load_config, build_parser
from web_grid_paradigm.i18n import STRINGS, Strings


def test_cli_overrides_config() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--input",
            "udp",
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
    config = _load_config(args)
    assert config.input == "udp"
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
    config = _load_config(args)
    assert config.subject == "from-file"
    assert config.rows == 5


def test_blocks_trials_and_grid_options() -> None:
    parser = build_parser()
    config = _load_config(
        parser.parse_args(
            ["--blocks", "3", "--trials", "20", "--rows", "8", "--cols", "6",
             "--block-rest", "5"]
        )
    )
    assert (config.blocks, config.targets, config.rows, config.cols) == (3, 20, 8, 6)
    assert config.block_rest == 5
    assert config.total_trials == 60
    # --targets stays as an alias of --trials
    assert _load_config(parser.parse_args(["--targets", "7"])).targets == 7


def test_i18n_tables_have_the_same_keys_and_format() -> None:
    assert set(STRINGS["zh"]) == set(STRINGS["en"])
    for language in ("zh", "en"):
        strings = Strings(language)
        assert strings["title"] == "BCI Web-Grid"
        assert "12" in strings.format("progress", current=12, total=40)
        assert "1.50" in strings.format("score", bps=1.5)


def test_iti_option_and_validation() -> None:
    parser = build_parser()
    assert _load_config(parser.parse_args(["--iti", "1.5"])).iti == 1.5
    assert _load_config(parser.parse_args([])).iti == 0.0
    import pytest

    with pytest.raises(ValueError, match="iti"):
        _load_config(parser.parse_args(["--iti", "-1"]))
