"""Colour palette and glow effect constants for the paradigm window.

The dark blue/red palette and the cursor/target glow follow the
``CursorTasks_namedpipe`` visuals (``conf/visuals.yaml``): a near-black blue
canvas, a red cursor and a blue target.  Targets keep one colour per click
type so the multi-button modes remain distinguishable.
"""

from __future__ import annotations

# Canvas and chrome.
BG = "#050D19"
PANEL = "#0A1422"
PANEL_EDGE = "#1E3A5F"
GRID = "#FFFFFF"
TEXT = "#EAF2FF"
MUTED = "#8FA6C4"
ACCENT = "#469EFF"
ERROR = "#FF6B6B"
HOVER = "#0F2238"

# Cursor.
CURSOR = "#F4474D"
CURSOR_GLOW = "#F4474D"
CURSOR_FLASH = "#FFFFFF"

# Target rings/glow.
TARGET_RING = "#D6E6FF"

# Glow and ribbon effect parameters (visuals.yaml).
CURSOR_GLOW_RADIUS_FACTOR = 3.2
CURSOR_GLOW_OPACITY = 0.30
CURSOR_RING_RADIUS_FACTOR = 1.5
CURSOR_RING_OPACITY = 0.45
CURSOR_RING_WIDTH_PX = 1.0
TARGET_GLOW_RADIUS_FACTOR = 2.8
TARGET_GLOW_OPACITY = 0.18
TARGET_RING_RADIUS_FACTOR = 1.35
TARGET_RING_OPACITY = 0.22
TARGET_RING_WIDTH_PX = 1.0
TARGET_PULSATE_SCALE = 1.15
TRAIL_SEGMENTS = 24
TRAIL_DURATION_S = 0.9

# Targets are colour-coded by the button they require.
TARGET_COLORS = {1: "#469EFF", 2: "#FFB340", 3: "#C77DFF"}
