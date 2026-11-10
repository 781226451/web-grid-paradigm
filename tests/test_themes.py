from __future__ import annotations

import pytest

from web_grid_paradigm.core.settings import THEMES
from web_grid_paradigm.presentation.themes import get_theme


def test_theme_registry_matches_settings() -> None:
    assert {get_theme(name).name for name in THEMES} == set(THEMES)


def test_unknown_theme_is_rejected() -> None:
    with pytest.raises(ValueError, match="theme must be one of"):
        get_theme("neon")
