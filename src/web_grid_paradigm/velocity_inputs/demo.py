"""Demo autopilot strategy: a deterministic synthetic cursor.

``--input demo`` is used by examples and smoke tests.  A real device cannot
know the current target, but a demo source deliberately does: the facade
calls :meth:`DemoVelocitySource.set_target_norm` once per frame, the source
steers towards it at ``speed`` normalised units per second and emits one
click when it arrives.  This exception is confined to the demo strategy and
documented here; all real sources stay target-agnostic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .base import (
    InitialPositionProvider,
    VelocityCapabilities,
    VelocityFrame,
    VelocitySample,
    VelocitySourceStatus,
)
from .registry import register_velocity_source


@dataclass(frozen=True, slots=True)
class DemoVelocityOptions:
    """Configuration of the demo autopilot."""

    speed: float = 2.2  # normalised units per second


@register_velocity_source("demo")
class DemoVelocitySource(InitialPositionProvider):
    """Autopilot that steers to the target and clicks once it arrives."""

    name = "demo"
    capabilities = VelocityCapabilities(
        category="demo", continuous=True, absolute=True, clicks=True
    )

    def __init__(
        self,
        *,
        options: DemoVelocityOptions | None = None,
        context: object | None = None,
    ) -> None:
        self.options = options or DemoVelocityOptions()
        self.context = context
        self.x = 0.0
        self.y = 0.0
        self._target: tuple[float, float] | None = None
        self._clicked = False
        self._button = 1
        self._last_t: float | None = None
        self._opened = False
        self._frames = 0
        self._error: str | None = None

    # ------------------------------------------------------------------
    def open(self) -> None:
        if self._opened:
            return
        if self.options.speed <= 0:
            raise ValueError("demo speed must be positive")
        self._opened = True
        self._last_t = None

    def close(self) -> None:
        self._opened = False

    def reset(self) -> None:
        """Re-arm the click for a new block (position is kept)."""
        self._clicked = False

    def set_target_norm(
        self,
        target: tuple[float, float] | None,
        button: int | None = None,
    ) -> None:
        if target is None:
            self._target = None
            self._clicked = False
            return
        target = (float(target[0]), float(target[1]))
        if target != self._target:
            self._target = target
            self._clicked = False
        if button is not None:
            self._button = max(1, min(3, int(button)))

    # ------------------------------------------------------------------
    def read(self, now: float) -> VelocityFrame:
        if not self._opened:
            return VelocityFrame()
        dt = None if self._last_t is None else now - self._last_t
        self._last_t = now
        self._frames += 1
        if self._target is None or dt is None or dt <= 0.0:
            return VelocityFrame()

        dx = self._target[0] - self.x
        dy = self._target[1] - self.y
        distance = math.hypot(dx, dy)
        step = max(0.0, self.options.speed * dt)
        clicks: tuple[int, ...] = ()
        if distance <= max(step, 1e-9):
            self.x, self.y = self._target
            vx = dx / dt
            vy = dy / dt
            if not self._clicked:
                self._clicked = True
                clicks = (self._button,)
        else:
            vx = dx / distance * self.options.speed
            vy = dy / distance * self.options.speed
            self.x += vx * dt
            self.y += vy * dt
        return VelocityFrame((VelocitySample(now, vx, vy),), clicks)

    # ------------------------------------------------------------------
    def initial_position_norm(self) -> tuple[float, float]:
        return self.x, self.y

    def status(self) -> VelocitySourceStatus:
        return VelocitySourceStatus(
            name=self.name,
            category=self.capabilities.category,
            connected=self._opened,
            device={"speed": f"{self.options.speed:g}"},
            frames=self._frames,
            error=self._error,
        )
