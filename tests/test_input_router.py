"""Tests for the input facade: strategy + integrator + runner-facing API."""

from __future__ import annotations

import pytest

from web_grid_paradigm.core.config import ExperimentConfig
from web_grid_paradigm.core.geometry import Cell, Layout
from web_grid_paradigm.core.session import Target
from web_grid_paradigm.input_router import InputReader
from web_grid_paradigm.velocity_inputs import (
    VelocityCapabilities,
    VelocityFrame,
    VelocitySample,
    VelocitySourceStatus,
)

LAYOUT = Layout.create(800, 600, 4, 4)


class FakeSource:
    """Minimal VelocitySource double with a fixed frame sequence."""

    name = "fake"
    capabilities = VelocityCapabilities(category="fake", clicks=True)

    def __init__(self, frames: list[VelocityFrame] | None = None) -> None:
        self.frames = list(frames or [])
        self.opened = False
        self.closed = False
        self.resets = 0
        self.initial: tuple[float, float] | None = None
        self.pressed = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def reset(self) -> None:
        self.resets += 1

    def read(self, now: float) -> VelocityFrame:
        return self.frames.pop(0) if self.frames else VelocityFrame()

    def status(self) -> VelocitySourceStatus:
        return VelocitySourceStatus(
            name=self.name, category=self.capabilities.category, connected=self.opened
        )

    def initial_position_norm(self) -> tuple[float, float] | None:
        return self.initial

    def button_pressed(self) -> bool:
        return self.pressed


def make_reader(source: FakeSource, config: ExperimentConfig | None = None) -> InputReader:
    return InputReader(
        None, LAYOUT, config or ExperimentConfig(), source=source
    )


def test_facade_integrates_samples_and_returns_clicks() -> None:
    source = FakeSource(
        [
            VelocityFrame(),
            VelocityFrame((VelocitySample(1.1, 1.0, 0.0),), clicks=(2,)),
        ]
    )
    reader = make_reader(source)
    assert source.opened is True

    assert reader.read(1.0, None) == (0.0, 0.0, [])
    x, y, clicks = reader.read(1.1, None)
    assert (x, y) == pytest.approx((40.0, 0.0))
    assert clicks == [2]
    reader.close()
    assert source.closed is True


def test_facade_syncs_the_initial_absolute_position() -> None:
    source = FakeSource()
    source.initial = (0.5, 0.5)
    reader = make_reader(source)
    assert reader.cursor_px == (0.0, 0.0)  # nothing read yet
    reader.read(1.0, None)
    assert reader.cursor_px == pytest.approx((200.0, 150.0))


def test_facade_cursor_setter_uses_pixels() -> None:
    source = FakeSource()
    reader = make_reader(source)
    reader.cursor_px = (200.0, -150.0)
    assert reader.cursor_px == pytest.approx((200.0, -150.0))


def test_facade_start_and_reset_hooks() -> None:
    source = FakeSource([VelocityFrame(clicks=(1,))])
    reader = make_reader(source)
    assert reader.start_requested(1.0, ["space"]) is True
    assert reader.start_requested(1.1, []) is True  # queued click
    source.pressed = True
    assert reader.any_pressed() is True
    reader.reset_buttons()
    assert source.resets == 1


def test_demo_strategy_through_the_facade() -> None:
    config = ExperimentConfig(input="demo", demo_speed=5.0)
    reader = InputReader(None, LAYOUT, config)
    try:
        cell = Cell(2, 2)
        centre = LAYOUT.centre_px(cell)
        target = Target(
            index=1,
            cell=cell,
            required_button=1,
            onset=0.0,
            start_px=(0.0, 0.0),
            centre_px=centre,
        )
        clicks: list[int] = []
        for step in range(1, 100):
            x, y, frame_clicks = reader.read(step / 60, target)
            clicks.extend(frame_clicks)
            if clicks:
                break
        assert clicks == [1]
        assert (x, y) == pytest.approx(centre)
    finally:
        reader.close()
