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

On Windows the position is read from ``GetCursorPos`` every frame instead of
Pyglet's event cache, which can lag or freeze during a fast flick and make the
cursor appear to hit a wall before jumping.  Other platforms keep PsychoPy's
mouse position.  Before the one-time centring warp, :class:`WindowsFocus`
brings the experiment window to the foreground: a background process cannot
move the pointer with ``SetCursorPos``.

The device is injectable (``device=...``) so the strategy can be tested
without PsychoPy or a real window.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from loguru import logger

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

try:  # Windows-only adapters; keep this package importable on other platforms.
    from .windows_focus import WindowsFocus
    from .windows_pointer import WindowsPointer
except Exception:  # pragma: no cover - non-Windows fallback
    WindowsFocus = None  # type: ignore[assignment]
    WindowsPointer = None  # type: ignore[assignment]

# PsychoPy reports buttons as left, middle, right; the paradigm uses
# left=1, right=2, middle=3.
_MOUSE_BUTTONS = ((0, 1), (2, 2), (1, 3))


def _window_handles(window: Any) -> tuple[int, ...]:
    """All usable native handles, preferring the rendering view then the top level."""
    handle = getattr(window, "winHandle", None)
    found: list[int] = []
    for candidate in (
        getattr(handle, "_view_hwnd", None),
        getattr(handle, "_hwnd", None),
        getattr(window, "_hw_handle", None),
        getattr(window, "_hwnd", None),
    ):
        if not candidate:
            continue
        value = getattr(candidate, "value", candidate)
        try:
            hwnd = int(value)
        except (TypeError, ValueError):
            continue
        if hwnd and hwnd not in found:
            found.append(hwnd)
    return tuple(found)


def _window_handle(window: Any) -> int | None:
    """Return the preferred native window handle for pointer mapping."""
    handles = _window_handles(window)
    return handles[0] if handles else None


