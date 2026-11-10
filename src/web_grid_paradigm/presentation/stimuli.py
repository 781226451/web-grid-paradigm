"""Stimulus construction for the paradigm window.

One :class:`Stimuli` instance owns every PsychoPy visual object.  It is built
once per session; the drawing code only moves and draws them, so no stimulus
is ever constructed inside the render loop.
"""

from __future__ import annotations

from psychopy import visual
from psychopy.colors import Color

from ..core.config import ExperimentConfig
from ..core.geometry import Layout
from ..core.i18n import Strings
from .themes import Theme


def _rgb(color: str) -> list[float]:
    """Convert a hex colour to PsychoPy's -1..1 RGB space."""
    return list(Color(color, space="rgb").rgb)


class Stimuli:
    """All visual objects of the task screen, plus the optional intro page."""

    def __init__(
        self,
        win: visual.Window,
        layout: Layout,
        ui: float,
        font: str,
        strings: Strings,
        theme: Theme,
    ) -> None:
        self.win = win
        self.layout = layout
        self.ui = ui
        self.font = font
        self.strings = strings
        self.theme = theme

        self._build_board()
        self._build_task_stimuli()
        self._build_intro()

    # ------------------------------------------------------------------
    def _build_board(self) -> None:
        layout = self.layout
        theme = self.theme
        board = visual.Rect(
            self.win,
            width=layout.board_w,
            height=layout.board_h,
            pos=layout.board_centre,
            fillColor=theme.background,
            lineColor=None,
            units="pix",
        )
        lines = [board]
        board_cx, board_cy = layout.board_centre
        for col in range(layout.cols + 1):
            x = layout.left + col * layout.pitch + layout.line / 2
            lines.append(
                visual.Rect(
                    self.win,
                    width=layout.line,
                    height=layout.board_h,
                    pos=(x, board_cy),
                    fillColor=theme.grid,
                    lineColor=None,
                    units="pix",
                )
            )
        for row in range(layout.rows + 1):
            y = layout.top - row * layout.pitch - layout.line / 2
            lines.append(
                visual.Rect(
                    self.win,
                    width=layout.board_w,
                    height=layout.line,
                    pos=(board_cx, y),
                    fillColor=theme.grid,
                    lineColor=None,
                    units="pix",
                )
            )
        # One bitmap for the whole grid: cheap to draw every frame.
        self.grid_bg = visual.BufferImageStim(self.win, stim=lines)
        del lines

    def _build_task_stimuli(self) -> None:
        layout = self.layout
        theme = self.theme
        self.hover_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=theme.hover,
            lineColor=theme.accent if theme.hover_outline else None,
            lineWidth=theme.hover_outline_width,
            opacity=theme.hover_opacity,
            units="pix",
        )
        self.target_glow = None
        if theme.target_glow:
            self.target_glow = visual.GratingStim(
                self.win,
                tex=None,
                mask="gauss",
                size=(
                    layout.cell * theme.target_glow_radius_factor,
                    layout.cell * theme.target_glow_radius_factor,
                ),
                color=_rgb(theme.target_colors[1]),
                colorSpace="rgb",
                opacity=theme.target_glow_opacity,
                units="pix",
                texRes=64,
                interpolate=True,
                autoLog=False,
            )
        self.target_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=theme.target_colors[1],
            lineColor=theme.target_colors[1] if theme.target_outline else None,
            lineWidth=theme.target_line_width if theme.target_outline else 0,
            units="pix",
        )
        self.target_hover = None
        if theme.target_overlay:
            self.target_hover = visual.Rect(
                self.win,
                width=layout.cell,
                height=layout.cell,
                fillColor=theme.target_overlay_color,
                opacity=theme.target_overlay_opacity,
                lineColor=None,
                units="pix",
            )
        self.miss_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=theme.error,
            lineColor=None,
            opacity=0.85,
            units="pix",
        )
        if theme.cursor_radius_basis == "cell":
            raw_radius = layout.cell * theme.cursor_radius_factor
        else:
            raw_radius = min(layout.window_w, layout.window_h) * theme.cursor_radius_factor
        radius = max(
            theme.cursor_radius_min,
            min(theme.cursor_radius_max, raw_radius),
        )
        self.cursor_glow = None
        if theme.cursor_glow:
            self.cursor_glow = visual.GratingStim(
                self.win,
                tex=None,
                mask="gauss",
                size=(
                    radius * 2 * theme.cursor_glow_radius_factor,
                    radius * 2 * theme.cursor_glow_radius_factor,
                ),
                color=_rgb(theme.cursor_glow_color),
                colorSpace="rgb",
                opacity=theme.cursor_glow_opacity,
                units="pix",
                texRes=64,
                interpolate=True,
                autoLog=False,
            )
        self.cursor_stim = visual.Circle(
            self.win,
            radius=radius,
            fillColor=theme.cursor,
            lineColor=theme.cursor_edge,
            lineWidth=theme.cursor_line_width,
            units="pix",
        )
        trail_segments = theme.trail_segments if theme.trail else 0
        self.trail_lines = [
            visual.Line(
                self.win,
                start=(0, 0),
                end=(0, 0),
                lineColor=theme.cursor,
                lineWidth=2,
                opacity=0,
                units="pix",
                autoLog=False,
            )
            for _ in range(trail_segments)
        ]
        self.trail_glow_lines = [
            visual.Line(
                self.win,
                start=(0, 0),
                end=(0, 0),
                lineColor=theme.cursor,
                lineWidth=2,
                opacity=0,
                units="pix",
                autoLog=False,
            )
            for _ in range(trail_segments)
        ]
        self.dwell_bar = visual.Rect(
            self.win,
            width=2,
            height=max(3.0, layout.cell * 0.05),
            fillColor=theme.dwell_fill,
            lineColor=theme.dwell_line,
            lineWidth=1,
            units="pix",
        )

    def _build_intro(self) -> None:
        # Optional human instruction screen; skipped by default.
        layout = self.layout
        theme = self.theme
        w, h, ui = layout.window_w, layout.window_h, self.ui
        panel_w = min(w * 0.72, 900 * ui)
        self.panel = visual.Rect(
            self.win,
            width=panel_w,
            height=h * 0.56,
            pos=(0, 0),
            fillColor=theme.panel,
            lineColor=theme.panel_edge,
            lineWidth=2,
            units="pix",
        )
        self.intro_title = self.text(
            self.strings["title"], 46 * ui, self.theme.text, (0, h * 0.20), bold=True
        )
        self.intro_subtitle = self.text(
            self.strings["subtitle"], 20 * ui, self.theme.muted, (0, h * 0.145)
        )
        self.intro_body = self.text(
            "", 21 * ui, self.theme.text, (0, h * 0.02), wrap=panel_w * 0.84
        )
        self.intro_mode = self.text("", 17 * ui, self.theme.accent, (0, -h * 0.08))
        self.intro_start = self.text(
            self.strings["start_hint"], 19 * ui, self.theme.text, (0, -h * 0.17)
        )

    # ------------------------------------------------------------------
    def text(
        self,
        text: str,
        height: float,
        color: str | None = None,
        pos: tuple[float, float] = (0, 0),
        anchor: str = "center",
        wrap: float | None = None,
        bold: bool = False,
        align: str = "center",
    ) -> visual.TextStim:
        return visual.TextStim(
            self.win,
            text=text,
            font=self.font,
            height=height,
            color=color or self.theme.text,
            pos=pos,
            units="pix",
            anchorHoriz=anchor,
            anchorVert="center",
            alignText=align,
            wrapWidth=wrap,
            bold=bold,
        )

    def configure_intro_texts(self, config: ExperimentConfig) -> None:
        """Fill the intro page with the wording for this configuration."""
        if config.selection == "dwell":
            body_key = "instr_dwell"
        elif config.click_types > 1:
            body_key = "instr_click_multi"
        else:
            body_key = "instr_click"
        strings = self.strings
        self.intro_body.text = strings[body_key]
        self.intro_mode.text = {
            "mouse": strings["mode_mouse"],
            "demo": strings["mode_demo"],
            "joystick": strings.format(
                "mode_joystick", port=config.joystick_port or "-"
            ),
            "lsl": strings.format(
                "mode_lsl",
                stream=config.lsl_velocity_stream or config.lsl_velocity_type,
            ),
        }[config.input]
