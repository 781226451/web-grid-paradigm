"""Grid geometry and target sequencing (no PsychoPy dependency)."""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass

# Layout constants for a centred, Neuralink-like line grid.
_MIN_CELL = 8
_MARGIN_FRACTION = 0.05


@dataclass(frozen=True, slots=True)
class Cell:
    """Zero-based grid cell."""

    row: int
    col: int

    @property
    def label(self) -> str:
        return f"r{self.row + 1}c{self.col + 1}"


@dataclass(frozen=True, slots=True)
class Layout:
    """Pixel geometry of a square, line-drawn grid inside a window.

    PsychoPy pixel coordinates have their origin at the window centre, ``+x``
    to the right and ``+y`` upwards.  The board is a dark square with light
    grid lines, centred in the window.
    """

    window_w: int
    window_h: int
    rows: int
    cols: int
    cell: int  # visible cell size, excluding the grid line
    pitch: int  # cell size including one grid line
    line: int  # grid line width
    left: float  # board outer left edge
    top: float  # board outer top edge
    board_w: float
    board_h: float
    margin: float

    # ------------------------------------------------------------------
    @classmethod
    def create(cls, window_w: int, window_h: int, rows: int, cols: int) -> Layout:
        if window_w <= 0 or window_h <= 0:
            raise ValueError("window size must be positive")
        if rows < 1 or cols < 1:
            raise ValueError("rows and cols must be >= 1")
        margin = max(16.0, min(window_w, window_h) * _MARGIN_FRACTION)
        avail_w = window_w - 2 * margin
        avail_h = window_h - 2 * margin
        line = max(1, round(min(window_w, window_h) * 0.0015))
        pitch = int((min(avail_w, avail_h) - line) // max(rows, cols))
        if pitch - line < _MIN_CELL:
            raise ValueError(
                "grid is too dense for this window; use a larger window, "
                "a smaller grid, or fullscreen"
            )
        board_w = cols * pitch + line
        board_h = rows * pitch + line
        left = -board_w / 2
        top = board_h / 2
        return cls(
            window_w=window_w,
            window_h=window_h,
            rows=rows,
            cols=cols,
            cell=pitch - line,
            pitch=pitch,
            line=line,
            left=left,
            top=top,
            board_w=board_w,
            board_h=board_h,
            margin=margin,
        )

    # ------------------------------------------------------------------
    @property
    def n_cells(self) -> int:
        return self.rows * self.cols

    @property
    def right(self) -> float:
        return self.left + self.board_w

    @property
    def bottom(self) -> float:
        return self.top - self.board_h

    @property
    def board_centre(self) -> tuple[float, float]:
        return 0.0, 0.0

    def centre_px(self, cell: Cell) -> tuple[float, float]:
        self._check_cell(cell)
        x = self.left + self.line + cell.col * self.pitch + self.cell / 2
        y = self.top - self.line - cell.row * self.pitch - self.cell / 2
        return x, y

    def rect_px(self, cell: Cell) -> tuple[float, float, float, float]:
        """Return ``(x, y, width, height)`` ready for a PsychoPy Rect."""
        x, y = self.centre_px(cell)
        return x, y, float(self.cell), float(self.cell)

    def cell_at_px(self, x: float, y: float) -> Cell | None:
        """Hit-test a pixel coordinate against the board.

        Grid lines belong to the cell to their right/below, matching the
        canvas hit-testing of the Neuralink-style board.  Points outside the
        board return ``None``.
        """
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        if not (self.left <= x <= self.right and self.bottom <= y <= self.top):
            return None
        col = int((x - self.left) // self.pitch)
        row = int((self.top - y) // self.pitch)
        col = min(self.cols - 1, max(0, col))
        row = min(self.rows - 1, max(0, row))
        return Cell(row, col)

    # ------------------------------------------------------------------
    def norm_to_px(self, nx: float, ny: float) -> tuple[float, float]:
        """Map BCI coordinates in [-1, 1] (y up) to window pixels."""
        return nx * self.window_w / 2, ny * self.window_h / 2

    def px_to_norm(self, x: float, y: float) -> tuple[float, float]:
        return 2 * x / self.window_w, 2 * y / self.window_h

    def clamp_norm(self, nx: float, ny: float) -> tuple[float, float]:
        return min(1.0, max(-1.0, nx)), min(1.0, max(-1.0, ny))

    # ------------------------------------------------------------------
    def _check_cell(self, cell: Cell) -> None:
        if not (0 <= cell.row < self.rows and 0 <= cell.col < self.cols):
            raise IndexError(f"cell {cell} outside {self.rows}x{self.cols} grid")

    def iter_cells(self) -> Iterator[Cell]:
        for row in range(self.rows):
            for col in range(self.cols):
                yield Cell(row, col)


class TargetBag:
    """Shuffled-bag target sequence with no immediate repeats.

    Every cell is shown once per bag, which keeps spatial coverage balanced
    across short blocks instead of relying on independent random draws.
    """

    def __init__(self, rows: int, cols: int, rng: random.Random | None = None) -> None:
        self.rows = rows
        self.cols = cols
        self.rng = rng or random.Random()
        self._bag: list[Cell] = []
        self._last: Cell | None = None

    def _refill(self) -> None:
        self._bag = [Cell(r, c) for r in range(self.rows) for c in range(self.cols)]
        self.rng.shuffle(self._bag)

    def next(self, avoid: Cell | None = None) -> Cell:
        if not self._bag:
            self._refill()
            avoid = avoid or self._last
            # The pop below comes from the end of the bag, so move the avoided
            # cell away from the end rather than to it.
            if avoid is not None and len(self._bag) > 1 and self._bag[-1] == avoid:
                self._bag[-1], self._bag[0] = self._bag[0], self._bag[-1]
        cell = self._bag.pop()
        self._last = cell
        return cell

    def __len__(self) -> int:
        return len(self._bag)
