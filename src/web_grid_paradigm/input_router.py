"""Input devices: turn mouse / keyboard / UDP / autopilot into a cursor.

The runner asks for ``(x, y, clicks)`` once per frame; this module owns the
device handles and the per-device quirks (button ordering, key mapping,
smoothing), so the render loop stays device-agnostic.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from psychopy import event

from .config import ExperimentConfig
from .geometry import Layout
from .inputs import AutoPilot, UdpCursorSource
from .session import Target

# PsychoPy reports buttons as left, middle, right; the paradigm uses
# left=1, right=2, middle=3.
_MOUSE_BUTTONS = ((0, 1), (2, 2), (1, 3))
_KEY_BUTTONS = (("1", 1), ("2", 2), ("3", 3))


class InputReader:
    """Cursor position and clicks for the configured input source."""

    def __init__(self, win: Any, layout: Layout, config: ExperimentConfig) -> None:
        self.cfg = config
        self.layout = layout
        self.mouse = event.Mouse(win=win, visible=not config.hide_cursor)
        self._prev_mouse = [False, False, False]
        self._cursor_px: tuple[float, float] = (0.0, 0.0)
        self._auto = (
            AutoPilot(config.demo_speed) if config.input == "demo" else None
        )
        self._udp = (
            UdpCursorSource(config.udp_host, config.udp_port, config.smoothing)
            if config.input == "udp"
            else None
        )

    # ------------------------------------------------------------------
    @property
    def cursor_px(self) -> tuple[float, float]:
        return self._cursor_px

    @cursor_px.setter
    def cursor_px(self, value: tuple[float, float]) -> None:
        self._cursor_px = (float(value[0]), float(value[1]))

    def restart_autopilot(self) -> None:
        """Fresh autopilot state so that a repeated target is clicked again."""
        if self._auto is not None:
            self._auto = AutoPilot(
                self.cfg.demo_speed, self.layout.px_to_norm(*self._cursor_px)
            )

    def reset_buttons(self) -> None:
        """Forget button edges (e.g. when a block starts)."""
        self._prev_mouse = [bool(v) for v in self.mouse.getPressed()]

    # ------------------------------------------------------------------
    def read(
        self, now: float, dt: float, keys: list[str], target: Target | None
    ) -> tuple[float, float, list[int]]:
        """One frame of cursor movement and button presses."""
        clicks: list[int] = []
        x, y = self._cursor_px
        width, height = self.layout.window_w, self.layout.window_h

        if self.cfg.input == "mouse":
            x, y = self._mouse_position()
            pressed = [bool(v) for v in self.mouse.getPressed()]
            for index, button in _MOUSE_BUTTONS:
                if (
                    button <= self.cfg.click_types
                    and pressed[index]
                    and not self._prev_mouse[index]
                ):
                    clicks.append(button)
            self._prev_mouse = pressed
        elif self.cfg.input == "keyboard":
            x, y = self._keyboard_position(x, y, keys, clicks)
        elif self.cfg.input == "udp" and self._udp is not None:
            state = self._udp.poll(now)
            if state is not None:
                self.cursor_px = self.layout.norm_to_px(state.x, state.y)
                clicks.extend(state.clicks)
            x, y = self._cursor_px
        elif self.cfg.input == "demo" and self._auto is not None and target is not None:
            nx, ny = self.layout.px_to_norm(*target.centre_px)
            state = self._auto.poll(dt, (nx, ny))
            self.cursor_px = self.layout.norm_to_px(state.x, state.y)
            if state.clicks:
                clicks.append(target.required_button)
            x, y = self._cursor_px

        x = min(width / 2, max(-width / 2, float(x)))
        y = min(height / 2, max(-height / 2, float(y)))
        self._cursor_px = (x, y)
        return (
            x,
            y,
            [button for button in clicks if 1 <= button <= self.cfg.click_types],
        )

    def poll_cursor(self, now: float) -> tuple[float, float]:
        """Position only (countdown / rest); buttons are still flushed."""
        if self.cfg.input == "mouse":
            self.cursor_px = self._mouse_position()
            self._prev_mouse = [bool(v) for v in self.mouse.getPressed()]
        elif self.cfg.input == "udp" and self._udp is not None:
            state = self._udp.poll(now)
            if state is not None:
                self.cursor_px = self.layout.norm_to_px(state.x, state.y)
        return self._cursor_px

    def start_requested(self, now: float, keys: list[str]) -> bool:
        """Any deliberate input on the intro screen starts the session."""
        if "space" in keys or "return" in keys:
            return True
        pressed = [bool(v) for v in self.mouse.getPressed()]
        self._prev_mouse = pressed
        if any(pressed):
            return True
        if self.cfg.input == "udp" and self._udp is not None:
            state = self._udp.poll(now)
            if state is not None:
                self.cursor_px = self.layout.norm_to_px(state.x, state.y)
                return bool(state.clicks)
        return False

    def close(self) -> None:
        if self._udp is not None:
            self._udp.close()

    # ------------------------------------------------------------------
    def _mouse_position(self) -> tuple[float, float]:
        try:
            return self.mouse.getPos()
        except Exception:  # noqa: BLE001 - backend focus edge case
            logger.debug("mouse position unavailable; keeping the last position")
            return self._cursor_px

    def _keyboard_position(
        self,
        x: float,
        y: float,
        keys: list[str],
        clicks: list[int],
    ) -> tuple[float, float]:
        step_x = self.cfg.keyboard_step * self.layout.window_w / 2
        step_y = self.cfg.keyboard_step * self.layout.window_h / 2
        if "left" in keys:
            x -= step_x
        if "right" in keys:
            x += step_x
        if "up" in keys:
            y += step_y
        if "down" in keys:
            y -= step_y
        if "space" in keys or "return" in keys:
            clicks.append(1)
        for key, button in _KEY_BUTTONS:
            if key in keys:
                clicks.append(button)
        return x, y
