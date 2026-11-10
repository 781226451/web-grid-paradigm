"""Visual theme definitions for the paradigm window.

Themes only carry presentation values; the experimental logic stays in
``core/``.  Adding a theme means adding one :class:`Theme` instance and its
name to ``core.settings.THEMES``; the CLI, TOML and WebUI expose the names
automatically.

Every visual field is required.  A new theme therefore fails loudly at
construction time instead of silently inheriting a value from another theme.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..core.settings import THEMES

_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\Z")


@dataclass(frozen=True, slots=True)
class Theme:
    name: str

    # Canvas and chrome.
    background: str
    panel: str
    panel_edge: str
    grid: str
    text: str
    muted: str
    accent: str
    error: str
    hover: str

    # Cursor.
    cursor: str
    cursor_edge: str | None
    cursor_flash: str
    cursor_line_width: float
    cursor_glow: bool
    cursor_glow_color: str
    cursor_glow_radius_factor: float
    cursor_glow_opacity: float
    cursor_radius_basis: str  # "window" | "cell"
    cursor_radius_factor: float
    cursor_radius_min: float
    cursor_radius_max: float

    # Targets.
    target_colors: Mapping[int, str]
    target_outline: bool
    target_line_width: float
    target_glow: bool
    target_glow_radius_factor: float
    target_glow_opacity: float
    target_pulse: bool
    target_pulse_scale: float
    target_overlay: bool
    target_overlay_color: str
    target_overlay_opacity: float
    miss_opacity: float

    # Grid-cell hover.
    hover_outline: bool
    hover_outline_width: float
    hover_opacity: float

    # Cursor trail.
    trail: bool
    trail_segments: int
    trail_duration_s: float
    trail_min_width: float
    trail_max_width: float
    trail_opacity_min: float
    trail_opacity_max: float
    trail_glow_width_factor: float
    trail_glow_opacity_min: float
    trail_glow_opacity_max: float

    # Dwell bar and layout.
    dwell_fill: str
    dwell_line: str
    grid_margin: float

    def __post_init__(self) -> None:
        for name in ("name", "background", "grid", "cursor", "accent"):
            if not getattr(self, name):
                raise ValueError(f"theme field {name!r} must not be empty")
        if set(self.target_colors) != {1, 2, 3}:
            raise ValueError("target_colors must define buttons 1, 2 and 3")
        for button, color in self.target_colors.items():
            if not isinstance(color, str) or not _HEX_COLOR.fullmatch(color):
                raise ValueError(
                    f"target_colors[{button}] must be a #RRGGBB colour"
                )
        object.__setattr__(
            self,
            "target_colors",
            MappingProxyType(dict(self.target_colors)),
        )

        for name in (
            "background",
            "panel",
            "panel_edge",
            "grid",
            "text",
            "muted",
            "accent",
            "error",
            "hover",
            "cursor",
            "cursor_flash",
            "cursor_glow_color",
            "target_overlay_color",
            "dwell_fill",
            "dwell_line",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not _HEX_COLOR.fullmatch(value):
                raise ValueError(f"theme field {name!r} must be a #RRGGBB colour")
        if self.cursor_edge is not None and not _HEX_COLOR.fullmatch(
            self.cursor_edge
        ):
            raise ValueError("cursor_edge must be None or a #RRGGBB colour")

        if self.cursor_radius_basis not in {"window", "cell"}:
            raise ValueError("cursor_radius_basis must be 'window' or 'cell'")
        if not 0.0 < self.grid_margin < 0.5:
            raise ValueError("grid_margin must be between 0 and 0.5")
        if self.cursor_radius_min <= 0 or self.cursor_radius_max < self.cursor_radius_min:
            raise ValueError("cursor radius bounds are invalid")
        if self.cursor_radius_factor <= 0:
            raise ValueError("cursor_radius_factor must be positive")
        if self.cursor_line_width < 1:
            raise ValueError("cursor_line_width must be at least 1")
        if self.cursor_glow_radius_factor < 1:
            raise ValueError("cursor_glow_radius_factor must be at least 1")
        if self.target_glow_radius_factor < 1:
            raise ValueError("target_glow_radius_factor must be at least 1")
        if self.target_line_width < 0 or self.hover_outline_width < 0:
            raise ValueError("line widths must not be negative")
        if self.target_outline and self.target_line_width <= 0:
            raise ValueError("target_line_width must be positive when target_outline is on")
        if self.hover_outline and self.hover_outline_width <= 0:
            raise ValueError("hover_outline_width must be positive when hover_outline is on")
        if self.target_pulse_scale < 1:
            raise ValueError("target_pulse_scale must be at least 1")

        for name in (
            "cursor_glow_opacity",
            "target_glow_opacity",
            "target_overlay_opacity",
            "miss_opacity",
            "hover_opacity",
            "trail_opacity_min",
            "trail_opacity_max",
            "trail_glow_opacity_min",
            "trail_glow_opacity_max",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

        if self.trail_segments < 0:
            raise ValueError("trail_segments must not be negative")
        if self.trail_duration_s <= 0:
            raise ValueError("trail_duration_s must be positive")
        if self.trail_min_width < 0 or self.trail_max_width < 0:
            raise ValueError("trail widths must not be negative")
        if self.trail_max_width < self.trail_min_width:
            raise ValueError("trail_max_width must be >= trail_min_width")
        if self.trail_glow_width_factor < 1:
            raise ValueError("trail_glow_width_factor must be at least 1")
        if self.trail_opacity_max < self.trail_opacity_min:
            raise ValueError("trail_opacity_max must be >= trail_opacity_min")
        if self.trail_glow_opacity_max < self.trail_glow_opacity_min:
            raise ValueError(
                "trail_glow_opacity_max must be >= trail_glow_opacity_min"
            )
        if self.trail and self.trail_segments < 2:
            raise ValueError("trail_segments must be at least 2 when trail is on")


DARK = Theme(
    name="dark",
    background="#050D19",
    panel="#0A1422",
    panel_edge="#1E3A5F",
    grid="#FFFFFF",
    text="#EAF2FF",
    muted="#8FA6C4",
    accent="#469EFF",
    error="#FF6B6B",
    hover="#0F2238",
    cursor="#F4474D",
    cursor_edge=None,
    cursor_flash="#FFFFFF",
    cursor_line_width=1.0,
    cursor_glow=True,
    cursor_glow_color="#F4474D",
    cursor_glow_radius_factor=3.2,
    cursor_glow_opacity=0.30,
    cursor_radius_basis="window",
    cursor_radius_factor=0.015,
    cursor_radius_min=6.0,
    cursor_radius_max=18.0,
    target_colors={1: "#469EFF", 2: "#FFB340", 3: "#C77DFF"},
    target_outline=True,
    target_line_width=2.0,
    target_glow=True,
    target_glow_radius_factor=2.8,
    target_glow_opacity=0.18,
    target_pulse=True,
    target_pulse_scale=1.15,
    target_overlay=False,
    target_overlay_color="#000000",
    target_overlay_opacity=0.18,
    miss_opacity=0.85,
    hover_outline=True,
    hover_outline_width=3.0,
    hover_opacity=1.0,
    trail=True,
    trail_segments=24,
    trail_duration_s=0.9,
    trail_min_width=2.0,
    trail_max_width=9.0,
    trail_opacity_min=0.10,
    trail_opacity_max=0.42,
    trail_glow_width_factor=2.8,
    trail_glow_opacity_min=0.03,
    trail_glow_opacity_max=0.10,
    dwell_fill="#469EFF",
    dwell_line="#050D19",
    grid_margin=0.05,
)

CLASSIC = Theme(
    name="classic",
    background="#FFFFFF",
    panel="#F5F5F7",
    panel_edge="#D2D2D7",
    grid="#111111",
    text="#111111",
    muted="#6E6E73",
    accent="#0A84FF",
    error="#FF3B30",
    hover="#EDEDED",
    cursor="#111111",
    cursor_edge="#FFFFFF",
    cursor_flash="#FF3B30",
    cursor_line_width=2.0,
    cursor_glow=False,
    cursor_glow_color="#111111",
    cursor_glow_radius_factor=1.0,
    cursor_glow_opacity=0.0,
    cursor_radius_basis="cell",
    cursor_radius_factor=0.16,
    cursor_radius_min=5.0,
    cursor_radius_max=12.0,
    target_colors={1: "#0A84FF", 2: "#FF9500", 3: "#AF52DE"},
    target_outline=False,
    target_line_width=2.0,
    target_glow=False,
    target_glow_radius_factor=1.0,
    target_glow_opacity=0.0,
    target_pulse=False,
    target_pulse_scale=1.0,
    target_overlay=True,
    target_overlay_color="#000000",
    target_overlay_opacity=0.18,
    miss_opacity=0.85,
    hover_outline=False,
    hover_outline_width=0.0,
    hover_opacity=1.0,
    trail=False,
    trail_segments=0,
    trail_duration_s=0.9,
    trail_min_width=0.0,
    trail_max_width=0.0,
    trail_opacity_min=0.0,
    trail_opacity_max=0.0,
    trail_glow_width_factor=1.0,
    trail_glow_opacity_min=0.0,
    trail_glow_opacity_max=0.0,
    dwell_fill="#FFFFFF",
    dwell_line="#111111",
    grid_margin=0.03,
)

_THEMES = {"dark": DARK, "classic": CLASSIC}
if tuple(_THEMES) != THEMES:  # pragma: no cover - import-time guard
    raise RuntimeError(
        f"theme registry {tuple(_THEMES)} does not match settings.THEMES {THEMES}"
    )
for _key, _theme in _THEMES.items():  # pragma: no cover - import-time guard
    if _theme.name != _key:
        raise RuntimeError(
            f"theme registry key {_key!r} does not match Theme.name {_theme.name!r}"
        )


def get_theme(name: str) -> Theme:
    try:
        return _THEMES[name]
    except KeyError:
        raise ValueError(f"theme must be one of {THEMES}") from None
