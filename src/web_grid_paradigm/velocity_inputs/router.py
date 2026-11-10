"""Input facade: one strategy plus the velocity integrator.

The runner asks for ``(x, y, clicks)`` once per frame, exactly as before.  This
module owns the selected :class:`~web_grid_paradigm.velocity_inputs.base.VelocitySource`,
sets the demo target, integrates the returned velocity samples and exposes the
cursor position.  The render loop therefore never talks to a device or to a
concrete strategy.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..core.config import ExperimentConfig
from ..core.geometry import Layout
from ..core.session import Target
from .base import DeviceContext, VelocitySource
from .demo import DemoVelocityOptions
from .integrator import VelocityIntegrator
from .joystick import SerialJoystickVelocityOptions
from .lsl import LslVelocityOptions
from .mouse import MouseVelocityOptions
from .registry import build_velocity_source


class InputReader:
    """Cursor position, clicks and source lifecycle for the configured input."""

    def __init__(
        self,
        win: Any,
        layout: Layout,
        config: ExperimentConfig,
        *,
        source: VelocitySource | None = None,
    ) -> None:
        self.cfg = config
        self.layout = layout
        self.context = DeviceContext(layout=layout, window=win)
        self.source = source or self._build_source(config)
        try:
            self.source.open()
        except BaseException:
            self.source.close()
            raise
        self.integrator = VelocityIntegrator(layout)
        self._initial_synced = False
        logger.info(
            "input source: {} ({}), clicks={}",
            self.source.name,
            self.source.capabilities.category,
            self.source.capabilities.clicks,
        )

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_source(self, config: ExperimentConfig) -> VelocitySource:
        name = config.input
        if name == "mouse":
            options: Any = MouseVelocityOptions(visible=not config.hide_cursor)
        elif name == "demo":
            options = DemoVelocityOptions(speed=config.demo_speed)
        elif name == "joystick":
            options = SerialJoystickVelocityOptions(
                port=config.joystick_port,
                baud=config.joystick_baud,
                address=(
                    None if config.joystick_address == 0 else config.joystick_address
                ),
                stream_mode=config.joystick_stream_mode,
                stale_after=config.joystick_stale_after,
                speed_px_per_s=config.joystick_speed,
                invert_x=config.joystick_invert_x,
                invert_y=config.joystick_invert_y,
                deadzone=config.joystick_deadzone,
                center_on_open=config.joystick_center_on_open,
            )
        elif name == "lsl":
            options = LslVelocityOptions(
                stream_name=config.lsl_velocity_stream,
                stream_type=config.lsl_velocity_type,
                resolve_timeout=config.lsl_velocity_timeout,
                stale_after=config.lsl_velocity_stale_after,
            )
        else:  # pragma: no cover - config.validate() rejects unknown modes
            raise ValueError(f"unknown input source {name!r}")
        return build_velocity_source(name, options=options, context=self.context)

    # ------------------------------------------------------------------
    # cursor / frame API used by the runner
    # ------------------------------------------------------------------
    @property
    def cursor_px(self) -> tuple[float, float]:
        return self.integrator.position_px

    @cursor_px.setter
    def cursor_px(self, value: tuple[float, float]) -> None:
        self.integrator.set_position_px(*value)

    def center_cursor(self) -> None:
        """Put the cursor at the window centre and disable the initial sync.

        A session starts from the centre even for absolute devices (the mouse);
        subsequent movement is still relative to that centre.
        """
        self.integrator.set_position_norm(0.0, 0.0)
        self._initial_synced = True

    def read(
        self,
        now: float,
        target: Target | None,
    ) -> tuple[float, float, list[int]]:
        """One frame of cursor movement and button edges."""
        self._set_target(target)
        frame = self.source.read(now)
        self._sync_initial()
        self.integrator.update(frame, now)
        x, y = self.cursor_px
        return x, y, [int(button) for button in frame.clicks]

    def poll_cursor(self, now: float) -> tuple[float, float]:
        """Position only (countdown / rest); clicks are discarded."""
        self._set_target(None)
        frame = self.source.read(now)
        self._sync_initial()
        self.integrator.update(frame, now)
        return self.cursor_px

    def start_requested(self, now: float, keys: list[str]) -> bool:
        """Any deliberate input on the intro screen starts the session."""
        if "space" in keys or "return" in keys:
            return True
        self._set_target(None)
        frame = self.source.read(now)
        self._sync_initial()
        self.integrator.update(frame, now)
        if frame.clicks:
            return True
        pressed = getattr(self.source, "button_pressed", None)
        return bool(pressed()) if callable(pressed) else False

    def any_pressed(self) -> bool:
        """True while a selection button is held (used on the end screen)."""
        pressed = getattr(self.source, "button_pressed", None)
        return bool(pressed()) if callable(pressed) else False

    def reset_buttons(self) -> None:
        """Forget button edges when a block starts (keep cursor tracking)."""
        resetter = getattr(self.source, "reset_buttons", None)
        if callable(resetter):
            resetter()
        else:
            self.source.reset()

    def restart_autopilot(self) -> None:
        """Re-arm the demo autopilot after a block (no-op for real devices)."""
        self.source.reset()

    def close(self) -> None:
        self.source.close()

    def status(self) -> dict[str, Any]:
        snapshot = self.source.status()
        return {
            "name": snapshot.name,
            "category": snapshot.category,
            "connected": snapshot.connected,
            "device": dict(snapshot.device),
            "frames": snapshot.frames,
            "invalid": snapshot.invalid,
            "dropped": snapshot.dropped,
            "stale": snapshot.stale,
            "error": snapshot.error,
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _set_target(self, target: Target | None) -> None:
        setter = getattr(self.source, "set_target_norm", None)
        if not callable(setter):
            return
        if target is None:
            setter(None)
        else:
            setter(
                self.layout.px_to_norm(*target.centre_px),
                target.required_button,
            )

    def _sync_initial(self) -> None:
        if self._initial_synced:
            return
        getter = getattr(self.source, "initial_position_norm", None)
        if not callable(getter):
            return
        position = getter()
        if position is None:
            return
        self.integrator.set_position_norm(*position)
        self._initial_synced = True
