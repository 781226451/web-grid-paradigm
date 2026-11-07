"""Drawing routines.

The renderer turns engine state into pixels.  It owns the short-lived visual
feedback (miss flash, cursor flash) so that the session logic in
:mod:`web_grid_paradigm.runner` never has to think about drawing state.
"""

from __future__ import annotations

from psychopy import visual

from .geometry import Cell, Layout
from .palette import ACCENT, CURSOR, ERROR, TARGET_COLORS
from .session import Phase, SessionEngine
from .stimuli import Stimuli

MISS_FLASH_S = 0.2
CURSOR_FLASH_S = 0.25


class Renderer:
    """Draws one frame for the current phase."""

    def __init__(self, win: visual.Window, layout: Layout, stimuli: Stimuli) -> None:
        self.win = win
        self.layout = layout
        self.stim = stimuli
        self._miss_cell: Cell | None = None
        self._miss_until = 0.0
        self._cursor_flash_until = 0.0

    # ------------------------------------------------------------------
    # feedback state (owned here, triggered by the runner)
    # ------------------------------------------------------------------
    def flash_miss(self, cell: Cell | None, now: float) -> None:
        """Short red flash on a wrong click and on the cursor."""
        self._cursor_flash_until = now + CURSOR_FLASH_S
        if cell is not None:
            self._miss_cell = cell
            self._miss_until = now + MISS_FLASH_S

    def reset(self) -> None:
        self._miss_cell = None
        self._miss_until = 0.0
        self._cursor_flash_until = 0.0

    @property
    def cursor_flash_until(self) -> float:
        return self._cursor_flash_until

    # ------------------------------------------------------------------
    # frames
    # ------------------------------------------------------------------
    def draw_intro(self) -> None:
        stim = self.stim
        stim.panel.draw()
        stim.intro_title.draw()
        stim.intro_subtitle.draw()
        stim.intro_body.draw()
        stim.intro_mode.draw()
        stim.intro_start.draw()

    def draw_countdown(self) -> None:
        stim = self.stim
        stim.grid_bg.draw()
        stim.fixation_bg.draw()
        stim.fixation_h.draw()
        stim.fixation_v.draw()

    def draw_rest(self) -> None:
        """Blank screen between blocks."""

    def draw_run(
        self, now: float, engine: SessionEngine, cursor_px: tuple[float, float]
    ) -> None:
        stim = self.stim
        layout = self.layout
        stim.grid_bg.draw()

        # During the inter-trial interval only the empty grid and cursor show.
        target = engine.target if engine.phase is not Phase.ITI else None
        cursor_cell = layout.cell_at_px(*cursor_px)

        if target is not None:
            target_x, target_y = target.centre_px
            if cursor_cell is not None and cursor_cell != target.cell:
                stim.hover_stim.pos = layout.centre_px(cursor_cell)
                stim.hover_stim.draw()

            stim.target_stim.pos = (target_x, target_y)
            stim.target_stim.fillColor = TARGET_COLORS.get(
                target.required_button, ACCENT
            )
            stim.target_stim.draw()

            if cursor_cell == target.cell and engine.phase is Phase.RUNNING:
                stim.target_hover.pos = (target_x, target_y)
                stim.target_hover.draw()

            if self._miss_cell is not None and now < self._miss_until:
                stim.miss_stim.pos = layout.centre_px(self._miss_cell)
                stim.miss_stim.draw()

            progress = engine.dwell_progress
            if progress > 0.01:
                self._draw_dwell_bar(target_x, target_y, progress)

        stim.cursor_stim.pos = cursor_px
        stim.cursor_stim.fillColor = (
            ERROR if now < self._cursor_flash_until else CURSOR
        )
        stim.cursor_stim.draw()

    def _draw_dwell_bar(self, target_x: float, target_y: float, progress: float) -> None:
        stim = self.stim
        layout = self.layout
        inner = layout.cell * 0.72
        bar_h = max(3.0, layout.cell * 0.05)
        bar_w = max(1.0, inner * progress)
        stim.dwell_bar.width = bar_w
        stim.dwell_bar.pos = (
            target_x - inner / 2 + bar_w / 2,
            target_y - layout.cell / 2 + bar_h + 2,
        )
        stim.dwell_bar.draw()

    def draw_done(self) -> None:
        """Blank end screen: the animal sees no text."""
