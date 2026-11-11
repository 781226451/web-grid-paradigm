from __future__ import annotations

import pytest

from web_grid_paradigm.core.geometry import Layout
from web_grid_paradigm.velocity_inputs import (
    DeviceContext,
    InitialPositionProvider,
    LslVelocityOptions,
    LslVelocitySource,
    MouseVelocityOptions,
    MouseVelocitySource,
    SerialJoystickVelocityOptions,
    SerialJoystickVelocitySource,
    VelocityFrame,
    VelocitySample,
    VelocitySource,
    VelocitySourceUnavailable,
    available_velocity_sources,
    build_velocity_source,
    get_velocity_source_class,
    register_velocity_source,
)


class FakeMouse:
    """Stand-in for ``psychopy.event.Mouse`` (no window needed)."""

    def __init__(self, pos: tuple[float, float] = (0.0, 0.0)) -> None:
        self.pos = pos
        self.buttons = [False, False, False]

    def getPos(self) -> tuple[float, float]:
        return self.pos

    def setPos(self, pos: tuple[float, float]) -> None:
        self.pos = pos

    def getPressed(self) -> list[bool]:
        return list(self.buttons)


class FakeInlet:
    """Stand-in for ``pylsl.StreamInlet``."""

    def __init__(self, samples: list[list[float]] | None = None) -> None:
        self.samples = list(samples or [])
        self.closed = False

    def pull_sample(self, timeout: float = 0.0) -> tuple[list[float], float]:
        if not self.samples:
            return [], 0.0
        return self.samples.pop(0), 0.0

    def close_stream(self) -> None:
        self.closed = True


def make_context() -> DeviceContext:
    return DeviceContext(layout=Layout.create(800, 600, 4, 4))


# ----------------------------------------------------------------------
# registry / factory
# ----------------------------------------------------------------------
def test_all_strategies_are_registered() -> None:
    assert set(available_velocity_sources()) == {
        "mouse",
        "demo",
        "joystick",
        "lsl",
    }
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
# mouse strategy (absolute contract)
# ----------------------------------------------------------------------
def test_mouse_reports_the_absolute_pointer_position() -> None:
    context = make_context()
    device = FakeMouse(pos=(100.0, 60.0))
    mouse = MouseVelocitySource(context=context, device=device)
    mouse.open()
    frame = mouse.read(now=10.0)
    assert frame.samples == ()
    assert frame.position == pytest.approx((0.25, 0.20))


def test_mouse_position_follows_the_pointer_each_frame() -> None:
    device = FakeMouse(pos=(0.0, 0.0))
    mouse = MouseVelocitySource(context=make_context(), device=device)
    mouse.open()
    assert mouse.read(now=1.0).position == pytest.approx((0.0, 0.0))

    device.pos = (200.0, -150.0)
    assert mouse.read(now=1.1).position == pytest.approx((0.5, -0.5))

    device.pos = (-400.0, 300.0)
    assert mouse.read(now=1.2).position == pytest.approx((-1.0, 1.0))


def test_mouse_never_recenters_near_the_window_edge() -> None:
    device = FakeMouse(pos=(0.0, 0.0))
    mouse = MouseVelocitySource(context=make_context(), device=device)
    mouse.open()
    mouse.read(now=1.0)

    device.pos = (380.0, 0.0)  # inside the old 8% edge margin
    frame = mouse.read(now=1.1)
    assert device.pos == (380.0, 0.0)
    assert frame.position == pytest.approx((0.95, 0.0))
    mouse.read(now=1.2)
    assert device.pos == (380.0, 0.0)


def test_mouse_reset_keeps_the_absolute_position() -> None:
    device = FakeMouse(pos=(100.0, 60.0))
    mouse = MouseVelocitySource(context=make_context(), device=device)
    mouse.open()
    mouse.read(now=1.0)

    mouse.reset()
    frame = mouse.read(now=1.1)
    assert frame.position == pytest.approx((0.25, 0.20))
    assert frame.clicks == ()


def test_mouse_center_pointer_warps_the_pointer_once() -> None:
    device = FakeMouse(pos=(200.0, -150.0))
    mouse = MouseVelocitySource(context=make_context(), device=device)
    mouse.open()
    mouse.read(now=1.0)

    mouse.center_pointer()
    assert device.pos == (0.0, 0.0)
    assert mouse.read(now=1.1).position == pytest.approx((0.0, 0.0))


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


def test_lsl_strategy_reads_velocity_and_button_edges() -> None:
    inlet = FakeInlet(
        [
            [0.0, 0.5, -0.25, 0.0],
            [0.0, 0.5, -0.25, 2.0],
            [0.0, 0.5, -0.25, 2.0],
        ]
    )
    lsl = LslVelocitySource(inlet=inlet)
    lsl.open()
    frame = lsl.read(now=1.0)
    assert len(frame.samples) == 1
    assert (frame.samples[0].vx, frame.samples[0].vy) == (0.5, -0.25)
    assert frame.samples[0].timestamp == 1.0
    assert frame.clicks == (2,)

    # Holding the button does not repeat the click.
    assert lsl.read(now=1.1).clicks == ()
    lsl.close()
    assert inlet.closed is True


def test_lsl_strategy_without_a_stream_fails_at_open(monkeypatch) -> None:
    import pylsl

    predicates: list[str] = []

    def resolve(predicate: str, **_kwargs):
        predicates.append(predicate)
        return []

    monkeypatch.setattr(pylsl, "resolve_bypred", resolve)
    lsl = build_velocity_source(
        "lsl", options=LslVelocityOptions(resolve_timeout=0.05)
    )
    with pytest.raises(VelocitySourceUnavailable, match="no LSL velocity stream"):
        lsl.open()
    assert predicates == ["name='WebGridVelocity' and type='Velocity'"]


def test_lsl_options_require_both_name_and_type() -> None:
    with pytest.raises(ValueError, match="both"):
        LslVelocityOptions(stream_name="")
    with pytest.raises(ValueError, match="both"):
        LslVelocityOptions(stream_type="")


def test_lsl_match_predicate_requires_and_trims_both() -> None:
    from web_grid_paradigm.velocity_inputs.lsl import _match_predicate

    assert _match_predicate(" WebGridVelocity ", " Velocity ") == (
        "name='WebGridVelocity' and type='Velocity'"
    )


def test_data_model_defaults() -> None:
    read = VelocityFrame()
    assert read.samples == () and read.clicks == ()
    assert read.position is None
    sample = VelocitySample(timestamp=1.0, vx=0.5, vy=-0.25)
    assert (sample.timestamp, sample.vx, sample.vy) == (1.0, 0.5, -0.25)
    assert VelocityFrame(clicks=(1,)).clicks == (1,)
    assert VelocityFrame(position=(0.5, 0.5)).position == (0.5, 0.5)


def test_mouse_button_edges_are_reported_once() -> None:
    device = FakeMouse()
    mouse = MouseVelocitySource(context=make_context(), device=device)
    mouse.open()
    mouse.read(now=1.0)

    device.buttons[0] = True  # left -> button 1
    assert mouse.read(now=1.1).clicks == (1,)
    assert mouse.read(now=1.2).clicks == ()  # held is not a new edge
    device.buttons[0] = False
    mouse.read(now=1.3)
    device.buttons[1] = True  # PsychoPy middle -> paradigm button 3
    assert mouse.read(now=1.4).clicks == (3,)
    assert mouse.button_pressed() is True
