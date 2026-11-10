"""Pixel-level smoke tests for every visual theme.

These are semantic checks, not golden-image diffs: the background, one grid
line, the target and the cursor must use the colours declared by the theme.
That catches the most common theme regression (a partial palette swap) without
becoming brittle across GPU/font/anti-aliasing differences.
"""

from __future__ import annotations

import os
import sys

import pytest
from PIL import Image, ImageColor

from web_grid_paradigm.app.runner import WebGridApp
from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.presentation.themes import get_theme
from web_grid_paradigm.recording.markers import NullMarkerSink

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("theme visual tests require a display", allow_module_level=True)


def _pixel(image: Image.Image, layout, x: float, y: float) -> tuple[int, int, int]:
    px = int(round(x + layout.window_w / 2))
    py = int(round(layout.window_h / 2 - y))
    return image.getpixel((px, py))


def _assert_colour_near(
    image: Image.Image,
    layout,
    x: float,
    y: float,
    expected: str,
    *,
    tolerance: int = 4,
    radius: int = 3,
) -> None:
    """Allow a few pixels of rounding/anti-aliasing around a thin line."""
    centre_x = int(round(x + layout.window_w / 2))
    centre_y = int(round(layout.window_h / 2 - y))
    wanted = ImageColor.getrgb(expected)
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            actual = image.getpixel((centre_x + dx, centre_y + dy))
            if all(abs(a - b) <= tolerance for a, b in zip(actual, wanted)):
                return
    actual = _pixel(image, layout, x, y)
    raise AssertionError(
        f"no pixel near ({x}, {y}) matched {expected}; centre is {actual}"
    )


def _assert_colour(
    actual: tuple[int, int, int],
    expected: str | tuple[int, int, int],
    tolerance: int = 4,
) -> None:
    wanted = ImageColor.getrgb(expected) if isinstance(expected, str) else expected
    assert all(
        abs(a - b) <= tolerance for a, b in zip(actual, wanted)
    ), f"got {actual}, expected {wanted}"


@pytest.mark.parametrize("theme_name", ["dark", "classic"])
def test_theme_renders_its_declared_colours(tmp_path, theme_name: str) -> None:
    theme = get_theme(theme_name)
    config = ExperimentConfig(
        theme=theme_name,
        input="demo",
        fullscreen=False,
        window_width=320,
        window_height=240,
        rows=4,
        cols=4,
        click_types=1,
        reward="off",
        skip_instructions=True,
    )
    app = WebGridApp(config, recorder=None, marker_sink=NullMarkerSink())
    try:
        path = app.render_preview(tmp_path / f"{theme_name}.png")
        image = Image.open(path).convert("RGB")
        layout = app.layout

        # Window background outside the board.
        _assert_colour(_pixel(image, layout, 2, 2), theme.background)
        # The leftmost vertical grid line.
        _assert_colour_near(
            image, layout, layout.left + layout.line / 2, 0, theme.grid
        )
        # A point inside the target, away from the cursor.  Classic draws a
        # translucent overlay over the target while the cursor is inside it.
        target = app.engine.target
        assert target is not None
        target_x, target_y = target.centre_px
        target_expected: str | tuple[int, int, int] = theme.target_colors[1]
        if theme.target_overlay:
            base = ImageColor.getrgb(theme.target_colors[1])
            overlay = ImageColor.getrgb(theme.target_overlay_color)
            alpha = theme.target_overlay_opacity
            target_expected = tuple(
                round(base[i] * (1 - alpha) + overlay[i] * alpha)
                for i in range(3)
            )
        _assert_colour(
            _pixel(image, layout, target_x + layout.cell * 0.25, target_y),
            target_expected,
        )
        # Cursor centre (drawn last, so it must win over glow/target).
        cursor_x, cursor_y = app.input.cursor_px
        _assert_colour(
            _pixel(image, layout, cursor_x, cursor_y),
            theme.cursor,
        )
    finally:
        app.close()
