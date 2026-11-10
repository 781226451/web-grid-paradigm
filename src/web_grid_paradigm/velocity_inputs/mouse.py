"""Mouse strategy: the absolute OS pointer mapped to the cursor.

The mouse is an absolute device, so every frame reports where the OS pointer
is, in normalised window units, through :attr:`VelocityFrame.position`.  The
facade applies that position directly, so the cursor and the pointer stay in
the same coordinate frame: no differentiation, no accumulated drift and no
periodic re-centring.  Button edges are reported as clicks so the paradigm
can still offer click selection.

The OS pointer itself is moved only once, when a session starts
(:meth:`MouseVelocitySource.center_pointer`), so the cursor begins at the
window centre.  During the session the pointer is never warped: when it
reaches the window edge the cursor simply stops there, and moving back moves
the cursor back immediately.

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
    VelocitySourceError,
    VelocitySourceStatus,
)
from .registry import register_velocity_source

# PsychoPy reports buttons as left, middle, right; the paradigm uses
# left=1, right=2, middle=3.
_MOUSE_BUTTONS = ((0, 1), (2, 2), (1, 3))


@dataclass(frozen=True, slots=True)
class MouseVelocityOptions:
    """Configuration of the mouse strategy."""

    visible: bool = True


@register_velocity_source("mouse")
class MouseVelocitySource(InitialPositionProvider):
    """Absolute pointer position and button edges from ``psychopy.event.Mouse``."""

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
        self._last_read: float | None = None
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
        """Forget button edges (the cursor position is absolute)."""
        self.reset_buttons()

    def center_pointer(self) -> None:
        """Move the OS pointer to the window centre (session start only).

        The cursor is absolute, so this is the only time the pointer is
        warped: it aligns the physical pointer with the centred cursor at the
        start of a session.  No periodic re-centring happens afterwards.
        """
        if self._device is not None:
            setter = getattr(self._device, "setPos", None)
            if callable(setter):
                try:
                    setter((0, 0))
                except Exception as exc:  # noqa: BLE001 - backend edge case
                    self._invalid += 1
                    self._error = f"{type(exc).__name__}: {exc}"

    def reset_buttons(self) -> None:
        """Forget button edges only (block start); keep tracking the pointer."""
        self._prev_pressed = [False, False, False]

    # ------------------------------------------------------------------
    def read(self, now: float) -> VelocityFrame:
        """Return the pointer's absolute position plus any new button edges."""
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
        self._last_read = now
        norm = self.layout.px_to_norm(float(px), float(py))
        return VelocityFrame(position=norm, clicks=clicks)

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
        """Absolute starting position reported to the facade at session start."""
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
            last_rx=self._last_read,
            frames=self._frames,
            invalid=self._invalid,
            error=self._error,
        )
