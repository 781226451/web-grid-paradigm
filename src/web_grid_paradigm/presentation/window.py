"""PsychoPy window creation.

Kept apart from the stimuli so that the window (a global, exclusive resource)
is created in exactly one place and can be closed by its owner.
"""

from __future__ import annotations

from loguru import logger
from psychopy import logging as plog
from psychopy import visual

from ..core.config import ExperimentConfig
from .palette import BG


def create_window(config: ExperimentConfig) -> visual.Window:
    """Open the experiment window (fullscreen by default)."""
    size = (config.window_width, config.window_height)
    if config.fullscreen:
        try:
            import pyglet

            screens = pyglet.canvas.get_display().get_screens()
            screen = screens[min(max(config.screen, 0), len(screens) - 1)]
            size = (screen.width, screen.height)
        except Exception:  # noqa: BLE001 - backend fallback
            logger.debug("could not query the physical screen size")

    window = visual.Window(
        size=size,
        fullscr=config.fullscreen,
        screen=config.screen,
        units="pix",
        color=BG,
        allowGUI=False,
        winType="pyglet",
        checkTiming=False,
        title="BCI Web-Grid",
    )
    # PsychoPy buffers its own log entries; emit window-setup messages now
    # (routed to loguru by web_grid_paradigm.app.log) instead of at shutdown.
    plog.flush()
    logger.debug(
        "window opened: size={} fullscreen={}",
        tuple(int(v) for v in window.size),
        config.fullscreen,
    )
    return window
