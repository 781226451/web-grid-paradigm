from __future__ import annotations

from dataclasses import replace

import pytest

from web_grid_paradigm.core.settings import THEMES
from web_grid_paradigm.presentation.themes import DARK, get_theme


def test_theme_registry_matches_settings() -> None:
    assert {get_theme(name).name for name in THEMES} == set(THEMES)


def test_unknown_theme_is_rejected() -> None:
    with pytest.raises(ValueError, match="theme must be one of"):
        get_theme("neon")


def test_theme_target_colors_are_read_only() -> None:
    with pytest.raises(TypeError):
        DARK.target_colors[1] = "#FFFFFF"


def test_theme_validation_rejects_incomplete_or_invalid_values() -> None:
    with pytest.raises(ValueError, match="target_colors"):
        replace(DARK, target_colors={1: "#469EFF"})
    with pytest.raises(ValueError, match="target_glow_opacity"):
        replace(DARK, target_glow_opacity=1.5)
    with pytest.raises(ValueError, match="background"):
        replace(DARK, background="white")
    with pytest.raises(ValueError, match="target_colors"):
        replace(
            DARK,
            target_colors={1: "blue", 2: "#FFB340", 3: "#C77DFF"},
        )
    with pytest.raises(ValueError, match="trail widths"):
        replace(DARK, trail_min_width=-1, trail_max_width=2)
    with pytest.raises(ValueError, match="target_line_width"):
        replace(DARK, target_outline=True, target_line_width=0)
    with pytest.raises(ValueError, match="miss_opacity"):
        replace(DARK, miss_opacity=2.0)
    with pytest.raises(ValueError, match="font"):
        replace(DARK, font="")
    with pytest.raises(ValueError, match="grid_line_width_factor"):
        replace(DARK, grid_line_width_factor=0.0)
