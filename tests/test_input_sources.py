"""Unit tests for the demo source and the velocity integrator."""

from __future__ import annotations

import pytest

from web_grid_paradigm.geometry import Layout
from web_grid_paradigm.velocity_inputs import (
    DemoVelocityOptions,
    DemoVelocitySource,
    VelocityFrame,
    VelocityIntegrator,
    VelocitySample,
)

LAYOUT = Layout.create(800, 600, 4, 4)


def test_demo_autopilot_reaches_target_and_clicks_once() -> None:
    source = DemoVelocitySource(options=DemoVelocityOptions(speed=5.0))
    source.open()
    try:
        source.set_target_norm((0.5, 0.5))
        clicks: list[int] = []
        for step in range(1, 100):
            frame = source.read(now=step * 0.02)
            clicks.extend(frame.clicks)
            if clicks:
                break
        assert source.initial_position_norm() == pytest.approx((0.5, 0.5))
        assert clicks == [1]

        # Re-polling the same target must not repeat the click.
        assert source.read(now=2.1).clicks == ()
        # A new target re-arms the click.
        source.set_target_norm((0.0, 0.0))
        assert source.read(now=2.2).clicks == ()
    finally:
        source.close()


def test_integrator_converts_velocity_to_pixels() -> None:
    integrator = VelocityIntegrator(LAYOUT)
    integrator.update(VelocityFrame(), 1.0)  # start the clock
    integrator.update(
        VelocityFrame((VelocitySample(1.1, 1.0, -0.5),)),
        1.1,
    )
    assert integrator.position_norm == pytest.approx((0.1, -0.05))
    x, y = integrator.position_px
    assert (x, y) == pytest.approx((40.0, -15.0))


def test_integrator_clamps_and_accepts_a_pixel_position() -> None:
    integrator = VelocityIntegrator(LAYOUT)
    integrator.update(VelocityFrame(), 0.0)
    integrator.update(VelocityFrame((VelocitySample(0.25, 100.0, -100.0),)), 0.25)
    assert integrator.position_norm == (1.0, -1.0)
    integrator.set_position_px(200.0, 150.0)
    assert integrator.position_norm == pytest.approx((0.5, 0.5))
