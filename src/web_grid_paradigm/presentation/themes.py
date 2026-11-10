"""Visual theme definitions for the paradigm window.

Themes only carry presentation values; the experimental logic stays in
``core/``.  Adding a theme means adding one :class:`Theme` instance and its
name to ``core.settings.THEMES``; the CLI, TOML and WebUI expose the names
automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.settings import THEMES


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
    label: str

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
    cursor_glow: bool
    cursor_glow_color: str
    cursor_glow_radius_factor: float
    cursor_glow_opacity: float
    cursor_radius_basis: str  # "window" | "cell"
    cursor_radius_factor: float
    cursor_radius_min: float
    cursor_radius_max: float

    # Targets.
    target_colors: dict[int, str] = field(default_factory=dict)
    target_outline: bool = False
    target_glow: bool = False
    target_glow_radius_factor: float = 2.8
    target_glow_opacity: float = 0.18
    target_pulse: bool = False
    target_pulse_scale: float = 1.15
    target_overlay: bool = False

    # Grid-cell hover.
    hover_outline: bool = False
    hover_outline_width: float = 0.0

    # Cursor trail.
    trail: bool = False
    trail_segments: int = 0
    trail_duration_s: float = 0.9

    # Dwell bar and layout.
    dwell_fill: str = "#ffffff"
    dwell_line: str = "#111111"
    grid_margin: float = 0.05


DARK = Theme(
    name="dark",
    label="暗色发光",
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
    target_glow=True,
    target_glow_radius_factor=2.8,
    target_glow_opacity=0.18,
    target_pulse=True,
    target_pulse_scale=1.15,
    target_overlay=False,
    hover_outline=True,
    hover_outline_width=3.0,
    trail=True,
    trail_segments=24,
    trail_duration_s=0.9,
    dwell_fill="#469EFF",
    dwell_line="#050D19",
    grid_margin=0.05,
)

CLASSIC = Theme(
    name="classic",
    label="经典白底",
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
    target_glow=False,
    target_glow_radius_factor=1.0,
    target_glow_opacity=0.0,
    target_pulse=False,
    target_pulse_scale=1.0,
    target_overlay=True,
    hover_outline=False,
    hover_outline_width=0.0,
    trail=False,
    trail_segments=0,
    trail_duration_s=0.9,
    dwell_fill="#FFFFFF",
    dwell_line="#111111",
    grid_margin=0.03,
)

_THEMES = {"dark": DARK, "classic": CLASSIC}
if tuple(_THEMES) != THEMES:  # pragma: no cover - import-time guard
    raise RuntimeError(
        f"theme registry {tuple(_THEMES)} does not match settings.THEMES {THEMES}"
    )


def get_theme(name: str) -> Theme:
    try:
        return _THEMES[name]
    except KeyError:
        raise ValueError(f"theme must be one of {THEMES}") from None
