from __future__ import annotations

import pytest

from web_grid_paradigm.geometry import Layout
from web_grid_paradigm.inputs import (
    ButtonEvent,
    DeviceContext,
    InitialPositionProvider,
    InputRead,
    InputSample,
    InputSource,
    InputSourceUnavailable,
    LslInputSource,
    LslOptions,
    MouseOptions,
    MouseSource,
    SerialJoystickOptions,
    SerialJoystickSource,
    available_sources,
    build_input_source,
    get_source_class,
    register_source,
)


class FakeMouse:
    """Stand-in for ``psychopy.event.Mouse`` (no window needed)."""

    def __init__(
        self,
        pos: tuple[float, float] = (0.0, 0.0),
        pressed: tuple[bool, bool, bool] = (False, False, False),
    ) -> None:
        self.pos = pos
        self.pressed = pressed

    def getPos(self) -> tuple[float, float]:
        return self.pos

    def getPressed(self) -> list[bool]:
        return list(self.pressed)


def make_context() -> DeviceContext:
    return DeviceContext(layout=Layout.create(800, 600, 4, 4))


# ----------------------------------------------------------------------
# registry / factory
# ----------------------------------------------------------------------
def test_three_strategies_are_registered() -> None:
    assert set(available_sources()) >= {"mouse", "joystick", "lsl"}
    assert available_sources() == tuple(sorted(available_sources()))


def test_factory_builds_the_selected_strategy_only() -> None:
    mouse = build_input_source(
        "mouse", options=MouseOptions(), context=make_context()
    )
    assert isinstance(mouse, MouseSource)
    assert mouse.name == "mouse"
    assert isinstance(mouse, InputSource)
    assert isinstance(mouse, InitialPositionProvider)
    assert mouse.status().connected is False  # factory never opens the device

    joystick = build_input_source(
        "joystick", options=SerialJoystickOptions(port="/dev/null")
    )
    assert isinstance(joystick, SerialJoystickSource)
    assert joystick.options.port == "/dev/null"

    lsl = build_input_source("lsl", options=LslOptions(stream_name="WT"))
    assert isinstance(lsl, LslInputSource)
    assert lsl.options.stream_name == "WT"


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown input source"):
        build_input_source("gamepad")


def test_duplicate_registration_is_rejected() -> None:
    with pytest.raises(ValueError, match="already registered"):
        register_source("mouse")(type("Duplicate", (), {}))


def test_source_classes_are_looked_up_by_name() -> None:
    assert get_source_class("  MOUSE  ") is MouseSource


# ----------------------------------------------------------------------
# mouse strategy (velocity contract)
# ----------------------------------------------------------------------
def test_mouse_first_frame_only_establishes_the_baseline() -> None:
    mouse = MouseSource(context=make_context(), device=FakeMouse())
    mouse.open()
    read = mouse.read(now=10.0)
    assert read.samples == ()
    assert read.buttons == ()


def test_mouse_position_delta_becomes_velocity() -> None:
    context = make_context()
    device = FakeMouse(pos=(0.0, 0.0))
    mouse = MouseSource(options=MouseOptions(visible=True), context=context, device=device)
    mouse.open()
    mouse.read(now=1.0)

    device.pos = (100.0, 60.0)  # 800x600 window: 0.25 / 0.20 norm units
    read = mouse.read(now=1.1)
    assert len(read.samples) == 1
    sample = read.samples[0]
    assert sample.timestamp == pytest.approx(1.1)
    assert sample.vx == pytest.approx(0.25 / 0.1)
    assert sample.vy == pytest.approx(0.20 / 0.1)


def test_mouse_button_edges_are_reported_once() -> None:
    device = FakeMouse()
    mouse = MouseSource(context=make_context(), device=device)
    mouse.open()

    assert mouse.read(now=0.0).buttons == ()  # open() resets the edge baseline

    device.pressed = (True, False, False)  # left
    assert [b.button for b in mouse.read(now=0.1).buttons] == [1]
    assert mouse.read(now=0.2).buttons == ()  # still held: no second edge

    device.pressed = (False, True, False)  # middle -> logical button 3
    assert [b.button for b in mouse.read(now=0.3).buttons] == [3]

    device.pressed = (False, False, True)  # right -> logical button 2
    assert [b.button for b in mouse.read(now=0.4).buttons] == [2]


def test_mouse_reset_clears_position_and_button_baseline() -> None:
    device = FakeMouse()
    mouse = MouseSource(context=make_context(), device=device)
    mouse.open()
    mouse.read(now=1.0)

    device.pos = (50.0, 0.0)
    device.pressed = (True, False, False)
    mouse.read(now=1.1)

    mouse.reset()
    assert mouse.read(now=1.2).samples == ()  # baseline re-established
    assert mouse.read(now=1.2).buttons == ()  # held button is not a new edge


def test_mouse_initial_position_capability() -> None:
    device = FakeMouse(pos=(200.0, -150.0))
    mouse = MouseSource(context=make_context(), device=device)
    mouse.open()
    assert mouse.initial_position_norm() == pytest.approx((0.5, -0.5))


def test_mouse_status_snapshot() -> None:
    device = FakeMouse()
    mouse = MouseSource(context=make_context(), device=device)
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
# joystick / lsl skeletons
# ----------------------------------------------------------------------
def test_serial_joystick_defaults_match_the_hzl_type1_device() -> None:
    options = SerialJoystickOptions()
    assert (options.baud, options.frame_len) == (9600, 9)
    assert options.protocol == "hzl_rs232_t1"
    assert options.expected_rate_hz == 28.0


def test_unimplemented_strategies_fail_with_a_clear_error() -> None:
    joystick = build_input_source("joystick")
    with pytest.raises(InputSourceUnavailable, match="not implemented yet"):
        joystick.open()
    assert joystick.read(now=0.0) == InputRead()

    lsl = build_input_source("lsl")
    with pytest.raises(InputSourceUnavailable, match="not implemented yet"):
        lsl.open()
    assert lsl.read(now=0.0) == InputRead()


def test_data_model_defaults() -> None:
    read = InputRead()
    assert read.samples == () and read.buttons == ()
    sample = InputSample(timestamp=1.0, vx=0.5, vy=-0.25)
    event = ButtonEvent(button=1, timestamp=1.0)
    assert (sample.timestamp, sample.vx, sample.vy) == (1.0, 0.5, -0.25)
    assert event.button == 1