def _focus_handle(window: Any) -> int | None:
    """Return the top-level handle used to bring the experiment forward."""
    handle = getattr(window, "winHandle", None)
    for candidate in (
        getattr(handle, "_hwnd", None),
        getattr(window, "_hw_handle", None),
        getattr(window, "_hwnd", None),
    ):
        if not candidate:
            continue
        value = getattr(candidate, "value", candidate)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


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
        self._pointer: Any | None = None
        self._focus: Any | None = None
        self._pointer_attempts = 0
        self._focus_attempts = 0
        self._native_failures = 0
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
        self._pointer = self._create_native_pointer()
        self._focus = self._create_focus()
        logger.info(
            "mouse input: position={} focus={}",
            "win32.GetCursorPos" if self._pointer else "psychopy.event.Mouse",
            "win32" if self._focus else "none",
        )
        self.reset()

    def _create_native_pointer(self) -> Any | None:
        """Use Win32 ``GetCursorPos`` when available.

        Pyglet's ``_mouse_x/_mouse_y`` cache is updated only when a mouse
        message is dispatched.  During a fast flick the cache can lag or stop
        updating at the client edge, which looks like a wall followed by a
        jump.  Reading the OS pointer directly every frame keeps the cursor
        on the real pointer position, including outside the client area.
        """
        if WindowsPointer is None or sys.platform != "win32":
            return None
        if self.context is None or self.context.window is None:
            return None
        last_error: Exception | None = None
        for hwnd in _window_handles(self.context.window):
            try:
                pointer = WindowsPointer(hwnd, self.layout)
                # A handle can be a valid HWND but have no usable client area
                # (first frame / hidden view).  Validate before using it,
                # otherwise every read silently falls back to Pyglet's cache.
                pointer.getPos()
                return pointer
            except Exception as exc:  # noqa: BLE001 - try the next handle
                last_error = exc
        if last_error is not None:
            self._invalid += 1
            self._error = f"{type(last_error).__name__}: {last_error}"
        return None

    def _create_focus(self) -> Any | None:
        """Create the Windows foreground handoff used before centring.

        A background process cannot move the cursor with ``SetCursorPos`` on
        Windows; the experiment window must first become the foreground
        window.  Without this the first WebUI launch (browser still in front)
        can retry forever and time out.
        """
        if WindowsFocus is None or sys.platform != "win32":
            return None
        if self.context is None or self.context.window is None:
            return None
        hwnd = _focus_handle(self.context.window)
        if hwnd is None:
            return None
        try:
            return WindowsFocus(hwnd)
        except Exception as exc:  # noqa: BLE001 - centring will retry
            self._invalid += 1
            self._error = f"{type(exc).__name__}: {exc}"
            return None

    def _position_px(self) -> tuple[float, float]:
        """Current pointer position in layout pixels."""
        self._ensure_native_adapters()
        if self._pointer is not None:
            try:
                px, py = self._pointer.getPos()
                self._native_failures = 0
                return px, py
            except Exception as exc:  # noqa: BLE001 - fall back per frame
                self._invalid += 1
                self._error = f"{type(exc).__name__}: {exc}"
                self._native_failures += 1
                if self._native_failures >= 2:
                    logger.warning(
                        "native mouse position unavailable ({}); using PsychoPy",
                        exc,
                    )
                    self._pointer = None
                    self._native_failures = 0
        if self._device is None:
            raise VelocitySourceError("mouse source has no open device")
        return self._device.getPos()

    def _ensure_native_adapters(self) -> None:
        """Retry the Windows adapters after the window has been shown.

        ``open()`` runs before the first buffer swap.  On the first window of
        a process the native handle or client area can still be unavailable at
        that point; retrying here, after ``win.flip()``, keeps positions and
        the focus handoff native instead of silently falling back to Pyglet's
        event cache.
        """
        if self._pointer is None and self._pointer_attempts < 3:
            self._pointer_attempts += 1
            self._pointer = self._create_native_pointer()
        if self._focus is None and self._focus_attempts < 3:
            self._focus_attempts += 1
            self._focus = self._create_focus()

    def close(self) -> None:
        self._opened = False
        self._pointer = None
        self._focus = None

    def reset(self) -> None:
        """Forget button edges (the cursor position is absolute)."""
        self.reset_buttons()

    def center_pointer(self) -> bool:
        """Move the OS pointer to the window centre.

        The cursor is absolute, so this is the only time the pointer is
        warped: it aligns the physical pointer with the centred cursor at the
        start of a session.  No periodic re-centring happens afterwards.

        Returns ``False`` when the warp call itself fails.  The facade then
        reads an absolute frame and verifies the resulting cursor position;
        a successful call here does not by itself prove the pointer landed at
        the centre.
        """
        self._ensure_native_adapters()
        if self._focus is not None:
            try:
                if not self._focus.acquire():
                    self._error = (
                        "could not bring the experiment window to the foreground"
                    )
                    return False
                if self.context is not None and self.context.window is not None:
                    handle = getattr(self.context.window, "winHandle", None)
                    dispatch = getattr(handle, "dispatch_events", None)
                    if callable(dispatch):
                        try:
                            dispatch()
                        except Exception as exc:  # noqa: BLE001 - focus is enough
                            logger.debug(
                                "could not dispatch activation events: {}", exc
                            )
            except Exception as exc:  # noqa: BLE001 - retried by the facade
                self._invalid += 1
                self._error = f"{type(exc).__name__}: {exc}"
                return False
        if self._pointer is not None:
            try:
                self._pointer.setPos((0.0, 0.0))
            except Exception as exc:  # noqa: BLE001 - retried by the facade
                self._invalid += 1
                self._error = f"{type(exc).__name__}: {exc}"
                return False
            return True
        if self._device is not None:
            setter = getattr(self._device, "setPos", None)
            if callable(setter):
                try:
                    setter((0, 0))
                except Exception as exc:  # noqa: BLE001 - retried by the facade
                    self._invalid += 1
                    self._error = f"{type(exc).__name__}: {exc}"
                    return False
                return True
        return False

    def reset_buttons(self) -> None:
        """Forget button edges only (block start); keep tracking the pointer."""
        self._prev_pressed = [False, False, False]

    # ------------------------------------------------------------------
    def read(self, now: float) -> VelocityFrame:
        """Return the pointer's absolute position plus any new button edges."""
        if not self._opened or self._device is None:
            return VelocityFrame()
        try:
            px, py = self._position_px()
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
        if self.context is None:
            return None
        try:
            return self.layout.px_to_norm(*self._position_px())
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
            device={
                "driver": (
                    "win32.GetCursorPos"
                    if self._pointer is not None
                    else "psychopy.event.Mouse"
                )
            },
            last_rx=self._last_read,
            frames=self._frames,
            invalid=self._invalid,
            error=self._error,
        )
