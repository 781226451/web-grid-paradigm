"""Input facade: one strategy plus the cursor integrator.

The runner asks for ``(x, y, clicks)`` once per frame, exactly as before.  This
module owns the selected :class:`~web_grid_paradigm.velocity_inputs.base.VelocitySource`,
sets the demo target, applies either the returned velocity samples or an
absolute cursor position and exposes the cursor position.  The render loop
therefore never talks to a device or to a concrete strategy.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ..core.config import ExperimentConfig
from ..core.geometry import Layout
from ..core.session import Target
from .base import DeviceContext, VelocityFrame, VelocitySource
from .demo import DemoVelocityOptions
from .integrator import VelocityIntegrator
from .joystick import SerialJoystickVelocityOptions
from .lsl import LslVelocityOptions
from .mouse import MouseVelocityOptions
from .registry import build_velocity_source

_CENTER_TOLERANCE_PX = 2.0


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

    def center_cursor(self, now: float | None = None) -> bool:
        """Put the cursor at the window centre and confirm the source.

        Returns ``False`` when the source could not move the pointer or, when
        ``now`` is given, when the next absolute frame does not report the
        cursor at the centre.  The runner retries before starting the countdown
        instead of silently beginning the session at an offset.
        """
        self.integrator.set_position_norm(0.0, 0.0)
        self._initial_synced = True
        center_pointer = getattr(self.source, "center_pointer", None)
        if not callable(center_pointer):
            return True
        try:
            result = center_pointer()
        except Exception as exc:  # noqa: BLE001 - retried by the runner
            logger.debug("cursor centring attempt failed: {}", exc)
            return False
        if result is False:
            return False
        if now is None:
            return True
        try:
            frame = self.source.read(now)
        except Exception as exc:  # noqa: BLE001 - retried by the runner
            logger.debug("could not read the cursor after centring: {}", exc)
            return False
        if frame.position is None:
            return False
        self._apply_frame(frame, now)
        x, y = self.cursor_px
        return abs(x) <= _CENTER_TOLERANCE_PX and abs(y) <= _CENTER_TOLERANCE_PX

    def read(
        self,
        now: float,
        target: Target | None,
    ) -> tuple[float, float, list[int]]:
        """One frame of cursor movement and button edges."""
        self._set_target(target)
        frame = self.source.read(now)
        self._sync_initial()
        self._apply_frame(frame, now)
        x, y = self.cursor_px
        return x, y, [int(button) for button in frame.clicks]

    def poll_cursor(self, now: float) -> tuple[float, float]:
        """Position only (countdown / rest); clicks are discarded."""
        self._set_target(None)
        frame = self.source.read(now)
        self._sync_initial()
        self._apply_frame(frame, now)
        return self.cursor_px

    def start_requested(self, now: float, keys: list[str]) -> bool:
        """Any deliberate input on the intro screen starts the session."""
        if "space" in keys or "return" in keys:
            return True
        self._set_target(None)
        frame = self.source.read(now)
        self._sync_initial()
        self._apply_frame(frame, now)
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
    def _apply_frame(self, frame: VelocityFrame, now: float) -> None:
        """Apply one source frame: absolute position or integrated velocity."""
        if frame.position is not None:
            self.integrator.set_position_norm(*frame.position)
        else:
            self.integrator.update(frame, now)

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
