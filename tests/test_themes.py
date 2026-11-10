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
        DARK.target.colors[1] = "#FFFFFF"


def test_theme_validation_rejects_incomplete_or_invalid_values() -> None:
    with pytest.raises(ValueError, match="target.colors"):
        replace(DARK, target=replace(DARK.target, colors={1: "#469EFF"}))
    with pytest.raises(ValueError, match="target.glow_opacity"):
        replace(DARK, target=replace(DARK.target, glow_opacity=1.5))
    with pytest.raises(ValueError, match="palette.background"):
        replace(DARK, palette=replace(DARK.palette, background="white"))
    with pytest.raises(ValueError, match="target.colors"):
        replace(
            DARK,
            target=replace(
                DARK.target,
                colors={1: "blue", 2: "#FFB340", 3: "#C77DFF"},
            ),
        )
    with pytest.raises(ValueError, match="trail widths"):
        replace(DARK, trail=replace(DARK.trail, min_width=-1, max_width=2))
    with pytest.raises(ValueError, match="target.line_width"):
        replace(DARK, target=replace(DARK.target, outline=True, line_width=0))
    with pytest.raises(ValueError, match="target.miss_opacity"):
        replace(DARK, target=replace(DARK.target, miss_opacity=2.0))
    with pytest.raises(ValueError, match="font"):
        replace(DARK, font="")
    with pytest.raises(ValueError, match="layout.grid_line_width_factor"):
        replace(
            DARK,
            layout=replace(DARK.layout, grid_line_width_factor=0.0),
        )
