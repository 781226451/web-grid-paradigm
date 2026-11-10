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


@pytest.mark.parametrize(
    "field",
    ("background", "panel", "panel_edge", "grid", "text", "muted", "accent", "error"),
)
def test_palette_rejects_invalid_colours(field: str) -> None:
    with pytest.raises(ValueError, match=rf"palette\.{field}"):
        replace(DARK.palette, **{field: "white"})


@pytest.mark.parametrize(
    ("component", "kwargs", "match"),
    [
        ("cursor", {"color": "red"}, "cursor.color"),
        ("cursor", {"edge": "red"}, "cursor.edge"),
        ("cursor", {"line_width": 0}, "cursor.line_width"),
        ("cursor", {"radius_basis": "screen"}, "cursor.radius_basis"),
        ("cursor", {"radius_factor": 0}, "cursor.radius_factor"),
        ("cursor", {"radius_min": 0}, "cursor radius bounds"),
        ("cursor", {"glow_radius_factor": 0.5}, "cursor.glow_radius_factor"),
        ("cursor", {"glow_opacity": 2}, "cursor.glow_opacity"),
        ("target", {"colors": {1: "#469EFF"}}, "target.colors"),
        (
            "target",
            {"colors": {1: "blue", 2: "#FFB340", 3: "#C77DFF"}},
            "target.colors",
        ),
        ("target", {"outline": True, "line_width": 0}, "target.line_width"),
        ("target", {"glow_radius_factor": 0.5}, "target.glow_radius_factor"),
        ("target", {"pulse_scale": 0.5}, "target.pulse_scale"),
        ("target", {"overlay_color": "white"}, "target.overlay_color"),
        ("target", {"overlay_opacity": 2}, "target.overlay_opacity"),
        ("target", {"miss_opacity": 2}, "target.miss_opacity"),
        ("hover", {"fill": "white"}, "hover.fill"),
        ("hover", {"outline": True, "outline_width": 0}, "hover.outline_width"),
        ("hover", {"opacity": 2}, "hover.opacity"),
        ("trail", {"segments": -1}, "trail.segments"),
        ("trail", {"enabled": True, "segments": 1}, "trail.segments"),
        ("trail", {"duration_s": 0}, "trail.duration_s"),
        ("trail", {"min_width": -1, "max_width": 2}, "trail widths"),
        ("trail", {"min_width": 2, "max_width": 1}, "trail.max_width"),
        ("trail", {"glow_width_factor": 0.5}, "trail.glow_width_factor"),
        ("trail", {"opacity_min": 2}, "trail.opacity_min"),
        (
            "trail",
            {"opacity_min": 0.5, "opacity_max": 0.2},
            "trail.opacity_max",
        ),
        (
            "trail",
            {"glow_opacity_min": 0.5, "glow_opacity_max": 0.2},
            "trail.glow_opacity_max",
        ),
        ("layout", {"grid_margin": 0}, "layout.grid_margin"),
        (
            "layout",
            {"grid_line_width_factor": 0},
            "layout.grid_line_width_factor",
        ),
        ("dwell", {"fill": "white"}, "dwell.fill"),
        ("dwell", {"line": ""}, "dwell.line"),
    ],
)
def test_substyle_validation(component: str, kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        child = replace(getattr(DARK, component), **kwargs)
        replace(DARK, **{component: child})


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"name": ""}, "theme.name"),
        ({"font": ""}, "theme.font"),
    ],
)
def test_theme_identity_validation(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        replace(DARK, **kwargs)
