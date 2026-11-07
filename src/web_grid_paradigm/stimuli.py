"""Stimulus construction for the paradigm window.

One :class:`Stimuli` instance owns every PsychoPy visual object.  It is built
once per session; the drawing code only moves and draws them, so no stimulus
is ever constructed inside the render loop.
"""

from __future__ import annotations

from psychopy import visual

from .config import ExperimentConfig
from .geometry import Layout
from .i18n import Strings
from .palette import (
    ACCENT,
    CURSOR,
    CURSOR_EDGE,
    ERROR,
    GRID,
    HOVER,
    MUTED,
    PANEL,
    PANEL_EDGE,
    TARGET_COLORS,
    TEXT,
)


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
            fillColor="#ffffff",
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
            lineColor=None,
            units="pix",
        )
        self.target_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=TARGET_COLORS[1],
            lineColor=None,
            units="pix",
        )
        self.target_hover = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor="#000000",
            opacity=0.18,
            lineColor=None,
            units="pix",
        )
        self.miss_stim = visual.Rect(
            self.win,
            width=layout.cell,
            height=layout.cell,
            fillColor=ERROR,
            lineColor=None,
            units="pix",
        )
        self.cursor_stim = visual.Circle(
            self.win,
            radius=max(5.0, min(12.0, layout.cell * 0.16)),
            fillColor=CURSOR,
            lineColor=CURSOR_EDGE,
            lineWidth=2,
            units="pix",
        )
        self.dwell_bar = visual.Rect(
            self.win,
            width=2,
            height=max(3.0, layout.cell * 0.05),
            fillColor="#ffffff",
            lineColor=GRID,
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
            fillColor="#ffffff",
            lineColor=None,
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
            "keyboard": strings["mode_keyboard"],
            "udp": strings.format("mode_udp", port=config.udp_port),
            "demo": strings["mode_demo"],
        }[config.input]
