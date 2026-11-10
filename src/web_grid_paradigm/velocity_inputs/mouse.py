"""Mouse strategy: the absolute OS pointer converted to velocity samples.

The mouse is an absolute device, so the interface still exposes velocity: the
source differentiates consecutive positions on the runner clock.  Because the
integrator integrates with the same sample timestamps, the round trip is
lossless (``pos + v * dt == pos``), which keeps mouse behaviour equivalent to
an absolute implementation.  Button edges are reported as clicks so the
paradigm can still offer click selection.

The device is injectable (``device=...``) so the strategy can be tested
without PsychoPy or a real window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.geometry import Layout
from .base import (
    DeviceContext,
    InitialPositionProvider,
    VelocityCapabilities,
    VelocityFrame,
    VelocitySample,
    VelocitySourceError,
    VelocitySourceStatus,
)
from .registry import register_velocity_source

# PsychoPy reports buttons as left, middle, right; the paradigm uses
# left=1, right=2, middle=3.
_MOUSE_BUTTONS = ((0, 1), (2, 2), (1, 3))

# Recenter the pointer before it reaches the physical window edge.  A pointer
# pinned at an edge produces no further position delta, which makes the cursor
# look stuck even though the user keeps moving the mouse.
_EDGE_MARGIN_FRACTION = 0.08


@dataclass(frozen=True, slots=True)
class MouseVelocityOptions:
    """Configuration of the mouse strategy."""

    visible: bool = True


@register_velocity_source("mouse")
class MouseVelocitySource(InitialPositionProvider):
    """Velocity samples and button edges derived from ``psychopy.event.Mouse``."""

    name = "mouse"
    capabilities = VelocityCapabilities(
        category="mouse", continuous=True, absolute=True, clicks=True
    )

    def __init__(
        self,
        *,
        options: MouseVelocityOptions | None = None,
        context: DeviceContext | None = None,
        device: Any | None = None,
    ) -> None:
        self.options = options or MouseVelocityOptions()
        self.context = context
        self._device = device
        self._opened = False
        self._last_norm: tuple[float, float] | None = None
        self._last_t: float | None = None
        self._prev_pressed: list[bool] = [False, False, False]
        self._frames = 0
        self._invalid = 0
        self._error: str | None = None

    # ------------------------------------------------------------------
    @property
    def layout(self) -> Layout:
        if self.context is None:
            raise VelocitySourceError("mouse source needs a DeviceContext")
        return self.context.layout

    def open(self) -> None:
        if self._opened:
            return
        if self.context is None:
            raise VelocitySourceError(
                "mouse source needs a DeviceContext with the window layout"
            )
        if self._device is None:
            if self.context.window is None:
                raise VelocitySourceError(
                    "mouse source needs an open PsychoPy window; "
                    "pass a DeviceContext with a window"
                )
            # Imported lazily so the input package stays importable headless.
            from psychopy import event

            self._device = event.Mouse(
                win=self.context.window, visible=self.options.visible
            )
        self._opened = True
        self.reset()

    def close(self) -> None:
        self._opened = False

    def reset(self) -> None:
        """Forget the position baseline and button edges (port opened)."""
        self._last_norm = None
        self._last_t = None
        self.reset_buttons()

    def center_pointer(self) -> None:
        """Warp the OS pointer to the window centre and restart the baseline.

        The cursor itself starts at the centre too; without warping, a pointer
        already resting at a screen edge would leave almost no room to move in
        that direction (the cursor appears to hit a wall).  The same warp is
        used when the pointer approaches an edge during a session.
        """
        if self._device is not None:
            setter = getattr(self._device, "setPos", None)
            if callable(setter):
                try:
                    setter((0, 0))
                except Exception as exc:  # noqa: BLE001 - backend edge case
                    self._invalid += 1
                    self._error = f"{type(exc).__name__}: {exc}"
        self._last_norm = None
        self._last_t = None

    def _near_window_edge(self, px: float, py: float) -> bool:
        margin_x = self.layout.window_w * _EDGE_MARGIN_FRACTION
        margin_y = self.layout.window_h * _EDGE_MARGIN_FRACTION
        return (
            abs(px) >= self.layout.window_w / 2 - margin_x
            or abs(py) >= self.layout.window_h / 2 - margin_y
        )

    def reset_buttons(self) -> None:
        """Forget button edges only (block start); keep tracking the pointer."""
        self._prev_pressed = [False, False, False]

    # ------------------------------------------------------------------
    def read(self, now: float) -> VelocityFrame:
        """Return at most one velocity sample plus any new button edges."""
        if not self._opened or self._device is None:
            return VelocityFrame()
        try:
            px, py = self._device.getPos()
        except Exception as exc:  # noqa: BLE001 - keep the frame loop alive
            self._invalid += 1
            self._error = f"{type(exc).__name__}: {exc}"
            return VelocityFrame()

        clicks = self._read_clicks()
        self._frames += 1
        norm = self.layout.px_to_norm(float(px), float(py))
        samples: tuple[VelocitySample, ...] = ()
        if self._last_norm is not None and self._last_t is not None:
            dt = now - self._last_t
            if dt > 0.0:
                vx = (norm[0] - self._last_norm[0]) / dt
                vy = (norm[1] - self._last_norm[1]) / dt
                samples = (VelocitySample(now, vx, vy),)
                self._last_norm = norm
                self._last_t = now
        else:
            self._last_norm = norm
            self._last_t = now
        if self._near_window_edge(float(px), float(py)):
            self.center_pointer()
        return VelocityFrame(samples=samples, clicks=clicks)

    def _read_clicks(self) -> tuple[int, ...]:
        getter = getattr(self._device, "getPressed", None)
        if getter is None:  # injected test doubles may be position-only
            return ()
        try:
            pressed = [bool(value) for value in getter()]
        except Exception as exc:  # noqa: BLE001 - backend focus edge case
            self._invalid += 1
            self._error = f"{type(exc).__name__}: {exc}"
            return ()
        if len(pressed) < len(self._prev_pressed):
            self._prev_pressed = [False] * len(pressed)
        previous = self._prev_pressed
        clicks = [
            button
            for index, button in _MOUSE_BUTTONS
            if index < len(pressed)
            and pressed[index]
            and not (index < len(previous) and previous[index])
        ]
        self._prev_pressed = pressed
        return tuple(clicks)

    # ------------------------------------------------------------------
    def initial_position_norm(self) -> tuple[float, float] | None:
        """Absolute starting position, so the integrator can sync to the mouse."""
        if self._device is None or self.context is None:
            return None
        try:
            return self.layout.px_to_norm(*self._device.getPos())
        except Exception:  # noqa: BLE001 - backend edge case
            return None

    def button_pressed(self) -> bool:
        """True while any mouse button is held (intro/exit screens)."""
        if self._device is None:
            return False
        getter = getattr(self._device, "getPressed", None)
        if getter is None:
            return False
        try:
            return any(bool(value) for value in getter())
        except Exception:  # noqa: BLE001 - backend focus edge case
            return False

    def status(self) -> VelocitySourceStatus:
        return VelocitySourceStatus(
            name=self.name,
            category=self.capabilities.category,
            connected=self._opened,
            device={"driver": "psychopy.event.Mouse"},
            last_rx=self._last_t,
            frames=self._frames,
            invalid=self._invalid,
            error=self._error,
        )
