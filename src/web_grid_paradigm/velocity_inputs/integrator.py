"""Velocity integrator: turns samples into the cursor position.

Sources never know the window geometry or the cursor; they only emit
``(timestamp, vx, vy)``.  The integrator is the single place that turns those
samples into a pixel position, clamps it to the window and keeps the clock
used to integrate the next sample.  It is pure Python and unit-testable.
"""

from __future__ import annotations

from ..geometry import Layout
from .base import VelocityFrame


class VelocityIntegrator:
    """Absolute cursor position (normalised) driven by velocity samples."""

    def __init__(self, layout: Layout, *, max_dt: float = 0.25) -> None:
        self.layout = layout
        self.max_dt = float(max_dt)
        self.x = 0.0
        self.y = 0.0
        self._last_t: float | None = None

    # ------------------------------------------------------------------
    def set_position_norm(self, x: float, y: float) -> None:
        self.x = _clamp(float(x))
        self.y = _clamp(float(y))

    def set_position_px(self, x: float, y: float) -> None:
        nx, ny = self.layout.px_to_norm(float(x), float(y))
        self.set_position_norm(nx, ny)

    @property
    def position_norm(self) -> tuple[float, float]:
        return self.x, self.y

    @property
    def position_px(self) -> tuple[float, float]:
        return self.layout.norm_to_px(self.x, self.y)

    # ------------------------------------------------------------------
    def update(self, frame: VelocityFrame, now: float) -> None:
        """Integrate the frame's samples up to ``now``.

        The integrator always advances its clock to the frame time, so a
        source that computes velocity from the interval between two reads
        (the mouse) is reproduced exactly even on frames without a sample.
        """
        if self._last_t is None:
            self._last_t = now
        for sample in frame.samples:
            dt = sample.timestamp - self._last_t
            if dt <= 0.0:
                continue
            dt = min(dt, self.max_dt)
            self.x = _clamp(self.x + sample.vx * dt)
            self.y = _clamp(self.y + sample.vy * dt)
            self._last_t = sample.timestamp
        self._last_t = max(self._last_t, now)


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))
