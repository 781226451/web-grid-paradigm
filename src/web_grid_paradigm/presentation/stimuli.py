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
from .palette import (
    ACCENT,
    BG,
    CURSOR,
    CURSOR_GLOW,
    CURSOR_GLOW_OPACITY,
    CURSOR_GLOW_RADIUS_FACTOR,
    CURSOR_RING_OPACITY,
    CURSOR_RING_RADIUS_FACTOR,
    CURSOR_RING_WIDTH_PX,
    ERROR,
    GRID,
    HOVER,
    MUTED,
    PANEL,
    PANEL_EDGE,
    TARGET_COLORS,
    TARGET_GLOW_OPACITY,
    TARGET_GLOW_RADIUS_FACTOR,
    TARGET_RING,
    TARGET_RING_OPACITY,
    TARGET_RING_RADIUS_FACTOR,
    TARGET_RING_WIDTH_PX,
    TEXT,
    TRAIL_SEGMENTS,
)


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
    ) -> None:
        self.win = win
        self.layout = layout
        self.ui = ui
        self.font = font
        self.strings = strings

        self._build_board()
        self._build_task_stimuli()
        self._build_fixation()
        self._build_intro()

    # ------------------------------------------------------------------
    def _build_board(self) -> None:
        layout = self.layout
        board = visual.Rect(
            self.win,
            width=layout.board_w,
            height=layout.board_h,
            pos=layout.board_centre,
            fillColor=BG,
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
                    fillColor=GRID,
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
                    fillColor=GRID,
                    lineColor=None,
                    units="pix",
                )
            )
        # One bitmap for the whole grid: cheap to draw every frame.
        self.grid_bg = visual.BufferImageStim(self.win, stim=lines)
        del lines

    def _build_task_stimuli(self) -> None:
        layout = self.layout
        self.hover_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=HOVER,
            lineColor=ACCENT,
            lineWidth=3,
            opacity=1.0,
            units="pix",
        )
        self.target_glow = visual.GratingStim(
            self.win,
            tex=None,
            mask="gauss",
            size=(
                layout.cell * TARGET_GLOW_RADIUS_FACTOR,
                layout.cell * TARGET_GLOW_RADIUS_FACTOR,
            ),
            color=_rgb(TARGET_COLORS[1]),
            colorSpace="rgb",
            opacity=TARGET_GLOW_OPACITY,
            units="pix",
            texRes=64,
            interpolate=True,
            autoLog=False,
        )
        self.target_ring = visual.Rect(
            self.win,
            width=layout.cell * TARGET_RING_RADIUS_FACTOR,
            height=layout.cell * TARGET_RING_RADIUS_FACTOR,
            fillColor=None,
            lineColor=TARGET_RING,
            lineWidth=TARGET_RING_WIDTH_PX,
            opacity=TARGET_RING_OPACITY,
            units="pix",
        )
        self.target_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=TARGET_COLORS[1],
            lineColor=TARGET_COLORS[1],
            lineWidth=2,
            units="pix",
        )
        self.miss_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=ERROR,
            lineColor=None,
            opacity=0.85,
            units="pix",
        )
        radius = max(6.0, min(18.0, min(layout.window_w, layout.window_h) * 0.015))
        self.cursor_glow = visual.GratingStim(
            self.win,
            tex=None,
            mask="gauss",
            size=(
                radius * 2 * CURSOR_GLOW_RADIUS_FACTOR,
                radius * 2 * CURSOR_GLOW_RADIUS_FACTOR,
            ),
            color=_rgb(CURSOR_GLOW),
            colorSpace="rgb",
            opacity=CURSOR_GLOW_OPACITY,
            units="pix",
            texRes=64,
            interpolate=True,
            autoLog=False,
        )
        self.cursor_ring = visual.Circle(
            self.win,
            radius=radius * CURSOR_RING_RADIUS_FACTOR,
            fillColor=None,
            lineColor=CURSOR_GLOW,
            lineWidth=CURSOR_RING_WIDTH_PX,
            opacity=CURSOR_RING_OPACITY,
            units="pix",
        )
        self.cursor_stim = visual.Circle(
            self.win,
            radius=radius,
            fillColor=CURSOR,
            lineColor=None,
            units="pix",
        )
        self.trail_lines = [
            visual.Line(
                self.win,
                start=(0, 0),
                end=(0, 0),
                lineColor=CURSOR,
                lineWidth=2,
                opacity=0,
                units="pix",
                autoLog=False,
            )
            for _ in range(TRAIL_SEGMENTS)
        ]
        self.trail_glow_lines = [
            visual.Line(
                self.win,
                start=(0, 0),
                end=(0, 0),
                lineColor=CURSOR,
                lineWidth=2,
                opacity=0,
                units="pix",
                autoLog=False,
            )
            for _ in range(TRAIL_SEGMENTS)
        ]
        self.dwell_bar = visual.Rect(
            self.win,
            width=2,
            height=max(3.0, layout.cell * 0.05),
            fillColor=ACCENT,
            lineColor=BG,
            lineWidth=1,
            units="pix",
        )

    def _build_fixation(self) -> None:
        # The animal-facing screen has no text: the only chrome is the
        # fixation cross shown before each block.
        fix = 18 * self.ui
        self.fixation_bg = visual.Circle(
            self.win,
            radius=26 * self.ui,
            fillColor=PANEL,
            lineColor=PANEL_EDGE,
            lineWidth=1,
            units="pix",
        )
        self.fixation_h = visual.Line(
            self.win,
            start=(-fix, 0),
            end=(fix, 0),
            lineColor=TEXT,
            lineWidth=2,
            units="pix",
        )
        self.fixation_v = visual.Line(
            self.win,
            start=(0, -fix),
            end=(0, fix),
            lineColor=TEXT,
            lineWidth=2,
            units="pix",
        )

    def _build_intro(self) -> None:
        # Optional human instruction screen; skipped by default.
        layout = self.layout
        w, h, ui = layout.window_w, layout.window_h, self.ui
        panel_w = min(w * 0.72, 900 * ui)
        self.panel = visual.Rect(
            self.win,
            width=panel_w,
            height=h * 0.56,
            pos=(0, 0),
            fillColor=PANEL,
            lineColor=PANEL_EDGE,
            lineWidth=2,
            units="pix",
        )
        self.intro_title = self.text(
            self.strings["title"], 46 * ui, TEXT, (0, h * 0.20), bold=True
        )
        self.intro_subtitle = self.text(
            self.strings["subtitle"], 20 * ui, MUTED, (0, h * 0.145)
        )
        self.intro_body = self.text(
            "", 21 * ui, TEXT, (0, h * 0.02), wrap=panel_w * 0.84
        )
        self.intro_mode = self.text("", 17 * ui, ACCENT, (0, -h * 0.08))
        self.intro_start = self.text(
            self.strings["start_hint"], 19 * ui, TEXT, (0, -h * 0.17)
        )

    # ------------------------------------------------------------------
    def text(
        self,
        text: str,
        height: float,
        color: str = TEXT,
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
            color=color,
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
                "mode_joystick", port=config.joystick_port or "—"
            ),
            "lsl": strings.format(
                "mode_lsl",
                stream=config.lsl_velocity_stream or config.lsl_velocity_type,
            ),
        }[config.input]
