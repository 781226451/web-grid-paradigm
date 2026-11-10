"""Drawing routines.

The renderer turns engine state into pixels.  It owns the short-lived visual
feedback (miss flash, cursor flash, motion trail) so that the session logic in
:mod:`web_grid_paradigm.app.runner` never has to think about drawing state.
"""

from __future__ import annotations

import math

from psychopy import visual
from psychopy.colors import Color

from ..core.geometry import Cell, Layout
from ..core.session import Phase, SessionEngine
from .palette import (
    ACCENT,
    CURSOR,
    CURSOR_FLASH,
    HOVER,
    TARGET_COLORS,
    TARGET_GLOW_RADIUS_FACTOR,
    TARGET_PULSATE_SCALE,
    TRAIL_DURATION_S,
    TRAIL_SEGMENTS,
)
from .stimuli import Stimuli

MISS_FLASH_S = 0.2
CURSOR_FLASH_S = 0.25

_TARGET_RGB = {
    button: list(Color(color, space="rgb").rgb)
    for button, color in TARGET_COLORS.items()
}
_CURSOR_RGB = list(Color(CURSOR, space="rgb").rgb)
_CURSOR_FLASH_RGB = list(Color(CURSOR_FLASH, space="rgb").rgb)


class Renderer:
    """Draws one frame for the current phase."""

    def __init__(self, win: visual.Window, layout: Layout, stimuli: Stimuli) -> None:
        self.win = win
        self.layout = layout
        self.stim = stimuli
        self._miss_cell: Cell | None = None
        self._miss_until = 0.0
        self._cursor_flash_until = 0.0
        self._trail: list[tuple[float, float, float]] = []

    # ------------------------------------------------------------------
    # feedback state (owned here, triggered by the runner)
    # ------------------------------------------------------------------
    def flash_miss(self, cell: Cell | None, now: float) -> None:
        """Short red flash on a wrong click and on the cursor."""
        self._cursor_flash_until = now + CURSOR_FLASH_S
        self._trail.clear()
        if cell is not None:
            self._miss_cell = cell
            self._miss_until = now + MISS_FLASH_S

    def reset(self) -> None:
        self._miss_cell = None
        self._miss_until = 0.0
        self._cursor_flash_until = 0.0
        self._trail.clear()

    @property
    def cursor_flash_until(self) -> float:
        return self._cursor_flash_until

    # ------------------------------------------------------------------
    # trail
    # ------------------------------------------------------------------
    def _append_trail(self, position: tuple[float, float], now: float) -> None:
        while self._trail and now - self._trail[0][2] > TRAIL_DURATION_S:
            self._trail.pop(0)
        if not self._trail:
            self._trail.append((*position, now))
            return
        last_x, last_y, _ = self._trail[-1]
        distance = math.hypot(position[0] - last_x, position[1] - last_y)
        break_distance = self.layout.cell * 2.5
        if distance > break_distance:
            self._trail.clear()
            self._trail.append((*position, now))
            return
        if distance < 1.0:
            return
        self._trail.append((*position, now))
        if len(self._trail) > TRAIL_SEGMENTS + 1:
            self._trail.pop(0)

    def _draw_trail(self, color: str, now: float) -> None:
        while self._trail and now - self._trail[0][2] > TRAIL_DURATION_S:
            self._trail.pop(0)
        points = self._trail
        if len(points) < 2:
            return
        segments = len(points) - 1
        for i in range(segments):
            fraction = (i + 1) / segments
            age = max(0.0, now - points[i + 1][2])
            freshness = max(0.0, 1.0 - age / TRAIL_DURATION_S)
            width = 2.0 + 7.0 * fraction
            for lines, line_width, opacity in (
                (
                    self.stim.trail_glow_lines,
                    width * 2.8,
                    (0.03 + 0.10 * fraction) * freshness,
                ),
                (
                    self.stim.trail_lines,
                    width,
                    (0.10 + 0.42 * fraction) * freshness,
                ),
            ):
                line = lines[i]
                line.start = points[i][:2]
                line.end = points[i + 1][:2]
                line.lineColor = color
                line.lineWidth = line_width
                line.opacity = opacity
                line.draw()

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
        target_color = ACCENT
        pulse = 1.0

        if target is not None:
            target_x, target_y = target.centre_px
            target_color = TARGET_COLORS.get(target.required_button, ACCENT)
            if cursor_cell == target.cell and engine.phase is Phase.RUNNING:
                pulse = TARGET_PULSATE_SCALE
            size = layout.cell * pulse

            if cursor_cell is not None and cursor_cell != target.cell:
                stim.hover_stim.pos = layout.centre_px(cursor_cell)
                stim.hover_stim.size = (layout.cell, layout.cell)
                stim.hover_stim.fillColor = HOVER
                stim.hover_stim.lineColor = target_color
                stim.hover_stim.draw()

            stim.target_glow.pos = (target_x, target_y)
            stim.target_glow.size = (
                size * TARGET_GLOW_RADIUS_FACTOR,
                size * TARGET_GLOW_RADIUS_FACTOR,
            )
            stim.target_glow.color = _TARGET_RGB[target.required_button]
            stim.target_glow.draw()

            stim.target_stim.pos = (target_x, target_y)
            stim.target_stim.size = (size, size)
            stim.target_stim.fillColor = target_color
            stim.target_stim.lineColor = target_color
            stim.target_stim.draw()

            if self._miss_cell is not None and now < self._miss_until:
                stim.miss_stim.pos = layout.centre_px(self._miss_cell)
                stim.miss_stim.draw()

            progress = engine.dwell_progress
            if progress > 0.01:
                stim.dwell_bar.fillColor = target_color
                self._draw_dwell_bar(target_x, target_y, progress)

        self._append_trail(cursor_px, now)
        flashing = now < self._cursor_flash_until
        cursor_color = CURSOR_FLASH if flashing else CURSOR
        cursor_rgb = _CURSOR_FLASH_RGB if flashing else _CURSOR_RGB
        self._draw_trail(cursor_color, now)

        stim.cursor_glow.pos = cursor_px
        stim.cursor_glow.color = cursor_rgb
        stim.cursor_glow.draw()
        stim.cursor_stim.pos = cursor_px
        stim.cursor_stim.fillColor = cursor_color
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
