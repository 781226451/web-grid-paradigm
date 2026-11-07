"""Mouse strategy: the absolute OS pointer converted to velocity samples.

The mouse is an absolute device, so the interface still exposes velocity:
the source differentiates consecutive positions on the runner clock.  Because
the integrator integrates with the same sample timestamps, the round trip is
lossless (``pos + v * dt == pos``), which keeps mouse behaviour equivalent to
the previous absolute implementation.

The device is injectable (``device=...``) so the strategy can be tested
without PsychoPy or a real window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..geometry import Layout
from .base import (
    ButtonEvent,
    Capabilities,
    DeviceContext,
    InitialPositionProvider,
    InputRead,
    InputSample,
    InputSourceError,
    SourceStatus,
)
from .registry import register_source

# PsychoPy reports mouse buttons as left, middle, right; the paradigm uses
# left=1, right=2, middle=3.
_MOUSE_BUTTONS = ((0, 1), (2, 2), (1, 3))


@dataclass(frozen=True, slots=True)
class MouseOptions:
    """Configuration of the mouse strategy."""

    visible: bool = True


@register_source("mouse")
class MouseSource(InitialPositionProvider):
    """Velocity samples derived from PsychoPy's ``event.Mouse``."""

    name = "mouse"
    capabilities = Capabilities(
        category="mouse", continuous=True, absolute=True, n_buttons=3
    )

    def __init__(
        self,
        *,
        options: MouseOptions | None = None,
        context: DeviceContext | None = None,
        device: Any | None = None,
    ) -> None:
        self.options = options or MouseOptions()
        self.context = context
        self._device = device
        self._opened = False
        self._last_norm: tuple[float, float] | None = None
        self._last_t: float | None = None
        self._prev_pressed: tuple[bool, ...] = ()
        self._frames = 0
        self._invalid = 0
        self._error: str | None = None

    # ------------------------------------------------------------------
    @property
    def layout(self) -> Layout:
        if self.context is None:
            raise InputSourceError("mouse source needs a DeviceContext")
        return self.context.layout

    def open(self) -> None:
        if self._opened:
            return
        if self._device is None:
            if self.context is None or self.context.window is None:
                raise InputSourceError(
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
        """Forget position baseline and button edges (block/trial start)."""
        self._last_norm = None
        self._last_t = None
        self._prev_pressed = ()
        if self._device is not None:
            try:
                self._prev_pressed = tuple(
                    bool(v) for v in self._device.getPressed()
                )
            except Exception:  # noqa: BLE001 - device backend edge case
                self._prev_pressed = ()

    # ------------------------------------------------------------------
    def read(self, now: float) -> InputRead:
        """Return at most one velocity sample and any new button edges."""
        if not self._opened or self._device is None:
            return InputRead()
        try:
            px, py = self._device.getPos()
            pressed = tuple(bool(v) for v in self._device.getPressed())
        except Exception as exc:  # noqa: BLE001 - keep the frame loop alive
            self._invalid += 1
            self._error = f"{type(exc).__name__}: {exc}"
            return InputRead()

        self._frames += 1
        norm = self.layout.px_to_norm(float(px), float(py))
        samples: tuple[InputSample, ...] = ()
        if self._last_norm is not None and self._last_t is not None:
            dt = now - self._last_t
            if dt > 0.0:
                vx = (norm[0] - self._last_norm[0]) / dt
                vy = (norm[1] - self._last_norm[1]) / dt
                samples = (InputSample(now, vx, vy),)
                self._last_norm = norm
                self._last_t = now
        else:
            self._last_norm = norm
            self._last_t = now

        buttons: list[ButtonEvent] = []
        previous = (
            self._prev_pressed
            if len(self._prev_pressed) == len(pressed)
            else (False,) * len(pressed)
        )
        for index, button in _MOUSE_BUTTONS:
            if index < len(pressed) and pressed[index] and not previous[index]:
                buttons.append(ButtonEvent(button, now))
        self._prev_pressed = pressed
        return InputRead(samples=samples, buttons=tuple(buttons))

    # ------------------------------------------------------------------
    def initial_position_norm(self) -> tuple[float, float] | None:
        """Absolute starting position, so the integrator can sync to the mouse."""
        if self._device is None:
            return None
        try:
            return self.layout.px_to_norm(*self._device.getPos())
        except Exception:  # noqa: BLE001 - backend edge case
            return None

    def status(self) -> SourceStatus:
        return SourceStatus(
            name=self.name,
            category=self.capabilities.category,
            connected=self._opened,
            device={"driver": "psychopy.event.Mouse"},
            last_rx=self._last_t,
            frames=self._frames,
            invalid=self._invalid,
            error=self._error,
        )
