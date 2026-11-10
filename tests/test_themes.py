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


def test_theme_validation_rejects_incomplete_or_invalid_values() -> None:
    with pytest.raises(ValueError, match="target_colors"):
        replace(DARK, target_colors={1: "#469EFF"})
    with pytest.raises(ValueError, match="target_glow_opacity"):
        replace(DARK, target_glow_opacity=1.5)
