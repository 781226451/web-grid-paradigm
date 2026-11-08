from __future__ import annotations

import pytest

from web_grid_paradigm.geometry import Layout
from web_grid_paradigm.velocity_inputs import (
    DeviceContext,
    InitialPositionProvider,
    VelocityFrame,
    VelocitySample,
    VelocitySource,
    VelocitySourceUnavailable,
    LslVelocitySource,
    LslVelocityOptions,
    MouseVelocityOptions,
    MouseVelocitySource,
    SerialJoystickVelocityOptions,
    SerialJoystickVelocitySource,
    available_velocity_sources,
    build_velocity_source,
    get_velocity_source_class,
    register_velocity_source,
)


class FakeMouse:
    """Stand-in for ``psychopy.event.Mouse`` (no window needed)."""

    def __init__(self, pos: tuple[float, float] = (0.0, 0.0)) -> None:
        self.pos = pos

    def getPos(self) -> tuple[float, float]:
        return self.pos


def make_context() -> DeviceContext:
    return DeviceContext(layout=Layout.create(800, 600, 4, 4))


# ----------------------------------------------------------------------
# registry / factory
# ----------------------------------------------------------------------
def test_three_strategies_are_registered() -> None:
    assert set(available_velocity_sources()) >= {"mouse", "joystick", "lsl"}
    assert available_velocity_sources() == tuple(sorted(available_velocity_sources()))


def test_factory_builds_the_selected_strategy_only() -> None:
    mouse = build_velocity_source(
        "mouse", options=MouseVelocityOptions(), context=make_context()
    )
    assert isinstance(mouse, MouseVelocitySource)
    assert mouse.name == "mouse"
    assert isinstance(mouse, VelocitySource)
    assert isinstance(mouse, InitialPositionProvider)
    assert mouse.status().connected is False  # factory never opens the device

    joystick = build_velocity_source(
        "joystick", options=SerialJoystickVelocityOptions(port="/dev/null")
    )
    assert isinstance(joystick, SerialJoystickVelocitySource)
    assert joystick.options.port == "/dev/null"

    lsl = build_velocity_source("lsl", options=LslVelocityOptions(stream_name="WT"))
    assert isinstance(lsl, LslVelocitySource)
    assert lsl.options.stream_name == "WT"


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown input source"):
        build_velocity_source("gamepad")


def test_duplicate_registration_is_rejected() -> None:
    with pytest.raises(ValueError, match="already registered"):
        register_velocity_source("mouse")(type("Duplicate", (), {}))


def test_source_classes_are_looked_up_by_name() -> None:
    assert get_velocity_source_class("  MOUSE  ") is MouseVelocitySource


# ----------------------------------------------------------------------
# mouse strategy (velocity contract)
# ----------------------------------------------------------------------
def test_mouse_first_frame_only_establishes_the_baseline() -> None:
    mouse = MouseVelocitySource(context=make_context(), device=FakeMouse())
    mouse.open()
    assert mouse.read(now=10.0).samples == ()


def test_mouse_position_delta_becomes_velocity() -> None:
    context = make_context()
    device = FakeMouse(pos=(0.0, 0.0))
    mouse = MouseVelocitySource(options=MouseVelocityOptions(visible=True), context=context, device=device)
    mouse.open()
    mouse.read(now=1.0)

    device.pos = (100.0, 60.0)  # 800x600 window: 0.25 / 0.20 norm units
    read = mouse.read(now=1.1)
    assert len(read.samples) == 1
    sample = read.samples[0]
    assert sample.timestamp == pytest.approx(1.1)
    assert sample.vx == pytest.approx(0.25 / 0.1)
    assert sample.vy == pytest.approx(0.20 / 0.1)


def test_mouse_reset_clears_the_position_baseline() -> None:
    device = FakeMouse()
    mouse = MouseVelocitySource(context=make_context(), device=device)
    mouse.open()
    mouse.read(now=1.0)

    device.pos = (50.0, 0.0)
    mouse.read(now=1.1)

    mouse.reset()
    assert mouse.read(now=1.2).samples == ()  # baseline re-established


def test_mouse_initial_position_capability() -> None:
    device = FakeMouse(pos=(200.0, -150.0))
    mouse = MouseVelocitySource(context=make_context(), device=device)
    mouse.open()
    assert mouse.initial_position_norm() == pytest.approx((0.5, -0.5))


def test_mouse_status_snapshot() -> None:
    device = FakeMouse()
    mouse = MouseVelocitySource(context=make_context(), device=device)
    status = mouse.status()
    assert status.connected is False
    assert status.frames == 0

    mouse.open()
    device.pos = (10.0, 0.0)
    mouse.read(now=1.0)
    mouse.read(now=1.1)
    status = mouse.status()
    assert status.name == "mouse"
    assert status.category == "mouse"
    assert status.connected is True
    assert status.frames == 2
    assert status.last_rx == pytest.approx(1.1)


# ----------------------------------------------------------------------
# joystick / lsl
# ----------------------------------------------------------------------
def test_serial_joystick_defaults_match_the_hall_protocol() -> None:
    options = SerialJoystickVelocityOptions()
    assert (options.baud, options.protocol) == (9600, "hall_rs232")
    assert options.address is None  # universal 9-byte frame
    assert options.stream_mode == "periodic"
    assert options.expected_rate_hz == 28.0


def test_lsl_strategy_is_still_a_stub() -> None:
    lsl = build_velocity_source("lsl")
    with pytest.raises(VelocitySourceUnavailable, match="not implemented yet"):
        lsl.open()
    assert lsl.read(now=0.0) == VelocityFrame()


def test_data_model_defaults() -> None:
    read = VelocityFrame()
    assert read.samples == ()
    sample = VelocitySample(timestamp=1.0, vx=0.5, vy=-0.25)
    assert (sample.timestamp, sample.vx, sample.vy) == (1.0, 0.5, -0.25)
