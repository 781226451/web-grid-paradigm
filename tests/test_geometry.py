from __future__ import annotations

import random

import pytest

from web_grid_paradigm.core.geometry import Cell, Layout, TargetBag


def test_layout_cells_are_square_and_inside_window() -> None:
    layout = Layout.create(1280, 800, 12, 12)
    assert layout.cell >= 8
    assert layout.board_w == pytest.approx(12 * layout.pitch + layout.line)
    assert layout.board_h == pytest.approx(12 * layout.pitch + layout.line)
    assert layout.left >= -layout.window_w / 2
    assert layout.right <= layout.window_w / 2
    assert layout.top <= layout.window_h / 2
    assert layout.bottom >= -layout.window_h / 2
    for cell in layout.iter_cells():
        x, y, w, h = layout.rect_px(cell)
        assert w == layout.cell and h == layout.cell
        assert layout.left <= x - w / 2
        assert x + w / 2 <= layout.right
        assert layout.bottom <= y - h / 2
        assert y + h / 2 <= layout.top
        assert layout.cell_at_px(x, y) == cell


def test_hit_testing_maps_grid_lines_and_outside_correctly() -> None:
    layout = Layout.create(1000, 700, 4, 4)
    x0, y0 = layout.centre_px(Cell(0, 0))
    x1, _ = layout.centre_px(Cell(0, 1))
    midpoint = layout.cell_at_px((x0 + x1) / 2, y0)
    assert midpoint in {Cell(0, 0), Cell(0, 1)}
    assert layout.cell_at_px(layout.right + layout.pitch, y0) is None
    assert layout.cell_at_px(x0, layout.top + layout.pitch) is None
    assert layout.cell_at_px(float("nan"), y0) is None


def test_normalised_coordinates_round_trip() -> None:
    layout = Layout.create(1280, 800, 12, 12)
    assert layout.norm_to_px(0.0, 0.0) == (0.0, 0.0)
    assert layout.norm_to_px(1.0, 1.0) == (640.0, 400.0)
    assert layout.px_to_norm(640.0, 400.0) == (1.0, 1.0)
    x, y = layout.norm_to_px(-0.4, 0.3)
    assert layout.px_to_norm(x, y) == pytest.approx((-0.4, 0.3))
    assert layout.clamp_norm(-2.0, 3.0) == (-1.0, 1.0)


def test_dense_grid_rejected_for_small_window() -> None:
    with pytest.raises(ValueError):
        Layout.create(640, 480, 60, 60)


def test_board_is_centred_in_the_window() -> None:
    layout = Layout.create(1280, 800, 12, 12)
    assert layout.left == pytest.approx(-layout.board_w / 2)
    assert layout.right == pytest.approx(layout.board_w / 2)
    assert layout.top == pytest.approx(layout.board_h / 2)
    assert layout.bottom == pytest.approx(-layout.board_h / 2)
    assert layout.right <= layout.window_w / 2 - layout.margin + 1
    assert layout.top <= layout.window_h / 2 - layout.margin + 1


def test_target_bag_covers_all_cells_without_immediate_repeats() -> None:
    bag = TargetBag(3, 3, random.Random(7))
    first = [bag.next() for _ in range(9)]
    assert len(set(first)) == 9
    previous = first[-1]
    sequence = first + [bag.next() for _ in range(40)]
    for cell in sequence[1:]:
        assert cell != previous
        previous = cell


def test_target_bag_can_avoid_a_specific_cell() -> None:
    bag = TargetBag(2, 2, random.Random(1))
    avoid = Cell(1, 1)
    for _ in range(20):
        cell = bag.next(avoid=avoid)
        assert cell != avoid
        avoid = cell
