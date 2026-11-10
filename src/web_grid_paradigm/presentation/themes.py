"""Visual theme definitions for the paradigm window.

A theme is split into small, cohesive value objects (palette, cursor, target,
hover, trail, layout, dwell).  The experimental logic stays in ``core/``.
Adding a theme means adding one :class:`Theme` instance and its name to
``core.settings.THEMES``; the CLI, TOML and WebUI expose the names
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


def _check_color(value: str, name: str) -> None:
    if not isinstance(value, str) or not _HEX_COLOR.fullmatch(value):
        raise ValueError(f"{name} must be a #RRGGBB colour")


@dataclass(frozen=True, slots=True)
class Palette:
    background: str
    panel: str
    panel_edge: str
    grid: str
    text: str
    muted: str
    accent: str
    error: str

    def __post_init__(self) -> None:
        for name, value in (
            ("background", self.background),
            ("panel", self.panel),
            ("panel_edge", self.panel_edge),
            ("grid", self.grid),
            ("text", self.text),
            ("muted", self.muted),
            ("accent", self.accent),
            ("error", self.error),
        ):
            _check_color(value, f"palette.{name}")


@dataclass(frozen=True, slots=True)
class CursorStyle:
    color: str
    edge: str | None
    flash: str
    line_width: float
    glow: bool
    glow_color: str
    glow_radius_factor: float
    glow_opacity: float
    radius_basis: str  # "window" | "cell"
    radius_factor: float
    radius_min: float
    radius_max: float

    def __post_init__(self) -> None:
        _check_color(self.color, "cursor.color")
        if self.edge is not None:
            _check_color(self.edge, "cursor.edge")
        _check_color(self.flash, "cursor.flash")
        _check_color(self.glow_color, "cursor.glow_color")
        if self.line_width < 1:
            raise ValueError("cursor.line_width must be at least 1")
        if self.radius_basis not in {"window", "cell"}:
            raise ValueError("cursor.radius_basis must be 'window' or 'cell'")
        if self.radius_factor <= 0:
            raise ValueError("cursor.radius_factor must be positive")
        if self.radius_min <= 0 or self.radius_max < self.radius_min:
            raise ValueError("cursor radius bounds are invalid")
        if self.glow_radius_factor < 1:
            raise ValueError("cursor.glow_radius_factor must be at least 1")
        if not 0.0 <= self.glow_opacity <= 1.0:
            raise ValueError("cursor.glow_opacity must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class TargetStyle:
    colors: Mapping[int, str]
    outline: bool
    line_width: float
    glow: bool
    glow_radius_factor: float
    glow_opacity: float
    pulse: bool
    pulse_scale: float
    overlay: bool
    overlay_color: str
    overlay_opacity: float
    miss_opacity: float

    def __post_init__(self) -> None:
        if set(self.colors) != {1, 2, 3}:
            raise ValueError("target.colors must define buttons 1, 2 and 3")
        for button, color in self.colors.items():
            _check_color(color, f"target.colors[{button}]")
        object.__setattr__(
            self,
            "colors",
            MappingProxyType(dict(self.colors)),
        )
        if self.line_width < 0:
            raise ValueError("target.line_width must not be negative")
        if self.outline and self.line_width <= 0:
            raise ValueError("target.line_width must be positive when outline is on")
        if self.glow_radius_factor < 1:
            raise ValueError("target.glow_radius_factor must be at least 1")
        if self.pulse_scale < 1:
            raise ValueError("target.pulse_scale must be at least 1")
        _check_color(self.overlay_color, "target.overlay_color")
        for name, value in (
            ("glow_opacity", self.glow_opacity),
            ("overlay_opacity", self.overlay_opacity),
            ("miss_opacity", self.miss_opacity),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"target.{name} must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class HoverStyle:
    fill: str
    outline: bool
    outline_width: float
    opacity: float

    def __post_init__(self) -> None:
        _check_color(self.fill, "hover.fill")
        if self.outline_width < 0:
            raise ValueError("hover.outline_width must not be negative")
        if self.outline and self.outline_width <= 0:
            raise ValueError("hover.outline_width must be positive when outline is on")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError("hover.opacity must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class TrailStyle:
    enabled: bool
    segments: int
    duration_s: float
    min_width: float
    max_width: float
    opacity_min: float
    opacity_max: float
    glow_width_factor: float
    glow_opacity_min: float
    glow_opacity_max: float

    def __post_init__(self) -> None:
        if self.segments < 0:
            raise ValueError("trail.segments must not be negative")
        if self.duration_s <= 0:
            raise ValueError("trail.duration_s must be positive")
        if self.min_width < 0 or self.max_width < 0:
            raise ValueError("trail widths must not be negative")
        if self.max_width < self.min_width:
            raise ValueError("trail.max_width must be >= trail.min_width")
        if self.glow_width_factor < 1:
            raise ValueError("trail.glow_width_factor must be at least 1")
        for name, value in (
            ("opacity_min", self.opacity_min),
            ("opacity_max", self.opacity_max),
            ("glow_opacity_min", self.glow_opacity_min),
            ("glow_opacity_max", self.glow_opacity_max),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"trail.{name} must be in [0, 1]")
        if self.opacity_max < self.opacity_min:
            raise ValueError("trail.opacity_max must be >= trail.opacity_min")
        if self.glow_opacity_max < self.glow_opacity_min:
            raise ValueError(
                "trail.glow_opacity_max must be >= trail.glow_opacity_min"
            )
        if self.enabled and self.segments < 2:
            raise ValueError("trail.segments must be at least 2 when enabled")


@dataclass(frozen=True, slots=True)
class LayoutStyle:
    grid_margin: float
    grid_line_width_factor: float

    def __post_init__(self) -> None:
        if not 0.0 < self.grid_margin < 0.5:
            raise ValueError("layout.grid_margin must be between 0 and 0.5")
        if not 0.0 < self.grid_line_width_factor < 0.05:
            raise ValueError(
                "layout.grid_line_width_factor must be between 0 and 0.05"
            )


@dataclass(frozen=True, slots=True)
class DwellStyle:
    fill: str
    line: str

    def __post_init__(self) -> None:
        _check_color(self.fill, "dwell.fill")
        _check_color(self.line, "dwell.line")


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
    font: str
    palette: Palette
    cursor: CursorStyle
    target: TargetStyle
    hover: HoverStyle
    trail: TrailStyle
    layout: LayoutStyle
    dwell: DwellStyle

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("theme.name must be a non-empty string")
        if not isinstance(self.font, str) or not self.font.strip():
            raise ValueError("theme.font must be a non-empty string")
        for field_name, expected in (
            ("palette", Palette),
            ("cursor", CursorStyle),
            ("target", TargetStyle),
            ("hover", HoverStyle),
            ("trail", TrailStyle),
            ("layout", LayoutStyle),
            ("dwell", DwellStyle),
        ):
            if not isinstance(getattr(self, field_name), expected):
                raise TypeError(
                    f"theme.{field_name} must be a {expected.__name__}"
                )


DARK = Theme(
    name="dark",
    font="Noto Sans SC",
    palette=Palette(
        background="#050D19",
        panel="#0A1422",
        panel_edge="#1E3A5F",
        grid="#FFFFFF",
        text="#EAF2FF",
        muted="#8FA6C4",
        accent="#469EFF",
        error="#FF6B6B",
    ),
    cursor=CursorStyle(
        color="#F4474D",
        edge=None,
        flash="#FFFFFF",
        line_width=1.0,
        glow=True,
        glow_color="#F4474D",
        glow_radius_factor=3.2,
        glow_opacity=0.30,
        radius_basis="window",
        radius_factor=0.015,
        radius_min=6.0,
        radius_max=18.0,
    ),
    target=TargetStyle(
        colors={1: "#469EFF", 2: "#FFB340", 3: "#C77DFF"},
        outline=True,
        line_width=2.0,
        glow=True,
        glow_radius_factor=2.8,
        glow_opacity=0.18,
        pulse=True,
        pulse_scale=1.15,
        overlay=False,
        overlay_color="#000000",
        overlay_opacity=0.18,
        miss_opacity=0.85,
    ),
    hover=HoverStyle(
        fill="#0F2238",
        outline=True,
        outline_width=3.0,
        opacity=1.0,
    ),
    trail=TrailStyle(
        enabled=True,
        segments=24,
        duration_s=0.9,
        min_width=2.0,
        max_width=9.0,
        opacity_min=0.10,
        opacity_max=0.42,
        glow_width_factor=2.8,
        glow_opacity_min=0.03,
        glow_opacity_max=0.10,
    ),
    layout=LayoutStyle(grid_margin=0.05, grid_line_width_factor=0.0015),
    dwell=DwellStyle(fill="#469EFF", line="#050D19"),
)

CLASSIC = Theme(
    name="classic",
    font="Microsoft YaHei",
    palette=Palette(
        background="#FFFFFF",
        panel="#F5F5F7",
        panel_edge="#D2D2D7",
        grid="#111111",
        text="#111111",
        muted="#6E6E73",
        accent="#0A84FF",
        error="#FF3B30",
    ),
    cursor=CursorStyle(
        color="#111111",
        edge="#FFFFFF",
        flash="#FF3B30",
        line_width=2.0,
        glow=False,
        glow_color="#111111",
        glow_radius_factor=1.0,
        glow_opacity=0.0,
        radius_basis="cell",
        radius_factor=0.16,
        radius_min=5.0,
        radius_max=12.0,
    ),
    target=TargetStyle(
        colors={1: "#0A84FF", 2: "#FF9500", 3: "#AF52DE"},
        outline=False,
        line_width=2.0,
        glow=False,
        glow_radius_factor=1.0,
        glow_opacity=0.0,
        pulse=False,
        pulse_scale=1.0,
        overlay=True,
        overlay_color="#000000",
        overlay_opacity=0.18,
        miss_opacity=0.85,
    ),
    hover=HoverStyle(
        fill="#EDEDED",
        outline=False,
        outline_width=0.0,
        opacity=1.0,
    ),
    trail=TrailStyle(
        enabled=False,
        segments=0,
        duration_s=0.9,
        min_width=0.0,
        max_width=0.0,
        opacity_min=0.0,
        opacity_max=0.0,
        glow_width_factor=1.0,
        glow_opacity_min=0.0,
        glow_opacity_max=0.0,
    ),
    layout=LayoutStyle(grid_margin=0.03, grid_line_width_factor=0.0015),
    dwell=DwellStyle(fill="#FFFFFF", line="#111111"),
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
